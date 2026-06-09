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
| `base.py` | `Builtin` abstract base class |
| `registry.py` | `BuiltinRegistry` and `@builtin` decorator |
| `__init__.py` | Imports all builtins to trigger registration |

### Builtin Commands by Category

**I/O Operations**
| File | Commands |
|------|----------|
| `io.py` | `echo`, `printf`, `pwd` (plus shared `process_escapes()` helper) |
| `print_builtin.py` | `print` (zsh-compatible) |
| `read_builtin.py` | `read` |

**Navigation & Directory**
| File | Commands |
|------|----------|
| `navigation.py` | `cd` |
| `directory_stack.py` | `pushd`, `popd`, `dirs` |

**Variables & Environment**
| File | Commands |
|------|----------|
| `environment.py` | `export`, `set`, `unset` |
| `shell_options.py` | `shopt` |
| `shell_state.py` | `history`, `version`, `local` |
| `positional.py` | `shift`, `getopts` |

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

**Flow Control**
| File | Commands |
|------|----------|
| `core.py` | `exit`, `:`, `true`, `false`, `exec` |

**Test & Type**
| File | Commands |
|------|----------|
| `test_command.py` | `test`, `[` |
| `type_builtin.py` | `type` |
| `command_builtin.py` | `command` |

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
| `debug_control.py` | Debug-related commands |
| `parser_control.py` | Parser control commands |

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

    def error(self, message: str, shell: 'Shell') -> None:
        """Print error to stderr."""
        print(f"{self.name}: {message}", file=shell.stderr)
```

### 2. Registration with Decorator

```python
from .registry import builtin

@builtin
class MyBuiltin(Builtin):
    name = "mycommand"

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

    name = "mycommand"
    aliases = ["mc"]  # Optional

    @property
    def synopsis(self) -> str:
        return "mycommand [-a] [-b value] [args...]"

    @property
    def description(self) -> str:
        return "Does something useful with the given arguments"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        # args[0] is the command name
        # Parse options
        i = 1
        opt_a = False
        opt_b = None

        while i < len(args) and args[i].startswith('-'):
            if args[i] == '-a':
                opt_a = True
            elif args[i] == '-b':
                if i + 1 >= len(args):
                    self.error("-b requires an argument", shell)
                    return 1
                i += 1
                opt_b = args[i]
            elif args[i] == '--':
                i += 1
                break
            else:
                self.error(f"unknown option: {args[i]}", shell)
                return 1
            i += 1

        # Remaining args
        remaining = args[i:]

        # Do the work
        print(f"Running with a={opt_a}, b={opt_b}, args={remaining}",
              file=shell.stdout)

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

```python
def execute(self, args, shell):
    # Output to stdout
    print("output", file=shell.stdout)

    # Output to stderr
    print("error", file=shell.stderr)

    # Read from stdin
    line = shell.stdin.readline()

    # Use self.error() for consistent error messages
    self.error("something went wrong", shell)
```

### Working with Job Control

```python
def execute(self, args, shell):
    # Get job manager
    job_manager = shell.job_manager

    # List jobs
    for job in job_manager.jobs.values():
        print(f"[{job.job_id}] {job.state} {job.command}")

    # Foreground a job
    job_manager.foreground_job(job)
```

## Testing

```bash
# Run all builtin tests
python -m pytest tests/unit/builtins/ -v

# Test specific builtin
python -m pytest tests/unit/builtins/test_echo.py -v

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

## Integration Points

### With Executor (`psh/executor/`)

The executor uses `BuiltinExecutionStrategy` to run builtins:

```python
# In strategies.py
class BuiltinExecutionStrategy:
    def execute(self, cmd_name, args, shell):
        builtin = registry.get(cmd_name)
        if builtin:
            return builtin.execute(args, shell)
```

### With Shell State (`psh/core/state.py`)

- Variables via `shell.state.get_variable()`, `shell.state.set_variable()`
- Options via `shell.state.options`
- Exit codes via `shell.state.last_exit_code`

### With Job Control (`psh/job_control.py`)

- Job manager via `shell.job_manager`
- Background jobs via `job_manager.jobs`
