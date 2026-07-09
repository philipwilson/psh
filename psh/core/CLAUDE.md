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
| `special_registry.py` | `SPECIAL_REGISTRY` + `SpecialParameterState` - the single declarative table + typed lifecycle state for computed specials (RANDOM/SECONDS/LINENO/...); see "Computed Special Parameters" below |
| `environment.py` | `is_environ_shell_name` - the one rule deciding which inherited env entries become shell variables vs stay opaque (appraisal H3) |
| `variables.py` | `Variable`, `VarAttributes`, `IndexedArray`, `AssociativeArray` |
| `option_registry.py` | `OPTION_REGISTRY` (single source of truth for all shell options) + `ShellOptions` (registry-backed, dict-compatible container; `ShellState.options`) |
| `options.py` | `OptionHandler` - option *behavior* helpers (nounset check, xtrace print) |
| `locale_service.py` | `LocaleService` (on `ShellState.locale`) - effective LC_CTYPE/LC_COLLATE from env at startup; the one home for collation (`collate_key`/`compare`), locale-gated case mapping (`upper`/`lower`/`toggle`), and POSIX character-class membership (`in_class`, `posix_class_ranges` — host libc `iswctype` via ctypes). See `docs/architecture/locale_service_design_2026-07-06.md` |
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

### 4. Variable-mutation model — the `VariableStore`

Every variable WRITE goes through one authoritative service,
`scope_manager.store` (a `VariableStore`, in `variable_store.py`). It is the
single transaction boundary, so readonly enforcement, nameref resolution,
negative-index resolution, and the env/PATH observers cannot be bypassed by a
caller that forgets a guard (core-state appraisal C2 / Phase 2).

```python
store = shell.state.scope_manager.store
store.assign(name, value, attributes=..., local=..., global_scope=...)
store.append(name, value, global_scope=...)   # target-scope-aware append base
store.set_element(name, key, value)           # guarded array-element write
store.unset_element(name, key)                # guarded array-element unset
store.add_attributes(name, attrs, global_scope=...)
store.remove_attributes(name, attrs, global_scope=...)
store.unset(name)
```

- Whole-variable ops are a typed facade over the `ScopeManager` authority
  (`set_variable`/`create_local`/`apply_attribute`/`remove_attribute`) — that is
  where the actual `.value`/`.attributes` writes live.
- `append` reads the append base from the scope the write TARGETS (so
  `declare -g x+=A` reads the global base, not a local shadow) and honors the
  target's integer attribute (`export n+=3` on `-i n` appends arithmetically).
- `set_element`/`unset_element` own the ONE negative-subscript formula
  (`IndexedArray.resolve_write_index`), validate readonly BEFORE mutating, and
  fire the observers.
- The four declaration builtins (`declare`/`export`/`readonly`, with
  `readonly` delegating to `declare -r`) run their SCALAR path through one
  `DeclarationEngine` (`builtins/declaration_engine.py`) that commits via the
  store. `local` keeps `ScopeManager.create_local` (its redeclare-merge,
  exported-shadow inheritance, and same-scope tombstone semantics are
  local-specific) — folding it into the store is Phase 4.

**Write-ban invariant** (`tests/unit/core/test_variable_store_write_ban.py`):
no production code outside `variable_store.py` and `scope.py` may write
`X.value.set/.unset/.clear/.append(` or `.attributes =/|=/&=`. Route new
mutations through the store. Known Phase-4 gap: `executor/array.py` still mutates
an existing array via a local alias (`array = var_obj.value; array.set(...)`),
which the textual ban cannot see; it is already readonly-guarded (P1).

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
but the registry is AUTHORITATIVE (appraisal H4) — a write with an unregistered
name raises (typos fail loudly), a write with the wrong `value_type` raises (a
bool option rejects `'false'`/`1`/`None`), and deleting a key is prohibited (it
would make a typed accessor `KeyError`). Every SET/SHOPT option must be READ
somewhere for behavior or listed in the `_PRESENTATION_ONLY` allowlist with a
reason (`test_option_registry.py` consumer meta-test) — this is what keeps inert
options (the retired `collect_errors` / phantom `parser-mode`) from returning.

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

### Subshell-Style Inheritance: `ShellState.clone_for_child()`

Child shells for `( ... )` subshells and command/process substitution are
built with `Shell.for_subshell(parent)` (v0.314). The pure state-copying half
is `ShellState.clone_for_child(parent_state, context)` (`state.py`, v0.656,
replacing the old build-then-overlay `adopt`): it builds the child via
`__new__` and assigns every inheritable field EXACTLY from the parent — no
fresh `os.environ` import and no seeded defaults, so a name the parent unset
stays unset in the child (no resurrection). Mutable inheritable data (env,
variable scopes with DEEP-copied arrays, command hash, options, execution
state, history, positional params, function stack, directory stack, traps) is
deep-cloned; process-local data (streams, terminal, arithmetic re-entrancy) is
reset; the locale is shared. `$PPID`/`$$` stay stable across subshells; RANDOM
reseeds. Mode flags (`interactive`, `stdin_mode`, `emacs`) are recomputed
afterwards by `Shell._init_interactive`. Jobs are never copied. The Shell-level
half (copying function/alias managers — per-instance `Function` metadata so a
child's `readonly -f`/redefinition can't leak) lives in
`Shell._inherit_from_parent`. Completeness is guarded by
`tests/unit/core/test_state_adopt_completeness.py` (a name drift-lock plus a
graph-independence identity walk). The `env` builtin is no longer an in-process
child — standard `env` runs the command externally (v0.656).

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
exception: an **expected shell error** — any `PshError`, `OSError`,
`SyntaxError` (redirection/fork failures, lexer/parse errors, arithmetic
errors) or `RecursionError` (runaway recursion hitting psh's implicit
FUNCNEST; the function-call boundary usually converts it first) — is
reported normally (message + exit 1); anything else (a genuine
Python-bug exception like a non-recursion `RuntimeError`/`AttributeError`/
`TypeError`/`KeyError`/plain `ValueError`) is an INTERNAL DEFECT.

The `strict-errors` shell option (seeded from `PSH_STRICT_ERRORS`) makes the
guard RE-RAISE internal defects instead of masking them as exit 1. **`conftest.py`
enables it suite-wide** (`PSH_STRICT_ERRORS=1`, in-process + subprocess), so a
genuine internal defect FAILS the test suite loudly. When adding a NEW legitimate
shell-error path, give it a `PshError` subclass (e.g. `FunctionDefinitionError`)
so it classifies as expected — do not let a bare Python exception stand in for
a shell error.

### Computed Special Parameters (`special_registry.py`)

The dynamically computed specials (`RANDOM`, `SECONDS`, `BASHPID`, `SRANDOM`,
`EPOCHSECONDS`, `EPOCHREALTIME`, `LINENO`, the READONLY option-reflection
pair `SHELLOPTS`/`BASHOPTS` — colon-joined sorted enabled set-o/shopt
options computed live from `SET_O_OPTION_NAMES`/`SHOPT_OPTION_NAMES`,
env-imported at startup and env-tracking via `ShellOptions.on_change` when
exported — plus the shell-view projections
`PIPESTATUS`, `BASH_COMMAND`, `FUNCNAME`) are declared in ONE table,
`SPECIAL_REGISTRY`, instead of scattered frozensets and an `if`-chain
(core-state appraisal H1). Each row (`SpecialVarSpec`) declares its `compute`
callable, `assign` policy (`SEED` resets SECONDS' baseline / seeds RANDOM;
`IGNORE` drops the value; `NONE` = ordinary path), whether reading has side
effects (guards nameref inspection), default attributes (INTEGER for the numeric
ones), and `lifecycle`.

`ScopeManager` holds one `SpecialParameterState` (`self._special`) that owns the
SECONDS baseline (on `time.monotonic()`, so a wall-clock step never moves
elapsed time), the RANDOM seed, the LINENO counter, the deactivated-on-`unset`
set, and a persistent-attribute OVERLAY. Two categories:

- **Dynamic specials** (`lifecycle=True`, the first seven): no stored `Variable`
  exists while active. `set_variable`/`apply_attribute`/`remove_attribute`/
  `unset_variable` intercept them via `has_lifecycle(name)`, so `readonly
  RANDOM` / `export SECONDS` PERSIST on the overlay (enforced on later
  assignment, materialised into `state.env` as a snapshot through
  `find_exported_instance`, and shown by `declare -p NAME`), and `unset`
  DEACTIVATES the name (it becomes an ordinary variable, bash).
- **Shell-view specials** (`lifecycle=False`): computed read that SHADOWS any
  stored variable; assignment/readonly/unset all take the ordinary path
  (already bash-correct, so no interception).

`UID`/`EUID`/`PPID` are NOT here — they are real readonly-integer variables
seeded at startup. When adding a computed special, add a `SpecialVarSpec` row
(and, for a `lifecycle` one, confirm the interception points cover it).

### Environment Policy (os.environ is read-once; opaque inherited entries)

`os.environ` is read ONCE at startup (`self.env = os.environ.copy()`);
`state.env` is the live environment from then on and is passed
EXPLICITLY to every child: `execvpe(args, shell.env)` in
`executor/strategies.py` and `builtins/core.py`, and
`Shell.for_subshell(parent)` copies it (via `ShellState.clone_for_child`)
for subshell-style children.
Nothing writes `os.environ` after startup — such a write would be
invisible to children and only leak state into the hosting Python
process (the pre-v0.312 `FOO=bar exec` leak).

At startup only inherited entries whose NAME is a valid shell identifier
(`environment.is_environ_shell_name`, bash's ASCII `legal_identifier`) are
imported as exported shell variables. An entry with an invalid name
(`bad-name`, `a.b`, a non-ASCII name) stays as an OPAQUE inherited entry — passed
to children and shown by `printenv`, but NOT a shell variable, so `set` /
`declare -p` / `export -p` / `compgen -v` do not list it (bash; appraisal H3).

**One env interface + materialization (v0.669, Phase 4).** The opaque entries
are held in an EXPLICIT typed store, `state._env_base`, and the execution
environment is MATERIALIZED (not incrementally mutated) as
`opaque-base + exported-vars + command-overlay`. `ShellState._materialize_env_name`
is the ONE place `state.env[name]` is written — precedence
**overlay > innermost exported variable > opaque base > absent** — and the
`variable_changed` observer, `clone_for_child`, and the temp-env teardown all go
through it. No production code poke `state.env[...]` directly.

- **Command temporary environment** (`ScopeManager.command_temp_env`, a
  `List[Dict[str, Variable]]` stack): a `VAR=x cmd` prefix over a
  builtin/external is bash's separate `temporary_env` — NAME LOOKUP consults it
  (`get_variable_object` / `get_declared_variable_object` /
  `find_exported_instance` check the stack; `$VAR`, `declare -p VAR`,
  `${VAR@a}`, the command's own process env all see it) but whole-table
  ENUMERATIONS skip it (`set` / `export -p` / `declare -p` no-name scan
  `scope_stack`, which the separate stack is NOT part of). It is exported for
  the command yet is not a shell variable, so it does not inherit the shadowed
  var's attributes and vanishes on teardown; a plain body assignment write-
  throughs to the layer while `export`/`declare -g` write past it, and `unset`
  peels it to reveal the shell variable underneath. A function call instead uses
  a temp-env SCOPE (`set_temp_env_var`), which IS enumerated in the body (bash
  merges a function's prefix vars into its locals). `push_command_temp_env` /
  `pop_command_temp_env` / `set_command_temp_env_var` own the stack; `restore`
  pops it, `commit` (POSIX special builtin) promotes the bindings to real
  exported vars then pops.
- **Command-env overlay** (`state._env_overlay`, `apply_command_env` /
  `restore_command_env`): the SEED path only — a prefix over a dynamic special
  (`RANDOM=5 cmd` → literal `5`), an array-object append (`a+=z cmd` → element-0
  view), or a nameref-to-element records the LITERAL string that name
  contributes to the process env, composed on top of the exported vars (overlay
  WINS). Plain temp-env vars need no overlay — they materialize through the
  `variable_changed` observer + `find_exported_instance`. Teardown
  re-materializes each name from the (restored) variable / base.

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
