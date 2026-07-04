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
| `execution_state.py` | `ExecutionState` - per-command execution scratch (`last_exit_code`, `last_bg_pid`, `pipestatus`, `in_forked_child`, ...); ShellState delegates via properties |
| `history_state.py` | `HistoryState` - command history list + persistence settings (ShellState delegates) |
| `terminal_state.py` | `TerminalState` - terminal capabilities (`is_terminal`/`supports_job_control`; ShellState delegates) |
| `stream_bindings.py` | `StreamBindings` - stdin/stdout/stderr overrides (ShellState delegates) |
| `command_hash.py` | `CommandHashTable` - remembered command locations (`hash` builtin; cleared via `ScopeManager.path_changed` on any PATH write) |
| `scope.py` | `ScopeManager`, `VariableScope` - hierarchical scope management |
| `variables.py` | `Variable`, `VarAttributes`, `IndexedArray`, `AssociativeArray` |
| `option_registry.py` | `OPTION_REGISTRY` (single source of truth for all shell options) + `ShellOptions` (registry-backed, dict-compatible container; `ShellState.options`) |
| `options.py` | `OptionHandler` - option *behavior* helpers (nounset check, xtrace print) |
| `functions.py` | `FunctionManager` - shell function definitions |
| `exceptions.py` | `PshError` root + error classes, and control-flow signals (`LoopBreak`, etc.) |
| `internal_errors.py` | Expected-error taxonomy + `report_internal_defect` (strict-errors guard) |
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
    NAMEREF = auto()     # -n: name reference (indirect)
    TRACE = auto()       # -t: function tracing enabled
    UNSET = auto()       # explicitly unset in scope (tombstone)
```

### 3. Hierarchical Scope Management

Function calls create nested scopes:

Scopes hold `Variable` objects (not plain strings); the stack lives in
`self.scope_stack`, with `scope_stack[0]` always the global scope:

```python
class ScopeManager:
    def __init__(self):
        self.global_scope = VariableScope(name="global")
        self.scope_stack: List[VariableScope] = [self.global_scope]

    def push_scope(self, name: Optional[str] = None) -> VariableScope:
        """Create new scope for function entry."""
        new_scope = VariableScope(parent=self.current_scope, name=name)
        self.scope_stack.append(new_scope)
        return new_scope

    def pop_scope(self) -> Optional[VariableScope]:
        """Remove scope on function exit (cannot pop global scope)."""
        ...

    def get_variable(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get variable value as string, following namerefs, or default."""
        var = self._lookup_resolved(name)   # walks scope chain + nameref chain
        return var.as_string() if var else default

    def get_variable_object(self, name: str) -> Optional[Variable]:
        """Full Variable through scope chain (no nameref deref).
        UNSET tombstones make lookup return None."""
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

`psh/core/option_registry.py` is the SINGLE source of truth for every option's
default, value type, category, short flag, and `$-` letter. The defaults dict,
`SetBuiltin.short_to_long`, `ShoptBuiltin.SHOPT_OPTIONS`, and the `$-` string
are all derived from it — do NOT re-add a parallel map.

1. Add one `_spec(...)` to `_SPECS` in `option_registry.py`:
```python
_spec("myoption", False, OptionCategory.SET, short_flag="M", dollar_dash="M"),
```

2. Add the name to `EXPECTED_OPTIONS` in
   `tests/unit/core/test_option_registry.py` (the drift-lock meta-test fails
   until you do — adding/removing an option is a deliberate edit).

3. Implement behavior where needed (executor, expansion, etc.). Read it via
   `state.options.get('myoption')` / `state.options['myoption']` as usual.

4. Add behavioral tests in `tests/unit/builtins/`.

`ShellState.options` is a `ShellOptions` (a registry-backed,
dict-compatible container): reads/writes use the same `['key']`/`.get()` API,
but a write with an unregistered name raises (typos fail loudly).

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

### Namerefs (`declare -n`)

A nameref `Variable` stores its target *name* as its value. Two resolution
paths in `scope.py`:

- **Reads**: `_lookup_resolved()` follows the nameref chain to the final
  non-nameref `Variable`. A cyclic chain prints bash's
  "warning: NAME: circular name reference" (via `warn_nameref_cycle()`)
  and reads as unset.
- **Writes/unsets**: `resolve_nameref_name(name)` returns the final target
  *name*. A nameref with an empty target resolves to its own name (so
  `declare -n r; r=x` sets r's target rather than writing through). A
  cycle raises `NamerefCycleError` (rejecting the write, like bash).

Tests: `tests/unit/core/test_nameref.py`.

### Unset Semantics & Tombstones

bash's dynamic scoping keeps a per-name stack of variable instances;
`unset` removes the **most recent** one, revealing the next-outer
instance (`x=g; f(){ local x=f; g; }; g(){ unset x; echo $x; }; f`
prints `g` — g's unset removed f's local). `unset_variable()` therefore
walks the scope chain and deletes the innermost instance wherever it
lives — unsetting a global from inside a function removes the global,
so a later assignment writes the global again (`x=1; f(){ unset x;
x=new; }; f` leaves `x=new`).

The one exception is a local unset **in its own declaring scope**: bash
(default, non-`localvar_unset`) leaves it "local and unset" — the outer
instance does not show through in that scope. That state is recorded as
a **tombstone** — `Variable(name, value="", attributes=VarAttributes.UNSET)`
— and this is the ONLY case `unset` plants one (`local`/`declare` without
a value create the same declared-but-unset cell). `get_variable_object()`
returns `None` when it hits a tombstone (stopping the walk, so the cell
shadows in child scopes too); `set_variable()` binds to the innermost
scope holding an instance *including* a tombstone (bash: `local x; unset
x; x=new` rebinds in the declaring scope, even from a called function);
a repeated `unset` of an own-scope tombstone is a no-op, but from a
DEEPER scope the same cell is removed outright.
`get_declared_variable_object()` finds tombstones so `declare -p x`
prints `declare -- x`; listing functions (`get_all_variables()`, etc.)
hide them. Unset strips
attributes (`local -i x=5; unset x` → `declare -- x`). Behaviors are
pinned by `tests/unit/core/test_scope_tombstones.py` and the
`unset_*` cases in `tests/behavioral/golden_cases.yaml`
(re-run against real bash via `--compare-bash`).

### Subshell-Style Inheritance: `ShellState.adopt()`

Child shells for `( ... )` subshells, command/process substitution and the
`env` builtin's in-process child are built with `Shell.for_subshell(parent)`
(v0.314). The pure state-copying half is `ShellState.adopt(parent_state)`
(`state.py`): it copies the live environment, every variable scope as
whole `Variable` objects (preserving export/readonly/array attributes),
positional parameters, shell options, `$?`, script mode, PIPESTATUS,
`$PPID` and `$$`, then re-syncs exports into the environment. Mode flags
(`interactive`, `stdin_mode`, `emacs`) are recomputed afterwards by
`Shell._init_interactive`. Jobs are never copied — those are
shell-specific (the Shell-level half, copying function/alias managers,
lives in `Shell._inherit_from_parent`).

### Exception Hierarchy (`exceptions.py`)

Two distinct families — do not mix them up:

- **Errors** derive from `PshError`, the root of every psh-specific error
  class (lexer, parser, arithmetic, expansion, builtins). Catch "any psh
  error" with one `except PshError`. Members here: `UnboundVariableError`,
  `ReadonlyVariableError`, `NamerefCycleError`, `ExpansionError` (with
  `FatalExpansionError` for the `${x:?}`/unknown-`@X`-transform kinds that
  exit a non-interactive shell — see `fatal_expansion_status` in
  `internal_errors.py` for the bash discard-line model),
  `FunctionDefinitionError` (invalid/reserved/readonly function name).
- **Control-flow signals** (`LoopBreak`, `LoopContinue`, `FunctionReturn`)
  implement `break`/`continue`/`return` and deliberately do NOT derive
  from `PshError` — a blanket `except PshError` must never swallow a
  `return` statement.

### Expected-error taxonomy & `strict-errors` (`internal_errors.py`)

The four last-resort guards (command dispatch, builtin execution, function
body, buffered-statement source) delegate to one helper,
`report_internal_defect(state, exc, *, prefix, stream)`. It classifies the
exception: an **expected shell error** — any `PshError`, `OSError`, or
`SyntaxError` (redirection/fork failures, lexer/parse errors, arithmetic
errors) — is reported normally (message + exit 1); anything else (a genuine
Python-bug exception like `RuntimeError`/`AttributeError`/`TypeError`/
`KeyError`/plain `ValueError`) is an INTERNAL DEFECT.

The `strict-errors` shell option (seeded from `PSH_STRICT_ERRORS`) makes the
guard RE-RAISE internal defects instead of masking them as exit 1. **`conftest.py`
enables it suite-wide** (`PSH_STRICT_ERRORS=1`, in-process + subprocess), so a
genuine internal defect FAILS the test suite loudly. When adding a NEW legitimate
shell-error path, give it a `PshError` subclass (e.g. `FunctionDefinitionError`)
so it classifies as expected — do not let a bare Python exception stand in for
a shell error.

### Environment Policy (os.environ is read-once)

`os.environ` is read ONCE at startup (`self.env = os.environ.copy()`);
`state.env` is the live environment from then on and is passed
EXPLICITLY to every child: `execvpe(args, shell.env)` in
`executor/strategies.py` and `builtins/core.py`, and
`Shell.for_subshell(parent)` copies it (via `ShellState.adopt`) for
subshell-style children.
Nothing writes `os.environ` after startup — such a write would be
invisible to children and only leak state into the hosting Python
process (the pre-v0.312 `FOO=bar exec` leak).

Exported variables are synced to `state.env`:

```python
def export_variable(self, name: str, value: str):
    self.scope_manager.set_variable(name, value,
                                    attributes=VarAttributes.EXPORT, local=False)
    self.env[name] = value
    self.scope_manager.sync_exports_to_environment(self.env)
```

### Allexport Mode

When `set -a` is enabled, all new variables are automatically exported:

```python
def set_variable(self, name: str, value: str):
    if self.options.get('allexport', False):
        self.scope_manager.set_variable(name, value,
                                        attributes=VarAttributes.EXPORT, local=False)
        self.env[name] = value
        self.scope_manager.sync_exports_to_environment(self.env)
    else:
        self.scope_manager.set_variable(name, value, local=False)
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

2. **Export Sync**: When modifying exported variables, sync to `state.env`
   (NEVER `os.environ` — it is read once at startup and never written;
   children receive `state.env` explicitly).

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
