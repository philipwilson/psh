# Slot 4B.1 — Immutable variable reads (MEDIUM-5) — first 4B slot

**Charter:** integrator plan §6 Wave 4 bullet 4B.1 + sequence §9 Package 4B
item 1: *"Make `VariableLookup` immutable, eliminate the mutable missing
singleton, and return an immutable binding snapshot or capability-free
`VariableView`. All writes continue through `VariableStore` by
identifier."* Exit criterion (sequence §9): *"Variable lookup values and
bindings reject mutation; readonly, nameref, observer, and
exported-environment coherence remain intact"* — pinned by MUTATION
ATTEMPTS (plan: "readonly/nameref/observer/export coherence pinned by
mutation attempts").

**Base:** 4f2facaf (v0.769.0). Branch `fix/remediation-4b-1`, worktree
`/Users/pwilson/src/psh-r4b-1`.
**Base figures (you RE-DERIVE in your first gate run):** attestation
18840ac9-committed (gated a4abd952): 23,546 passed / 1,618 skipped / 10
xfail; ruff clean; mypy 275 files; compare-bash 3,042/26 EXACT.

## The defect (MEDIUM-5), integrator-probed at 4f2facaf

r22 §MEDIUM-5 (`variable_lookup.py:55-72,97-110`, `scope.py:356-395`),
LEDGER row CONFIRMED both parts. **Measured
(`tmp/w4b1-dispatch-probes/probe_medium5_mutable_lookup.py`, subprocess
at base, all three legs reproduce):**

1. **`_MISSING` poisoning**: `lookup('unset_a')` returns the SHARED
   module singleton; setting `status=VALUE, value='POISON'` on it makes a
   DIFFERENT unset name read `VALUE 'POISON'` and fires end-to-end:
   `${SOME_OTHER_UNSET+FIRED}` expands to `FIRED`. Every future miss, any
   shell in-process, is poisoned.
2. **Readonly bypass**: `readonly RO=original` → normal write path
   refuses (rc 1, "readonly variable") but
   `lookup('RO').binding.value = 'hacked'` succeeds silently and the
   shell then reads `<hacked-past-readonly>`. No `ReadonlyVariableError`,
   no store transaction.
3. **Observer/export desync**: `export EX=one` →
   `lookup('EX').binding.value = 'two'` → shell reads `two`,
   `state.env` still `one` (the `variable_changed` →
   `_materialize_env_name` observer never fired; children see the stale
   value).

Nameref is the same class: `lookup()` follows the chain to the FINAL
cell (`_resolve_read`), so a binding write mutates the TARGET without
any of `resolve_nameref_name`'s write guards.

## Integrator recon facts (verify, then lean on)

- **The non-frozen design is a DOCUMENTED deliberate perf ruling.** The
  `variable_lookup.py` module docstring: plain `__slots__` because
  "``lookup()`` sits on the shell's hottest read path and freezing
  roughly triples construction cost (``object.__setattr__`` per field —
  the same measurement that drove W1's non-frozen ``FieldRun`` ruling)";
  discipline = ALLOCATE-FRESH-NEVER-MUTATE, `__slots__` guarded by
  `tests/unit/core/test_variable_lookup.py`. **This slot overturns that
  ruling BY CHARTER — but with MEASUREMENT, not argument.** Whatever
  representation lands, you re-measure the construction-cost claim at
  base and at tip (micro-benchmark of the lookup path + at least one
  macro observation, e.g. gate wall-time or a variable-heavy script),
  and the recorded delta goes in the ledger. If the measured cost of the
  chosen design is genuinely pathological, that is a STOP-AND-PROPOSE
  with numbers, not a silent design retreat.
- **Consumer census at base (re-derive; mine was grep-level):**
  `ScopeManager.lookup()` has ONE production call site —
  `expansion/operators.py:207` `_param_is_set` → reads `.is_set` only.
  `.binding` is consumed by NO production code; only
  `tests/unit/core/test_variable_lookup.py` (153 lines) reads it. The
  docstring's claimed consumers (`${x@a}`, `declare -p`) actually use
  `get_variable_object`/`get_declared_variable_object` directly. So
  r22's "omit the binding where no production consumer needs it" option
  is LIVE. Your census must also cover dynamic access
  (`getattr`/`__slots__` reflection), tests/, and tools/.
- **`_MISSING` is module-private and constructed once**
  (`variable_lookup.py:110`); `missing()` is the only reader. A FROZEN
  shared singleton (like `True`/`None`) plausibly satisfies "eliminate
  the mutable missing singleton" while keeping misses allocation-free —
  ruling (c) decides the reading; don't assume.
- **The `Variable` cell itself stays MUTABLE.** It is the live
  store-managed cell; freezing it is 4B-out-of-scope ocean-boiling. The
  boundary being fixed is what the READ AUTHORITY RETURNS. Sibling
  precedent: 3.2 (MEDIUM-6) froze pattern nodes with
  `@dataclass(frozen=True, eq=False, slots=True)` and RULED the threat
  model as HONEST-CALLER ACCIDENT — `object.__setattr__`/module
  rebinding declared out of scope, pins as raise-assertions. Read its
  LEDGER row before proposing yours.

## Phase A must settle (probe, don't argue)

1. **Representation design + measured cost.** Candidate space at
   minimum: frozen dataclass w/ slots (3.2 precedent), `NamedTuple`
   (tuple-fast construction, immutable, but adds iteration/indexing
   surface), `__slots__` + raising `__setattr__` with
   `object.__setattr__` in `__init__` (cost moves to construction),
   properties over private slots. Measure construction on the hot path
   for each candidate you take seriously; the docstring's "roughly
   triples" claim gets re-measured, not quoted. Decide and justify with
   numbers in the Phase A table.
2. **Binding policy (ruling slot (b)).** Omit `.binding` entirely
   (census says nothing production needs it — but then `${x@a}`/
   `declare -p` future needs re-do lookups) vs immutable SNAPSHOT
   (value/attributes copied at lookup — specify array-value semantics:
   arrays are mutable objects; a snapshot that aliases the live
   `IndexedArray` is not a snapshot) vs capability-free live VIEW
   (read-only accessors over the live cell — specify aliasing: a later
   legitimate store write SHOWS THROUGH; that must be documented
   behavior, not an accident). Whichever lands: no write capability, and
   every write remains `VariableStore` by identifier.
3. **Threat model (ruling slot (c)).** Propose the clause 3.2-style:
   what the pins PROVE (honest-caller accident: plain attribute
   assignment raises) vs what is declared out of scope
   (`object.__setattr__`, module rebinding). Plus the `_MISSING`
   reading: frozen-singleton-kept vs fresh-per-miss, with the perf
   figure for each.
4. **Coherence matrix (the exit criterion's four authorities).** For
   readonly / nameref / observer / export: the mutation ATTEMPT cell
   (raises at the new representation) and the coherence cell (the
   authority's guarantee still holds through the legitimate path).
   Nameref: binding (if kept) is the FINAL deref'd cell — attempted
   mutation must not touch the target; observer: no env write without
   `variable_changed`; export: `state.env` and shell reads agree after
   any legitimate sequence your cells drive.
5. **Scope boundary statement.** `get_variable_object` /
   `get_declared_variable_object` / `all_variables_with_attributes` and
   the store/scope internals deliberately return live `Variable` cells —
   that is the WRITE ENGINE's own surface and NOT this slot. State the
   boundary in the Phase A table (which returns are the sanctioned
   mutable internals, which is the public read contract being frozen) so
   the fence is drawn from evidence, not vibes.
6. **Tri-state semantics are FROZEN.** MISSING/PRESENT_UNSET/VALUE
   classification, H13 tombstone no-fallthrough, nameref-cycle
   reads-as-missing, `is_set`/`is_present` meanings, `get_variable`
   projection — all must-hold. This slot changes the CONTAINER, never
   the classification. Any classification delta observed = STOP.

## Pins YOU create

Red-on-base: the three probe families as raise-assertions (poisoning:
mutating a miss result raises AND a subsequent different-name miss is
clean; readonly-bypass: the binding surface rejects mutation; desync:
no path from a lookup result to a stale `state.env`), per-field ×
per-surface mutation attempts (status/value/binding on fresh and
singleton instances). Must-hold: the existing
`test_variable_lookup.py` tri-state suite (representation details may
move per ruling — semantics rows never), `_param_is_set` behavior,
H13/tombstone rows, write-ban invariant
(`test_variable_store_write_ban.py`), slots-closed guard (or its
successor under the new representation). M8 mutation locks for the new
guard arms (each rejection surface = its own kill reason). Composition
cells (lesson 3): mutation-attempt × nameref chain (attempt on the
deref'd binding, target unharmed); mutation-attempt × readonly ×
export (refused write leaves env coherent); poisoning-attempt ×
two-sequential-shells in one process (4A.1's multi-shell precedent);
frozen-lookup × computed-special read (lookup of an active dynamic
special returns a frozen result too — check how `lookup()` composes
with the special registry before assuming).

## Must-NOT-flip

- Tri-state classification: every H13/tombstone/nameref-cycle row,
  PRESENT_UNSET-stops-the-walk, no env fallback in `get_variable`.
- `${x+w}`/`${x-w}` operator set-ness (`operators.py#_param_is_set`).
- The write engine: `VariableStore` transaction semantics, readonly/
  nameref/observer guards, `_materialize_env_name` as the ONE env
  writer, the write-ban test.
- Shell-observable behavior ANYWHERE: this is an internal-integrity
  slot; compare-bash stays 3,042/26 EXACT and conformance counts hold.
  A shell-observable behavior delta is a FINDING to report (or
  stop-and-propose), never a silent flip.
- `Variable`/`IndexedArray`/`AssociativeArray` mutability (live cells;
  the store's own surface).
- 4A.1/4A.2 settled surfaces (lease suites, shutdown phases) — not
  plausibly touched, but the fence stands.

## FENCES (stop-and-report BEFORE touching)

- `variable_store.py` / `scope.py` WRITE paths (`set_variable`,
  `create_local`, attribute ops, unset, temp-env stack): this slot
  changes the READ RETURN TYPE; `lookup`/`_resolve_read` may be edited
  for the representation, the write engine only by stop-and-propose.
- `executor/array.py` Phase-4 alias-mutation gap (documented in
  core/CLAUDE.md §write-ban): REPORT-ONLY. It is the write-ban's known
  gap, not this slot's.
- `get_variable_object`-family returns (live cells): boundary stated in
  Phase A, not "fixed".
- 4B.2/4B.3/4B.4 subjects (input decoding, history, InputCursor);
  D-4A.1-s and D-4A.2-s successor rows and all D-3.x: MUST-NOT-ABSORB.
- `psh/protocols/__init__.py` mentions the lookup contract — keep any
  protocol text in sync if the type changes (doc sweep), but protocol
  WIDENING is stop-and-propose.

## Slot-specific test hygiene

- Mutation-attempt pins on the SHARED singleton must leave it clean for
  sibling tests (attempt-raises means no actual mutation lands — but
  prove it: a follow-up assertion that a fresh miss is unpoisoned
  belongs IN the pin). Never commit a test that mutates a live shared
  singleton and restores by hand — under xdist that is a race.
- Perf measurements: steady-state, pinned methodology recorded in the
  instrument (interpreter, N, variance), run at base AND tip from the
  same harness. No perf numbers pasted from memory — SHA
  paste-from-instrument applies to benchmarks too.
- Fresh-checkout portability is a standing verification leg: every
  scratch dir created by the test; assume a no-`tmp/` checkout.
- In-process shells in pins: 4A.1's coordinator-clean fixtures are your
  precedent; `close()` every shell you construct.

## Pre-declared ruling slots

- **(a)** Phase A disposition table + representation design with
  measured construction-cost figures (GO gate for Phase B).
- **(b)** Binding policy: omit vs immutable snapshot vs capability-free
  view, with aliasing semantics specified.
- **(c)** Threat-model clause + `_MISSING` reading (frozen singleton vs
  fresh-per-miss), each with its perf figure.

## Rules

The FULL binding rule set is `docs/reviews/evidence/
boundary_remediation_2026-07/4a.1-rescue/brief.md` §Rules (in THIS
worktree at that path) — binding verbatim: never-touch list, dead-drop +
ACK, mechanical tip rule, ledger freeze, per-hunk staging, SHA
paste-from-instrument, pre-registration + GO-binding citation, RN-Cdoc,
CERT-ROW-BEFORE-CLAIM, NAME-VS-BODY (your named siblings:
`test_variable_lookup.py`, `test_variable_store_write_ban.py`,
`test_scope_tombstones.py` — read them first), instrument discipline,
the 13 D-3.4 lessons + D-3.5 instrument-mirror + 3.x sets, axis
quantification (add: **MUTATION SURFACE × AUTHORITY GUARD** — reason
field-on-fresh / field-on-singleton / binding-value / binding-attributes
/ view-accessor × readonly / nameref / observer / export / tri-state),
discharge audit + bounced-rows replay, gate rules (ONE heavy run
machine-wide, unpiped pgrep, foreground, NEVER shell-`&`, NEVER
`run_tests.py --compare-bash`), oracle rules (PATH bash 5.2.26, never
/bin/bash, explicit argv), project tmp/ only, peer-escalation/
permission-laundering wrapper. PLUS the D-4A.1 additions: red-on-base
counts re-derived at the declared tip, never carried; "all X except Y"
claims stated as measured splits; scratch dirs created by tests;
verifier/probe cleanup never glob-deletes outside its own mktemp
scratch. PLUS the 4A.2 lessons now binding: vacuous cells that cannot
discriminate a rule get committed as LABELLED CONTROLS, never as proof;
claim boundaries stated BEFORE the verdict (a cell proves exactly what
it varies); when your battery certifies parity on the slot's own
headline surface, treat that cell as hostile and re-derive it
adversarially.

Done = Phase A table + three rulings + frozen lookup landed with the
three probe families flipped red→green + per-field/per-surface mutation
pins + coherence matrix green + M8 + composition cells + must-not-flip
green + perf figures recorded base-vs-tip + doc sweep
(`variable_lookup.py` module docstring rewritten for the new ruling —
it currently TEACHES the non-frozen design; `core/CLAUDE.md` scope/
lookup prose; `protocols/__init__.py` consistency — pointers verified)
+ green gate + compare-bash EXACT + ruff + mypy + discharge audit +
complete ledger → completion report with declared final tip + frozen
ledger.
