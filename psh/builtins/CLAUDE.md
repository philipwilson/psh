# Builtins Subsystem

This document provides guidance for working with the PSH builtins subsystem.

## Architecture Overview

The builtins subsystem provides shell built-in commands via a decorator-based registration system. Each builtin inherits from `Builtin` and is auto-registered using the `@builtin` decorator.

```
@builtin decorator → BuiltinRegistry → Executor Strategy Lookup
                           ↓
                    Builtin.execute(args, shell)
```

## Key Files

### Core Infrastructure

| File | Purpose |
|------|---------|
| `base.py` | `Builtin` abstract base class (I/O helpers, `parse_flags`, statelessness contract) |
| `registry.py` | `BuiltinRegistry` and `@builtin` decorator |
| `__init__.py` | Imports all builtins to trigger registration |

### Builtin Commands by Category

**I/O Operations**
| File | Commands |
|------|----------|
| `io.py` | `echo`, `printf`, `pwd`. The shared `process_escapes()` helper is a thin wrapper over `process_echo_escapes()` in `psh/utils/escapes.py`; printf's FORMAT/argument engine is NOT here either — it was extracted to `psh/utils/printf_formatter.py` (`format_printf()`, pure, no shell dependency; also used by `print -f`) |
| `print_builtin.py` | `print` (zsh-compatible) |
| `read_builtin.py` | `read` |
| `mapfile_builtin.py` | `mapfile` (alias `readarray`) |

**Navigation & Directory**
| File | Commands |
|------|----------|
| `navigation.py` | `cd` |
| `directory_stack.py` | `pushd`, `popd`, `dirs` |

**Variables & Environment**
| File | Commands |
|------|----------|
| `env_command.py` | `env` (standard external command: builds the child env and execs the argv through the normal external launcher — does NOT resolve shell builtins/functions, so it isolates process state; passes `use_hash=False` so it re-searches the overridden PATH rather than the shell command hash — D3) |
| `environment.py` | `export`, `set`, `unset` |
| `shell_options.py` | `shopt` |
| `shell_state.py` | `history`, `version`, `local` |
| `positional.py` | `shift`, `getopts` |
| (none) | `declare`/`local`/`export`/`readonly`/`typeset` array init `name=(...)` routes through the SAME structured expansion as the bare `a=(...)` path (`ArrayOperationExecutor.build_indexed_array`/`build_associative_array`); the parser attaches an `ArrayInitialization` to `Word.array_init`, delivered to the builtin as an explicit `BuiltinContext` parameter (the executor passes it through `execute_builtin_guarded` → `Builtin.execute_in_context`; declaration builtins read `context.array_init(arg)`). This replaced the former `shell._pending_array_inits` side channel — no mutable handoff state on the shell. The old string-reparse module (the former array_init.py) was removed. |

**Job Control**
| File | Commands |
|------|----------|
| `job_control.py` | `jobs`, `fg`, `bg`, `wait` |
| `disown.py` | `disown` |
| `kill_command.py` | `kill` |

**Functions & Scripts**
| File | Commands |
|------|----------|
| `function_support.py` | `declare`, `typeset`, `readonly`, `return` |
| `source_command.py` | `source`, `.` |
| `eval_command.py` | `eval` |
| `let_builtin.py` | `let` |

**Flow Control**
| File | Commands |
|------|----------|
| `core.py` | `exit`, `:`, `true`, `false`, `exec` |

**Test & Type**
| File | Commands |
|------|----------|
| `test_command.py` | `test`, `[` |
| `type_builtin.py` | `type` (thin adapter: maps options to a `ResolveQuery`, renders `CommandResolver.resolve`) |
| `hash_builtin.py` | `hash` (remembered command locations; the table itself is `shell.state.command_hash`; PATH search via `CommandResolver.search_path`) |
| `command_builtin.py` | `command` (`-v`/`-V` render `CommandResolver.resolve`; `-p` keeps builtin selection and only overrides the external search PATH) |

**Aliases**
| File | Commands |
|------|----------|
| `aliases.py` | `alias`, `unalias` |

**Signal Handling**
| File | Commands |
|------|----------|
| `signal_handling.py` | `trap` |

**System**
| File | Commands |
|------|----------|
| `system_builtins.py` | `umask`, `times` |

**Help & Debug**
| File | Commands |
|------|----------|
| `help_command.py` | `help` |
| `debug_control.py` | `debug-ast`, `debug`, `signals` |
| `parser_control.py` | `parser-config`, `parser-mode` |
| `parser_experiment.py` | `parser-select` (switch RD/combinator parser) |
| `parse_tree.py` | `parse-tree`, `show-ast`, `ast-dot` |

## Core Patterns

### 1. Builtin Base Class

All builtins inherit from `Builtin`:

```python
from .base import Builtin

class Builtin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Primary command name."""
        pass

    @property
    def aliases(self) -> List[str]:
        """Optional aliases (default: empty)."""
        return []

    @abstractmethod
    def execute(self, args: List[str], shell: 'Shell') -> int:
        """
        Execute the builtin.

        Args:
            args: Command arguments (args[0] is command name)
            shell: Shell instance for state and I/O

        Returns:
            Exit code (0 = success)
        """
        pass
```

**Statelessness contract (v0.313)**: builtin instances are process-wide
singletons — each class is instantiated exactly once at import time by the
`@builtin` decorator and shared by every Shell in the process (including
subshells and `Shell.for_subshell()` children). A builtin must keep NO
per-invocation or per-shell state on `self`; everything mutable lives on
the `shell` argument (`shell.state`, `shell.env`, ...). Concretely,
`vars(instance)` must stay empty after any command battery. The contract
is spelled out in the `Builtin` docstring in `base.py` and enforced by
`tests/unit/builtins/test_builtin_statelessness.py` (which iterates
`registry.instances()`).

The base class also provides forked-child-aware I/O helpers — use these,
never raw `print(..., file=sys.stderr)` (the error-channel convention,
established in v0.284, is: stdout via `self.write()`/`self.write_line()`,
errors via `self.error()`):

```python
def write(self, text: str, shell: 'Shell') -> None:
    """Write to the builtin's stdout (fd-level in forked children)."""
    if shell.state.in_forked_child:
        os.write(1, text.encode('utf-8', errors='replace'))
    else:
        stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
        stdout.write(text)
        stdout.flush()

def write_line(self, text: str, shell: 'Shell') -> None:
    """Write one line to the builtin's stdout (see write())."""
    self.write(text + '\n', shell)

def error(self, message: str, shell: 'Shell') -> None:
    """Print an error message to stderr."""
    if shell.state.in_forked_child:
        os.write(2, f"{self.name}: {message}\n".encode('utf-8', errors='replace'))
        return
    stderr = shell.stderr if hasattr(shell, 'stderr') else sys.stderr
    print(f"{self.name}: {message}", file=stderr)
    stderr.flush()
```

A fourth helper, `write_error_line()`, writes an UNPREFIXED line to
stderr — for usage/diagnostic lines that accompany an `error()` call.

For option parsing, use the shared getopt-style helper instead of
hand-rolling loops:

```python
def parse_flags(self, args: List[str], shell: 'Shell',
                flags: str = '', value_flags: str = ''
                ) -> Tuple[Optional[dict], List[str]]:
    """Parse leading single-dash options from args.

    flags: chars allowed as boolean flags (clusterable: -ab).
    value_flags: chars that consume an argument (-d X or -dX).
    Returns (opts, operands); on an invalid option an error is printed
    and (None, args) is returned — callers should `return 2`.
    """
```

### 2. Registration with Decorator

```python
from .registry import builtin

@builtin
class MyBuiltin(Builtin):
    @property
    def name(self) -> str:
        return "mycommand"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        # Implementation
        return 0
```

### 3. Registry Lookup

```python
from .registry import registry

# Check if builtin exists
if registry.has('echo'):
    builtin = registry.get('echo')
    exit_code = builtin.execute(args, shell)

# Get all builtin names
names = registry.names()  # ['cd', 'echo', 'exit', ...]
```

**Relationship to `SHELL_BUILTINS`**: the analysis visitors (linter,
metrics, enhanced validator) classify command names against
`SHELL_BUILTINS` in `psh/visitor/constants.py` — a *bash-scoped* set that
is a superset of the registry: it contains every builtin psh's registry
provides PLUS bash-only names (e.g. `suspend`, `fc`) so analyzing
bash scripts works cleanly. Both directions are pinned by
`tests/unit/visitor/test_shell_builtins_pinned.py`: registering a new
builtin without adding it there fails the suite.

### 4. Command resolution goes through `CommandResolver`

`psh/executor/command_resolver.py` is the ONE answer to "what does this
command name mean?" — consumed by the executor's external path, `command`,
`type`, and `hash`. Do NOT reimplement the PATH walk or hash consultation
in a builtin.

- `resolver.search_path(name, path)` — the single `$PATH` scan (empty
  component = cwd, slash name kept as given, `X_OK` gated). Every PATH scan
  uses it (`hash`, `exec -c`, and internally `type`/`command`).
- `resolver.resolve(name, query)` — the ordered typed candidates
  (`Alias`/`Keyword`/`Function`/`Builtin`/`HashedExternal`/`PathExternal`).
  A `ResolveQuery` selects participation (function bypass), which PATH
  (`command -p`, `env`), hash use (`type -a` ignores it), and first-vs-all
  (`type -a`). `type` and `command -v`/`-V` build a query and RENDER the
  result — no local lookup order.
- `resolver.resolve_for_exec(name)` — the executor's external resolution
  (consult+populate the hash, `checkhash`), returning the path to exec or
  None to let `execvpe` walk PATH.

Only the executor's exec path populates/checkhash-verifies the hash;
introspection (`type`/`command -v`) consults it (counting a bash hit) but
never remembers or verifies it. Because every surface renders the same
resolver, a fact seeded one way (e.g. `hash -p`) is visible everywhere.

## Adding a New Builtin

### Step 1: Create the Builtin File

```python
# psh/builtins/mycommand.py
"""My custom command builtin."""

from typing import List, TYPE_CHECKING
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class MyCommandBuiltin(Builtin):
    """Short description of what mycommand does."""

    @property
    def name(self) -> str:
        return "mycommand"

    @property
    def aliases(self) -> List[str]:
        return ["mc"]  # Optional

    @property
    def synopsis(self) -> str:
        return "mycommand [-a] [-b value] [args...]"

    @property
    def description(self) -> str:
        return "Does something useful with the given arguments"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        # args[0] is the command name. Parse options with the shared
        # helper: '-a' is a boolean flag, '-b' takes a value.
        opts, operands = self.parse_flags(args, shell, flags='a', value_flags='b')
        if opts is None:
            return 2  # invalid option/usage error (bash convention)

        # Do the work — stdout via write_line(), never raw print()
        self.write_line(
            f"Running with a={opts['a']}, b={opts['b']}, args={operands}",
            shell)

        return 0
```

### Step 2: Import in `__init__.py`

```python
# In psh/builtins/__init__.py
from . import mycommand  # Add this line
```

### Step 3: Add Tests

```python
# tests/unit/builtins/test_mycommand.py
import pytest

def test_mycommand_basic(captured_shell):
    result = captured_shell.run_command("mycommand arg1 arg2")
    assert result == 0
    assert "arg1" in captured_shell.get_stdout()

def test_mycommand_option_a(captured_shell):
    result = captured_shell.run_command("mycommand -a")
    assert result == 0
    assert "a=True" in captured_shell.get_stdout()
```

## Exit Code Conventions

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Usage/syntax error |
| 126 | Command not executable |
| 127 | Command not found |

## Key Implementation Details

### Accessing Shell State

```python
def execute(self, args, shell):
    # Get/set variables
    value = shell.state.get_variable('MY_VAR')
    shell.state.set_variable('MY_VAR', 'new_value')

    # Check options
    if shell.state.options.get('errexit'):
        ...

    # Access last exit code
    last_code = shell.state.last_exit_code
```

### I/O Operations

The error-channel convention (v0.284): all builtin output goes through the
base-class helpers, which are forked-child-aware. Never write directly to
`sys.stdout`/`sys.stderr` — that breaks fd-level redirections in pipeline
members and background jobs.

```python
def execute(self, args, shell):
    # Output to stdout
    self.write_line("output", shell)

    # Errors to stderr (prefixed with the builtin's name)
    self.error("something went wrong", shell)

    # Read from stdin
    line = shell.stdin.readline()
```

### Working with Job Control

```python
def execute(self, args, shell):
    # Get job manager
    job_manager = shell.job_manager

    # Look up a job by spec (%1, %+, %-, %prefix, or PID)
    job = job_manager.parse_job_spec(args[1] if len(args) > 1 else '')

    # List jobs
    for job in job_manager.jobs.values():
        self.write_line(f"[{job.job_id}] {job.state} {job.command}", shell)

    # Mark a job as the foreground job (restores its terminal modes);
    # see FgBuiltin in job_control.py for the full fg sequence
    job_manager.set_foreground_job(job)
```

## Testing

```bash
# Run all builtin tests
python -m pytest tests/unit/builtins/ -v

# Test specific builtin
python -m pytest tests/unit/builtins/test_echo_comprehensive.py -v

# Test with output capture
python -m pytest tests/unit/builtins/ -v --capture=no
```

## Common Pitfalls

1. **args[0] is Command Name**: First argument is the command itself, not the first user argument.

2. **Flush Output**: For interactive builtins, flush stdout/stderr.

3. **Exit Codes**: Always return an exit code; don't forget edge cases.

4. **Error Messages**: Use `self.error()` for consistent formatting.

5. **Option Parsing**: Handle `--` to stop option processing.

6. **Shell State**: Access state through `shell.state`, not global variables.

7. **No State on `self`**: builtin instances are shared singletons — storing
   anything on `self` leaks across shells and subshells and fails
   `tests/unit/builtins/test_builtin_statelessness.py`.

## Integration Points

### With Executor (`psh/executor/`)

The executor uses `BuiltinExecutionStrategy` to run builtins:

```python
# In strategies.py (trimmed)
class BuiltinExecutionStrategy(ExecutionStrategy):
    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        return (shell.builtin_registry.has(cmd_name) and
                cmd_name not in POSIX_SPECIAL_BUILTINS)

    def execute(self, cmd_name, args, shell, context, redirects=None,
                background=False, visitor=None) -> int:
        builtin = shell.builtin_registry.get(cmd_name)
        if not builtin:
            return 127
        return execute_builtin_guarded(builtin, cmd_name, args, shell)
```

### With Shell State (`psh/core/state.py`)

- Variables via `shell.state.get_variable()`, `shell.state.set_variable()`
- Options via `shell.state.options`
- Exit codes via `shell.state.last_exit_code`

### With Job Control (`psh/executor/job_control.py`)

- Job manager via `shell.job_manager`
- Background jobs via `job_manager.jobs`
