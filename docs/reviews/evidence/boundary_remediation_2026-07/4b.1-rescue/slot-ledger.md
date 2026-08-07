# SLOT LEDGER — 4B.1 immutable variable reads (MEDIUM-5)

Base: `4f2facaf0eede0dacf926e6718a2c348c3d3ce82` (v0.769.0).
Branch `fix/remediation-4b-1`, worktree `/Users/pwilson/src/psh-r4b-1`.
Interpreter (all instruments): CPython 3.14.2 (v3.14.2:df793163d58, Dec 5 2025) [Clang 16.0.0].
Bash oracle: `/opt/homebrew/bin/bash` GNU bash 5.2.26(1)-release (aarch64-apple-darwin23.2.0).

Every row below carries an instrument-file anchor under `tmp/4b1-instruments/`
and the SHA the instrument ran at. Counts are DERIVED by script, never
hand-tallied. No figure in this file is pasted from memory.

---

## §1 Phase A plan (written 2026-08-07, BEFORE execution — provenance)

### §1.1 Probe list (each becomes an instrument file)

| # | Instrument | Question it answers | Substrate |
|---|-----------|---------------------|-----------|
| P1 | `probe_p1_medium5_repro.py` | Do the three MEDIUM-5 legs reproduce at MY base tip? (`_MISSING` poisoning end-to-end; readonly bypass; observer/export desync) + nameref 4th leg | subprocess, real `Shell` + `ScopeManager` |
| P2 | `probe_p2_census.py` | Consumer census by AST (NOT grep — D-3.5 different-method rule): every attribute read on a `lookup()` result across `psh/`, `tests/`, `tools/`; every `VariableLookup` construction; dynamic access (`getattr`, `__slots__` reflection, `copy`/`pickle`) | AST walk of the tree |
| P3 | `bench_p3_construction.py` | MEASURED construction cost per candidate representation (the docstring's "roughly triples" claim re-measured, not quoted) | `timeit`, steady state |
| P4 | `bench_p4_lookup_path.py` | End-to-end `ScopeManager.lookup()` cost at base vs each candidate; and `get_variable` (which builds NO lookup) as the contrast arm | `timeit`, steady state |
| P5 | `probe_p5_construction_frequency.py` | MACRO: how many `VariableLookup` instances a real workload actually builds (variable-heavy scripts, `${x+w}`-heavy scripts, and a suite subset). Decides whether "hottest read path" is TRUE at base | counting instrumentation on a real shell |
| P6 | `probe_p6_coherence_matrix.py` | The four authorities (readonly / nameref / observer / export) × mutation-attempt cell and legitimate-path coherence cell | in-process `ScopeManager` + real `Shell` |
| P7 | `probe_p7_specials_composition.py` | How `lookup()` composes with the dynamic-special registry (RANDOM/SECONDS/LINENO...): does a special read produce a `VariableLookup` with a live binding? | in-process |
| P8 | `probe_p8_scope_boundary.py` | Which `ScopeManager`/`VariableStore` returns hand out LIVE `Variable` cells (the sanctioned write-engine surface) vs the public read contract being frozen | AST + runtime identity check |
| P9 | `probe_p9_array_aliasing.py` | If a binding SNAPSHOT is ruled: does a scalar-copy snapshot still alias a live `IndexedArray`/`AssociativeArray`? (a snapshot that aliases is not a snapshot) | in-process identity/mutation |

### §1.2 Census method

Two independent methods, per the D-3.5 different-method rule:
- **Method A (already run, grep):** recorded in §2.1 below as the FIRST
  derivation. Cross-check only.
- **Method B (authoritative, P2):** `ast` walk over every `.py` in `psh/`,
  `tests/`, `tools/`. Resolves (i) call sites of `*.lookup(`, (ii) attribute
  reads on the returned object where it is bound to a local, (iii) every
  `VariableLookup` / `LookupStatus` name reference, (iv) dynamic-access
  patterns (`getattr`/`setattr`/`hasattr` with a string literal matching a
  field, `__slots__` reflection, `copy`/`deepcopy`/`pickle`).
  Counts DERIVED from the AST result, printed by the instrument.

### §1.3 Benchmark methodology (pinned BEFORE measuring)

- Interpreter: CPython 3.14.2 (recorded above); no `-O`; default GC on.
- Harness: `timeit.Timer.repeat(repeat=R, number=N)`; **R=11, N=200_000** for
  bare construction (P3), **R=11, N=100_000** for the `lookup()` path (P4).
- Statistic reported: **min, median, and the min-of-repeats spread**
  (min is the standard timeit statistic for construction cost; median +
  spread reported so variance is visible, per the brief's "variance recorded").
- Each candidate measured in the SAME process, interleaved round-robin across
  repeats, so drift/thermal effects hit all candidates alike.
- Run at a DETACHED checkout of the declared SHA for any certification row
  (B71, extended to devs by 3.2's fault) — never from inside a live worktree.
  Phase A exploratory figures are labelled EXPLORATORY and are re-measured at
  the declared tip before any certification row is written.
- Macro arm (P5 + gate wall-time): construction COUNT during a real workload
  plus a variable-heavy script wall-time, base vs tip, same harness both ends.

### §1.4 Pre-registration SKETCH (D1 stage — NOT the binding block)

The binding pre-registration goes in §5 before any heavy run, with
red-on-base re-derived at my declared tip (never carried). Sketch:

- New pin file `tests/unit/core/test_variable_lookup_immutability.py`:
  expected **red-on-base** — the three MEDIUM-5 probe families as
  raise-assertions, plus per-field × per-surface mutation attempts
  (`status`/`value`/`binding` × fresh-VALUE / fresh-PRESENT_UNSET /
  MISSING-singleton), plus the binding-surface rejection cells, plus the
  composition cells (nameref-deref target unharmed; readonly × export env
  coherence; two-sequential-shells poisoning; special-read frozen result).
  Estimated 25–40 cells; EXACT counts and the measured red/green split
  pre-registered in §5 before the first heavy run.
- Must-hold (green at base AND tip): existing `test_variable_lookup.py`
  tri-state rows, `test_variable_store_write_ban.py`,
  `test_scope_tombstones.py`, `test_dynamic_special_masking.py`,
  `tests/conformance/bash/test_variable_truth_conformance.py`.
- Expected suite delta: **+N passed, 0 failed** where N = the new pin count
  (plus any representation-detail row edited in `test_variable_lookup.py`
  under ruling (a) — declared as a pin change, red-on-base verified).
- compare-bash: **3,042/26 EXACT, unchanged** (internal-integrity slot; any
  delta is a STOP).
- ruff clean; mypy 275 files (re-derived, not carried).

---

## §2 Phase A findings

(filled by execution; each row anchored to its instrument file + SHA)

### §2.1 Census — method A (grep, cross-check only)

Run at `4f2facaf`, `grep -rn 'VariableLookup\|LookupStatus' --include='*.py' psh tests tools`
and `grep -rn '\.lookup(' --include='*.py' psh tests tools`:

- `ScopeManager.lookup()` production call sites: **1** —
  `psh/expansion/operators.py:207` (`_param_is_set`), reads `.is_set` only.
- `.binding` reads anywhere: **`tests/unit/core/test_variable_lookup.py` only**
  (lines 27, 36, 48) — **zero production consumers**.
- `_MISSING`: module-private, **2** references total, both in
  `psh/core/variable_lookup.py` (:99 reader in `missing()`, :110 construction).
- No `getattr`/`setattr`/`hasattr` dynamic access to lookup fields anywhere in
  `psh/core` or `psh/expansion` (method B re-derives tree-wide).

Method B (P2, authoritative) supersedes these numbers on execution.

### §2.2 Census — method B (AST, AUTHORITATIVE)

Instrument `tmp/4b1-instruments/probe_p2_census.py`, output
`out_p2_census.txt`, SHA `4f2facaf`. 1,095 `.py` files parsed. All counts
derived by the instrument.

| Fact | Derived value |
|------|---------------|
| `.lookup(` call sites, all trees | 15 → **13** scope-manager family, 2 unrelated hash-table (`hash_builtin.py:127`, `command_resolver.py:287`) |
| **PRODUCTION** scope-manager `lookup()` call sites | **1** — `psh/expansion/operators.py:207` (`_param_is_set`) |
| test/tool scope-manager `lookup()` call sites | 12 (11 in `test_variable_lookup.py`, 1 in `test_dynamic_special_masking.py:90`) |
| attribute reads on a lookup result | 29 total |
| …**PRODUCTION** by field | `{'is_set': 1}` — **`.is_set` is the ONLY field production reads** |
| …test/tool by field | `{'binding': 5, 'is_present': 2, 'is_set': 5, 'status': 9, 'value': 7}` |
| **`.binding` readers in PRODUCTION** | **0** |
| `.binding` readers in tests | 5 (all `test_variable_lookup.py`, lines 27×2, 36, 48×2) |
| `_MISSING` references | **2**, both in `variable_lookup.py` (:99 reader, :110 construction) — module-private |
| dynamic access (`getattr`/`setattr`/`hasattr` with a literal field name) | 4 candidates, **all 4 manually confirmed FALSE POSITIVES** on unrelated objects: a `Variable` cell (`builtins/environment.py:706`), lexer Tokens (×2), an AST node (`tests/harness/gen_census.py:58`). **Real dynamic access to lookup fields: 0** |

Method A (grep) and Method B (AST) **agree** on every overlapping number.
The docstring's claimed `.binding` consumers (`${x@a}`, `declare -p`)
verified NOT to use it: they call `get_variable_object` /
`get_declared_variable_object` directly.

### §2.3 P1 — MEDIUM-5 reproduces at my base (4 legs, 4/4)

Instrument `probe_p1_medium5_repro.py`, output `out_p1_medium5_repro.txt`,
SHA `4f2facaf`. Each leg in its own subprocess; discriminator printed
(`psh from: /Users/pwilson/src/psh-r4b-1/psh/__init__.py`) after the FIRST
run tripped it — the editable install had resolved `import psh` to the MAIN
checkout, fixed with `PYTHONPATH`. The discriminator earning its keep is
itself recorded here.

| Leg | Verbatim result | Verdict |
|-----|-----------------|---------|
| L1 `_MISSING` poisoning | `lookup('unset_a')` is the shared singleton; plain assignment SUCCEEDED; `lookup('SOME_OTHER_UNSET')` → `VALUE 'POISON'`, `is_set=True`; live shell `echo "${SOME_UNSET_NAME+FIRED}"` printed `FIRED` rc=0 | REPRODUCES |
| L2 readonly bypass | normal path rc=1 + `psh: line 1: RO: readonly variable`, value stays `'original'`; `lookup('RO').binding.value='hacked'` SUCCEEDED; shell then reads `'hacked'` | REPRODUCES |
| L3 observer/export desync | `export EX=one` → binding write → shell reads `'two'`, `state.env['EX']` still `'one'` | REPRODUCES |
| L4 nameref target mutation (my addition) | `lookup('ref').binding.name == 'target'` (deref'd to the TARGET); binding write → `target` reads `'clobbered'` | REPRODUCES |

### §2.4 P6 — coherence matrix (MUTATION SURFACE × AUTHORITY GUARD)

Instrument `probe_p6_coherence_matrix.py`, output
`out_p6_coherence_matrix.txt`, SHA `4f2facaf`. Each cell its own subprocess.
**(M) = mutation attempt; (C) = legitimate-path coherence.**

| Authority | (M) mutation attempt at BASE | (C) legitimate path at BASE |
|-----------|------------------------------|------------------------------|
| readonly | **RED** — `.binding.value` accepted; shell reads `'hacked'` | **GREEN** — `RO=viaShell` rc 1; `store.assign` raises `ReadonlyVariableError: RO: readonly variable`; value `'original'` |
| nameref | **RED** — mutation on the deref'd binding clobbers the TARGET | **GREEN** — `ref=viaRef` lands on `target`; `readonly target` then `ref=blocked` rc 1 |
| observer | **RED** — read changed to `'two'`, observer fired `[]` (never) | **GREEN** — `EX=two` fires `['EX']`, shell and env both `'two'` |
| export | **RED** — shell `'two'` / `state.env` `'one'` disagree | **GREEN** — 5-step legitimate sequence (`export`/assign/`export`/`unset`/`export`), shell and env agree at every step |
| tri-state (1 manager) | **RED** — unrelated miss reads `VALUE 'POISON'` | n/a |
| tri-state (2 sequential shells, 1 process) | **RED** — shell A's poisoning survives A's `close()`; shell B's `${u+w}` fires, B's miss status `VALUE` | n/a |

**6/6 (M) cells RED-ON-BASE; 4/4 (C) cells GREEN.** The write engine is
intact; only the READ RETURN TYPE is broken. That is the evidence for the
scope boundary in §2.7 and for leaving the write engine fenced.

### §2.5 P3/P4 — representation cost, MEASURED (the perf ruling re-tested)

Instruments `bench_p3_construction.py` / `bench_p4_lookup_path.py`, outputs
`out_p3_construction.txt` / `out_p4_lookup_path.txt`, SHA `4f2facaf`.
CPython 3.14.2, GC on, R=11, N=200,000 (P3) / 100,000 (P4), interleaved
round-robin in one process. Figures are `min ns/op`. **EXPLORATORY** — to be
re-measured at a detached checkout of the declared tip before certification.

**P3 micro (bare construction / factory `of_value` / `.is_set` read):**

| Candidate | bare | vs C0 | factory | vs C0 | `.is_set` | mutation attempt |
|-----------|------|-------|---------|-------|-----------|------------------|
| C0 plain `__slots__` (CURRENT) | 59.29 | 1.00x | 90.38 | 1.00x | 26.29 | **ACCEPTED** → `value='MUTATED'` |
| C1 frozen dataclass slots | 188.17 | **3.17x** | 227.23 | 2.51x | 25.78 | rejected `FrozenInstanceError` |
| C2 `NamedTuple` | 126.69 | 2.14x | 164.42 | 1.82x | 30.50 | rejected `AttributeError` |
| C3 slots + raising `__setattr__` | 189.74 | **3.20x** | 226.33 | 2.50x | 26.51 | rejected `AttributeError` |
| C4 properties over private slots | 59.09 | **1.00x** | 90.55 | **1.00x** | 26.41 | rejected `AttributeError` (no setter) |

**The docstring's "freezing roughly triples construction cost" is CONFIRMED
ACCURATE — for the frozen-dataclass route (3.17x) and the raising-`__setattr__`
route (3.20x). It is REFUTED as a claim about immutability in general: C4
rejects mutation at 1.00x.**

**P4 end-to-end through the real `ScopeManager.lookup()`:**

| Candidate | VALUE | PRESENT_UNSET | MISSING | `get_variable` (control) |
|-----------|-------|---------------|---------|--------------------------|
| C0 (CURRENT) | 1380.06 | 1482.55 | 516.17 | 1323.64 |
| C1 frozen dataclass | +180.37 (1.13x) | +168.67 (1.11x) | +1.10 | −1.15 |
| C2 NamedTuple | +58.67 (1.04x) | +61.75 (1.04x) | −0.69 | +5.32 |
| C3 raising `__setattr__` | +168.24 (1.12x) | +157.76 (1.11x) | −0.66 | +2.05 |
| C4 properties | **+2.81 (1.00x)** | **+3.42 (1.00x)** | −0.54 | +0.55 |

The `get_variable` column is the instrument's own control: it builds no
lookup, so it must be flat across arms — it is (±5 ns), which is what
licenses reading the other columns as representation cost. A correctness
control confirmed all five arms return identical tri-state answers.

### §2.6 P5 — the MACRO figure that decides the ruling

Instrument `probe_p5_construction_frequency.py`, output
`out_p5_construction_frequency.txt`, SHA `4f2facaf`. Counters wrapped around
`ScopeManager.lookup` / `get_variable` / `_resolve_read`; shell-startup
counts taken separately.

| Workload | `lookup()` | `get_variable()` | `_resolve_read()` | lookup share |
|----------|-----------|------------------|-------------------|--------------|
| W1 variable-read heavy, no set-ness ops | **0** | 16,006 | 16,006 | 0.000% |
| W2 `${x+w}`/`${x-w}` heavy (lookup's ONE caller, deliberately maximised) | 6,000 | 12,005 | 18,005 | 33.324% |
| W3 arrays + params + functions (mixed realistic) | **0** | 2,006 | 2,006 | 0.000% |
| W4 nameref + export + readonly churn | **0** | 3,506 | 3,506 | 0.000% |
| Shell STARTUP | **0** | 0 | — | — |

**The docstring premise "`lookup()` sits on the shell's hottest read path" is
MEASURABLY FALSE at base.** The hot read path is `_resolve_read`, reached via
`get_variable`, which builds no `VariableLookup` at all (`scope.py:343` says
so in its own docstring). `lookup()` is reached only through
`${x+w}`/`${x-w}` set-ness tests. Even in W2 — a workload built to maximise
it — the worst-case frozen-dataclass arm would cost 6,000 × 180 ns ≈ **1.1 ms**
across 2,000 loop iterations. The chosen design costs ~0.

### §2.7 P8 — scope boundary (runtime identity, not docstring reading)

Instrument `probe_p789_design_facts.py` §p8, output
`out_p789_design_facts.txt`, SHA `4f2facaf`. Identity tested with `is`
against the cell in the scope dict.

| Return | Hands out the LIVE cell? | Classification |
|--------|--------------------------|----------------|
| `ScopeManager.get_variable_object('X')` | **True** | sanctioned mutable internal — write engine's own surface, **FENCED** |
| `ScopeManager.get_declared_variable_object('X')` | **True** | sanctioned mutable internal, **FENCED** |
| `VariableStore.get_variable_object('X')` | **True** | sanctioned mutable internal, **FENCED** |
| `ScopeManager.all_variables_with_attributes()` → X | **True** | sanctioned mutable internal, **FENCED** |
| **`ScopeManager.lookup('X').binding`** | **True** | **THE PUBLIC READ CONTRACT — this slot's subject** |
| `ScopeManager.get_variable('X')` | n/a — returns `str` | already immutable; the string projection |

The boundary is therefore drawn from evidence: four `Variable`-returning
entry points are the write engine's declared internals and stay as they are;
`lookup()` is the one READ AUTHORITY whose return is a public contract, and
it is the only one this slot changes.

### §2.8 P7 — `lookup()` × dynamic-special registry

Same instrument, §p7. `RANDOM`/`SECONDS`/`LINENO` are computed specials.
**Two consecutive `lookup()` calls on a special return DIFFERENT `Variable`
objects** (`two reads share the cell? False`), whereas a plain variable
returns the same cell (`True`). Mutating a special's binding SUCCEEDED and
changed nothing observable (`SECONDS` before `'0'` after `'0'`) — it is a
per-read THROWAWAY cell.

Consequence for the ruling: `.binding` is **not uniformly a live store
cell** — it is live for stored variables and a throwaway for computed
specials. Any policy that keeps `.binding` inherits that inconsistency and
must document it; omitting the field removes it. `local RANDOM=5` shadowing
verified still correct (prints `5`).

### §2.9 P9 — array aliasing (decides what "snapshot" can mean)

Same instrument, §p9. `arr` → `binding.value` is a mutable `IndexedArray`;
`m` → `AssociativeArray`. A naive snapshot copying only the scalar fields
**aliases the live array**: `snapshot.value is live_array` → `True`, and
`snapshot.value.set(0, ...)` propagated end-to-end — the shell then printed
`arr[0]=MUTATED_THROUGH_SNAPSHOT`. `Variable.copy()` deep-copies
(`deep.value is r2.binding.value` → `False`; mutating the copy left
`arr2[0]=x`).

**So an honest snapshot policy costs a `Variable.copy()` — an O(n) deep array
copy — on every VALUE lookup.** A cheap scalar-field snapshot would be a
snapshot in name only: exactly D-3.4 lesson 8, a careful label on a vacuous
artifact.

### §2.10 P3b/P3c — the PROPOSED design, measured on its own terms

Instruments `bench_p3b_proposed_design.py` / `bench_p3c_missing_policy.py`,
outputs `out_p3b_proposed_design.txt` / `out_p3c_missing_policy.txt`,
SHA `4f2facaf`. End-to-end through the real `ScopeManager.lookup()`.

Design **D** = properties over private `__slots__` + `binding` OMITTED +
MISSING *and* PRESENT_UNSET as shared FROZEN singletons.

| Cell | BASE | D | D3 (raising `__setattr__`) |
|------|------|---|-----------------------------|
| VALUE `lookup('SET')` | 1377.36 | 1377.74 (**1.000x**) | 1489.01 (1.081x) |
| PRESENT_UNSET `lookup('DECL')` | 1431.26 | 1368.90 (**0.956x — FASTER**) | 1366.15 (0.955x) |
| MISSING `lookup('NOPE')` | 510.16 | 515.23 (1.010x) | 515.85 (1.011x) |
| production shape `lookup('SET').is_set` | 1427.98 | 1431.67 (**1.003x**) | 1542.73 (1.080x) |

D is FASTER than base on PRESENT_UNSET because, once `binding` is gone, that
result carries no per-instance data and stops allocating. Controls: all three
arms return identical tri-state answers; D rejects mutation on **all six**
field × surface combinations (status/value × fresh-VALUE / MISSING-singleton /
PRESENT_UNSET-singleton) while BASE accepts all six.

Ruling (c)'s two readings, priced on the same harness (P3c):

| Nullary-status policy | MISSING | PRESENT_UNSET | Safety control |
|-----------------------|---------|---------------|----------------|
| BASE mutable shared `_MISSING` | 511.21 | 1432.74 | **mutation ACCEPTED; second miss poisoned=True** |
| **S frozen shared singletons** | +3.45 ns (1.007x) | **−59.62 ns (0.958x)** | mutation rejected; shared=True; **second miss clean=True** |
| F fresh instance per miss | **+68.51 ns (1.134x)** | +2.24 ns (1.002x) | mutation rejected; shared=False; second miss clean |

**Sharing was never the defect — mutability was.** A frozen shared singleton
is clean by the same argument that makes `True`/`None` safe to share, and
fresh-per-miss buys nothing while costing +68.51 ns on every miss.

### §2.11 Must-hold baseline at base (light runs, not a gate)

Measured at `4f2facaf`, `pgrep -f pytest` clean before each run:

| Suite | Result at base |
|-------|----------------|
| `test_variable_lookup.py` + `test_variable_store_write_ban.py` + `test_scope_tombstones.py` + `test_dynamic_special_masking.py` (one invocation) | **50 passed** in 0.46s |
| `tests/conformance/bash/test_variable_truth_conformance.py` | **35 passed** in 6.82s |

Sibling-suite reading (NAME-VS-BODY, done BEFORE any pin is written):

- `test_variable_store_write_ban.py` is a **textual source scan** over
  `PSH_ROOT.rglob("*.py")` with an ALLOWLIST of `core/variable_store.py` +
  `core/scope.py`. It bans `.value.set/.unset/.clear/.append(` and
  `.attributes =/|=/&=`; a bare scalar `.value =` is DELIBERATELY not banned
  (too many false positives — `Token.value`, AST `.value`). Consequence for
  me: it scans `psh/` only, so mutation-ATTEMPT pins living in `tests/` do
  not trip it — but any production edit of mine inside `variable_lookup.py`
  must not introduce a banned signature (it will not; that file holds no
  `Variable` mutation). Its `PSH_ROOT` is derived from `psh.__file__`, the
  same import-resolution hazard my probes hit — worth knowing if it ever
  looks spuriously green.
- `test_scope_tombstones.py` (25 tests) owns the tombstone/unset SEMANTICS
  rows; `test_dynamic_special_masking.py:90` owns the
  masked-special-reads-unset row via `lookup(...).is_set`. My pins must add
  the MUTATION dimension and must not duplicate or restate their semantics
  rows.

---

## §3 Rulings received

**R1 (integrator, 2026-08-07)** — inbox `INTEGRATOR-INBOX.md` lines 319-423,
inbox md5 at receipt `ebe57f7f6f4e8b9c134efd5e10936c3a`.

- **(a) ACCEPTED** — Phase A table accepted; **design D APPROVED** (properties
  over private `__slots__`, `binding` OMITTED, MISSING + PRESENT_UNSET as
  shared FROZEN singletons). Integrator independently re-ran P5 at my worktree
  and reproduced my table exactly (0 / 6000 / 0 / 0; startup 0/0), and checked
  a gap I had not: `_param_is_set` serves NON-colon operators only
  (`operators.py:173-174`), so W3's zero is not a workload artifact.
  5 binding conditions (a)1-(a)5.
- **(b) ACCEPTED** — OMIT. 3 conditions (b)1-(b)3.
- **(c) ACCEPTED, clause tightened** — frozen shared singletons; charter
  reading RECORDED as a reading; threat model extended with a THIRD
  out-of-scope clause (private-slot writes) that must be recorded as WEAKER
  than 3.2's, with the priced declined alternatives, plus ONE committed
  labelled `control-` cell making the boundary visible in the suite.

**R2 (integrator, 2026-08-07)** — inbox lines 552-607, inbox md5 at receipt
`b69df6769782cd1c6099b0d63fb2fa87`.

- **GO for Phase B**, GO-binding citation:
  `tmp/remediation-ledgers/SLOT-LEDGER-4b1.md` §5.1 lines 366-543, ledger md5
  `6f45955abe1c7e4864cb76d283ba50c6`, declared start tip `4f2facaf`.
- **§5.1.6 RULED IN** as a narrowly bounded SCOPE EXTENSION (4A.2 R4
  precedent: fix-in-slot by explicit extension, never silent). Conditions:
  doc-only (no code statement moves), its own hunk/commit labelled as the R2
  scope extension, and the doc-sweep enumeration gains it as item 6 — done
  above as a supervised edit to the frozen §5.1.5 under this ruling.
- Integrator's independent checks: re-ran the (a)4 licensing grep tree-wide
  (no whole-object lookup comparisons; 3 unrelated hits); read the
  `command_resolution.py:51-53` citation verbatim (my quote exact);
  re-added §5.1.3's arithmetic by class (58 = 33 + 25).
- **Both my flags ACCEPTED as declared.** Binding instruction on the class-7
  caveat: certification rows carry the split forward as **32
  defect-evidencing red + 1 incidental-red labelled control**, never "33 red"
  bare.

## §4 Certification rows

Ordered changes on `fix/remediation-4b-1`, base `4f2facaf`:

| # | SHA | Change |
|---|-----|--------|
| C1 | `ebff73db` | production: immutable `VariableLookup` (properties over private slots, `binding` omitted, both nullary statuses frozen singletons) + `scope.py` call sites/docstring + 58-cell pin file + 4 representation-detail edits to `test_variable_lookup.py` |
| C2 | `a4ace339` | doc sweep: `psh/core/CLAUDE.md` table row + Scope Stack prose |
| C3 | `c1c7b69a` | **R2 SCOPE EXTENSION, doc-only**: `psh/executor/command_resolution.py` stale precedent citation |
| C4 | `0e9603e6` | de-vacuate the PRESENT_UNSET equality pin (M8-5 self-catch) |

### §4.1 DEVIATIONS from the pre-registration (reported, not absorbed)

**The TOTAL matched exactly (33 RED / 25 GREEN of 58, as pre-registered in
§5.1.3) but TWO per-class splits deviated, and they CANCELLED.** That
cancellation is precisely the kind of accidental agreement the campaign's
lessons warn about, so it is reported rather than allowed to stand as
"pre-registration confirmed".

| Class | Pre-registered | Measured | Deviation |
|-------|----------------|----------|-----------|
| `TestCompositionCells` | 3 red / 1 green | **4 red / 0 green** | +1 red |
| `TestRepresentationSemantics` | 4 red / 2 green | **3 red / 3 green** | −1 red |
| all other classes | as registered | as registered | — |

Causes, derived from the per-cell output (`out_redonbase_base_final.txt`):

1. `test_masked_special_still_reads_unset_through_a_frozen_result` — I
   registered it as a green must-hold semantics cell. It is RED at base
   because I wrote it with a mutation attempt inside it (`result.value =
   "resurrected"`), which succeeds at base. My registration described the
   cell I intended, not the cell I wrote.
2. `test_equality_is_status_and_value` — I registered it red, expecting base
   equality to differ. It is GREEN at base: every instance the cell builds has
   `binding=None`, so base equality already agrees with status+value. The cell
   does not discriminate at base; it is a forward pin, not defect evidence.

Neither deviation changes a code decision, and no cell was added, removed, or
retuned to make the total match — the total matching is a coincidence of two
independent errors of opposite sign, and is recorded as such.

### §4.2 Red-on-base, re-derived at the DECLARED tip's pin file

Instrument `redonbase_split.py`, output `out_redonbase_base_final.txt`.
Run at a **detached worktree of base `4f2facaf`** with the final (post-C4) pin
file copied in; **each cell in its own interpreter**, because at base several
deletion cells actually succeed and would damage the shared singleton for
later cells in the same process — a single run would report collateral and the
number would not mean what it says.

**58 collected — 33 RED / 25 GREEN / 0 anomalies.** Per ruling R2, the red is
carried forward split as **32 defect-evidencing red + 1 incidental-red
labelled control** (`test_control_private_slot_write_is_declared_out_of_scope`
is red at base only because base has no `_status`/`_value` slots at all).

### §4.3 Post-state: all green at tip `0e9603e6`

| Check | Result |
|-------|--------|
| pin file + 4 must-hold unit suites | **108 passed** (58 new + 50 must-hold, the latter matching the base figure exactly) |
| `tests/unit/core/` + `test_variable_truth_conformance.py` | **897 passed** |
| `ruff check psh tests tools` | **All checks passed!** |
| `mypy` | **Success: no issues found in 275 source files** |

### §4.4 M8 mutation locks — 5/5 HOLD

Instruments `m8_plugin.py` + `m8_mutation_locks.py`, output
`out_m8_mutation_locks.txt`, at tip. Control run (no mutation) clean first, so
the comparisons are against a sound baseline. Each lock declares a
must-go-red AND a must-stay-green set; verdict requires both.

| Lock | Defect re-introduced | Red cells | Verdict |
|------|----------------------|-----------|---------|
| M8-1 | fields writable again | 37 | HOLDS |
| M8-2 | `present_unset()` allocates | 1 | HOLDS |
| M8-3 | `binding` restored AND the legacy `lookup()` that fills it | 10 | HOLDS |
| M8-4 | `missing()` allocates per miss | 1 | HOLDS |
| M8-5 | `__eq__` reverts to identity | 2 | HOLDS |

**M8-4 is the discrimination row that matters:** only
`test_missing_is_a_shared_singleton` went red; every poisoning pin stayed
GREEN. That is the proof they test IMMUTABILITY rather than allocation — had
they reddened there, they would have been passing for the wrong reason.

**DEV FAULT, SELF-CAUGHT BY M8 (recorded):** M8-5 initially FAILED.
`test_all_declared_unset_results_are_equal` compared two `lookup()` results,
but since PRESENT_UNSET is now a shared constant both sides were the SAME
object — so the cell stayed green under an identity `__eq__`. It pinned
sharing (already covered elsewhere) rather than the equality rule it claimed:
a vacuous cell with a careful label, D-3.4 lesson 8. Fixed in C4 by building
two distinct instances through the constructor and keeping the `lookup()` pair
as a second assertion. This is exactly what the M8 lock exists to catch, and
it caught it before the gate.

### §4.5 Perf certification — base vs tip, DIFFERENT method (condition (a)1)

Instrument `bench_p10_real_lookup.py`, outputs `out_p10_base.txt` /
`out_p10_tip.txt`. Deliberately a different method from Phase A's P3b/P4,
which swapped candidate classes into one process (D-3.5): P10 patches
NOTHING and measures whatever `psh` the checkout provides, run twice at
**detached checkouts** of base `4f2facaf` and tip `0e9603e6` (B71). Each run
prints its own SHA and the live `__slots__` so the halves cannot be silently
mismatched — base printed `('status', 'value', 'binding')`, tip printed
`('_status', '_value')`.

| Cell | base `4f2facaf` | tip `0e9603e6` | tip/base | delta |
|------|-----------------|----------------|----------|-------|
| VALUE `lookup('SET')` | 1484.68 | 1468.09 | 0.989x | −16.59 ns |
| PRESENT_UNSET `lookup('DECL')` | 1525.28 | **1428.33** | **0.936x** | **−96.95 ns** |
| MISSING `lookup('NOPE')` | 518.11 | 528.61 | 1.020x | +10.50 ns (within the 20 ns spread) |
| production `lookup('SET').is_set` | 1514.34 | 1520.81 | 1.004x | +6.47 ns |
| **control** `get_variable('SET')` | 1383.08 | 1376.11 | 0.995x | −6.97 ns |

The control is the cross-run validity check: `get_variable` is untouched by
this slot, so its flatness across two independent processes is what licenses
comparing the other rows between runs. The PRESENT_UNSET speedup independently
reproduces Phase A's in-process prediction (0.956x) by the other method.

**Certified claim, with its boundary stated:** immutability landed at no
measurable cost on the VALUE and production-shape paths, and at a real
improvement on PRESENT_UNSET (which stopped allocating). The claim is about
`ScopeManager.lookup()` on this interpreter and machine; it is NOT a claim
about frozen dataclasses in general — that cost is real (measured 3.17x
construction, 1.13x end-to-end) and is what the chosen representation avoids.

## §5 Pre-registration blocks (binding)

### §5.1 PRE-REGISTRATION — Phase B (written 2026-08-07 under R1, BEFORE any Phase B code)

Declared start tip: **`4f2facaf0eede0dacf926e6718a2c348c3d3ce82`** (= base;
no commits yet on `fix/remediation-4b-1`). Every count below is a PLANNED
figure; the MEASURED red/green split is re-derived at this tip once the pin
file exists, and any deviation is reported as a deviation, not silently
absorbed.

#### §5.1.1 Production change (the ruled design D)

`psh/core/variable_lookup.py` — `VariableLookup` becomes:
`__slots__ = ("_status", "_value")`; read-only `status` / `value` /
`is_set` / `is_present` properties; `missing()` → frozen `_MISSING`
singleton; `present_unset()` → frozen `_PRESENT_UNSET` singleton (NEW —
stops allocating); `of_value(value)` → fresh instance. **`binding` removed
from the type and from all three factory signatures.**

`psh/core/scope.py` — `lookup()` call sites updated:
`VariableLookup.of_value(var.as_string(), var)` → `of_value(var.as_string())`;
`VariableLookup.present_unset(declared)` → `present_unset()`. The `declared`
local is still needed for CLASSIFICATION (`declared is not None and
declared.is_unset`) — that logic is UNCHANGED; only what is passed on changes.
**No other production file changes** (subject to the §5.1.6 stop-and-propose).

#### §5.1.2 `__eq__` / `__repr__` declaration (condition (a)4)

- **Equality = `status` + `value`.** Measured base fact (probe, this tip):
  `present_unset(v1) == present_unset(v2)` is **False at base** — the binding
  differentiates. Under D all PRESENT_UNSET results are the SAME singleton,
  so they are both `==` and `is`. **Declared representation-detail change.**
- **Measured fact licensing it:** a tree-wide grep for whole-object
  comparisons of lookup results (`tests/` + `psh/`) returns **NONE** — no
  test or production site leans on binding-differentiated equality. So the
  change flips no existing assertion; it is pinned forward by a new cell.
- **`__repr__`** drops the `binding=` term: base emits
  `VariableLookup(VALUE, value='v', binding=None)`; tip emits the same
  without the binding term. Pinned by an agreement-form cell (contains
  status name + value repr, does NOT contain "binding").
- **Hashability PRESERVED, not changed:** base `VariableLookup.__hash__ is
  None` (defining `__eq__` sets it), so instances are unhashable today. D
  keeps `__eq__` and adds no `__hash__`, so they stay unhashable. Declared
  explicitly so the property is a decision, not an accident, and pinned.

#### §5.1.3 New pin file + PLANNED cell counts

`tests/unit/core/test_variable_lookup_immutability.py` — **58 cells**,
**33 expected RED-ON-BASE / 25 expected green-at-base**:

| Class | Cells | Planned RED | Planned green |
|-------|-------|-------------|---------------|
| 1 `TestMutationSurfaceRejected` — assignment (3 surfaces × 4 public names = 12), deletion (12), new-attribute/slots-closed (3), no-`__dict__` (3) | 30 | 12 | 18 |
| 2 `TestBindingSurfaceOmitted` — no `binding` attribute (3 surfaces), factories reject a binding argument (2) | 5 | 5 | 0 |
| 3 `TestMissingSingletonNotPoisonable` — mutate-a-miss + **follow-up clean-miss assertion**, `${u+w}` end-to-end, two-sequential-shells, PRESENT_UNSET singleton | 4 | 4 | 0 |
| 4 `TestAuthorityCoherence` — readonly / nameref / observer / export, each (M) + (C) | 8 | 4 | 4 |
| 5 `TestCompositionCells` — 2-level nameref chain, readonly×export, computed-special frozen, masked-special shadow | 4 | 3 | 1 |
| 6 `TestRepresentationSemantics` — MISSING shared, **PRESENT_UNSET shared (new)**, equality=status+value, all-PRESENT_UNSET-equal, repr, unhashable | 6 | 4 | 2 |
| 7 `TestDeclaredThreatModelBoundary` — the ONE labelled `control-` cell | 1 | 1 | 0 |
| **TOTAL** | **58** | **33** | **25** |

Surfaces axis (every class-1 cell quantifies over it): `fresh VALUE` /
`MISSING singleton` / `PRESENT_UNSET singleton`. Public-name axis:
`status` / `value` / `is_set` / `is_present`. This is the
**MUTATION SURFACE × AUTHORITY GUARD** axis walked in full.

Class-1 red/green split reasoning (stated as a MEASURED split, not "all X
except Y"): at base `status`/`value` are plain writable slots → the 6
assignment cells and 6 deletion cells on those two names are RED; `is_set`/
`is_present` are already setter-less properties → their 12 cells are GREEN
at base; `__slots__` already closes instances → the 6 slots-closed/no-dict
cells are GREEN at base.

Class-7's control cell is expected RED at base for an INCIDENTAL reason
(base has no `_status`/`_value` slots at all, so the write raises
`AttributeError` there); it becomes meaningful only at tip. Recorded so the
red is not miscounted as defect evidence.

#### §5.1.4 Edits to the existing suite (representation-detail, condition (b)1)

`tests/unit/core/test_variable_lookup.py` — 4 edits, each asserting the SAME
semantics through a sanctioned surface:

| Line | Today | Becomes |
|------|-------|---------|
| 27 | `r.binding is not None and r.binding.name == 'X'` | `r.is_present` + `mgr.get_variable_object('X').name == 'X'` |
| 36 | `r.binding is None` | `r.is_present is False` + `mgr.get_declared_variable_object('NOPE') is None` |
| 48 | `r.binding is not None and r.binding.is_unset` | `r.is_present` + `mgr.get_declared_variable_object('x').is_unset` |
| 133-145 | `test_slots_closed_no_dict` (+ its non-frozen-rationale docstring) | evolves per condition (a)3 into the THREE pinned properties: private slots present, public names reject assignment, instances stay closed |

Module docstring line 7 ("the read-only binding") also updated. **No
semantics row is touched** — every tri-state / H13 / nameref / projection
assertion stays byte-identical.

#### §5.1.5 Doc sweep enumeration (condition (b)2), pointers verified at tip

1. `psh/core/variable_lookup.py` — module docstring (the `binding` paragraph
   AND the non-frozen/"hottest read path" paragraph) + class docstring.
   Per (a)2 the rewrite records **both grounds** for D; per (a)5 it states
   THIS type's measured facts only and cross-references W1 `FieldRun` as a
   separate, still-standing ruling it does NOT overturn.
2. `psh/core/scope.py` — `lookup()` docstring, the `result.binding` sentence
   (:388-389). (`get_variable`'s ":343 skips building a VariableLookup"
   sentence stays TRUE — verified, left alone.)
3. `psh/core/CLAUDE.md` — table row :30 and Scope Stack prose :104-105
   (`VariableLookup(MISSING | PRESENT_UNSET | VALUE, binding)`).
4. `psh/protocols/__init__.py` — :15 and :95 lookup-contract text; pointers
   re-verified (no `binding` mention found; this is a pointer-accuracy check,
   and protocol WIDENING is not proposed).
5. `tests/unit/core/test_variable_lookup.py` module docstring (per §5.1.4).
6. **`psh/executor/command_resolution.py:51-53`** — ADDED under **R2's ruled
   SCOPE EXTENSION** (supervised edit to this frozen block, authorised by R2).
   Doc-only, own hunk/commit labelled as the R2 scope extension. Drops the
   `VariableLookup` half of the slots-non-frozen precedent citation, keeps
   `FieldRun`; `ResolvedCommand`'s own ruling is NOT reopened. Declared here
   so the diff audit EXPECTS `psh/executor/command_resolution.py` in the diff
   and does not read it as scope creep.

#### §5.1.6 STOP-AND-PROPOSE — a doc-sweep target OUTSIDE my scope that R1's enumeration missed

`psh/executor/command_resolution.py:51-53` reads: *"the campaign's ratified
allocate-fresh-never-mutate discipline (the W1 ``FieldRun`` / R2
``VariableLookup`` precedent — slots-non-frozen with a slots guard pin
instead of frozen)"*.

Once D lands, that citation is **false**: `VariableLookup` will no longer be
a slots-non-frozen precedent, so this docstring would teach a
now-nonexistent design — the exact rot pattern the project's no-sketch rule
was written for (reappraisal #19: the worst doc rot is a sketch teaching a
since-fixed design). But `psh/executor/` is OUTSIDE this slot's scope, so I
am NOT touching it without an explicit ruling.

**My recommendation (2 lines, doc-only):** drop the `VariableLookup` half of
the citation, keep `FieldRun`. `ResolvedCommand`'s own slots-non-frozen
ruling stands on its own measured grounds and is NOT reopened — the same
logic as condition (a)5. **Alternative:** leave it and file a D-4B.1-s
successor row. Integrator's call; I proceed with neither until ruled.

#### §5.1.7 M8 mutation-lock plan (each lock fails for its OWN reason)

Instrument `tmp/4b1-instruments/m8_mutation_locks.py` — re-introduces each
defect class against the tip pin suite and asserts a DISTINCT, named cell set
goes red:

| Lock | Re-introduced defect | Must go red | Must stay GREEN (discrimination) |
|------|----------------------|-------------|----------------------------------|
| M8-1 | `status`/`value` back to plain writable slots | class 1 assignment/deletion + class 3 poisoning | class 2 binding-omitted, class 6 singleton identity |
| M8-2 | `present_unset()` allocates fresh again | class 6 PRESENT_UNSET-shared + all-PRESENT_UNSET-equal | class 1, class 3 |
| M8-3 | `binding` property restored returning the live cell | class 2 + class 4 (M) authority cells | class 6 |
| M8-4 | `missing()` allocates fresh per miss | class 6 MISSING-shared | class 3 poisoning cells (still clean — proves they test the RIGHT property) |
| M8-5 | `__eq__` reverts to identity comparison | class 6 equality cells | classes 1-5 |

M8-4's discrimination row is the one that matters most: if the poisoning
pins went red under a fresh-per-miss mutation they would be testing
allocation rather than immutability.

#### §5.1.8 Must-hold set (green at base AND tip; re-derived both ends)

Measured at base this tip (§2.11): `test_variable_lookup.py` +
`test_variable_store_write_ban.py` + `test_scope_tombstones.py` +
`test_dynamic_special_masking.py` = **50 passed**;
`tests/conformance/bash/test_variable_truth_conformance.py` = **35 passed**.
Plus `expansion/operators.py#_param_is_set` behaviour (`${x+w}`/`${x-w}`)
and the H13 / tombstone / nameref-cycle rows.

#### §5.1.9 Expected gate deltas vs base

- Suite: **+58 passed**, 0 failed, 0 new skips (the 4 edited cells in
  `test_variable_lookup.py` stay 1-for-1, so its own count is unchanged).
- Base figures to be RE-DERIVED in my first gate run, never carried from the
  brief: attestation 18840ac9-committed cites 23,546 passed / 1,618 skipped /
  10 xfail; ruff clean; mypy 275 files; compare-bash 3,042/26 EXACT.
- **compare-bash: EXACT, unchanged.** This is an internal-integrity slot with
  no shell-observable delta; any compare-bash movement is a STOP, not an
  adjustment.
- ruff clean over `psh tests tools`; mypy clean (file count re-derived).

#### §5.1.10 Perf certification plan (condition (a)1)

Every EXPLORATORY figure in §2.5/§2.10 is re-measured at a **DETACHED
checkout of the declared tip** (B71, extended to devs by 3.2's fault), from
the same harness, and the base/tip pair carries per-TABLE provenance. No
figure moves from §2 into a certification row without that re-measurement.

## §5.2 ERRATA (required by R3; supervised edits to the frozen block)

Each row cites the §5.1 line it deviates from. All three were reported in D4
BEFORE the gate, not discovered afterwards.

### ERRATUM E1 — per-class red/green split, `TestCompositionCells`

- **Deviates from:** §5.1.3 line 428 (the class-5 row: "4 cells | 3 red | 1 green").
- **Measured:** 4 red / 0 green (`out_redonbase_base_final.txt`).
- **Cause:** I registered
  `test_masked_special_still_reads_unset_through_a_frozen_result` as a green
  must-hold semantics cell, but WROTE it with a mutation attempt inside
  (`result.value = "resurrected"`), which succeeds at base. The registration
  described the cell I intended, not the cell I wrote.
- **Disposition:** cell KEPT as written — a composition cell that varies both
  the semantics and the mutation dimension is the stronger artifact. No
  retuning; the registration was wrong, not the cell.

### ERRATUM E2 — per-class red/green split, `TestRepresentationSemantics`

- **Deviates from:** §5.1.3 line 430 (the class-6 row: "6 cells | 4 red | 2 green").
- **Measured:** 3 red / 3 green (`out_redonbase_base_final.txt`).
- **Cause:** I registered `test_equality_is_status_and_value` as red, expecting
  base equality to differ. It is GREEN at base: every instance that cell builds
  carries `binding=None`, so base equality already agrees with status+value.
  It is a forward pin, not defect evidence.
- **Disposition:** cell KEPT. Its discriminating power is supplied by the M8-5
  lock, not by base redness.

**E1 and E2 have opposite signs and CANCEL, so the §5.1.3 TOTAL (33/25)
matched exactly.** Recorded explicitly: the matching total is a coincidence of
two independent errors, and is NOT evidence that the pre-registration was
confirmed.

### ERRATUM E3 — DEV FAULT: vacuous equality cell (self-caught by M8-5)

- **Deviates from:** §5.1.7 line 509 (the M8-5 lock row) — the lock was
  declared to redden the equality cells; on first run it did not.
- **Fault:** `test_all_declared_unset_results_are_equal` compared two
  `lookup()` results. Since PRESENT_UNSET is now a shared constant, both sides
  were the SAME object, so the cell stayed green under an identity `__eq__`.
  It pinned SHARING — already covered by
  `test_present_unset_is_a_shared_singleton` — while claiming to pin the
  equality rule. A vacuous cell behind a careful label (D-3.4 lesson 8).
- **Fix:** C4 `0e9603e6` — build two distinct instances through the
  constructor; keep the `lookup()` pair as a second assertion where sharing
  makes equality hold for the stronger reason.
- **Detection:** the M8-5 mutation lock, pre-gate. Recorded as a DEV FAULT,
  SELF-CAUGHT.

---

## §6 Gate results at the declared tip `0e9603e6`

### §6.1 Base figures — DERIVED FROM THE TREE, not carried from the brief

`git show 4f2facaf:gate_attestation.json` (the committed attestation at base,
gating `a4abd952`, v0.769.0):

| Phase | passed | skipped | xfailed | deselected |
|-------|--------|---------|---------|------------|
| 1 (parallel) | 22,524 | 1,618 | 8 | 1,041 |
| 1b (serial) | 1,022 | 0 | 2 | 24,167 |
| **combined** | **23,546** | **1,618** | **10** | — |

`ruff: true`, `mypy_files: 275`.

### §6.2 My gate run (`tmp/gate-1.txt`), tip `0e9603e6`

| Phase | passed | skipped | xfailed | deselected |
|-------|--------|---------|---------|------------|
| 1 (parallel) | 22,582 | 1,618 | 8 | — |
| 1b (serial) | 1,022 | 0 | 2 | 24,225 |
| **combined** | **23,604** | **1,618** | **10** | — |

`✅ All test phases PASSED`. Run foreground; it exceeded the 600 s foreground
window and was MOVED to background per the gate rule (not stopped), then
awaited in-turn by a bounded poll — never left in flight across a turn.

### §6.3 Delta vs §5.1.9, with an INDEPENDENT cross-derivation

| Figure | pre-registered (§5.1.9) | measured | verdict |
|--------|-------------------------|----------|---------|
| passed | +58 | 23,604 − 23,546 = **+58** | MATCH |
| failed | 0 | **0** | MATCH |
| skipped | 0 new | 1,618 − 1,618 = **0** | MATCH |
| xfailed | unchanged | 10 − 10 = **0** | MATCH |
| compare-bash | 3,042 / 26 EXACT | **3,042 passed, 26 skipped** | **EXACT, unchanged** |
| ruff | clean | **All checks passed!** | MATCH |
| mypy | re-derived | **Success, 275 source files** (base attestation: 275) | MATCH |

**Independent cross-derivation of the +58 (D-3.5 different-method):** the
serial phase's DESELECTED count moved 24,167 → 24,225 = **+58**. That is the
same number reached by a different route — the serial phase deselects the new
unit cells rather than running them — so the pass-count delta and the
tree-size delta agree without sharing a derivation. Serial-phase PASSED is
unchanged at 1,022 both ends, confirming all 58 landed in phase 1 and none
became serial-marked.

No flakes observed; nothing re-run.

---

## §7 Discharge audit at final tip `0e9603e6`

Every claim row, its instrument anchor, and its evidence SHA.

| # | Claim | Instrument | Evidence SHA | Status |
|---|-------|-----------|--------------|--------|
| 1 | MEDIUM-5 reproduces (4 legs incl. nameref) | `probe_p1_medium5_repro.py` / `out_p1_medium5_repro.txt` | base `4f2facaf` | DISCHARGED |
| 2 | 1 production `lookup()` caller; 0 production `.binding` readers; 0 dynamic access | `probe_p2_census.py` / `out_p2_census.txt` (AST) + grep cross-check | base `4f2facaf` | DISCHARGED |
| 3 | 6/6 mutation cells red, 4/4 legitimate-path cells green | `probe_p6_coherence_matrix.py` / `out_p6_coherence_matrix.txt` | base `4f2facaf` | DISCHARGED |
| 4 | "roughly triples" TRUE for its routes (3.17x / 3.20x), FALSE as a claim about immutability (C4 1.00x) | `bench_p3_construction.py` / `out_p3_construction.txt` | base `4f2facaf` | DISCHARGED |
| 5 | "hottest read path" premise FALSE (0 constructions on 3 of 4 workloads + startup) | `probe_p5_construction_frequency.py` / `out_p5_construction_frequency.txt` | base `4f2facaf` | DISCHARGED (integrator independently reproduced) |
| 6 | Scope boundary: 4 live-cell returns fenced, `lookup()` the one public read contract | `probe_p789_design_facts.py` §p8 | base `4f2facaf` | DISCHARGED |
| 7 | `.binding` never uniformly live (computed specials hand out throwaways) | `probe_p789_design_facts.py` §p7 | base `4f2facaf` | DISCHARGED (report row) |
| 8 | Cheap snapshot aliases the live array end-to-end; honest one costs a deep copy | `probe_p789_design_facts.py` §p9 | base `4f2facaf` | DISCHARGED |
| 9 | Design D: 1.000x / 1.003x / 0.956x, mutation rejected on 6/6 field×surface | `bench_p3b_proposed_design.py` | base `4f2facaf` | DISCHARGED |
| 10 | Frozen singleton +3.45 ns vs fresh-per-miss +68.51 ns; both safe once frozen | `bench_p3c_missing_policy.py` | base `4f2facaf` | DISCHARGED |
| 11 | Red-on-base 33/25 (32 defect + 1 incidental control), 0 anomalies | `redonbase_split.py` / `out_redonbase_base_final.txt` | detached base `4f2facaf`, final pin file | DISCHARGED |
| 12 | M8 5/5 locks hold; M8-4 discrimination row proves poisoning pins test immutability not allocation | `m8_mutation_locks.py` + `m8_plugin.py` | tip `0e9603e6` | DISCHARGED |
| 13 | Perf base→tip: VALUE 0.989x, PRESENT_UNSET 0.936x, production 1.004x, control flat | `bench_p10_real_lookup.py` | detached `4f2facaf` + `0e9603e6` | DISCHARGED |
| 14 | Gate +58/0/0/0; compare-bash 3,042/26 EXACT; ruff clean; mypy 275 | `tmp/gate-1.txt`, `tmp/compare-bash-1.txt` | tip `0e9603e6` | DISCHARGED |
| 15 | Doc sweep propagated exhaustively; 0 stale `.binding` / precedent references | tree-wide grep, §D4 | tip `0e9603e6` | DISCHARGED |

**Counts derived, not hand-tallied:** 15 rows, 15 discharged, 0 outstanding.

### §7.1 Bounced-rows replay

No row has been bounced by the integrator in this slot (verification round
pending). The one self-bounced row is **E3** (the M8-5 vacuous cell): replayed
at tip after C4 — M8-5 now reddens BOTH equality cells and the lock HOLDS
(`out_m8_mutation_locks.txt`).

### §7.2 Exit criterion, restated against evidence

*"Variable lookup values and bindings reject mutation; readonly, nameref,
observer, and exported-environment coherence remain intact — pinned by
mutation attempts."*

- **values reject mutation** — 30 cells across 3 surfaces × 4 public names ×
  {assign, delete, grow, `__dict__`}; 12 red-on-base, all green at tip.
- **bindings reject mutation** — discharged by ELIMINATION under ruling (b):
  there is no binding surface. 5 cells pin its absence; all 5 red-on-base.
- **readonly / nameref / observer / export coherence** — 8 cells, each
  authority carrying a mutation-attempt cell (4 red-on-base) and a
  legitimate-path cell (green both ends, proving the write engine was not
  weakened).
- **pinned by mutation attempts** — every cell above is an attempt, not an
  inspection. 4 composition cells and the two-sequential-shells poisoning cell
  extend it past the single-authority case.

### §7.3 Successor rows (MUST-NOT-ABSORB, filed not fixed)

- **D-4B.1-s1** — a future consumer wanting attributes without a second lookup
  (per ruling (b)3): re-add a capability-free view, never the live cell.
  Filed, not built; nothing needs it today (census: 0 consumers).
- **D-4B.1-s2** — the threat model's third clause (private-slot writes) is
  weaker than slot 3.2's frozen-dataclass surface. Closing it costs a measured
  1.081x (raising `__setattr__`) or 1.13x (frozen dataclass) end-to-end on
  `lookup()`. Committed as a labelled control so strengthening it later flips
  a visible cell.
- **`executor/array.py` Phase-4 alias-mutation gap** — FENCED, report-only,
  untouched. Still the write-ban's known gap.

---

# §8 FIX ROUND (opened 2026-08-07 by R4 BOUNCE; freeze lifted by that verdict)

R4 verdict: BOUNCE, 1 blocker + 5 required nits. Sections §1-§7 above are
FROZEN and are NOT rewritten; every change lands below as a dated erratum or
addendum. New tip declared at the end of this section.

Fix-round commits (each declared by SendMessage BEFORE it landed, per the
mechanical tip rule):

| # | SHA | Change |
|---|-----|--------|
| F1 | `862f949d` | BL-1 docstring line + RN-2 carried-successor labels |
| F2 | `7d42c79e` | RN-1 threat-model OPEN CLASS (both declarations + control cell) |
| F3 | `2f08bd7a` | repair ruff B018 introduced by F2 (dev fault, §8.7) |

**NEW TIP: `2f08bd7a1b251066d68126cc5ad086ef2a1a664c`.**

## §8.1 ERRATUM E4 — BL-1, the doc-sweep miss (BLOCKER)

- **Deviates from:** §5.1.4 line 456 ("Module docstring line 7 ... also
  updated") and the D4 claim that the doc sweep was exhaustive.
- **Defect:** `tests/unit/core/test_variable_lookup.py:3` still read
  ``VariableLookup(MISSING | PRESENT_UNSET | VALUE, binding)`` while lines
  7-8 of the SAME docstring — which I rewrote — said the result carries no
  cell reference. A docstring contradicting itself within one paragraph, in
  the sibling the brief named to read FIRST.
- **ROOT CAUSE (the part worth keeping):** my propagation grep was
  `\.binding\b`. That pattern cannot match a bare `, binding)` — the field
  appearing as a SIGNATURE TERM rather than as an attribute access. The sweep
  was exhaustive over the wrong alphabet. A doc sweep for a removed field must
  search the field NAME, not one syntactic form of it.
- **Fixed:** F1 `862f949d`.

## §8.2 ERRATUM E5 — RN-1, threat model was a CLOSED enumeration (ruling c-1)

- **Deviates from:** §5.1.3's class-7 description and the ruling (c) clause
  recorded at §3, both of which named exactly three out-of-scope routes.
- **Defect:** at least five routes into the private slots land. Reproduced by
  me at tip `0e9603e6` (`out_rn1_routes.txt`) after the integrator reproduced
  the first independently:

| route | result |
|-------|--------|
| `missing().__init__(VALUE,'POISON')` | **LANDS** — an unrelated fresh miss then reads `VALUE 'POISON'`; poisons the shared singleton end-to-end |
| `delattr(fresh, '_value')` | **LANDS** — subsequent `.value` raises (slot removed) |
| plain `_value` assignment | LANDS (the one route already declared) |
| `object.__setattr__` | LANDS (already declared) |
| `__class__` reassignment | **LANDS** |
| `pickle` round-trip | **does NOT circumvent** — distinct clone, itself immutable, real singleton unharmed |

- **Fixed:** F2 `7d42c79e`. Both declarations (module docstring + pin-file
  clause) now state an OPEN CLASS per ruling (c-1); the labelled control cell
  DEMONSTRATES each route as sub-assertions instead of asserting one and
  describing the rest.
- **Cell count STABLE at 58** (verified by collection), so no count erratum is
  needed. The control cell was RENAMED
  `test_control_private_slot_write_is_declared_out_of_scope` →
  `test_control_private_slot_routes_are_declared_out_of_scope`; §4.2 and
  §5.1.3 reference the old name and are frozen — this erratum is the pointer.
- **Declined deliberately:** I drafted a second control cell pinning the
  pickle non-circumvention, then removed it because it would have taken the
  count to 59 after I had told the integrator the count would stay 58. R4's
  optional item asked for "one sentence folded into the RN-1 rewording" — that
  is what landed, in both declarations. The pickle PIN remains available as an
  optional follow-up if wanted.
- **Fairness, per R4:** NOT a regression. Base was worse on every route, and
  slot 3.2's frozen dataclass admits the identical `__init__` hole. This is
  claim-boundary accuracy.

## §8.3 ERRATUM E6 — RN-2, unlabelled carried successors (+ a count discrepancy)

- **Deviates from:** §5.1.3's class-1 row, which gave a red/green split without
  saying WHY the green cells were green.
- **Fixed:** F1 `862f949d` — a clause in the `TestMutationSurfaceRejected`
  class docstring labelling them as carried successors of the retired
  `test_slots_closed_no_dict` guard, widened to three surfaces.
- **DISCREPANCY REPORTED, not silently matched:** R4 names **five** cells
  (`test_new_attribute_rejected[fresh_value]`, `[present_unset_singleton]`,
  and all three `test_no_instance_dict[*]`). The measured set is **SIX** —
  `test_new_attribute_rejected[missing_singleton]` is also green-on-base and
  belongs to the same class. Derived from `out_redonbase_base_final.txt`:
  class 1 was 12 red / 18 green, and the 12 red are exactly the assignment and
  deletion cells on `status`/`value` across three surfaces, so all six
  `new_attribute` + `no_instance_dict` cells are green at base for the same
  reason (base `__slots__` already closed instances). The committed clause
  covers all six.
- **SETTLED BY MEASUREMENT (ruling R4-a): SIX.** The integrator measured
  rather than arbitrated, at a detached BASE worktree with the tip pin file:
  `test_new_attribute_rejected[missing_singleton]` **PASSES at base in one
  interpreter, one node**; the whole function in one interpreter is 3 passed;
  the whole CLASS in one interpreter is **17 failed / 13 passed** including
  that cell — because earlier assignment cells LAND at base and poison the
  singleton, so the later cell's `assert_intact` trips on damage it did not
  cause.
- **METHOD NOTE for successors (R4-a directs this be recorded):** same file,
  same base — **12 red isolated vs 17 red batched**. This is the second
  independent demonstration (after my own, §4.2) that **the red-on-base number
  is well-defined ONLY per-cell**. Any slot whose pins attempt mutations on
  shared process state must derive red-on-base per-interpreter, or it reports
  collateral as defect evidence. The collateral is itself evidence the defect
  was real — but it is not a count.

## §8.4 ADDENDUM A1 — RN-3 + RN-4, M8 SHA anchor and named checkouts

- **RN-3 corrects:** §4.4, which anchored M8 "at tip" while the instrument
  header honestly printed `c1c7b69a` **DIRTY** (C4 was uncommitted when that
  run happened). The anchor and the instrument disagreed; the instrument was
  right.
- **Re-run at a CLEAN DETACHED checkout of the new tip**
  (`git worktree add --detach tmp/rn3-tip 2f08bd7a`, instruments placed under
  the checkout's gitignored `tmp/`, worktree removed after).
  Instrument header verbatim: `SHA: 2f08bd7a1b251066d68126cc5ad086ef2a1a664c`,
  `worktree dirty: no`. Output `out_m8_rerun_clean_tip.txt`.

| Lock | Red cells | Verdict |
|------|-----------|---------|
| M8-1 | 37 | HOLDS |
| M8-2 | 1 | HOLDS |
| M8-3 | 10 | HOLDS |
| M8-4 | 1 | HOLDS |
| M8-5 | 2 | HOLDS |

**5/5, control run clean first, red-cell counts IDENTICAL to both the
pre-fix run and the verifier's independent replay (37/1/10/1/2)** — so the
fix round changed no lock behaviour.

- **RN-4 (§4.3/§4.4 named no checkout):** the same clean detached checkout of
  `2f08bd7a` is the named tip leg. Measured there:
  **108 passed** (58 pins + 50 must-hold) and **35 passed** conformance
  variable-truth (`out_rn4_clean_tip_suites.txt`). Static checks at the
  worktree tip, unpiped exit codes: `ruff` exit 0 "All checks passed!",
  `mypy` exit 0 (275 files).

## §8.5 ERRATUM E7 — RN-5, the §1.3 macro wall-time arm

- **Deviates from:** §1.3's methodology, which pre-registered "a macro
  observation, e.g. gate wall-time or a variable-heavy script, run at base AND
  tip".
- **Never performed.** It was materially SUPERSEDED by P5 (§2.6) before the
  design was chosen, and I failed to erratum it at the time.
- **DISCHARGED BY THE P5 BOUND, no measurement:** P5 measured **zero**
  `VariableLookup` constructions on variable-read-heavy work, mixed realistic
  scripting, nameref/export churn, and shell startup. A macro wall-time delta
  is bounded by (constructions × per-construction delta); with the construction
  count zero on every non-`${x+w}` workload, and the per-construction delta
  measured at ~0 for the chosen design anyway (§4.5: VALUE 0.989x, production
  shape 1.004x), any macro delta is bounded below measurement noise. Measuring
  it would produce a number with no discriminating power — D-3.4 lesson 8.

## §8.6 D-4B.1-s2 RESTATED under ruling (c-1)

The successor row in §7.3 describes the private-slot clause as a single
weaker clause. Under (c-1) it is an OPEN CLASS covering at least five routes
(§8.2). Narrowing it costs a measured 1.081x (raising `__setattr__`, which
closes assignment/`delattr`/`object.__setattr__` but NOT `__init__`
re-invocation) or 1.13x (frozen dataclass, which also admits `__init__`).
**No available representation closes the whole class** — that is the honest
statement of the boundary, and it is why the control cell demonstrates rather
than merely declares.

## §8.7 DEV FAULT — ruff break masked by a piped exit code (F2 → F3)

- **Fault:** F2 introduced a ruff B018 (bare expression statement inside
  `pytest.raises`) and I committed over it.
- **Why it got through:** I ran
  `ruff check psh tests tools 2>&1 | tail -3 && ... && git commit`. The pipe
  replaced ruff's exit code with `tail`'s, so the `&&` chain saw success while
  ruff was printing "Found 1 error" in the same output I read.
- **Class:** identical to the campaign's unpiped-`pgrep` rule — a pipeline
  that swallows an exit status.
- **RULE EXTENSION ADOPTED AS STANDING (ruling R4-b), effective immediately
  and banked campaign-wide at ceremony so 4B.2+ briefs carry it:** the unpiped
  requirement extends from `pgrep` to **every exit-status-bearing check** —
  `ruff`, `mypy`, pytest subset runs, and any command whose exit code gates a
  commit or a claim. Wording as adopted: *"run it unpiped, or redirect to a
  file and branch on the command's OWN exit status; never pipe a gating check
  through a filter on the same command line."*
- **Commit-cleanliness invariant, stated explicitly (R4-b):** F2 `7d42c79e` is
  a **known ruff-red intermediate commit**. The invariant this slot claims is
  **TIP-clean**; per-commit cleanliness is NOT claimed and was never asserted.
- **Fixed:** F3 `2f08bd7a`, landed as its own visible commit rather than an
  amend so the break and the fix both stay in the record. Re-verified unpiped:
  ruff exit 0, mypy exit 0, 58 cells green.

## §8.8 Fix-round post-state at tip `2f08bd7a`

| Check | Result | Where |
|-------|--------|-------|
| pin cells collected | **58** (unchanged) | worktree |
| pins + 4 must-hold suites | **108 passed** | clean detached `2f08bd7a` |
| conformance variable-truth | **35 passed** | clean detached `2f08bd7a` |
| M8 locks | **5/5 HOLD**, counts 37/1/10/1/2 | clean detached `2f08bd7a` |
| ruff (unpiped exit code) | **exit 0, All checks passed!** | worktree + detached tip |
| mypy (unpiped exit code) | **exit 0**, 275 source files | worktree + detached tip |

No heavy run this round, per R4's fix-round protocol (unit subset + M8
re-run); the full gate re-runs at ceremony attestation. Base-vs-tip perf
(§4.5) is unaffected: F1/F2/F3 changed only docstrings, a class docstring,
and test-cell bodies — no production statement moved. Verified: the only
production file touched in the fix round is `psh/core/variable_lookup.py`,
and its diff is entirely within the module docstring.

**LEDGER RE-FROZEN at this line.** New tip
`2f08bd7a1b251066d68126cc5ad086ef2a1a664c`.
