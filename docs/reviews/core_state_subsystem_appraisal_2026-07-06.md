# Core/State Subsystem Appraisal — 2026-07-06

## Scope

This is a fresh appraisal of the core/state subsystem, graded for:

- shell-state correctness and Bash/POSIX semantics;
- ownership, mutation, and lifecycle invariants;
- variable scope, attributes, arrays, and environment synchronization;
- child-shell and subshell isolation;
- option, trap, history, terminal, stream, and execution state;
- textbook-quality architecture and maintainability;
- efficiency and resource safety; and
- test quality and production readiness.

The review covered all modules under `psh/core/`, their principal integrations
with `psh/shell.py`, expansion, execution, builtins, and interaction, focused
tests, conformance coverage, static checks, focused coverage, and targeted
differential and in-process probes.

## Executive Judgment

The subsystem has strong semantic ambition, unusually detailed compatibility
commentary, and substantial focused and conformance testing. Its dynamic-scope
tombstone behavior, export synchronization, option-name registry, error/control-
flow distinction, and initial state decomposition are all sound foundations.

It nevertheless remains below the production and textbook-quality bar. The
central problem is that state invariants are described but not enforced by the
types and APIs:

- child-state adoption is not an exact independent clone;
- arrays and function metadata are shared across an in-process child boundary;
- mutable variable values permit callers to bypass readonly enforcement;
- computed special variables do not have persistent attribute or lifecycle
  semantics;
- in-process child traps leak process-global signal dispositions;
- the environment and variable store are competing writable authorities; and
- the option registry declares type information that its container does not
  enforce.

Several defects were directly reproduced:

- a variable unset in the parent can reappear in a `( )` child;
- `env unset 'a[0]'` mutates the parent array;
- `env readonly -f f` makes the parent function readonly;
- readonly array elements can be removed with `unset`;
- sparse negative array unsets use the wrong index;
- `readonly RANDOM` and `export RANDOM` do not persist their attributes;
- unsetting `EPOCHSECONDS`, `EPOCHREALTIME`, or `LINENO` does not deactivate
  their special behavior;
- `env trap ':' USR1` leaves the child handler installed in the parent process;
- `trap -p` cannot round-trip an action containing a single quote;
- `parser-config disable arrays` writes an unregistered option and fails; and
- changing explicit `getopts` arguments at the same `OPTIND` can raise
  `string index out of range`.

Overall grade: **C (5.5/10)**.

## Grades

| Dimension | Grade | Assessment |
| --- | --- | --- |
| Functional breadth | A- | The subsystem models a large portion of Bash state and special-variable behavior. |
| Correctness on tested paths | B+ | Focused core and selected conformance tests are green. |
| State isolation | D | Parent/child variable and function isolation is observably broken. |
| Mutation invariants | D+ | Public mutable values and attributes permit readonly and observer bypasses. |
| Architecture | C+ | Useful typed subobjects exist, but `ShellState` and `ScopeManager` remain semantic hubs. |
| Efficiency | B- | Common paths are reasonable, but sparse enumeration and repeated child initialization are avoidably expensive. |
| Maintainability | C | Complex mutation paths, `Any`, reverse dependencies, and informal copy policies raise change risk. |
| Testing | B | Test volume is strong, but the most important ownership and mutation invariants are missing. |
| Documentation | B | Commentary is extensive, but some claims are stronger than the implementation and parts of `CLAUDE.md` are stale. |
| Textbook quality | C | The design intent is good; authoritative ownership and unrepresentable invalid states are not yet achieved. |

## Critical Findings

### C1. Child-state adoption is not an exact independent clone

`ShellState.adopt()` constructs a complete fresh state first and then overlays
the parent:

```python
self.env = parent.env.copy()
for name, var in parent.scope_manager.global_scope.variables.items():
    self.scope_manager.global_scope.variables[name] = var.copy()
```

The fresh child's global scope is not cleared. A variable absent from the
parent can therefore survive from the child's initialization defaults or its
new `os.environ` import.

#### Reproduction: an unset variable reappears

```sh
bash --noprofile --norc -c \
  'unset HOME; (printf "HOME=<%s> flag=<%s>\n" "$HOME" "${HOME+set}")'
# HOME=<> flag=<>

python -m psh --norc -c \
  'unset HOME; (printf "HOME=<%s> flag=<%s>\n" "$HOME" "${HOME+set}")'
# HOME=</Users/pwilson> flag=<set>
```

The same defect affects seeded defaults such as `PS4`: unsetting it in the
parent allows the fresh child's `+ ` default to reappear.

#### Arrays are shallow-copied

`Variable.copy()` copies `value` by reference and even records the limitation:

```python
value=self.value,  # Note: arrays would need deep copy
```

Both indexed and associative arrays remain shared between parent and child.
The fork boundary hides this behind OS copy-on-write, but `Shell.for_subshell`
is also used by the `env` builtin's in-process child:

```sh
python -m psh --norc -c \
  'a=(x y); env unset "a[0]"; printf "<%s>\n" "${a[*]}"'
# <y>
```

The child operation has mutated the parent's array.

#### Function metadata is also shared

`FunctionManager.copy()` copies only the dictionary; each mutable `Function`
object is shared. The AST may legitimately be shared if it is immutable, but
the `readonly`, `exported`, `trace`, `redirects`, and source metadata must not
be.

```sh
python -m psh --norc -c \
  'f(){ :; }; env readonly -f f; f(){ echo ok; }; echo rc=$?'
# psh: f: readonly function
# rc=1
```

The `env` child was intended to isolate builtin side effects but changed the
parent function.

#### The adoption drift-lock is insufficient

`test_state_adopt_completeness.py` (since renamed
`test_state_clone_completeness.py`, r19-P2) verifies that each field name appears in the
source text of `adopt()`. This catches omission by name, but not:

- overlay instead of replacement;
- shallow aliases;
- wrong copy policy;
- omitted state inside subobjects;
- observer/hook desynchronization; or
- a field mentioned in a comment but not copied correctly.

For example, `VariableScope.copy()` omits `dash_snapshot`, while
`ExecutionState.copy_into()` still depends on a handwritten field list.

#### Recommendation

Replace construction-plus-overlay with an explicit factory:

```python
ShellState.clone_for_child(parent, context=ChildContext.SUBSHELL)
```

Each state component should own a typed clone operation with a documented
policy:

- immutable data: share;
- mutable inheritable data: clone;
- process-local data: reset;
- derived state: recompute through the authoritative hook; and
- external resources: acquire explicitly for the child context.

Add graph-independence tests that traverse mutable parent and child state and
assert that no unapproved mutable object identity is shared.

### C2. Variable and array invariants are not centrally enforced

`Variable.value` is public `Any`, and both array implementations expose
mutators. `ScopeManager.set_variable()` enforces readonly state for operations
that pass through it, but other subsystems mutate the container directly.

Examples include:

- `var.value.set(...)` in expansion;
- `var.value.unset(...)` in `unset`;
- direct `var.attributes` updates in builtins; and
- array builders that can receive an existing live container.

Readonly correctness therefore depends on every caller remembering a guard.
That has already failed:

```sh
bash --noprofile --norc -c \
  'a=(x y); readonly a; unset "a[0]"; echo "rc=$? <${a[*]}>"'
# error, rc=1, <x y>

python -m psh --norc -c \
  'a=(x y); readonly a; unset "a[0]"; echo "rc=$? <${a[*]}>"'
# rc=0, <y>
```

#### Negative subscript semantics are duplicated and inconsistent

Reads and writes use the sparse-aware formula based on
`highest_index + 1 + negative_index`. `unset` instead indexes into the list of
defined indices.

For an array containing indices 5 and 10, Bash maps `-2` to slot 9, so the
unset is a successful no-op. PSH selects the second-from-last defined index
and removes index 5:

```text
bash: rc=0 vals=<x|y> idx=<5 10>
psh:  rc=0 vals=<|y>  idx=<10>
```

#### Invalid states are representable

The current data model permits:

- both `ARRAY` and `ASSOC_ARRAY`;
- an array attribute with a scalar value;
- readonly variables containing externally mutable objects;
- `UNSET` with arbitrary values and attributes;
- a variable name different from its dictionary key; and
- direct removal or addition of protected attributes.

#### Recommendation

Create one authoritative `VariableStore` API:

```text
declare
assign
append
set_element
unset_element
unset
add_attributes
remove_attributes
```

Every operation must perform, in one transaction:

1. nameref resolution;
2. target-scope selection;
3. readonly validation;
4. subscript evaluation;
5. attribute transformation;
6. value replacement;
7. environment notification; and
8. PATH/other special notifications.

Array values should be immutable or copy-on-write values. Callers should
receive a read-only view, not the live mutable container. Use a validated
value union such as `ScalarValue`, `IndexedArrayValue`,
`AssociativeArrayValue`, and `UnsetValue`.

## High-Severity Findings

### H1. Computed special variables lack a coherent state machine

Special parameters are split between:

- `ShellState.get_special_variable()` for punctuation and positionals; and
- `ScopeManager._get_special_variable()` for named computed values.

`_ALL_COMPUTED_SPECIAL_VARS` contains only `SECONDS`, `RANDOM`, `BASHPID`, and
`SRANDOM`, despite its name and comment. It excludes at least:

- `EPOCHSECONDS`;
- `EPOCHREALTIME`;
- `LINENO`;
- `PIPESTATUS`;
- `BASH_COMMAND`; and
- `FUNCNAME`.

Computed reads return temporary `Variable` objects. Attribute operations look
for stored variables and therefore do not persist on most computed specials.

#### Confirmed failures

`readonly RANDOM` and `readonly SECONDS` report success but do not make the
names readonly. A following assignment succeeds.

`export RANDOM` and `export SECONDS` do not create environment values:

```text
bash: printenv RANDOM -> a value, rc=0
psh:  no value, rc=1
```

After unsetting `EPOCHSECONDS`, Bash exposes an ordinary unset name and a later
assignment stores the assigned value. PSH continues returning the live epoch.
`EPOCHREALTIME` and `LINENO` have the same missing deactivation path.

`SECONDS` uses `time.time()` for elapsed time. Wall-clock corrections can make
elapsed time jump or run backward; the elapsed baseline should use
`time.monotonic()`. Epoch variables should continue to use wall time.

#### Recommendation

Introduce a declarative `SpecialParameterRegistry`. Each entry should define:

- side-effect-free name inspection;
- read behavior;
- assignment behavior;
- unset/deactivation behavior;
- persistent attributes;
- export materialization;
- child inheritance policy; and
- whether reading has side effects.

Back it with a typed `SpecialParameterState`. Inject wall clock, monotonic
clock, and entropy interfaces to make semantics deterministic in tests.

### H2. Trap lifecycle leaks across in-process child shells

For unmanaged signals, `TrapManager` installs a Python process-global signal
handler. `Shell.close()` closes signal self-pipes but does not restore those
handlers. An in-process child can therefore leave a closure over its
`TrapManager` installed after the child is closed.

#### Reproduction

```sh
python -m psh --norc -c \
  "env trap ':' USR1; kill -USR1 \$\$; sleep 0.05; echo survived"
# survived
# rc=0
```

A process with the default `SIGUSR1` disposition terminates with
`128 + SIGUSR1`. The supposed isolated child has changed the parent's process
behavior and now swallows the signal by queueing it on an object that the
parent never services.

#### Trap listing does not quote actions correctly

```sh
trap "echo 'x'" INT
trap -p INT
```

Bash emits a reusable single-quoted representation:

```text
trap -- 'echo '\''x'\''' SIGINT
```

PSH emits invalid/non-equivalent input:

```text
trap -- 'echo 'x'' SIGINT
```

The repository already contains correct single-quote helpers; trap rendering
does not use them.

The pending trap queue also uses `list.pop(0)`, making a burst of queued traps
quadratic.

#### Recommendation

Add an explicit process-level `SignalDispositionLease`:

- snapshot the prior disposition;
- install the shell disposition;
- distinguish forked from in-process child policy;
- restore the prior disposition on close; and
- fail visibly if the operation cannot be installed in the current thread.

Move handlers, inherited/listing-only status, pending traps, reentrancy flags,
and exit-fired state into a cohesive `TrapState`. Use `collections.deque` and
the shared shell single-quote utility.

### H3. Environment and shell variables are competing writable authorities

`ShellState` keeps both:

- `env`, a public mutable dictionary; and
- scope variables carrying the `EXPORT` attribute.

Observers synchronize common variable operations, but many paths write
`shell.env` directly. `get_variable()` then falls back to `env`, making the
boundary even less explicit. Correctness depends on every caller maintaining
the two stores in the correct order and rolling both back on failure.

This contributes to:

- child adoption resurrecting values from `os.environ`;
- partial updates when a later variable operation fails;
- temporary command assignments needing complex snapshots;
- environment-only entries appearing as shell variables; and
- broad direct mutation throughout builtins and execution.

#### Invalid inherited names are incorrectly imported as shell variables

```sh
/usr/bin/env 'bad-name=x' bash --noprofile --norc -c \
  'printenv bad-name; export -p | grep bad-name; echo rc=$?'
# x
# rc=1

/usr/bin/env 'bad-name=x' python -m psh --norc -c \
  'printenv bad-name; export -p | grep bad-name; echo rc=$?'
# x
# declare -x bad-name="x"
# rc=0
```

Bash preserves the opaque environment entry but does not create an invalid
shell variable. PSH imports every entry into the scope manager.

#### Recommendation

Use the variable store as the single source for valid shell variables. Keep
opaque inherited environment entries, including invalid shell names, in a
separate immutable base map. Materialize an execution environment from:

```text
opaque inherited entries
+ currently exported shell variables
+ command-local environment overlay
```

Temporary commands should use overlays rather than mutating and rolling back
the shell environment.

### H4. The option registry is only partially authoritative

`OptionSpec` declares `value_type`, but `ShellOptions.__setitem__()` checks only
the name.

Confirmed:

```text
opts["errexit"] = "false"   # accepted and truthy
opts["parser-mode"] = True  # accepted
del opts["errexit"]         # accepted
```

Deletion can make typed accessors raise `KeyError`. The string-valued
`parser-mode` has no allowed-value validation and is not the state used by the
`parser-mode` builtin, which instead changes `posix` and `collect_errors`.

`parser-config` has a second feature map containing unregistered options:

```sh
python -m psh --norc -c 'parser-config disable arrays; echo rc=$?'
# psh: parser-config: "unknown shell option 'no_arrays' ..."
# rc=1
```

Options with behavioral side effects can also desynchronize. A child that
adopts `debug-scopes=True` retains `ScopeManager._debug=False` because the
dictionary update does not execute the property side effect.

#### Recommendation

- Enforce `OptionSpec.value_type`.
- Add an allowed-values validator for finite string options.
- Prohibit deletion of registry keys.
- Route all writes through a typed `set()` method with change hooks.
- Separate parser backend, language dialect, error collection policy, and
  grammar feature flags.
- Remove dead or phantom options.
- Add a meta-test proving that each public option has a consumer or is
  explicitly presentation-only.

## Architecture and Maintainability

### A1. `ScopeManager` is a semantic god object

At 993 lines it owns:

- dynamic scope and temporary environment layers;
- variable mutation and attribute transformation;
- nameref resolution;
- computed special parameters;
- exported-environment observers;
- PATH invalidation;
- line-number state;
- random and time state;
- diagnostic output; and
- a back-reference to `Shell` for arithmetic evaluation and array-element
  assignment through expansion.

`set_variable()` and `_get_special_variable()` both have cyclomatic complexity
19. `ScopeManager` imports upward into expansion and reaches through
`self._shell.expansion_manager`, making the core layer dependent on
orchestration details.

Split it into:

- `ScopeStack`;
- `VariableStore`;
- `SpecialParameterRegistry/State`;
- `VariableAttributeTransformer`;
- `EnvironmentMaterializer`; and
- explicit observer/event interfaces.

Inject an arithmetic-evaluator protocol rather than retaining the whole
`Shell`.

### A2. `ShellState` remains an oversized facade

`ShellState` is 741 lines. The extraction of `ExecutionState`, `HistoryState`,
`TerminalState`, and `StreamBindings` is useful, but the facade still mixes:

- startup policy;
- environment import;
- child inheritance;
- variable and option APIs;
- history policy;
- stream compatibility properties;
- special-parameter rendering;
- terminal capabilities;
- traps;
- getopts cursor state; and
- builtin-owned lazy state.

`directory_stack: Any` is particularly revealing: core state owns a field
whose type lives in builtins. Move directory state into an appropriate runtime
component or a neutral core type.

### A3. Typed decomposition has not reached state semantics

Several related state groups remain loose:

- `_getopts_charpos` and `_getopts_charpos_optind`;
- `function_stack` and `source_depth`;
- `trap_handlers` and `inherited_traps`;
- history strings and command numbering; and
- option values plus their side effects.

The getopts cursor is already insufficient. If one call processes `-ab` and a
second call supplies a different explicit argument list at the same `OPTIND`,
PSH resumes the old within-word offset:

```text
bash: second call -> option b, OPTIND=2
psh:  string index out of range, option remains a, OPTIND=1
```

Introduce a typed `GetoptsState` that records the argument source and current
argument identity as well as `OPTIND` and character offset.

`HistoryState` should store `HistoryEntry(event_id, text)` and a monotonic next
event ID. Raw list positions are not stable after trimming or removal.

### A4. Diagnostics bypass stream ownership

Scope debug output and circular-nameref warnings write directly to
`sys.stderr`, while other core code uses `state.stderr`. This breaks embedded
shell stream routing and makes diagnostics inconsistent.

Inject a diagnostics sink or route all user-visible output through shell
streams.

### A5. Some subobject invariants are incomplete

`TerminalState.detect()` does not clear `terminal_fd` when a second detection
finds that stdin is no longer a terminal:

```text
is_terminal=False, terminal_fd=0, supports_job_control=False
```

The invariant should be:

```text
not is_terminal => terminal_fd is None and not supports_job_control
```

`VariableScope.parent` is never used for lookup, is reset to `None` by copying,
and contradicts the actual stack-based hierarchy. Remove it or make it the
authoritative hierarchy rather than retaining dead structural state.

## Efficiency

### E1. Sparse array enumeration is proportional to the highest index

`IndexedArray` stores a sparse dictionary but `all_elements()` scans:

```python
for i in range(self._max_index + 1):
```

Measured with one stored element:

| Highest index | Approximate `all_elements()` time |
| ---: | ---: |
| 10,000 | 0.00018 s |
| 1,000,000 | 0.0188 s |
| 10,000,000 | 0.179 s |

The correct implementation should iterate sorted defined indices, making it
`O(n log n)` for `n` stored elements rather than `O(max_index)`. Shell input
can select very large indices, so the current implementation is also a
denial-of-service surface.

### E2. Child construction performs discarded initialization

Every `Shell.for_subshell()`:

1. copies `os.environ`;
2. imports it into a new scope;
3. seeds defaults and platform variables;
4. creates fresh state components; and then
5. overlays the parent.

Apart from causing the resurrection bug, this performs work that is
immediately discarded. A child clone factory is both simpler and more
efficient.

### E3. Trap queue removal is quadratic

`pending_traps.pop(0)` shifts the list for every trap. Use `deque.popleft()`.

Normal dynamic-scope lookup is linear in call depth, which is acceptable for
the current design. It should not be optimized before the ownership and
correctness work.

## Testing Appraisal

### Validation completed

Focused core, computed-special, LINENO, and variable-assignment run:

```text
python -m pytest \
  tests/unit/core \
  tests/conformance/bash/test_computed_special_vars_conformance.py \
  tests/conformance/bash/test_lineno_conformance.py \
  tests/integration/variables/test_variable_assignment.py -q

396 passed in 14.33s
```

Focused core coverage:

```text
python -m pytest tests/unit/core \
  --cov=psh.core --cov-report=term-missing -q

324 passed in 9.30s
TOTAL: 76%
```

Notable focused unit coverage:

| Module | Coverage |
| --- | ---: |
| `execution_state.py` | 100% |
| `history_state.py` | 100% |
| `stream_bindings.py` | 100% |
| `option_registry.py` | 93% |
| `state.py` | 84% |
| `variables.py` | 83% |
| `terminal_state.py` | 76% |
| `scope.py` | 73% |
| `functions.py` | 70% |
| `trap_manager.py` | 70% |
| `command_hash.py` | 58% |
| `internal_errors.py` | 56% |
| `options.py` | 51% |
| `assignment_utils.py` | 47% |

Static checks:

```text
ruff check psh/core tests/unit/core
# All checks passed

python -m mypy psh/core
# Success: no issues found
```

Stricter checks expose the remaining quality gap:

```text
python -m mypy --strict psh/core
# 69 errors in 9 files

ruff check --select C901,PLR0911,PLR0912,PLR0915 psh/core
# 7 complexity findings
```

The repository-wide `python run_tests.py --quick` run was stopped while still
in its long-running first phase and produced no final result. Its orphaned
pytest process group was terminated. No source files were modified by this
review.

### Missing regression categories

Add tests for:

1. Exact child keysets: a variable absent from the parent is absent from the
   child.
2. Parent/child independence for indexed arrays, associative arrays, function
   attributes, redirects, scope snapshots, history, traps, and options.
3. In-process `env` isolation for every mutable state category.
4. Readonly enforcement through every array mutation route.
5. One differential negative-subscript matrix shared by read, write, append,
   arithmetic mutation, and unset.
6. Readonly/export/unset/reassignment behavior for every computed special.
7. Signal-disposition restoration after nested/in-process shells.
8. Round-trip `trap -p` actions containing quotes, backslashes, newlines, and
   expansion syntax.
9. Option type/domain/deletion validation.
10. Every `parser-config` feature operation.
11. Getopts argument-source changes and cursor reset.
12. Sparse arrays with very large highest indices.
13. Environment entries that are not valid shell identifiers.
14. Declarative copy-policy completeness for every state subobject.

Property-based state-machine tests would be especially valuable for variable
operations. Generate sequences of declaration, assignment, local scope,
nameref, export, readonly, array mutation, unset, child clone, and scope pop;
assert invariants after every transition and compare bounded cases with Bash.

## Recommended Remediation Plan

### Phase 1: Establish ownership and isolation

1. Add the failing child-isolation regressions.
2. Implement exact `ShellState.clone_for_child()`.
3. Clone mutable array and function metadata.
4. Replace the textual adoption drift-lock with declarative copy policies and
   graph-independence tests.
5. Fix in-process `env` isolation before treating the child mechanism as safe.

Exit criterion: no child operation changes an unapproved parent object or
process resource, and an absent parent variable never reappears.

### Phase 2: Make variable mutation authoritative

1. Introduce `VariableStore`.
2. Move all scalar, array, nameref, attribute, and unset mutations behind it.
3. Make array values immutable or copy-on-write.
4. Centralize negative-index resolution.
5. Remove external direct writes to `.value` and `.attributes`.
6. Add an architectural test banning those writes outside the store.

Exit criterion: readonly enforcement, observers, and index semantics cannot be
bypassed by callers.

### Phase 3: Repair special, environment, and trap state

1. Add the special-parameter registry and typed state.
2. Use a monotonic clock for elapsed `SECONDS`.
3. Separate opaque inherited environment entries from valid shell variables.
4. Materialize child environments from exported state plus overlays.
5. Add signal-disposition leases and trap-state ownership.
6. Reuse the shared shell quoting implementation.

Exit criterion: every special parameter has explicit read/write/unset/export/
inheritance semantics, and in-process children restore all process-global
state.

### Phase 4: Complete the typed decomposition

1. Make `ShellOptions` enforce type, domain, and hooks.
2. Reconcile or remove parser-mode and parser-feature state.
3. Extract `GetoptsState`, `TrapState`, stable history entries, and function
   context.
4. Split `ScopeManager` and remove its `Shell` back-reference.
5. Remove the core-to-builtins `directory_stack: Any` dependency.
6. Route diagnostics through an injected stream/sink.

Exit criterion: core modules depend on narrow protocols rather than the shell
or expansion orchestration.

### Phase 5: Efficiency, typing, and documentation

1. Make sparse enumeration proportional to stored elements.
2. Replace the trap list with a deque.
3. Eliminate discarded fresh initialization during child cloning.
4. Bring `psh/core` to strict mypy.
5. Update `psh/core/CLAUDE.md` to reflect the actual registry, state
   decomposition, environment model, and copy contracts.

Exit criterion: strict typing passes, complexity hotspots have been split, and
performance tests cover adversarial sparse state.

## Final Assessment

The subsystem is not weak because it lacks semantic work; it is weak because
the semantic work is encoded in comments and distributed caller discipline
rather than authoritative types and mutation boundaries. The best parts of the
current implementation—tombstones, option-name registration, execution-state
extraction, export observers, and the error taxonomy—show the correct
direction.

The next improvement should not be another isolated Bash edge-case patch. The
highest return comes from making child cloning exact, making variable mutation
central, and making process-global trap state explicitly owned. Once those
invariants are structural, the existing conformance effort will become much
more durable and the subsystem can move from a C-grade implementation toward a
textbook-quality design.
