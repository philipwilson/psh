# Core/State Subsystem

This document provides guidance for working with the PSH core state management subsystem.

## Architecture Overview

The core subsystem provides centralized state management for the shell, including variables, scopes, options, and execution state.

```
ShellState (central container)
     ↓
┌────┴─────┬──────────┬──────────┬──────────┐
↓          ↓          ↓          ↓          ↓
Scope    Options   Variables  Execution  Traps
Manager            (arrays)    State    Manager
```

## Key Files

| File | Purpose |
|------|---------|
| `state.py` | `ShellState` - central state container for entire shell |
| `scope.py` | `ScopeManager`, `VariableScope` - hierarchical scope management |
| `variables.py` | `Variable`, `VarAttributes`, `IndexedArray`, `AssociativeArray` |
| `options.py` | Shell option handlers (errexit, pipefail, etc.) |
| `exceptions.py` | Shell-specific exceptions (`ReadonlyVariableError`, etc.) |
| `trap_manager.py` | Signal trap handling |
| `assignment_utils.py` | Shared assignment validation utilities |

## Core Patterns

### 1. ShellState as Central Container

All shell state goes through `ShellState`:

```python
class ShellState:
    def __init__(self):
        # Scope manager for variables
        self.scope_manager = ScopeManager()

        # Shell options dictionary
        self.options = {
            'errexit': False,    # -e
            'nounset': False,    # -u
            'xtrace': False,     # -x
            'pipefail': False,   # -o pipefail
            ...
        }

        # Execution state
        self.last_exit_code = 0
        self.last_bg_pid = None
        self.positional_params = []

        # Environment
        self.env = os.environ.copy()
```

### 2. Variable Attributes with Flags

Variables have metadata via `VarAttributes` flags:

```python
class VarAttributes(Flag):
    NONE = 0
    READONLY = auto()    # -r: cannot be modified
    EXPORT = auto()      # -x: exported to environment
    INTEGER = auto()     # -i: integer values
    LOWERCASE = auto()   # -l: convert to lowercase
    UPPERCASE = auto()   # -u: convert to uppercase
    ARRAY = auto()       # -a: indexed array
    ASSOC_ARRAY = auto() # -A: associative array
    NAMEREF = auto()     # -n: name reference
    UNSET = auto()       # explicitly unset in scope
```

### 3. Hierarchical Scope Management

Function calls create nested scopes:

```python
class ScopeManager:
    def push_scope(self, name: str):
        """Enter new scope (function call)."""
        new_scope = VariableScope(name, parent=self.current_scope)
        self._scope_stack.append(new_scope)

    def pop_scope(self):
        """Exit scope (function return)."""
        return self._scope_stack.pop()

    def get_variable(self, name: str) -> Optional[str]:
        """Look up variable, walking scope chain."""
        for scope in reversed(self._scope_stack):
            if name in scope.variables:
                return scope.variables[name]
        return None
```

## State Components

### Variables

```python
# Get/set variables
state.set_variable('MY_VAR', 'value')
value = state.get_variable('MY_VAR', default='')

# Export to environment
state.export_variable('PATH', '/usr/bin')

# With attributes (via scope manager)
state.scope_manager.set_variable(
    'readonly_var', 'fixed',
    attributes=VarAttributes.READONLY
)
```

### Special Variables

```python
state.get_special_variable('?')  # Exit code
state.get_special_variable('$')  # Shell PID
state.get_special_variable('!')  # Last bg PID
state.get_special_variable('#')  # Arg count
state.get_special_variable('@')  # All args
state.get_special_variable('*')  # All args as string
state.get_special_variable('-')  # Option flags
state.get_special_variable('0')  # Script name
state.get_special_variable('1')  # First positional
```

### Shell Options

```python
# Check options
if state.options.get('errexit'):
    # Exit on error behavior

# Set options
state.options['xtrace'] = True

# Get option string for $-
flags = state.get_option_string()  # e.g., "ex"
```

### Arrays

```python
# Indexed array
arr = IndexedArray()
arr.set(0, 'first')
arr.set(1, 'second')
arr.get(0)           # 'first'
arr.all_elements()   # ['first', 'second']
arr.indices()        # [0, 1]
arr.length()         # 2

# Associative array
assoc = AssociativeArray()
assoc.set('key1', 'value1')
assoc.get('key1')    # 'value1'
assoc.keys()         # ['key1']
```

## Common Tasks

### Adding a New Shell Option

1. Add to `state.py` options dictionary:
```python
self.options = {
    ...
    'myoption': False,  # -o myoption: description
}
```

2. Add to short-to-long mapping in `builtins/environment.py` `SetBuiltin`:
```python
short_to_long = {
    'M': 'myoption',  # if single-letter option
    ...
}
```

3. Implement behavior where needed (executor, expansion, etc.)

4. Add tests in `tests/unit/builtins/`

### Adding a New Variable Attribute

1. Add to `VarAttributes` enum in `variables.py`:
```python
class VarAttributes(Flag):
    ...
    MY_ATTR = auto()  # Description of attribute
```

2. Add property to `Variable` class:
```python
@property
def is_my_attr(self) -> bool:
    return bool(self.attributes & VarAttributes.MY_ATTR)
```

3. Handle in scope manager as needed

### Creating Local Variables in Functions

```python
# In function execution
state.scope_manager.push_scope('my_function')

# Create local variable
state.scope_manager.set_variable('local_var', 'value', local=True)

# On function exit
state.scope_manager.pop_scope()  # local_var no longer visible
```

## Key Implementation Details

### Environment Variable Sync

Exported variables are synced to `os.environ`:

```python
def export_variable(self, name: str, value: str):
    self.scope_manager.set_variable(name, value, attributes=VarAttributes.EXPORT)
    self.env[name] = value
    os.environ[name] = value
    self.scope_manager.sync_exports_to_environment(self.env)
```

### Allexport Mode

When `set -a` is enabled, all new variables are automatically exported:

```python
def set_variable(self, name: str, value: str):
    if self.options.get('allexport', False):
        self.scope_manager.set_variable(name, value, attributes=VarAttributes.EXPORT)
        self.env[name] = value
        os.environ[name] = value
```

### Terminal Detection

```python
def _detect_terminal_capabilities(self):
    if os.isatty(0):
        self.is_terminal = True
        try:
            os.tcgetpgrp(0)
            self.supports_job_control = True
        except OSError:
            self.supports_job_control = False
```

## Testing

```bash
# Run core unit tests
python -m pytest tests/unit/core/ -v

# Test variable scoping
python -m pytest tests/unit/core/test_scope*.py -v

# Debug scoping
python -m psh --debug-scopes -c 'f() { local x=1; echo $x; }; f'
```

## Common Pitfalls

1. **Scope Confusion**: Variables set in functions without `local` go to global scope (bash behavior).

2. **Export Sync**: When modifying exported variables, remember to sync to `os.environ`.

3. **Readonly Check**: Always check `is_readonly` before modifying a variable.

4. **Array vs Scalar**: Check `is_array` before treating a variable as a string.

5. **Unset vs Empty**: `VarAttributes.UNSET` means explicitly unset; empty string is still set.

6. **Positional Params**: These are 1-indexed (`$1`, not `$0`).

## Debug Options

```bash
python -m psh --debug-scopes  # Trace scope operations
```

Output example:
```
[SCOPE] Pushing scope: my_function
[SCOPE] Setting local variable: x = 1
[SCOPE] Popping scope: my_function
```

## Integration Points

### With Expansion (`psh/expansion/`)

- Variables resolved via `state.get_variable()`
- Special variables via `state.get_special_variable()`
- Arrays via scope manager

### With Executor (`psh/executor/`)

- Exit codes: `state.last_exit_code`
- Options checked: `state.options.get('errexit')`
- Background PIDs: `state.last_bg_pid`

### With Builtins (`psh/builtins/`)

- `export`, `readonly`, `declare` modify variable attributes
- `set` modifies shell options
- `local` creates function-local variables

### With Job Control (`psh/executor/job_control.py`)

- Terminal state: `state.is_terminal`, `state.supports_job_control`
- Process groups: `state.foreground_pgid`
