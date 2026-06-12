# PSH Builtins: Programmer's Guide

This guide covers the builtins package in detail: its external API, internal
architecture, and the responsibilities of every source file.  It is aimed at
developers who need to add new builtins, modify existing ones, or understand
how shell commands are registered and dispatched.

## 1. What the Builtins Package Does

The builtins package provides the shell's built-in commands: commands that
execute within the shell process itself rather than spawning an external
program.  Each builtin is a Python class that inherits from `Builtin` and is
auto-registered with a global `BuiltinRegistry` via the `@builtin` decorator.

The builtins package does **not** decide when to invoke a builtin vs. an
external command.  That decision is made by the executor's strategy pattern
(see section 6).  The builtins package only provides the registry and the
command implementations.

## 2. External API

The public interface is defined in `psh/builtins/__init__.py`.  The declared
`__all__` contains five items: `registry`, `builtin`, `Builtin`,
`FunctionReturn`, and `PARSERS`.  See `docs/guides/builtins_public_api.md`
for full signature documentation and API tiers.

### 2.1 `registry`

```python
from psh.builtins import registry

if registry.has('echo'):
    echo = registry.get('echo')
    exit_code = echo.execute(['echo', 'hello'], shell)
```

The global `BuiltinRegistry` instance.  Supports `get()`, `has()`, `all()`,
`names()`, `instances()`, `in` operator, and dict-style access.

### 2.2 `@builtin` decorator

```python
from psh.builtins import Builtin, builtin

@builtin
class EchoBuiltin(Builtin):
    name = "echo"
    def execute(self, args, shell):
        print(' '.join(args[1:]), file=shell.stdout)
        return 0
```

Applying `@builtin` to a `Builtin` subclass instantiates it and registers it
(and any aliases) with the global `registry`.  Registration happens at import
time when `psh/builtins/__init__.py` imports all builtin modules.

### 2.3 `Builtin` base class

Abstract base class with two required overrides:

- `name` (abstract property) &mdash; the primary command name.
- `execute(args, shell)` (abstract method) &mdash; execute the command.
  `args[0]` is always the command name.  Returns an integer exit code.

Optional overrides: `aliases` (list of alternate names), `synopsis`,
`description`, `help`.

Utility method: `error(message, shell)` &mdash; prints
`"{name}: {message}"` to `shell.stderr`.

### 2.4 `FunctionReturn`

Exception class used by the `return` builtin to implement function returns.
The executor catches `FunctionReturn` in its function-call handler and
extracts `.exit_code`.

### 2.5 `PARSERS`

Dictionary mapping parser implementation names (`'recursive_descent'`,
`'combinator'`) to their CLI aliases.  Used by the `parser-select` builtin
and the `--parser` CLI argument.

### 2.6 Convenience imports

All builtin classes are importable from their defining submodules (e.g.
`from psh.builtins.test_command import TestBuiltin`), but these are not part
of the public API.  See `docs/guides/builtins_public_api.md` for the full
tier breakdown.


## 3. Architecture

### 3.1 Registration flow

```
Module import (triggered by __init__.py)
     |
     v
@builtin decorator
     |
     v
BuiltinRegistry.register(cls)
     |
     ├─ Instantiate class
     ├─ Register primary name: _builtins[name] = instance
     └─ Register aliases:      _builtins[alias] = instance
```

All registration happens at import time.  By the time the `Shell` constructor
completes, the global `registry` contains all builtins.

### 3.2 Command dispatch

The executor resolves commands through a strategy chain (defined in
`psh/executor/strategies.py`):

```
Expanded command name
     |
     v
1. SpecialBuiltinExecutionStrategy   — POSIX special builtins (: break eval ...)
     |  (if not matched)
     v
2. FunctionExecutionStrategy          — User-defined functions
     |  (if not matched)
     v
3. BuiltinExecutionStrategy           — Regular builtins (echo cd test ...)
     |  (if not matched)
     v
4. AliasExecutionStrategy             — Shell aliases
     |  (if not matched)
     v
5. ExternalExecutionStrategy          — External programs (PATH lookup + fork/exec)
```

Both `SpecialBuiltinExecutionStrategy` and `BuiltinExecutionStrategy` use
`registry.get(cmd_name)` to find the builtin instance, then call
`builtin.execute([cmd_name] + args, shell)`.

### 3.3 POSIX special builtins

POSIX defines a set of special builtins that take precedence over functions.
These are listed in `psh/executor/strategies.py`:

```python
POSIX_SPECIAL_BUILTINS = {
    ':', 'break', 'continue', 'eval', 'exec', 'exit', 'export',
    'readonly', 'return', 'set', 'shift', 'trap', 'unset'
}
```

Special builtins differ from regular builtins in two ways:

1. They are found before functions in the lookup order.
2. Variable assignments preceding a special builtin persist after the
   command completes (POSIX requirement).

### 3.4 I/O and state access

Builtins access the shell through the `shell` parameter:

```python
def execute(self, args, shell):
    # Output
    print("hello", file=shell.stdout)
    print("error", file=shell.stderr)

    # Input
    line = shell.stdin.readline()

    # Variables
    value = shell.state.get_variable('HOME')
    shell.state.set_variable('MY_VAR', 'value')

    # Options
    if shell.state.options.get('errexit'):
        ...

    # Exit code
    last = shell.state.last_exit_code

    # Functions
    func = shell.function_manager.get_function('my_func')

    # Jobs
    jobs = shell.job_manager.jobs

    return 0
```

### 3.5 Control flow exceptions

Three exception types are used for shell control flow.  The executor catches
these at appropriate levels:

| Exception | Source | Caught by |
|-----------|--------|-----------|
| `FunctionReturn` | `return` builtin (`function_support.py`) | `FunctionOperationExecutor` |
| `LoopBreak` | `break` builtin (handled by parser/executor) | `ControlFlowExecutor` |
| `LoopContinue` | `continue` builtin (handled by parser/executor) | `ControlFlowExecutor` |

`FunctionReturn` is defined in the builtins package.  `LoopBreak` and
`LoopContinue` are defined in `psh/core/exceptions.py`.


## 4. Source File Reference

All files are under `psh/builtins/`.  Line counts are approximate.

### 4.1 Core infrastructure

#### `__init__.py` (~65 lines)

Package entry point.  Imports all 27 builtin modules to trigger
registration.  Re-exports the public API (`registry`, `builtin`, `Builtin`,
`FunctionReturn`, `PARSERS`) and declares `__all__`.  Contains a module-level
docstring listing all modules and their commands.

#### `base.py` (~60 lines)

The `Builtin` abstract base class.  Defines the interface that all builtins
must implement: `name`, `execute()`, plus optional `aliases`, `synopsis`,
`description`, `help`, and the `error()` utility method.

#### `registry.py` (~65 lines)

The `BuiltinRegistry` class and the `@builtin` decorator function.  The
registry stores builtin instances keyed by both primary names and aliases.
A global `registry` instance is created at module level.

### 4.2 I/O operations

#### `io.py` (~770 lines)

Three builtins:

- **`EchoBuiltin`** (`echo`) &mdash; outputs arguments separated by spaces,
  followed by a newline.  Supports `-n` (no trailing newline), `-e`
  (interpret escape sequences), and `-E` (disable escape sequences).
  Pipeline-aware: writes directly to fd 1 in forked children.

- **`PrintfBuiltin`** (`printf`) &mdash; formatted output following the
  POSIX `printf` specification.  Supports format specifiers (`%s`, `%d`,
  `%f`, `%x`, `%o`, `%b`, `%q`), escape sequences, field width and
  precision, and argument recycling when there are more arguments than
  format specifiers.

- **`PwdBuiltin`** (`pwd`) &mdash; prints the current working directory.
  Supports `-L` (logical, follows symlinks, default) and `-P` (physical,
  resolves symlinks).

#### `read_builtin.py` (~665 lines)

**`ReadBuiltin`** (`read`) &mdash; reads a line from stdin and assigns words
to variables.  Supports `-r` (raw mode, no backslash escaping), `-p prompt`
(display prompt), `-t timeout`, `-n nchars` (read N characters), `-d delim`
(custom delimiter), `-s` (silent/no echo), `-a array` (read into array),
and `-u fd` (read from file descriptor).

### 4.3 Navigation and directory

#### `navigation.py` (~160 lines)

**`CdBuiltin`** (`cd`) &mdash; changes the working directory.  Supports `-L`
(logical) and `-P` (physical) modes, `cd -` (return to `$OLDPWD`), and
`$CDPATH` search.  Updates `$PWD` and `$OLDPWD`.

#### `directory_stack.py` (~510 lines)

Four items:

- **`DirectoryStack`** &mdash; internal helper class managing the directory
  stack as a list.  Provides `push()`, `pop()`, `rotate()`, and `list()`
  operations.

- **`PushdBuiltin`** (`pushd`) &mdash; pushes a directory onto the stack
  and changes to it.  Supports `+N`/`-N` rotation.

- **`PopdBuiltin`** (`popd`) &mdash; pops and changes to the top directory.
  Supports `+N`/`-N` removal.

- **`DirsBuiltin`** (`dirs`) &mdash; displays the directory stack.  Supports
  `-c` (clear), `-l` (long format), `-p` (one per line), `-v` (verbose),
  and `+N`/`-N` indexing.

### 4.4 Variables and environment

#### `environment.py` (~580 lines)

Four builtins:

- **`EnvBuiltin`** (`env`) &mdash; displays the current environment.

- **`ExportBuiltin`** (`export`) &mdash; marks variables for export to child
  processes.  Supports `-n` (remove export attribute), `-p` (print all
  exports), `-f` (export functions).

- **`SetBuiltin`** (`set`) &mdash; sets shell options and positional
  parameters.  Supports all POSIX short options (`-e`, `-u`, `-x`, `-f`,
  `-n`, `-v`, `-b`, `-C`, `-h`, `-o`, `-p`) and long options via
  `-o optionname`.

- **`UnsetBuiltin`** (`unset`) &mdash; removes variables or functions.
  Supports `-v` (variable, default) and `-f` (function).

#### `function_support.py` (~825 lines)

Four builtins plus one exception class:

- **`FunctionReturn`** &mdash; exception class for implementing `return`.
  Part of the public API.

- **`DeclareBuiltin`** (`declare`) &mdash; declares variables with
  attributes.  The most complex builtin, supporting all bash `declare`
  flags: `-a` (indexed array), `-A` (associative array), `-f`/`-F`
  (functions), `-g` (global), `-i` (integer), `-l`/`-u` (case transform),
  `-p` (print), `-r` (readonly), `-t` (trace), `-x` (export), and `+flag`
  for attribute removal.

- **`TypesetBuiltin`** (`typeset`) &mdash; subclass of `DeclareBuiltin`
  providing ksh compatibility.  Identical behaviour.

- **`ReadonlyBuiltin`** (`readonly`) &mdash; marks variables or functions as
  readonly.  Supports `-f` (functions) and `-p` (print).  Delegates to
  `DeclareBuiltin` internally.

- **`ReturnBuiltin`** (`return`) &mdash; returns from a function with an
  optional exit code.  Raises `FunctionReturn`.

#### `shell_options.py` (~145 lines)

**`ShoptBuiltin`** (`shopt`) &mdash; manages shell options beyond those
handled by `set`.  Supports `-s` (set), `-u` (unset), `-o` (set-style
options), `-p` (print), and `-q` (quiet).

#### `shell_state.py` (~330 lines)

Three builtins:

- **`HistoryBuiltin`** (`history`) &mdash; displays and manages command
  history.  Supports `-c` (clear), `-d N` (delete entry), `-a` (append to
  history file), `-r` (read from history file).

- **`VersionBuiltin`** (`version`) &mdash; displays the psh version.

- **`LocalBuiltin`** (`local`) &mdash; declares local variables inside
  functions.  PSH-specific implementation with scope management.

#### `positional.py` (~245 lines)

Two builtins:

- **`ShiftBuiltin`** (`shift`) &mdash; shifts positional parameters left
  by N positions (default 1).

- **`GetoptsBuiltin`** (`getopts`) &mdash; parses positional parameters
  according to an option string.  POSIX-compliant implementation with
  `$OPTIND` and `$OPTARG` management.

### 4.5 Job control

#### `job_control.py` (~335 lines)

Four builtins:

- **`JobsBuiltin`** (`jobs`) &mdash; lists background jobs.  Supports `-l`
  (long format with PIDs) and `-p` (PIDs only).

- **`FgBuiltin`** (`fg`) &mdash; brings a background job to the foreground.

- **`BgBuiltin`** (`bg`) &mdash; resumes a stopped job in the background.

- **`WaitBuiltin`** (`wait`) &mdash; waits for background jobs to complete.
  Supports waiting for specific PIDs or job specs.

#### `kill_command.py` (~295 lines)

**`KillBuiltin`** (`kill`) &mdash; sends signals to processes.  Supports
`-s SIGNAL`, `-SIGNAL`, `-l` (list signals), and `-L` (list in table
format).  Also defines `SIGNAL_NAMES`, a dict mapping POSIX signal names
to `signal` module constants.

#### `disown.py` (~165 lines)

**`DisownBuiltin`** (`disown`) &mdash; removes jobs from the job table.
Supports `-a` (all jobs), `-h` (mark so SIGHUP is not sent), `-r` (running
jobs only).

### 4.6 Flow control

#### `core.py` (~225 lines)

Five builtins:

- **`ExitBuiltin`** (`exit`) &mdash; exits the shell with an optional status
  code.  Raises `SystemExit`.

- **`NoopBuiltin`** (`:`) &mdash; no-op command, always succeeds.

- **`TrueBuiltin`** (`true`) &mdash; always returns 0.

- **`FalseBuiltin`** (`false`) &mdash; always returns 1.

- **`ExecBuiltin`** (`exec`) &mdash; replaces the shell process with a
  command via `os.execvp()`, or applies redirections to the current shell
  when called without arguments.

#### `eval_command.py` (~40 lines)

**`EvalBuiltin`** (`eval`) &mdash; concatenates arguments and executes them
as a shell command string.

#### `source_command.py` (~125 lines)

**`SourceBuiltin`** (`source`, alias `.`) &mdash; reads and executes
commands from a file in the current shell context.  Searches `$PATH` if the
filename contains no `/`.

#### `signal_handling.py` (~115 lines)

**`TrapBuiltin`** (`trap`) &mdash; sets signal handlers.  Supports listing
current traps, setting handlers for named signals, resetting with `-`, and
`-l` to list signal names.

### 4.7 Test and type

#### `test_command.py` (~410 lines)

**`TestBuiltin`** (`test`, alias `[`) &mdash; evaluates conditional
expressions.  Supports file tests (`-e`, `-f`, `-d`, `-r`, `-w`, `-x`,
`-s`, `-L`, `-b`, `-c`, `-p`, `-S`, `-g`, `-u`, `-k`, `-O`, `-G`, `-N`,
`-nt`, `-ot`, `-ef`), string tests (`-z`, `-n`, `=`, `!=`, `<`, `>`),
integer comparisons (`-eq`, `-ne`, `-lt`, `-le`, `-gt`, `-ge`), and
logical operators (`!`, `-a`, `-o`, `(`, `)`).

#### `type_builtin.py` (~180 lines)

**`TypeBuiltin`** (`type`) &mdash; indicates how a command would be
interpreted.  Supports `-t` (type only), `-a` (all locations), `-p` (path
only).  Reports `alias`, `keyword`, `function`, `builtin`, or `file`.

#### `command_builtin.py` (~150 lines)

**`CommandBuiltin`** (`command`) &mdash; executes a command bypassing
functions and aliases.  Supports `-v` (describe command), `-V` (verbose
describe), `-p` (use default PATH).

### 4.8 Aliases

#### `aliases.py` (~150 lines)

Two builtins:

- **`AliasBuiltin`** (`alias`) &mdash; defines or displays aliases.  With
  no arguments, lists all aliases.

- **`UnaliasBuiltin`** (`unalias`) &mdash; removes aliases.  Supports `-a`
  (remove all).

### 4.9 Help and debug

#### `help_command.py` (~220 lines)

**`HelpBuiltin`** (`help`) &mdash; displays help for shell builtins and
syntax.  With no arguments, lists all builtins with brief descriptions.

#### `debug_control.py` (~290 lines)

Four builtins for toggling debug modes:

- **`DebugASTBuiltin`** (`debug-ast`) &mdash; toggles AST display.
- **`DebugTokensBuiltin`** (`debug-tokens`) &mdash; toggles token display.
- **`DebugExpansionBuiltin`** (`debug-expansion`) &mdash; toggles expansion
  tracing.
- **`DebugExecBuiltin`** (`debug-exec`) &mdash; toggles executor debug
  output.

#### `parser_control.py` (~280 lines)

**`ParserConfigBuiltin`** (`parser-config`) &mdash; displays or modifies
parser configuration settings at runtime.

#### `parser_experiment.py` (~65 lines)

**`ParserSelectBuiltin`** (`parser-select`) &mdash; selects the active
parser implementation.  With no arguments, lists available parsers and marks
the active one.  Also defines the `PARSERS` dict (public API) and
`PARSER_LABELS` dict (internal).

### 4.10 Parse tree

#### `parse_tree.py` (~195 lines)

**`ParseTreeBuiltin`** (`parse-tree`) &mdash; displays the AST for a given
command string.  Uses the parser's visualization subsystem.


## 5. Common Tasks

### 5.1 Adding a new builtin

1. Create a file in `psh/builtins/` (e.g. `mycommand.py`):

   ```python
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

       def execute(self, args: List[str], shell: 'Shell') -> int:
           # args[0] is the command name
           i = 1
           while i < len(args) and args[i].startswith('-'):
               if args[i] == '-a':
                   ...
               elif args[i] == '--':
                   i += 1
                   break
               else:
                   self.error(f"unknown option: {args[i]}", shell)
                   return 1
               i += 1

           # Do the work
           print("output", file=shell.stdout)
           return 0
   ```

2. Add the import in `psh/builtins/__init__.py`:

   ```python
   from . import (
       ...
       mycommand,   # Add this line
       ...
   )
   ```

3. Update the docstring in `__init__.py` to include the new module.

4. If the builtin is a POSIX special builtin, add it to
   `POSIX_SPECIAL_BUILTINS` in `psh/executor/strategies.py`.

5. Add tests in `tests/unit/builtins/test_mycommand.py`.

6. Add conformance tests in `tests/conformance/` if the builtin has
   POSIX/bash semantics.

### 5.2 Adding an alias to an existing builtin

Override the `aliases` property in the builtin class:

```python
@builtin
class SourceBuiltin(Builtin):
    name = "source"

    @property
    def aliases(self):
        return ['.']
```

The decorator registers both the primary name and all aliases.

### 5.3 Adding options to a builtin

Follow the standard option-parsing pattern used throughout the codebase:

```python
def execute(self, args, shell):
    i = 1
    opt_verbose = False

    while i < len(args) and args[i].startswith('-'):
        if args[i] == '-v':
            opt_verbose = True
        elif args[i] == '--':
            i += 1
            break
        else:
            self.error(f"invalid option: {args[i]}", shell)
            return 2  # usage error
        i += 1

    remaining = args[i:]
    ...
```

### 5.4 Testing a builtin

```python
# tests/unit/builtins/test_mycommand.py

def test_mycommand_basic(captured_shell):
    result = captured_shell.run_command("mycommand arg1 arg2")
    assert result == 0
    assert "expected output" in captured_shell.get_stdout()

def test_mycommand_error(captured_shell):
    result = captured_shell.run_command("mycommand --bad-flag")
    assert result != 0
    assert "unknown option" in captured_shell.get_stderr()
```

Run tests:

```bash
python -m pytest tests/unit/builtins/ -v              # All builtin tests
python -m pytest tests/unit/builtins/test_echo.py -v  # Specific builtin
```


## 6. Design Rationale

### Why a decorator-based registry instead of explicit registration?

The `@builtin` decorator eliminates boilerplate.  Adding a new builtin
requires only creating a class with the decorator &mdash; no registration
calls, no factory functions, no configuration files.  The decorator pattern
also ensures that registration happens at import time, so the registry is
fully populated before the shell starts accepting input.

### Why is `args[0]` the command name?

This follows the Unix convention where `argv[0]` is the program name.  It
allows builtins with aliases (like `source` / `.`) to know which name was
used to invoke them, which matters for error messages and edge-case
behaviour.

### Why is `FunctionReturn` an exception?

Shell functions can `return` from deeply nested execution contexts (inside
loops, conditionals, and subshells).  Using an exception for control flow
provides a clean way to unwind the Python call stack to the function-call
handler, regardless of nesting depth.  This is the same pattern used for
`LoopBreak` and `LoopContinue`.

### Why are special builtins handled separately from regular builtins?

POSIX requires special builtins to take precedence over functions in command
lookup order.  A separate execution strategy (`SpecialBuiltinExecutionStrategy`)
handles this priority, while the builtins themselves are registered in the
same registry.  This separates lookup policy from implementation.

### Why does `declare` not live in `environment.py`?

`declare` manages variable attributes (readonly, integer, array types, case
transforms) and function introspection.  Its complexity (&gt;600 lines) and
its tight coupling with `typeset`, `readonly`, and `return` made
`function_support.py` a more natural home.  `environment.py` focuses on the
simpler export/set/unset commands.


## 7. Complete Builtin Reference

### POSIX Special Builtins

| Command | File | Description |
|---------|------|-------------|
| `:` | `core.py` | No-op, always succeeds |
| `break` | (executor) | Break from loop |
| `continue` | (executor) | Continue to next iteration |
| `eval` | `eval_command.py` | Execute arguments as shell command |
| `exec` | `core.py` | Replace shell with command |
| `exit` | `core.py` | Exit the shell |
| `export` | `environment.py` | Mark variables for export |
| `readonly` | `function_support.py` | Mark variables as readonly |
| `return` | `function_support.py` | Return from function |
| `set` | `environment.py` | Set shell options/positional params |
| `shift` | `positional.py` | Shift positional parameters |
| `trap` | `signal_handling.py` | Set signal handlers |
| `unset` | `environment.py` | Remove variables or functions |

### Regular Builtins

| Command | File | Description |
|---------|------|-------------|
| `alias` | `aliases.py` | Define or display aliases |
| `bg` | `job_control.py` | Resume job in background |
| `cd` | `navigation.py` | Change working directory |
| `command` | `command_builtin.py` | Execute bypassing functions |
| `declare` | `function_support.py` | Declare variables with attributes |
| `dirs` | `directory_stack.py` | Display directory stack |
| `disown` | `disown.py` | Remove jobs from table |
| `echo` | `io.py` | Display text |
| `false` | `core.py` | Return failure (1) |
| `fg` | `job_control.py` | Resume job in foreground |
| `getopts` | `positional.py` | Parse positional parameters |
| `help` | `help_command.py` | Display builtin help |
| `history` | `shell_state.py` | Display/manage command history |
| `jobs` | `job_control.py` | List background jobs |
| `kill` | `kill_command.py` | Send signals to processes |
| `local` | `shell_state.py` | Declare local variables |
| `popd` | `directory_stack.py` | Pop directory from stack |
| `printf` | `io.py` | Formatted output |
| `pushd` | `directory_stack.py` | Push directory onto stack |
| `pwd` | `io.py` | Print working directory |
| `read` | `read_builtin.py` | Read line from stdin |
| `shopt` | `shell_options.py` | Manage shell options |
| `source` / `.` | `source_command.py` | Execute file in current shell |
| `test` / `[` | `test_command.py` | Evaluate conditional expression |
| `true` | `core.py` | Return success (0) |
| `type` | `type_builtin.py` | Describe command type |
| `typeset` | `function_support.py` | Declare variables (ksh compat) |
| `unalias` | `aliases.py` | Remove aliases |
| `version` | `shell_state.py` | Display psh version |
| `wait` | `job_control.py` | Wait for background jobs |

### Debug / Parser Builtins (PSH-specific)

| Command | File | Description |
|---------|------|-------------|
| `debug-ast` | `debug_control.py` | Toggle AST display |
| `debug-exec` | `debug_control.py` | Toggle executor debug |
| `debug-expansion` | `debug_control.py` | Toggle expansion tracing |
| `debug-tokens` | `debug_control.py` | Toggle token display |
| `parse-tree` | `parse_tree.py` | Display AST for a command |
| `parser-config` | `parser_control.py` | Manage parser configuration |
| `parser-select` | `parser_experiment.py` | Select parser implementation |


## 8. File Dependency Graph

```
__init__.py
├── base.py              (Builtin ABC)
├── registry.py          (BuiltinRegistry, @builtin)
├── function_support.py  (FunctionReturn exception)
├── parser_experiment.py (PARSERS dict)
│
├── core.py              — exit, :, true, false, exec
├── io.py                — echo, printf, pwd
├── read_builtin.py      — read
├── navigation.py        — cd
├── directory_stack.py   — pushd, popd, dirs
├── environment.py       — export, set, unset
├── shell_options.py     — shopt
├── shell_state.py       — history, version, local
├── positional.py        — shift, getopts
├── job_control.py       — jobs, fg, bg, wait
├── kill_command.py      — kill
├── disown.py            — disown
├── eval_command.py      — eval
├── source_command.py    — source, .
├── signal_handling.py   — trap
├── test_command.py      — test, [
├── type_builtin.py      — type
├── command_builtin.py   — command
├── aliases.py           — alias, unalias
├── help_command.py      — help
├── debug_control.py     — debug-ast, debug-tokens, debug-expansion, debug-exec
├── parser_control.py    — parser-config
└── parse_tree.py        — parse-tree

External dependencies (outside the builtins package):
- psh/core/state.py          — ShellState (variables, options, exit codes)
- psh/core/variables.py      — Variable, VarAttributes, IndexedArray, AssociativeArray
- psh/core/exceptions.py     — ReadonlyVariableError, LoopBreak, LoopContinue
- psh/shell.py               — Shell (passed as parameter to execute())
- psh/executor/strategies.py — POSIX_SPECIAL_BUILTINS, execution strategy classes
- psh/utils/                  — ShellFormatter (function body formatting)
```
