# Core Public API Reference

**As of v0.185.0** (post-cleanup)

This document describes the public API of the `psh.core` package: the
items declared in `__all__`, their signatures, and guidance on internal
imports that are available but not part of the public contract.

## Public API (`__all__`)

The declared public API consists of eighteen items:

```python
__all__ = [
    # Exceptions
    'LoopBreak', 'LoopContinue', 'UnboundVariableError',
    'ReadonlyVariableError', 'ExpansionError',
    # Variables
    'Variable', 'VarAttributes', 'IndexedArray', 'AssociativeArray',
    # Scope management
    'EnhancedScopeManager', 'VariableScope',
    # State
    'ShellState',
    # Options
    'OptionHandler',
    # Traps
    'TrapManager',
    # Assignment utilities
    'is_valid_assignment', 'extract_assignments', 'is_exported',
]
```

---

### `ShellState`

```python
from psh.core import ShellState

state = ShellState(
    args: list = None,
    script_name: str = None,
    debug_ast: bool = False,
    debug_tokens: bool = False,
    debug_scopes: bool = False,
    debug_expansion: bool = False,
    debug_expansion_detail: bool = False,
    debug_exec: bool = False,
    debug_exec_fork: bool = False,
    norc: bool = False,
    rcfile: str = None,
)
```

Central container for all shell state.  Every component accesses
variables, options, execution state, history, and terminal capabilities
through this object.

#### Key attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `scope_manager` | `EnhancedScopeManager` | Variable scope chain. |
| `env` | `dict` | Copy of `os.environ` at shell startup. |
| `options` | `dict` | Shell option flags (see section below). |
| `positional_params` | `list` | Positional parameters (`$1`, `$2`, ...). |
| `script_name` | `str` | Value of `$0`. |
| `last_exit_code` | `int` | Exit code of last command (`$?`). |
| `last_bg_pid` | `int or None` | PID of last background process (`$!`). |
| `foreground_pgid` | `int or None` | Process group ID of foreground job. |
| `function_stack` | `list` | Call stack for shell functions. |
| `trap_handlers` | `dict` | Signal name &rarr; trap command string. |
| `is_terminal` | `bool` | Whether stdin is a TTY. |
| `supports_job_control` | `bool` | Whether `tcsetpgrp()` is available. |

#### Key methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_variable(name, default='')` | `str` | Get variable value (scope manager first, then `env`). |
| `set_variable(name, value)` | `None` | Set variable (respects `allexport`). |
| `export_variable(name, value)` | `None` | Set variable with `EXPORT` attribute and sync to `os.environ`. |
| `get_positional_param(index)` | `str` | Get 1-based positional parameter. |
| `set_positional_params(params)` | `None` | Replace all positional parameters. |
| `get_special_variable(name)` | `str` | Get `$?`, `$$`, `$!`, `$#`, `$@`, `$*`, `$-`, `$0`, or `$N`. |
| `get_option_string()` | `str` | Flags string for `$-` (e.g. `"ehimsB"`). |

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `variables` | `dict` | All visible variables as `{name: str_value}`. |
| `stdout` | file | Current stdout (respects pytest capture). |
| `stderr` | file | Current stderr. |
| `stdin` | file | Current stdin. |
| `debug_ast` | `bool` | Whether AST debug output is enabled. |
| `debug_tokens` | `bool` | Whether token debug output is enabled. |
| `debug_scopes` | `bool` | Whether scope debug output is enabled. |

---

### `EnhancedScopeManager`

```python
from psh.core import EnhancedScopeManager

mgr = EnhancedScopeManager()
```

Manages a stack of `VariableScope` objects.  The bottom of the stack is
always the global scope.  Function calls push new scopes; function
returns pop them.

| Method | Returns | Description |
|--------|---------|-------------|
| `push_scope(name=None)` | `VariableScope` | Create and push a new scope (function entry). |
| `pop_scope()` | `VariableScope` | Remove and return the current scope (function exit). |
| `get_variable(name, default=None)` | `str or None` | Look up variable value walking the scope chain. |
| `get_variable_object(name)` | `Variable or None` | Look up full `Variable` object through scope chain. |
| `set_variable(name, value, attributes=NONE, local=False)` | `None` | Set variable in appropriate scope (respects readonly). |
| `unset_variable(name)` | `bool` | Unset a variable (creates tombstone in function scopes). |
| `get_all_variables()` | `dict` | All visible variables as `{name: str_value}`. |
| `sync_exports_to_environment(env)` | `None` | Sync exported variables to the environment dict. |
| `enable_debug(enabled=True)` | `None` | Toggle scope-operation debug output. |

### `VariableScope`

```python
from psh.core import VariableScope
```

A single scope in the scope chain.  Holds a `variables` dict mapping
names to `Variable` objects, an optional `parent` link, and a `name`
string.

| Attribute | Type | Description |
|-----------|------|-------------|
| `variables` | `dict[str, Variable]` | Variables defined in this scope. |
| `parent` | `VariableScope or None` | Enclosing scope. |
| `name` | `str` | Scope name (e.g. `"global"`, function name). |

---

### `Variable`

```python
from psh.core import Variable, VarAttributes

var = Variable(name='MY_VAR', value='hello', attributes=VarAttributes.EXPORT)
```

Dataclass representing a shell variable with its value and attributes.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | -- | Variable name. |
| `value` | `Any` | -- | Value (str, int, `IndexedArray`, or `AssociativeArray`). |
| `attributes` | `VarAttributes` | `NONE` | Combinable attribute flags. |

| Property | Type | Description |
|----------|------|-------------|
| `is_array` | `bool` | True if indexed or associative array. |
| `is_indexed_array` | `bool` | True if indexed array. |
| `is_assoc_array` | `bool` | True if associative array. |
| `is_readonly` | `bool` | True if readonly (`-r`). |
| `is_exported` | `bool` | True if exported (`-x`). |
| `is_integer` | `bool` | True if integer attribute (`-i`). |
| `is_lowercase` | `bool` | True if lowercase attribute (`-l`). |
| `is_uppercase` | `bool` | True if uppercase attribute (`-u`). |
| `is_nameref` | `bool` | True if name reference (`-n`). |
| `is_unset` | `bool` | True if explicitly unset (tombstone). |

| Method | Returns | Description |
|--------|---------|-------------|
| `as_string()` | `str` | Convert value to string representation. |
| `copy()` | `Variable` | Shallow copy of this variable. |

### `VarAttributes`

```python
from psh.core import VarAttributes

attrs = VarAttributes.EXPORT | VarAttributes.READONLY
```

`Flag` enum of combinable variable attributes:

| Member | Flag | Bash option | Description |
|--------|------|-------------|-------------|
| `NONE` | `0` | -- | No attributes. |
| `READONLY` | auto | `-r` | Cannot be modified or unset. |
| `EXPORT` | auto | `-x` | Exported to child processes. |
| `INTEGER` | auto | `-i` | Integer arithmetic on assignment. |
| `LOWERCASE` | auto | `-l` | Convert to lowercase on assignment. |
| `UPPERCASE` | auto | `-u` | Convert to uppercase on assignment. |
| `ARRAY` | auto | `-a` | Indexed array. |
| `ASSOC_ARRAY` | auto | `-A` | Associative array. |
| `NAMEREF` | auto | `-n` | Name reference (indirect variable). |
| `TRACE` | auto | `-t` | Function tracing enabled. |
| `UNSET` | auto | -- | Explicitly unset in current scope. |

### `IndexedArray`

```python
from psh.core import IndexedArray

arr = IndexedArray()
arr.set(0, 'first')
arr.set(1, 'second')
arr.get(0)            # 'first'
arr.all_elements()    # ['first', 'second']
arr.indices()         # [0, 1]
arr.length()          # 2
```

Bash-compatible indexed array with sparse index support.

| Method | Returns | Description |
|--------|---------|-------------|
| `set(index, value)` | `None` | Set element (non-negative index only). |
| `get(index)` | `str or None` | Get element (supports negative indices). |
| `unset(index)` | `None` | Remove element at index. |
| `all_elements()` | `list[str]` | All elements in index order. |
| `indices()` | `list[int]` | All defined indices, sorted. |
| `length()` | `int` | Number of defined elements. |
| `clear()` | `None` | Remove all elements. |
| `as_string()` | `str` | Element at index 0, or empty string. |

### `AssociativeArray`

```python
from psh.core import AssociativeArray

assoc = AssociativeArray()
assoc.set('key', 'value')
assoc.get('key')          # 'value'
assoc.keys()              # ['key']
assoc.length()            # 1
```

Bash-compatible associative array (hash map).

| Method | Returns | Description |
|--------|---------|-------------|
| `set(key, value)` | `None` | Set element with string key. |
| `get(key)` | `str or None` | Get element by key. |
| `unset(key)` | `None` | Remove element by key. |
| `all_elements()` | `list[str]` | All values in insertion order. |
| `keys()` | `list[str]` | All keys in insertion order. |
| `items()` | `list[tuple]` | All `(key, value)` pairs in insertion order. |
| `length()` | `int` | Number of elements. |
| `clear()` | `None` | Remove all elements. |
| `as_string()` | `str` | Always empty string (bash behaviour). |

---

### `OptionHandler`

```python
from psh.core import OptionHandler
```

Static methods implementing shell option behaviours.  These are called
by the executor and expansion engine to enforce `errexit`, `nounset`,
`xtrace`, and `pipefail` semantics.

| Method | Returns | Description |
|--------|---------|-------------|
| `should_exit_on_error(state, in_conditional=False, in_pipeline=False, is_negated=False)` | `bool` | Whether the shell should exit due to `errexit` (`set -e`). Returns `False` in conditional contexts, for negated commands, and for non-final pipeline commands (unless `pipefail` is set). |
| `check_unset_variable(state, var_name, in_expansion=False)` | `None` | Raise `UnboundVariableError` if `nounset` (`set -u`) is active and the variable is unset. Handles special variables, positional parameters, and expansion contexts. |
| `print_xtrace(state, command_parts)` | `None` | Print `xtrace` (`set -x`) output using `$PS4` as the prompt prefix. |
| `get_pipeline_exit_code(state, exit_codes)` | `int` | Compute pipeline exit code.  With `pipefail`: rightmost non-zero.  Without: last command's exit code. |

---

### `TrapManager`

```python
from psh.core import TrapManager

trap_mgr = TrapManager(shell)
```

Manages signal trap handlers for the shell.  Maps signal names (and
pseudo-signals `EXIT`, `DEBUG`, `ERR`) to command strings that are
executed when the signal is received.

| Method | Returns | Description |
|--------|---------|-------------|
| `set_trap(action, signals)` | `int` | Set trap: command string, `''` to ignore, `'-'` to reset. |
| `remove_trap(signals)` | `int` | Reset traps to default (alias for `set_trap('-', ...)`). |
| `execute_trap(signal_name)` | `None` | Execute the trap command for a signal. |
| `execute_exit_trap()` | `None` | Execute the `EXIT` trap if set. |
| `execute_debug_trap()` | `None` | Execute the `DEBUG` trap if set. |
| `execute_err_trap(exit_code)` | `None` | Execute the `ERR` trap if command failed. |
| `list_signals()` | `list[str]` | List available signal names with numbers. |
| `show_traps(signals=None)` | `str` | Formatted display of current trap settings. |

---

### Exceptions

#### `LoopBreak`

```python
from psh.core import LoopBreak

raise LoopBreak(level=1)
```

Exception used to implement the `break` statement.  The `level`
attribute (default 1) indicates how many enclosing loops to break out
of.

#### `LoopContinue`

```python
from psh.core import LoopContinue

raise LoopContinue(level=1)
```

Exception used to implement the `continue` statement.  The `level`
attribute (default 1) indicates how many enclosing loops to skip to.

#### `UnboundVariableError`

```python
from psh.core import UnboundVariableError
```

Raised when accessing an unset variable with `nounset` (`set -u`)
enabled.

#### `ReadonlyVariableError`

```python
from psh.core import ReadonlyVariableError

raise ReadonlyVariableError(name='MY_VAR')
```

Raised when attempting to modify or unset a readonly variable.  The
`name` attribute carries the variable name.

#### `ExpansionError`

```python
from psh.core import ExpansionError

raise ExpansionError("message", exit_code=1)
```

Raised when parameter expansion fails (e.g. the `${VAR:?message}`
operator when `VAR` is unset).  The `exit_code` attribute (default 1)
is the exit code the shell should report.

---

### Assignment Utilities

#### `is_valid_assignment()`

```python
from psh.core import is_valid_assignment

is_valid_assignment("FOO=bar")    # True
is_valid_assignment("123=bad")    # False
is_valid_assignment("no_equals")  # False
```

Check if a string is a valid shell variable assignment (`NAME=value`).
The name must start with a letter or underscore and contain only
alphanumeric characters and underscores.

#### `extract_assignments()`

```python
from psh.core import extract_assignments

extract_assignments(["FOO=bar", "BAZ=qux", "echo", "hello"])
# [("FOO", "bar"), ("BAZ", "qux")]
```

Extract consecutive variable assignments from the beginning of an
argument list.  Stops at the first non-assignment argument.

#### `is_exported()`

```python
from psh.core import is_exported

is_exported("PATH")   # True (typically)
is_exported("MY_VAR") # False (typically)
```

Check if a variable name exists in `os.environ`.

---

## Submodule-Only Imports

All items in `__all__` are the complete public API.  The core package
does not have additional convenience imports beyond `__all__`.  The
following are importable from their defining submodules but are not
re-exported at the package level:

| Item | Canonical path | Purpose |
|------|---------------|---------|
| (none) | -- | All public items are in `__all__`. |

Internal classes and helpers within individual modules (e.g.
`VariableScope.copy()`, `EnhancedScopeManager._apply_attributes()`)
are implementation details.

## API Tiers Summary

| Tier | Scope | How to import | Stability guarantee |
|------|-------|---------------|-------------------|
| **Public** | All 18 items in `__all__` | `from psh.core import ...` | Stable. Changes are versioned. |
| **Internal** | Private methods, module-level helpers | `from psh.core.<module> import ...` | Internal. May change without notice. |

## Typical Usage

### Access shell variables

```python
from psh.core import ShellState

state = ShellState()
state.set_variable('MY_VAR', 'hello')
value = state.get_variable('MY_VAR')  # 'hello'
state.export_variable('PATH', '/usr/bin')
```

### Use variable attributes

```python
from psh.core import VarAttributes, Variable

var = Variable('count', '42', VarAttributes.INTEGER | VarAttributes.READONLY)
var.is_integer   # True
var.is_readonly  # True
```

### Work with arrays

```python
from psh.core import IndexedArray, AssociativeArray

arr = IndexedArray()
arr.set(0, 'a')
arr.set(5, 'b')   # sparse: indices 1-4 are unset
arr.length()       # 2

assoc = AssociativeArray()
assoc.set('name', 'psh')
assoc.keys()  # ['name']
```

### Handle shell options

```python
from psh.core import OptionHandler

if OptionHandler.should_exit_on_error(state):
    sys.exit(state.last_exit_code)
```

### Catch control flow exceptions

```python
from psh.core import LoopBreak, LoopContinue

try:
    # execute loop body
    pass
except LoopBreak as e:
    # break N levels
    if e.level > 1:
        raise LoopBreak(e.level - 1)
except LoopContinue as e:
    if e.level > 1:
        raise LoopContinue(e.level - 1)
```

## Related Documents

- `docs/guides/core_guide.md` -- Full programmer's guide (architecture,
  file reference, design rationale)
- `docs/guides/core_public_api_assessment.md` -- Analysis that led to
  this cleanup
- `psh/core/CLAUDE.md` -- AI assistant working guide for the core
  subsystem
