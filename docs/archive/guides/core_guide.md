# PSH Core: Programmer's Guide

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> references `scope_enhanced.py`, which has since been renamed to `psh/core/scope.py`.
> See the subsystem CLAUDE.md files for current structure.

This guide covers the core package in detail: its external API, internal
architecture, and the responsibilities of every source file.  It is aimed at
developers who need to modify state management, add shell options, work with
variable scoping, or understand how shell state flows through the system.

## 1. What the Core Package Does

The core package provides centralised state management for the shell.  It owns
the variable system (scalars, arrays, attributes, scoping), shell options,
control-flow exceptions, signal trap management, and assignment-parsing
utilities.

Every other subsystem reads and writes state through `ShellState`.  The core
package does **not** execute commands, expand variables, or handle I/O; those
responsibilities belong to the executor, expansion, and I/O redirect packages.

## 2. External API

The public interface is defined in `psh/core/__init__.py`.  The declared
`__all__` contains eighteen items grouped into six categories: exceptions,
variables, scope management, state, options, traps, and assignment utilities.
See `docs/guides/core_public_api.md` for the full reference including
signatures and usage examples.

### 2.1 `ShellState`

```python
from psh.core import ShellState

state = ShellState(args=['arg1'], script_name='myscript.sh')
```

Central container for all mutable shell state.  Every component receives a
reference to `ShellState` (usually through `shell.state`) and uses it for
variable access, option checks, exit-code tracking, history, and terminal
capability queries.

Key groups of state:

| Group | Attributes | Description |
|-------|-----------|-------------|
| **Variables** | `scope_manager`, `env` | Variable scopes and OS environment. |
| **Options** | `options` | Dict of ~35 shell option flags. |
| **Execution** | `last_exit_code`, `last_bg_pid`, `foreground_pgid`, `command_number` | Process and exit-code tracking. |
| **Positional** | `positional_params`, `script_name` | `$1`..`$N`, `$0`. |
| **History** | `history`, `history_file`, `max_history_size` | Command history. |
| **Functions** | `function_stack` | Call stack for shell functions. |
| **Traps** | `trap_handlers`, `_original_signal_handlers` | Signal trap state. |
| **Terminal** | `is_terminal`, `supports_job_control`, `terminal_fd` | TTY capabilities. |
| **I/O** | `stdout`, `stderr`, `stdin` | Current I/O streams (properties). |

### 2.2 Variable System

```python
from psh.core import Variable, VarAttributes, IndexedArray, AssociativeArray
```

- **`Variable`** &mdash; dataclass with `name`, `value`, and `attributes`
  fields.  Properties like `is_readonly`, `is_exported`, `is_array` provide
  quick attribute checks.
- **`VarAttributes`** &mdash; `Flag` enum with 10 combinable flags (READONLY,
  EXPORT, INTEGER, LOWERCASE, UPPERCASE, ARRAY, ASSOC_ARRAY, NAMEREF, TRACE,
  UNSET).
- **`IndexedArray`** &mdash; sparse indexed array with `set(index, value)`,
  `get(index)`, `all_elements()`, `indices()`, `length()`.
- **`AssociativeArray`** &mdash; string-keyed hash map with `set(key, value)`,
  `get(key)`, `keys()`, `items()`, `length()`.

### 2.3 Scope Management

```python
from psh.core import EnhancedScopeManager, VariableScope
```

`EnhancedScopeManager` maintains a stack of `VariableScope` objects.  The
global scope is always at the bottom.  Function calls push scopes; returns
pop them.  Variable lookups walk the chain from innermost to outermost.

Key methods: `push_scope()`, `pop_scope()`, `get_variable()`,
`get_variable_object()`, `set_variable()`, `unset_variable()`.

### 2.4 Exceptions

```python
from psh.core import LoopBreak, LoopContinue, UnboundVariableError, \
    ReadonlyVariableError, ExpansionError
```

Control-flow exceptions (`LoopBreak`, `LoopContinue`) implement `break` and
`continue` with multi-level support via a `level` attribute.  Error exceptions
(`UnboundVariableError`, `ReadonlyVariableError`, `ExpansionError`) are raised
by the variable system and expansion engine.

### 2.5 Options and Traps

```python
from psh.core import OptionHandler, TrapManager
```

- **`OptionHandler`** &mdash; static methods for `errexit`, `nounset`,
  `xtrace`, and `pipefail` behaviour.
- **`TrapManager`** &mdash; manages `trap` command handlers for signals and
  pseudo-signals (`EXIT`, `DEBUG`, `ERR`).

### 2.6 Assignment Utilities

```python
from psh.core import is_valid_assignment, extract_assignments, is_exported
```

Shared functions for parsing `VAR=value` patterns, used by both the executor
and command modules.


## 3. Architecture

### 3.1 Component Diagram

```
ShellState (central container)
     |
     +--- scope_manager: EnhancedScopeManager
     |         |
     |         +--- scope_stack: [VariableScope, ...]
     |         |         |
     |         |         +--- variables: {name: Variable}
     |         |                   |
     |         |                   +--- value: str | IndexedArray | AssociativeArray
     |         |                   +--- attributes: VarAttributes
     |         |
     |         +--- global_scope: VariableScope
     |
     +--- options: dict  (35+ shell option flags)
     |
     +--- env: dict  (copy of os.environ)
     |
     +--- trap_handlers: dict  (signal -> command string)
     |
     +--- positional_params: list
     |
     +--- last_exit_code: int
     +--- last_bg_pid: int | None
     +--- function_stack: list
     +--- history: list
```

### 3.2 Variable Lookup Flow

When any component calls `state.get_variable(name)`:

```
ShellState.get_variable(name)
    |
    v
EnhancedScopeManager.get_variable(name)
    |
    v
1. Check special variables (RANDOM, LINENO, SECONDS, BASH_*)
    |
    v
2. Walk scope stack (innermost -> outermost):
    |   For each scope:
    |     If name in scope.variables:
    |       If variable has UNSET flag: return None (tombstone)
    |       Else: return variable.as_string()
    |
    v
3. Not found -> return None
    |
    v
ShellState falls back to env.get(name, default)
```

### 3.3 Variable Assignment Flow

When `state.set_variable(name, value)` is called:

```
ShellState.set_variable(name, value)
    |
    +-- if allexport: set with EXPORT attribute, sync to os.environ
    +-- else: scope_manager.set_variable(name, value, local=False)
              |
              v
         1. Check existing variable for READONLY -> raise ReadonlyVariableError
         2. Merge attributes (EXPORT is additive)
         3. Apply attribute transformations (integer, case conversion)
         4. Determine target scope:
              - local=True -> current scope
              - In function -> search scope chain for existing variable
              - Not found -> global scope
         5. Create or update Variable object
```

### 3.4 Scope Stack Lifecycle

```
Shell start:   [global]

Function call: [global, function_a]
  Nested call: [global, function_a, function_b]
  Return:      [global, function_a]

Function exit: [global]
```

`local` keyword creates a variable in the current (innermost) scope.  Without
`local`, assignments in functions update existing variables in their original
scope, or create new variables in the global scope.

### 3.5 Option System

Shell options are stored as a flat dictionary in `ShellState.options`.  The
`set` builtin maps single-letter flags to option names (e.g. `-e` &rarr;
`errexit`) and the `shopt` builtin handles bash-specific options.

`OptionHandler` provides the logic for option-dependent behaviours.  It is
called by the executor and expansion engine rather than checking options
directly, to centralise the complex conditional rules (e.g. `errexit` is
suppressed inside conditionals).

### 3.6 Trap System

Traps are stored in `ShellState.trap_handlers` as `{signal_name: command}`.
`TrapManager` provides the management API (`set_trap`, `remove_trap`,
`execute_trap`).  The actual signal handler registration is coordinated with
`psh/utils/signal_manager.py`.

Three pseudo-signals have special handling:
- **EXIT** &mdash; executed when the shell exits.
- **DEBUG** &mdash; executed before each command.
- **ERR** &mdash; executed when a command fails (non-zero exit code).


## 4. Source File Reference

All files are under `psh/core/`.  Line counts are approximate.

### 4.1 Package Entry Point

#### `__init__.py` (~52 lines)

Defines the public API via `__all__` (18 items).  Imports from all six
submodules.  Module docstring lists all submodules and their purpose.

### 4.2 Central State

#### `state.py` (~370 lines)

`ShellState` &mdash; the central container.  Constructor initialises the scope
manager, imports environment variables with `EXPORT` attributes, sets default
shell options (~35 options covering POSIX, bash compatibility, debug, and
parser configuration), detects terminal capabilities, and initialises history,
function stack, and trap handler state.

Key methods:

- `get_variable()` / `set_variable()` / `export_variable()` &mdash; variable
  access with scope-manager delegation and environment sync.
- `get_special_variable()` &mdash; handles `$?`, `$$`, `$!`, `$#`, `$@`,
  `$*`, `$-`, `$0`, and numeric positional parameters.
- `get_option_string()` &mdash; builds the `$-` flags string from active
  options.
- `_detect_terminal_capabilities()` &mdash; probes `isatty()` and
  `tcgetpgrp()` to determine job-control availability.

Properties provide transparent access to debug flags, I/O streams, and the
`variables` convenience dict.

### 4.3 Variables

#### `variables.py` (~240 lines)

Three classes:

- **`VarAttributes`** &mdash; `Flag` enum with 10 combinable members.
  Used throughout the shell to test and set variable metadata.

- **`Variable`** &mdash; dataclass with `name`, `value`, `attributes`.
  Boolean properties (`is_readonly`, `is_exported`, `is_array`, etc.)
  provide convenient attribute checks.  `as_string()` normalises the value
  to a string.  `copy()` creates a shallow duplicate.

- **`IndexedArray`** &mdash; sparse indexed array backed by a
  `Dict[int, str]`.  Supports negative indexing on `get()`.  `all_elements()`
  returns values in index order, skipping gaps.

- **`AssociativeArray`** &mdash; string-keyed dictionary.  Insertion order is
  preserved (Python 3.7+ guarantee) for bash compatibility.  `as_string()`
  always returns empty string (bash does not allow `${assoc}` without a
  subscript).

### 4.4 Scope Management

#### `scope_enhanced.py` (~467 lines)

Two classes:

- **`VariableScope`** &mdash; a single scope holding a `variables` dict,
  optional `parent` link, and `name`.  `copy()` creates a deep copy of the
  scope and its variables.

- **`EnhancedScopeManager`** &mdash; manages the scope stack with full
  attribute support.  Key implementation details:

  - **Lookup**: `get_variable_object()` walks the stack in reverse,
    checking for UNSET tombstones (which stop the search and return `None`).
  - **Assignment**: `set_variable()` determines the target scope based on the
    `local` flag and whether the variable already exists in the scope chain.
    In functions without `local`, existing variables are updated in place;
    new variables go to the global scope.
  - **Attribute merging**: new attributes are OR-merged with existing ones
    (e.g. adding EXPORT to an INTEGER variable preserves both flags).
  - **Attribute transformations**: `_apply_attributes()` handles integer
    coercion, case conversion, and nameref resolution at assignment time.
  - **Special variables**: `_get_special_variable()` handles `RANDOM`,
    `LINENO`, `SECONDS`, `BASH_SOURCE`, `FUNCNAME`, `BASH_LINENO`, and
    `BASH_SUBSHELL`.
  - **Nameref resolution**: `_resolve_nameref()` follows nameref chains
    (with cycle detection) to find the target variable.
  - **Export sync**: `sync_exports_to_environment()` copies all EXPORT-flagged
    variables into the environment dict and `os.environ`.

### 4.5 Options

#### `options.py` (~132 lines)

`OptionHandler` with four static methods:

- **`should_exit_on_error()`** &mdash; implements `errexit` logic.  Returns
  `False` in conditional contexts (`if`, `while`, `&&`, `||`), for negated
  commands (`!`), and for non-final pipeline commands (unless `pipefail`).
- **`check_unset_variable()`** &mdash; implements `nounset` logic.  Exempts
  special variables (`$?`, `$$`, `$#`, `$0`), `$@`/`$*` with no positional
  parameters, and parameter expansion contexts that provide defaults.
- **`print_xtrace()`** &mdash; prints the trace line using `$PS4` as prefix.
  Flushes stderr immediately so trace output appears before command output.
- **`get_pipeline_exit_code()`** &mdash; with `pipefail`: returns the
  rightmost non-zero exit code.  Without: returns the last command's code.

### 4.6 Exceptions

#### `exceptions.py` (~29 lines)

Five exception classes:

| Class | Base | Purpose |
|-------|------|---------|
| `LoopBreak` | `Exception` | Implement `break [N]`.  Attribute: `level`. |
| `LoopContinue` | `Exception` | Implement `continue [N]`.  Attribute: `level`. |
| `UnboundVariableError` | `Exception` | `set -u` violation. |
| `ReadonlyVariableError` | `Exception` | Modify/unset readonly variable.  Attribute: `name`. |
| `ExpansionError` | `Exception` | Expansion failure (e.g. `${var:?msg}`).  Attribute: `exit_code`. |

### 4.7 Trap Management

#### `trap_manager.py` (~239 lines)

`TrapManager` &mdash; initialised with a shell reference.  Builds a
`signal_map` (name &rarr; signal number) and reverse `signal_names` map
covering all named signals plus numeric signals 1&ndash;31.

Key methods:

- `set_trap(action, signals)` &mdash; routes to `_set_signal_handler()`,
  `_ignore_signal()`, or `_reset_trap()` based on the action string.
- `execute_trap(signal_name)` &mdash; executes the trap command via
  `shell.run_command()`, saving and restoring `last_exit_code` for non-EXIT
  traps.
- `show_traps()` &mdash; formats current traps as `trap -- 'action' SIGNAL`
  lines.

Pseudo-signals (EXIT, DEBUG, ERR) are stored in `trap_handlers` like real
signals but do not register OS signal handlers.  They are invoked by the
executor at the appropriate points.

### 4.8 Assignment Utilities

#### `assignment_utils.py` (~88 lines)

Three standalone functions:

- **`is_valid_assignment(arg)`** &mdash; checks for `NAME=value` pattern
  where name starts with a letter or underscore and contains only
  alphanumeric characters and underscores.
- **`extract_assignments(args)`** &mdash; scans consecutive valid
  assignments from the front of an argument list.  Stops at the first
  non-assignment.
- **`is_exported(var_name)`** &mdash; checks `os.environ` membership.


## 5. Common Tasks

### 5.1 Adding a New Shell Option

1. Add the option to the `options` dict in `ShellState.__init__()` with its
   default value and a comment:

   ```python
   'myoption': False,  # -o myoption: description
   ```

2. If the option has a single-letter flag, add the mapping in
   `psh/builtins/environment.py` `SetBuiltin`:

   ```python
   short_to_long = {
       'M': 'myoption',
       ...
   }
   ```

3. If the option is a `shopt` option (bash-specific), add it to the
   `ShoptBuiltin` list in `psh/builtins/shell_options.py`.

4. Implement the behaviour in the relevant component (executor, expansion,
   etc.).  Prefer using `OptionHandler` for complex conditional logic.

5. Add tests in `tests/unit/builtins/`.

### 5.2 Adding a New Variable Attribute

1. Add a member to `VarAttributes` in `variables.py`:

   ```python
   class VarAttributes(Flag):
       ...
       MY_ATTR = auto()  # Description
   ```

2. Add a property to `Variable`:

   ```python
   @property
   def is_my_attr(self) -> bool:
       return bool(self.attributes & VarAttributes.MY_ATTR)
   ```

3. If the attribute affects assignment (like INTEGER or LOWERCASE), add
   transformation logic to `EnhancedScopeManager._apply_attributes()`.

4. Handle the attribute in the `declare` builtin
   (`psh/builtins/function_support.py`).

5. Add tests.

### 5.3 Adding a New Special Variable

1. Add handling in `EnhancedScopeManager._get_special_variable()` in
   `scope_enhanced.py`:

   ```python
   if name == 'MY_SPECIAL':
       return Variable('MY_SPECIAL', self._compute_value(), VarAttributes.NONE)
   ```

2. If the variable needs to appear in `$-`, add it to
   `ShellState.get_option_string()`.

3. If the variable is a special parameter (`$?`, `$$`, etc.), add it to
   `ShellState.get_special_variable()`.

4. Add tests.

### 5.4 Working with Scopes in the Executor

```python
# Function call: push a new scope
shell.state.scope_manager.push_scope('my_function')

# Create a local variable
shell.state.scope_manager.set_variable('local_var', 'value', local=True)

# On function exit: pop the scope (local variables are destroyed)
shell.state.scope_manager.pop_scope()
```

### 5.5 Adding a New Trap Pseudo-Signal

1. Add the pseudo-signal name to `TrapManager.__init__()`:

   ```python
   self.signal_map['MYEVENT'] = 'MYEVENT'
   ```

2. Add special-case handling in `_set_signal_handler()`,
   `_ignore_signal()`, and `_reset_trap()`.

3. Add an `execute_myevent_trap()` method.

4. Call it from the appropriate point in the executor.

5. Add tests.


## 6. Design Rationale

### Why a single `ShellState` container?

A shell has a lot of interconnected state: variables affect expansion, options
affect execution, exit codes affect control flow, traps affect signal handling.
Centralising everything in one object makes dependencies explicit and avoids
hidden global state.  Every component receives `ShellState` (via
`shell.state`) and reads/writes through its methods.

### Why a scope stack instead of a single dictionary?

Bash variables have function-local scoping: `local` creates a variable visible
only within the current function and its callees.  A flat dictionary cannot
represent this.  The scope stack mirrors bash's runtime behaviour: each
function call pushes a scope, each return pops it, and lookups walk the chain.

### Why tombstones for unset variables?

When a function calls `unset x` where `x` exists in a parent scope, the
`unset` should only affect the current function's view.  A tombstone
(`VarAttributes.UNSET`) in the current scope stops the lookup without
modifying the parent scope.  When the function returns and its scope is
popped, the parent's `x` becomes visible again.

### Why use exceptions for control flow?

`break` and `continue` can cross multiple levels of nesting and must unwind
through arbitrary call stacks (especially with `eval` and `source`).
Exceptions provide clean, automatic unwinding with a natural place to
decrement the level counter at each loop boundary.

### Why is `OptionHandler` a class with static methods?

`OptionHandler` groups related option-behaviour logic in one place rather than
scattering `if state.options.get(...)` checks throughout the executor and
expansion engine.  The methods are static because they only need `ShellState`
as input (no instance state).  This keeps option semantics testable in
isolation.

### Why is the options dictionary flat instead of nested?

Bash's `set -o` and `shopt` options are all simple boolean flags (with one
exception: `parser-mode` is a string).  A flat dict with string keys matches
the way builtins enumerate and modify options.  The short-letter-to-long-name
mapping lives in the `set` builtin where it belongs.


## 7. File Dependency Graph

```
__init__.py
├── exceptions.py           (no internal imports)
├── variables.py            (no internal imports)
├── scope_enhanced.py
│   ├── exceptions.py       (ReadonlyVariableError)
│   └── variables.py        (Variable, VarAttributes, IndexedArray, AssociativeArray)
├── state.py
│   ├── scope_enhanced.py   (EnhancedScopeManager)
│   └── variables.py        (VarAttributes)
├── options.py
│   └── exceptions.py       (UnboundVariableError)
├── trap_manager.py         (no internal imports; uses shell reference)
└── assignment_utils.py     (no internal imports)

External dependencies (outside the core package):
- psh/version.py            — __version__ (used by state.py)
- psh/shell.py              — Shell class (TYPE_CHECKING import in trap_manager, options)
```


## 8. Integration Points

### With Expansion (`psh/expansion/`)

- Variables resolved via `state.get_variable()` and
  `scope_manager.get_variable_object()`.
- Special variables via `state.get_special_variable()`.
- Arrays via `IndexedArray` / `AssociativeArray` on `Variable.value`.
- `ExpansionError` and `UnboundVariableError` raised during expansion.
- `OptionHandler.check_unset_variable()` called for `nounset` enforcement.

### With Executor (`psh/executor/`)

- Exit codes: `state.last_exit_code`.
- Options: `OptionHandler.should_exit_on_error()`,
  `OptionHandler.print_xtrace()`.
- Control flow: `LoopBreak`, `LoopContinue` caught by loop executors.
- Assignments: `extract_assignments()`, `is_valid_assignment()` used by
  `CommandExecutor`.
- Functions: `scope_manager.push_scope()` / `pop_scope()` in
  `FunctionOperationExecutor`.

### With Builtins (`psh/builtins/`)

- `export`, `readonly`, `declare`, `local` modify variable attributes via
  `scope_manager.set_variable()`.
- `set` modifies shell options via `state.options`.
- `trap` uses `TrapManager` for signal handler management.
- `ReadonlyVariableError` caught by `export`, `unset`, `declare`.

### With I/O and Job Control

- Terminal state: `state.is_terminal`, `state.supports_job_control`.
- Process groups: `state.foreground_pgid`.
- Trap execution: `TrapManager.execute_exit_trap()` called on shell exit.


## 9. Testing

```bash
# Run core unit tests (if they exist)
python -m pytest tests/unit/core/ -v

# Test variable scoping
python -m pytest -k "scope" -v

# Test shell options
python -m pytest tests/unit/builtins/test_set.py -v

# Test traps
python -m pytest -k "trap" -v

# Debug scope operations
python -m psh --debug-scopes -c 'f() { local x=1; echo $x; }; f; echo $x'
```


## 10. Common Pitfalls

1. **Scope confusion**: Variables set in functions without `local` go to the
   global scope (bash behaviour).  Use `local` for function-private variables.

2. **Export sync**: When modifying exported variables, call
   `export_variable()` or ensure `sync_exports_to_environment()` is called.
   Direct modification of `scope_manager` without syncing to `env` and
   `os.environ` will cause child processes to see stale values.

3. **Readonly check**: Always check `is_readonly` before modifying a variable.
   The scope manager does this automatically; direct manipulation of
   `Variable.value` bypasses the check.

4. **Array vs scalar**: Check `variable.is_array` before treating a variable
   as a string.  `as_string()` handles the conversion, but the result may not
   be what you expect for arrays.

5. **Unset vs empty**: `VarAttributes.UNSET` means explicitly unset (returns
   `None` on lookup); an empty string `""` is still a set variable.

6. **Positional params are 1-indexed**: `$1` is `positional_params[0]`.  The
   `get_positional_param()` method handles the conversion.

7. **Option name formats**: Options use lowercase with hyphens in the
   `options` dict (e.g. `'debug-ast'`), which matches bash's `set -o` naming.
   Single-letter flags are mapped by the `set` builtin, not by `ShellState`.
