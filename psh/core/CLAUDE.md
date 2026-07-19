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
| `scope.py` | `ScopeManager`, `VariableScope` - the scope stack (flat list, `scope_stack[0]` global) |
| `variable_store.py` | `VariableStore` (`scope_manager.store`) - the single variable-WRITE transaction boundary (readonly/nameref/observer guards); see "Variable-mutation model" below |
| `variable_lookup.py` | `LookupStatus` (MISSING/PRESENT_UNSET/VALUE) + `VariableLookup` - the typed tri-state result of `ScopeManager.lookup()`, the single variable-READ authority (appraisal #20 H13; see "Scope Stack" below) |
| `getopts_state.py` | `GetoptsState` - typed `getopts` scan state (OPTIND tracking, restart detection) |
| `special_registry.py` | `SPECIAL_REGISTRY` + `SpecialParameterState` - the single declarative table + typed lifecycle state for computed specials (RANDOM/SECONDS/LINENO/...); see "Computed Special Parameters" below |
| `environment.py` | `is_environ_shell_name` - the one rule deciding which inherited env entries become shell variables vs stay opaque (appraisal H3) |
| `variables.py` | `Variable`, `VarAttributes`, `IndexedArray`, `AssociativeArray` |
| `option_registry.py` | `OPTION_REGISTRY` (single source of truth for all shell options) + `ShellOptions` (registry-backed, dict-compatible container; `ShellState.options`) |
| `options.py` | `OptionHandler` - option *behavior* helpers (nounset check, xtrace print) |
| `locale_service.py` | `LocaleService` (on `ShellState.locale`) - effective LC_CTYPE/LC_COLLATE from env at startup; the one home for collation (`collate_key`/`compare`), locale-gated case mapping (`upper`/`lower`/`toggle`), and POSIX character-class membership (`in_class`, `posix_class_ranges` — host libc `iswctype` via ctypes). Construction is PURE (campaign F2): the shell's service is `deferred=True`, libc application happens at activation under the coordinator's LOCALE lease (`ShellState._acquire_locale_lease`), and the process-active slot is written only by the activation glue (`set_process_active_locale`). See `docs/architecture/locale_service_design_2026-07-06.md` |
| `process_lease.py` | `ProcessLeaseCoordinator` (campaign F2) - the ONE gate for process-global ownership: one active shell owner per process, LIFO `ActivationLease` nesting (implicit on first execution via `ShellState.activate`), `ComponentKind` leases (LOCALE / SIGNALS / STD_FDS) restored LIFO at `Shell.close()`/`shutdown()`, competing live owners rejected before mutation, fork-reset safety, and the recursion-headroom raise at ownership grant. Static ratchet: `tests/unit/tooling/test_process_global_ratchet_f2.py`; invariants: `tests/unit/core/test_process_lease.py`, purity pin `tests/unit/core/test_construction_purity_f2.py` |
| `functions.py` | `FunctionManager` - shell function definitions |
| `exceptions.py` | `PshError` root + error classes, and control-flow signals (`LoopBreak`, etc.) |
| `internal_errors.py` | Expected-error taxonomy + `report_internal_defect` (strict-errors guard) |
| `trap_manager.py` | Signal trap handling. Unmanaged-signal installs lease the prior disposition; the first lease registers ONE `SIGNALS` component with the `ProcessLeaseCoordinator` (`_register_signal_lease`), so overlapping cross-shell leases on one signal are unrepresentable (continuation finding B) and restore order is coordinator-owned |
| `assignment_utils.py` | Shared assignment validation utilities |

## Core Patterns

### 1. ShellState as Central Container

All shell state goes through `ShellState`:

```python
class ShellState:
    def __init__(self):
        # Scope manager for variables
        self.scope_manager = ScopeManager()

        # Shell options: a registry-backed ShellOptions mapping (NOT a plain
        # dict). Defaults come from option_registry.py; CLI/debug flags are
        # passed as `overrides`. Reads/writes use the ['key']/.get() API but
        # an unregistered name or wrong value_type raises. See "Adding a New
        # Shell Option" below.
        self.options = ShellOptions(overrides={...})

        # Execution state — one cohesive delegate object; ShellState
        # exposes last_exit_code / last_bg_pid / pipestatus /
        # in_forked_child ... as delegating properties over it.
        self.execution = ExecutionState()

        # Environment (read from os.environ ONCE, at startup — see the
        # Environment Policy section)
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

### 3. Scope Stack

Function calls push a new scope. `ScopeManager`
(`scope.py#ScopeManager`) holds a **flat** `self.scope_stack` list, with
`scope_stack[0]` always the global scope — a `VariableScope` carries NO
parent pointer; lookups walk the stack from the top down. Each scope holds
`Variable` objects (not plain strings).

- `push_scope(name)` appends `VariableScope(name=name)` and returns it
  (`VariableScope.__init__` takes only `name` — there is no `parent`).
- `pop_scope()` removes the top scope on function exit (never the global).
- `lookup(name)` (`scope.py#ScopeManager.lookup`, `variable_lookup.py`) is THE
  tri-state read authority: it returns a `VariableLookup(MISSING |
  PRESENT_UNSET | VALUE, binding)`, following namerefs. A declared-unset local
  (tombstone / bare `local x` / declared-but-unset export) stops the lookup at
  PRESENT_UNSET — it never falls through to an outer instance or the
  environment (appraisal #20 H13). `get_variable(name, default)` is its string
  projection (VALUE → its value, else `default`), and `ShellState.get_variable`
  delegates with **no env fallback** (inherited env is imported as exported
  shell variables at startup; a fallback would resurrect an outer exported
  value under a `local` shadow). The parameter operators' set-ness
  (`operators.py#_param_is_set`) asks `lookup(name).is_set`.
- `get_variable_object(name)` returns the full `Variable`
  through the scope stack WITHOUT nameref deref (`UNSET` tombstones make the
  lookup return None).

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
`SetBuiltin.short_to_long`, the shopt name set (`SHOPT_OPTION_NAMES`), and the
`$-` string are all derived from it — do NOT re-add a parallel map.

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

- **Reads**: `lookup(name)` (the tri-state read authority — see below) follows
  the nameref chain to the final non-nameref `Variable`. A cyclic chain prints
  bash's "warning: NAME: circular name reference" (via `warn_nameref_cycle()`)
  and reads as unset.
- **Writes/unsets**: `resolve_nameref_name(name)` returns the final target
  *name*. A nameref with an empty target resolves to its own name (so
  `declare -n r; r=x` sets r's target rather than writing through). A
  cycle raises `NamerefCycleError` (rejecting the write, like bash).
- **Attribute changes** (`apply_attribute`/`remove_attribute`) also
  `resolve_nameref_name` to the target — `declare -n r=x; declare -i r` makes
  x integer, `readonly r`/`export r` mark x — EXCEPT the nameref attribute
  itself (`declare -n`/`declare +n`), which lands on the reference cell.
  A MISSING target gets a declared-unset attribute-carrying cell (the upvar
  idiom `declare -n ref=$1; declare -i ref`): declare/typeset/readonly create
  it in declare's target scope (LOCAL inside a function —
  `function_support.py#_declare_bare_name`), export creates it non-locally so
  it survives the function (`environment.py#_export_existing`). A CYCLIC
  chain under an attribute op warns TWICE and CONTINUES rc 0 (bash; unlike a
  value write, which rejects) — the catch lives in the
  `apply_attribute`/`remove_attribute` chokepoint and the two builtin
  pre-resolutions.

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
deep-cloned; process-local data (streams, terminal, arithmetic re-entrancy, the
`input_cursors` registry — a forked child inherits no userspace read buffer,
matching bash; campaign I1 — and the `reserved_script_fds` map, since a child
does not own the parent's lazy script reader; campaign I2) is reset; the locale
is shared. `$PPID`/`$$` stay stable across subshells; RANDOM
reseeds. Mode flags (`interactive`, `stdin_mode`, `emacs`) are recomputed
afterwards by `Shell._init_interactive`. Jobs are never copied. The Shell-level
half (copying function/alias managers — per-instance `Function` metadata so a
child's `readonly -f`/redefinition can't leak) lives in
`Shell._inherit_from_parent`. Completeness is guarded by
`tests/unit/core/test_state_clone_completeness.py` (a name drift-lock plus a
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
  `FunctionDefinitionError` (invalid/reserved/readonly function name), and
  `ReadError` (a `read`/`mapfile` option-VALUE error carrying bash's exit
  code). The lexer's `UnclosedQuoteError` also roots here, dual-inheriting
  `(PshError, SyntaxError)` so the load-bearing `except SyntaxError`
  line-continuation sites keep catching it — see its class docstring in
  `lexer/position.py#UnclosedQuoteError`.
- **Control-flow signals** (`LoopBreak`, `LoopContinue`, `FunctionReturn`)
  implement `break`/`continue`/`return` and deliberately do NOT derive
  from `PshError` — a blanket `except PshError` must never swallow a
  `return` statement.

### Expected-error taxonomy & `strict-errors` (`internal_errors.py`)

Every structurally identical last-resort guard — command dispatch, builtin
execution, control-flow/compound execution, function body, buffered-statement
source, the analysis-visitor modes, and trap-action bodies — delegates to one
helper, `report_internal_defect(state, exc, *, prefix, stream)` (grep for its
call sites rather than trusting a count here). It classifies the
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
  DEACTIVATES the name (it becomes an ordinary variable, bash). Every one of
  those interception points (plus the two read paths and `find_exported_instance`)
  consults `_local_shadows_special(name)`: a `local RANDOM` — or a
  function-prefix `RANDOM=5 f` (the temp-env scope is in the scan) — makes
  RANDOM an ordinary variable for that scope and any nested call (dynamic
  scoping), suspending the dynamic behaviour until the scope exits, while a
  global `RANDOM=5` still SEEDS. A READONLY special (overlay readonly)
  REFUSES a masking local outright (`create_local`'s special-readonly gate:
  bash `local: SECONDS: readonly variable`, rc 1, function continues, reads
  stay dynamic). The uniformity is drift-locked by
  `tests/unit/tooling/test_variable_truth_guard.py` (every `has_lifecycle` /
  `is_computed` gate must consult the mask).
- **Shell-view specials** (`lifecycle=False`): computed read that SHADOWS any
  stored variable; assignment/readonly/unset all take the ordinary path
  (already bash-correct, so no interception).

`UID`/`EUID`/`PPID` are NOT here — they are real readonly-integer variables
seeded at startup. When adding a computed special, add a `SpecialVarSpec` row
(and, for a `lifecycle` one, confirm the interception points cover it).

**No-arg enumeration** (`set` / `declare -p` with no name, both iterating
`all_variables_with_attributes`): only the two option-reflection specials
`SHELLOPTS`/`BASHOPTS` are injected (bash lists them with values; the pair is
`special_registry.OPTION_REFLECTION_SPECIALS`). Every other computed special —
the dynamic clock/counter family AND the shell-view `FUNCNAME`/`PIPESTATUS`/
`BASH_COMMAND` — is a DELIBERATE, documented divergence: it is listed only by
explicit name (`declare -p RANDOM`), because bash's no-arg rendering of the
dynamic ones is reference-state-dependent and internally inconsistent (see the
`OPTION_REFLECTION_SPECIALS` docstring and the #34 core-state-polish ledger).

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
  merges a function's prefix vars into its locals). That merge carries
  PROVENANCE (bash `att_tempvar`, psh `VarAttributes.TEMPVAR`): a `local x[=V]`
  in the PREFIXED invocation keeps it, and a value-less `local x` at any deeper
  call inherits value+export from the nearest provenance-carrying instance it
  shadows — copies do not carry it onward
  (`scope.py#ScopeManager._tempvar_inherit_source`; R2-B1 probe matrix).
  `push_command_temp_env` /
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

Exported variables reach `state.env` through an OBSERVER, never a direct
write (this is the invariant the Environment Policy section declares).
`ShellState.export_variable` (`state.py#ShellState.export_variable`) only
sets the EXPORT attribute — `scope_manager.set_variable(..., attributes=
VarAttributes.EXPORT, local=False, skip_temp_env=True)`. The scope manager
then fires `variable_changed` → `_sync_exported_variable` →
`_materialize_env_name`, the ONE place `state.env[name]` is written. No
production code pokes `state.env[...]` directly.

### Allexport Mode

When `set -a` is enabled, `ShellState.set_variable`
(`state.py#ShellState.set_variable`) adds the EXPORT attribute to each new
variable before delegating to the scope manager (a computed dynamic special
like `RANDOM` is exempt — bash leaves it unexported). The env entry then
materializes through the same `variable_changed` observer, so allexport
needs no separate `state.env` write.

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

2. **Export Sync**: Exported-variable writes materialize into `state.env`
   AUTOMATICALLY via the `variable_changed` observer
   (`_materialize_env_name`, the one writer). Never poke `state.env[...]`
   directly, and never write `os.environ` (read once at startup; children
   receive `state.env` explicitly).

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
