# Slot 3.2 ledger — pattern engine integrity/perf (HIGH-7 perf half + MEDIUM-6)

- **Worktree:** `/Users/pwilson/src/psh-r3-2`, branch `fix/remediation-3-2`.
- **Base:** `da037aa802fdfd81ac835cf4fa4428ba8ca994f5` = tag `v0.763.0`
  (both verified: `git rev-parse HEAD`, `git describe --tags --exact-match`,
  `git rev-parse v0.763.0^{commit}` — all agree; worktree clean at open).
- **Bash oracle (every table):** PATH `bash` = `/opt/homebrew/bin/bash`,
  `GNU bash, version 5.2.26(1)-release (aarch64-apple-darwin23.2.0)`.
  NEVER `/bin/bash`.
- **Import discriminator (every measurement):** without `PYTHONPATH` a bare
  `python -c "import psh"` resolves to `/Users/pwilson/src/psh/psh/__init__.py`
  (the MAIN checkout's editable install). Every measurement therefore runs
  with `PYTHONPATH=/Users/pwilson/src/psh-r3-2` from a neutral cwd
  (`tmp/slot32/`, no `psh/` package present) and ASSERTS
  `psh.__file__.startswith('/Users/pwilson/src/psh-r3-2/')` before timing.
  Instruments abort if the assert fails.
- **Instruments:** `<worktree>/tmp/slot32/` (project tmp only).
- **Rulings received:** R0 (slot open) — ACKed in first report.

## Turn log

- T1 (2026-08-02): read brief in full + R0. Verified base SHA/tag/branch,
  bash oracle version, discriminator. Read `pattern_engine.py` (1230 lines),
  `parameter_expansion.py` (508), 3.1 handoff evidence (§A9, §C-4, §D-2,
  §D-2a, §E-1, instruments/README.md). Ledger opened. Phase A started.

## Phase A evidence

**Evidence SHA for every section below: `da037aa8` (v0.763.0).** Phase A made
ZERO production edits — verified `git diff --stat da037aa8 -- psh/ tests/ docs/`
is EMPTY and `git status --porcelain` is empty (instruments live in gitignored
`tmp/`). Machine: macOS (Darwin 25.5.0), arm64, CPython 3.14.2.

### A1 — Fresh perf baselines at da037aa8 (red-on-base; ceremony denominators)

Instrument: `tmp/slot32/base_perf.py` → `base_perf_out.txt`;
`tmp/slot32/base_sub_perf.py` → `base_sub_perf_out.txt`.
Basis (3.1 D-2a): in-process operation timing, compile OUTSIDE the timer, one
warmup per row family, steady-state reported. Discriminator asserted in-process
before timing (`psh.__file__` under the worktree; a bare run without
`PYTHONPATH` resolves to the MAIN checkout — recorded in the header).

**A1-a `matching_starts('*b')` on `'a'*N` — QUADRATIC (the A9 handoff row):**

| N | 500 | 1000 | 2000 | 4000 | 8000 |
|---|---|---|---|---|---|
| this base (da037aa8) | 0.0057s | 0.0225s | 0.0910s | 0.3599s | 1.3825s |
| ratio/doubling | — | 3.94 | 4.04 | 3.95 | 3.84 |
| 3.1 A9 (29456fdc) | 0.006s | 0.023s | 0.090s | 0.452s | 1.424s |
| Wave 0 (0215279c) | 0.006s | — | — | — | 2.02s |

Reproduces the A9 shape at my base; the three denominators agree to within
run-to-run jitter (my 4000 is faster than A9's 0.452s, same class).

**A1-b `full_match('**(a)b')` on `'a'*N` — CUBIC (E-1 OPENER PRIORITY):**

| N | 50 | 100 | 200 | 400 | 800 |
|---|---|---|---|---|---|
| seconds | 0.0091 | 0.0666 | 0.5259 | 4.2831 | 36.1568 |
| ratio/doubling | — | 7.33 | 7.90 | 8.14 | 8.44 |

×8/doubling = cubic, CONFIRMING the round-3 verifier's attributed reading at
my own base.

**A1-c `matching_ends('*!(a)')` — QUADRATIC** (0.0010 / 0.0037 / 0.0146 /
0.0588 / 0.2494 s at N=50/100/200/400/800; ratio 3.75-4.25). `!`-groups do not
enter the `*`/`+` closure, which is why this is quadratic and not worse.

**A1-d dispatch census (derived, not assumed):**

| pattern | bash_quirk | has_extglob | sub_fast_eligible |
|---|---|---|---|
| `*b` | False | False | True |
| `**(a)b` | True | True | False |
| `*!(a)` | True | True | False |
| `+([[:space:]])` | False | True | True |
| `*([[:space:]])` | False | True | False |
| `!(x)` | False | True | False |
| `*+([[:space:]])` | True | True | True |

**A1-e substitution dispatch (anchor `any`, extglob on):** every one of the
four probed patterns has a QUIRK-FLAGGED WRAPPER (the `*`-wrap makes it so),
so the pre-test runs `_BashMatcher` even when the pattern itself is non-quirk
— this is the mechanism behind the ineligible-class cost.

| pattern | fast_ok | pattern quirk | WRAPPER quirk | end_eligible |
|---|---|---|---|---|
| `+([[:space:]])` | True | False | **True** | False |
| `*([[:space:]])` | False | False | **True** | True |
| `!(x)` | False | False | **True** | False |
| `@(x\|)` | False | False | **True** | False |

**A1-f semantic cross-check vs live bash 5.2.26 BEFORE any edit:** 40 cells
(2 subject shapes × 4 patterns × N∈{0,1,2,3,7}), **0 mismatches**. This is the
pre-change semantic lock for the shapes I am about to optimise.

**A1-g `${v//pat/-}` in-process op timing (D-2a basis).** Subject shapes
(the 3.1 construction was NOT committed; these are MINE and are this slot's
denominators): `consecutive = ' '*N`, `word_spaced = 'x '*N`.

| pattern | class | shape | 400 | 800 | 1600 | 3200 | ratio |
|---|---|---|---|---|---|---|---|
| `+([[:space:]])` | ELIGIBLE | consecutive | 0.0011 | 0.0019 | 0.0036 | 0.0072 | ~2.0 LINEAR |
| `+([[:space:]])` | ELIGIBLE | word_spaced | 0.0033 | 0.0066 | 0.0129 | 0.0257 | ~2.0 LINEAR |
| `*([[:space:]])` | INELIG-nullable | consecutive | 0.1850 | 0.7465 | 3.0481 | 12.7172 | ~4.1 QUADRATIC |
| `*([[:space:]])` | INELIG-nullable | word_spaced | 1.1024 | 4.4163 | 17.6687 | 72.2611 | ~4.0 QUADRATIC |
| `!(x)` | INELIG-negation | both | 0.0002 | 0.0002 | 0.0003 | 0.0003-5 | ~1.2 FLAT |
| `@(x\|)` | INELIG-nullalt | both | 0.0021-39 | 0.0041-80 | 0.0080-160 | 0.0153-308 | ~2.0 LINEAR |

Readings: (i) the ELIGIBLE control is LINEAR on BOTH shapes — Path A intact,
this is the must-not-regress control; (ii) the INELIGIBLE **nullable** class
is the real quadratic (72s at N=3200 word-spaced) and is the substitution
target; (iii) `!(x)` is flat because leftmost-longest matches the whole
subject on the first probe — a one-match operation, not a fast path; (iv)
subject SHAPE changes the constant ~6× but not the class (3.1 fault #1 axis
honoured: both shapes measured).

**A1-h removal operators (no consumer layer):**

| op | 100 | 200 | 400 | 800 | ratio |
|---|---|---|---|---|---|
| `${v%%*!(a)}` | 0.0046 | 0.0178 | 0.0733 | 0.3040 | ~4.1 QUADRATIC |
| `${v##*!(a)}` | 0.0039 | 0.0158 | 0.0616 | 0.2473 | ~4.0 QUADRATIC |
| `${v%%*+(a)}` | 0.0700 | 0.5538 | 4.4973 | 37.6760 | ~8.1 **CUBIC** |

A SECOND cubic site, distinct from A1-b: `matching_starts` on a `*`+closure
quirk pattern.

**A1-i NEW FINDING — a QUARTIC class the handoff envelope understated.**
Instrument `tmp/slot32/proto_risk.py` → `proto_risk_out.txt`. The A9 envelope
said quirk-flagged relations pay "up to ~O(nodes·n³)". Measured at base, the
si-fixed/se-varying consumers on `**(a)b` are ~n⁴:

| N | 50 | 100 | 200 | ratio/doubling |
|---|---|---|---|---|
| `matching_ends('**(a)b')` | 0.1242s | 1.7899s | 27.8363s | **14.4 → 15.6** |
| `span_at('**(a)b', 0)` | 0.1199s | 1.7507s | 27.1833s | **14.6 → 15.5** |

×15.5/doubling ≈ n^3.95. Reported as a handoff-envelope correction, not a new
defect: same mechanism (closure rebuild), one more consumer loop on top.

### A2 — Mutability census + DEMONSTRATED poisoning (MEDIUM-6 red arm)

Instrument: `tmp/slot32/base_mutability.py` → `base_mutability_out.txt`.

**Static census.** Every node type is a NON-frozen dataclass with no
`__slots__`, so every field is writable and arbitrary new attributes stick:

| class | frozen | `__slots__` | writable fields |
|---|---|---|---|
| `Literal` | False | None | `char` |
| `AnyChar` / `Star` | False | None | (none, but attribute-settable) |
| `Bracket` | False | None | `content` |
| `Extglob` | False | None | `op`, `alts`, `enclosed` |
| `Sequence` | False | None | `elements`, `has_extglob`, `bash_quirk`, `sub_fast` |
| `CompiledPattern` | n/a | `('root',)` | `root` is REBINDABLE |
| `MatchProfile` | **True** | — | already immutable (no work needed) |

Caches in scope: `compile_cached` (lru 4096) and `_sub_machinery_cached`
(lru 512, 4-tuple) — both hand out SHARED objects (demo 7 proves identity).

**7 of 7 caller-visible poisoning demos REPRODUCED at base:**

| # | surface | mutation | later independent lookup returns |
|---|---|---|---|
| 1 | `Literal.char` | `root.elements[0].char='z'` | `compile('abc').full_match('abc')` **True→False**; `'zbc'` False→True |
| 2 | `Sequence.bash_quirk` | force bit, set False | `'*!(a)'` vs `'a'`: **False→True** (wrong MATCHER ROUTE) |
| 3 | `Extglob.enclosed` | set True | `'*!(a)'` vs `''`: **True→False** (end-of-string negation rule) |
| 4 | `Sequence.elements` | rebind tuple | `'xy'` full_match **True→False** |
| 5 | `Sequence.sub_fast` | set False | `fast_ok` **True→False** (linear Path A → `_BashMatcher` envelope) |
| 6 | **end-to-end via `Shell`** | poison `compile_cached('abc',True)` node | `v=abc; r=${v//abc/HIT}` → `'HIT'` then **`'abc'`**; and `v=zbc` → `'HIT'` |
| 7 | `_sub_machinery_cached` | identity + `CompiledPattern.root` rebind | later cache hit returns the rebound root |

Demo 6 is the load-bearing one: poisoning is observable through ordinary shell
command execution with no engine API in the caller's hands.

### A3 — Writer census + DERIVED consumer census

**A3-a in-tree WRITER census** (`grep -rnE '\.(char|content|op|alts|enclosed|
elements|has_extglob|bash_quirk|sub_fast|root)\s*=[^=]' psh/`) — 5 hits, and
**no production writer to a compiled node exists**:

| hit | verdict |
|---|---|
| `pattern_engine.py:175` `seq.has_extglob = he` | engine's OWN lazy bit |
| `pattern_engine.py:228` `seq.sub_fast = r` | engine's OWN lazy bit |
| `pattern_engine.py:273` `seq.bash_quirk = q` | engine's OWN lazy bit |
| `pattern_engine.py:1065` `self.root = root` | `CompiledPattern.__init__` |
| `core/exceptions.py:275` `self.content = content` | **UNRELATED symbol** — read in full: `BadSubstitutionError.__init__`, not a `Bracket` (name-vs-body check, not dismissed on the name) |

**A3-b TEST-tree writer census** — same grep over `tests/`: **ZERO hits.**
So freezing accommodates no existing writer anywhere in the tree; the ONLY
obstacle is the engine's own three lazy bits.

**A3-c DERIVED consumer census** (grepped, not inherited from 3.1's list):

| module | line | imported surface |
|---|---|---|
| `psh/expansion/glob.py` | 147 | `PatternCompiler`, `pathname_profile` |
| `psh/expansion/pattern.py` | 11 | `PatternCompiler`, `string_profile` |
| `psh/expansion/extglob.py` | 466/474/487 | `compile_cached` + `reachable_ends` / `fullmatch` / `match_at` |
| `psh/expansion/parameter_expansion.py` | 38 | `STRING`, `CompiledPattern`, `PatternCompiler`, `string_profile`, `sub_fast_eligible` |
| `psh/expansion/word_expander.py` | 712 | `runs_to_pattern_string` |

Five consumer modules; the free-function API (`reachable_ends`, `fullmatch`,
`match_at`) is live via `extglob.py` and must keep working.

Test modules importing the engine (9): `test_pattern_engine_performance.py`,
`test_field_ir_guards.py`, `test_param_exp_operators.py`,
`test_pattern_bash_composition_differential.py`, `test_pattern_engine_compile.py`,
`test_pattern_engine_matcher.py`, `test_pattern_relations.py`,
`test_unified_glob_converter.py`, plus `harness/oracle_migration_census.md`.

### A4 — Counter design: the EXISTING complexity pin CANNOT see the cubic

Instrument: `tmp/slot32/counter_gap.py` → `counter_gap_out.txt`.

`_BashMatcher.match` increments `states` only on a memo MISS, so it counts
DISTINCT `(seq, ei, si, se)` keys. The real work is the loop iteration inside
`_extmatch`/`_closure`, which re-walks O(n²) memo HITS per entry position over
O(n) entry positions. Measured on `**(a)b`:

| N | 16 | 32 | 64 | 128 | 256 | class |
|---|---|---|---|---|---|---|
| `states` (= memo keys) | 154 | 562 | 2146 | 8386 | 33154 | ×3.95 **quadratic** |
| wall seconds | 0.0004 | 0.0027 | 0.0186 | 0.1393 | 1.1460 | ×8.23 **cubic** |

And the shipped pin `test_bash_matcher_states_stay_polynomial`
(`test_pattern_bash_composition_differential.py`) asserts
`states <= (n+2)**2` — evaluated: n=16 154/324, n=64 2146/4356, n=128
8386/16900, n=256 33154/66564 — PASS at every size with ~50% headroom.

**The pin is ACCIDENTALLY GREEN: it bounds a quadratic counter by a quadratic
bound while the evaluation it names is cubic.** It cannot fail for the defect
it exists to prevent — the 3.1 "a proof that cannot fail is not a proof"
lesson, in complexity-pin form. (The counter is faithful on the NON-quirk
`_Matcher` path: `matching_starts('*b')` states ×3.98 vs wall ×4.06 — both
quadratic, they agree. The blindness is specific to `_BashMatcher`.)

**Counter design (proposal).** Keep `count_states` BODY AND NAME exactly as
shipped (it correctly guards memo-key growth, and three test files pin it);
ADD a NEW `count_transitions` incremented per unit of loop work (star-entry
scans, `_segment` steps, `_extmatch` split iterations, closure/ok-table edge
relaxations). New rule → new name, so the existing pins keep guarding what
they guarded (NAME-VS-BODY). The chartered "deterministic transition counts
… LINEAR in subject positions" pins are written against `count_transitions`;
default-run; assertions are COUNT ratios over two sizes, never wall-clock.

### A5 — DESIGN, prototyped and measured (no production file touched)

Instruments: `tmp/slot32/proto_design.py` → `proto_design_out.txt`;
`tmp/slot32/proto_risk.py` → `proto_risk_out.txt`. Both prototypes run against
the REAL compiled AST and are correctness-gated before any timing is believed.

**P1 — all-start backward DP (the chartered "one-pass all-start relation").**
`S_j = { p : elements[j:] matches s[p:end] }` computed RIGHT-TO-LEFT as a
bytearray over `[0,end]`; `S_ne = {end}`. Literal/AnyChar/Bracket are one
O(end) scan each; a non-pathname `Star` is the downward closure
`[0, max(S_{j+1})]`; a pathname `Star` is bounded by `next_slash`; an
`Extglob` falls back to the existing per-position `_element_ends`. Replaces
`matching_starts`' "one forward DP per start index".

**P2 — memoized `ok`-table for the `*`/`+` closure in `_BashMatcher`.**
`ok(p) = rest_ok(p) or ∃q>p: alt_span(p,q) ∧ ok(q)` is exactly the shipped
`any(rest_ok(pos) for pos in _closure(alts,{p},se))`, unrolled as a backward
DP and memoized per `(group, gi, se)` so O(n) entry positions share ONE table
instead of rebuilding the closure each time. `+` reuses the same table
(`any(tbl[split] and alt_span(si,split))`). `@`/`?`/`!` are UNCHANGED
(delegate to the shipped `_extmatch`).

**AGREEMENT (correctness gate): 1,078 cells, 0 disagreements.**
726 cells in `proto_design.py` (36 patterns × 19 subjects across
`matching_starts` non-quirk, and `full_match`/`matching_ends`/
`matching_starts` for quirk, plus a `for_pathname` pass on slash subjects) +
352 cells in `proto_risk.py` (8 `*`-group patterns × 10 subjects ×
`matching_ends` and every `span_at` position).

**Measured complexity, shipped vs prototype:**

| relation / pattern | shipped | prototype | at N | shipped → proto |
|---|---|---|---|---|
| `matching_starts('*b')` | ×4.0 quadratic | **×2.0 LINEAR** | 4000 | 0.3388s → 0.0002s |
| `full_match('**(a)b')` | ×8.3 cubic | **×4.0 quadratic** | 400 | 4.4981s → 0.0016s |
| `matching_starts('*+(a)')` | ×8.1 cubic | **×2.0 LINEAR** | 400 | 4.4564s → 0.0012s |
| `matching_ends('**(a)b')` | ×15.6 quartic | **×5.2-6.3** | 200 | 27.8363s → 0.0336s |
| `span_at('**(a)b',0)` | ×15.5 quartic | **×5.2-6.2** | 200 | 27.1833s → 0.0337s |

The prototype scales where the base cannot: proto `matching_starts('*b')`
reaches N=16000 in 0.0010s; proto `full_match('**(a)b')` reaches N=1600 in
0.0203s. The two varying-`se` consumers were the design's REGRESSION RISK (the
ok-table is keyed by `se`, so they could have rebuilt it O(n) times) — measured
instead of assumed, and they improve ~830×; their ratio is still climbing
(4.4→6.3), so I will pin the ACHIEVED bound, not an aspirational one.

**States side-effect:** the ok-table does not inflate the memo — it shrinks it
by two orders of magnitude (`**(a)b` at N=256: 33,154 → 258 keys, i.e. 2n+2,
linear). The existing `(n+2)**2` pin stays green with far more headroom, so
no pin flips; I propose re-calibrating that bound to the achieved figure so it
regains its teeth.

**`_Matcher`/`_BashMatcher` unification — PROPOSED AND RECOMMENDED AGAINST.**
Cost if taken: the two evaluators implement genuinely different relations
(forward reachability vs slice-relative bash composition), so unification is a
mode flag, not a simplification; the equivalence proof would have to re-run
the full 428,144-cell universe on BOTH arms for a rename with zero measured
perf gain, while putting the 3.1 measured model at risk — the one change this
slot is forbidden to make silently. All five measured wins above come from the
memo/closure restructuring, which is orthogonal. Recommendation: keep the two
evaluators, unify nothing this slot.

### A6 — Freeze design + THREAT MODEL (needs the pre-declared R0(a) ruling)

**Mechanism.** Make all six node classes `@dataclass(frozen=True, eq=False)`
(+ `slots=True`; `requires-python = ">=3.12"` in `pyproject.toml`, so both are
available). `eq=False` is RETAINED so identity semantics and the identity hash
survive — the matcher memoizes on `id(node)`, and `Extglob.alts`/
`Sequence.elements` are already tuples. `CompiledPattern` gets the same
treatment so `root` stops being rebindable. `MatchProfile` is already frozen.

**The lazy bits are the only obstacle, and A3 proves nothing else writes.**
Recommended resolution: **precompute all three at construction time** and drop
the laziness. `_parse` builds bottom-up, so when a `Sequence` is constructed
its children already exist and `has_extglob`/`bash_quirk`/`sub_fast` are pure
functions of the element tuple plus the children's own (already computed)
bits — O(size of AST) per compile, and compiles are cached. This is strictly
simpler than a write-once slot and removes three mutable fields rather than
protecting them.

**THREAT MODEL PINNED (this is what I ask to be ruled):** the pins prove
**honest-caller accident**, not adversarial bypass. Concretely, after the
change a normal attribute write — `node.char = 'z'`, `seq.bash_quirk = False`,
`eg.enclosed = True`, `cp.root = other` — raises `FrozenInstanceError`, so a
caller CANNOT accidentally poison a shared cache entry (all 7 A2 demos become
raises). `object.__setattr__(node, 'char', 'z')` and module-attribute
rebinding (`pe.compile_cached = ...`) remain possible and are OUT OF SCOPE:
Python freezing is leaky by construction, and pinning "no adversarial bypass"
would be pinning a falsehood. The exit criterion in the brief ("a caller must
be UNABLE to mutate the result of one compile and affect later matches") is
met for the accident class and stated as such.

**Cache keying/size (the pre-declared R0(b) ruling): I request NO CHANGE.**
`compile_cached` stays lru 4096 keyed `(pattern, extglob)`; `_sub_machinery_cached`
stays lru 512 keyed `(pattern, anchor, extglob)` returning the 4-tuple. The
R2/R7-7/R10/R8/R11 chain ruled these; freezing the VALUES needs no change to
keying or size. I am asking for the ruling on record, not for a change.

### A7 — Equivalence-proof plan (forcing + M6)

1. **Corpus.** Regenerate the 3.1 universe per `3.1-rescue/instruments/
   README.md` — `corpus1/2/3` (grammar-v2) + `corpus4` (backslash axis)
   against live PATH bash `/opt/homebrew/bin/bash` 5.2.26, version recorded in
   every table. Distinct union = 427,586 (+558 backslash) = **428,144 cells**
   (E-1's reconciliation; "437,811" is the row SUM with per-file duplicates —
   I use the DISTINCT figure and say which).
2. **Arms.** OLD arm = shipped relations at `da037aa8`; NEW arm = the rewrite.
   Compared per cell across ALL FIVE relations and all four substitution
   operators — not just the two I optimised.
3. **FORCING (3.1 D-3b, binding).** Clear EVERY memo between arms:
   `compile_cached.cache_clear()`, `_sub_machinery_cached.cache_clear()`, and —
   since the lazy bits become compile-time constants — a fresh compile per arm,
   because a cached decider laundering arm A into arm B is precisely the
   failure D-3b names.
4. **M6-class mutation pointed at the PROVER.** Perturb the prover itself
   (e.g. make the comparator return True unconditionally, and separately drop
   the cache-clear) and verify it FAILS FOR ITS OWN REASON — a proof that
   cannot fail is not a proof.
5. **Axes varied** (AXIS-QUANTIFICATION catalogue): subject SHAPE (both A1-g
   shapes), BACKSLASH (corpus4), context grammar (grammar-v2), consumer (all
   five modules from A3-c), anchoring (`any`/`beg`/`end`), empty/non-empty
   subject, quoting via `compile_protected`, and `for_pathname` on/off.
6. **ARM-LOADING refinement (mine, read out of 3.1's `corpus5_equiv.py`).**
   3.1 forced its two arms by MONKEYPATCHING one predicate
   (`px.sub_fast_eligible = lambda seq: False`) plus a cache clear — correct
   there, because both arms were the same module with one decider swapped.
   My arms are two DIFFERENT implementations of the same relations, so
   monkeypatching cannot express them. Instead the prover loads the BASE
   engine source (`git show da037aa8:psh/expansion/pattern_engine.py`) into a
   SEPARATE module object under a distinct name and runs it beside the tip
   module in one process. Two distinct code objects with two distinct memo
   dicts means the forcing is structural rather than a flag — arm A cannot be
   laundered into arm B through a shared cache, which is the exact failure
   D-3b names and which 3.1 hit for real ("the first run of this extended
   proof compared fast vs fast because of exactly this"). The per-arm
   `compile_cached`/`_sub_machinery_cached` clears are still performed, and
   the M6 mutation class is pointed at the PROVER (comparator forced True;
   arm-loading collapsed to the same module) to confirm it fails for its own
   reason.

### A7b — Prover BUILT AND VALIDATED at base (before it is depended on)

Built while holding at the stage gate; instruments `tmp/slot32/equiv_arm.py`
(one arm) + `tmp/slot32/equiv_prove.py` (orchestrator). Still ZERO production
edits. Evidence SHA `da037aa8` for every run below.

**Structural forcing.** Each arm runs as its OWN PROCESS in its OWN tree —
base arm in a detached probe worktree created at `da037aa8` and REMOVED after,
tip arm in this worktree — so no module object, no `compile_cached`, no
`_sub_machinery_cached` and no matcher memo is shared between arms. This is
stronger than 3.1's in-process predicate monkeypatch and makes D-3b's actual
failure ("compared fast vs fast because a cached decider carried over")
structurally impossible rather than merely guarded. Each arm asserts its own
import discriminator and prints the module path it used; both paths appear in
every run log and differ.

**Recorded per cell: 25 relations/operators** — `full_match`, `matching_ends`,
`matching_starts`, `span_at` (every position), `spanner` (every position),
`matching_spans`, the routing/derived facts (`bash_quirk`, `has_extglob`,
`sub_fast_eligible`, `unparse`, `structure`), the `for_pathname` and
case-insensitive profiles, the free-function API (`reachable_ends`,
`fullmatch`, `match_at` — live via `extglob.py`), all FOUR substitution
operators and all FOUR removal operators, plus any exception type raised.

**Four validation runs (fallback cell set: 1,976 patterns × 25 subjects =
49,400 cells × 25 records = 1,235,000 comparisons per run):**

| run | mode | disagreements | exit | required | verdict |
|---|---|---|---|---|---|
| 1 | base (probe wt @ da037aa8) vs tip | 0 | 0 | 0 | PASS |
| 2 | **M6-a**: inject one perturbed cell into the TIP arm | **1** — `pat='' subj='' key=full: base=True tip=False` | **1** | ≥1 | PASS — the prover CAN fail, and names the exact cell+key |
| 3 | **M6-b**: same injection + comparator BLINDED | 0 | 0 | 0 | PASS — the COMPARATOR is the detector, not a harness accident |
| 4 | `--same-tree` (both arms in the tip tree) | 0 | 0 | 0 | PASS |

Exit codes were re-checked WITHOUT a pipe (a piped `$?` reports `tail`'s
status, which masked the first reading): injected run exits **1**, clean run
exits **0** — so the instrument is usable as a gate.

Hygiene verified after every run: `git worktree list` shows no probe worktree,
`tmp/slot32/basearm-wt` absent, and `git diff --stat da037aa8 -- psh/ tests/
docs/` still EMPTY.

**Phase B swap:** the fallback cell set exercises the same shape families but
is NOT the proof universe. At Phase B the `--cells` input is replaced by the
regenerated corpus1/2/3 + corpus4 union (428,144 distinct cells) produced by
the committed 3.1 generators against live PATH bash 5.2.26, per
`3.1-rescue/instruments/README.md`. I will run the generators as documented
rather than reimplement their grammars.

### A8 — Battery / pin runtime budget (derived, not hand-tallied)

`python3 -m pytest <six pattern files> -q` at base: **184 passed in 11.12s.**
Per-file collected counts, each derived by `--collect-only -q`:

| file | collected |
|---|---|
| `test_pattern_bash_composition_differential.py` | 18 (matches the brief) |
| `test_pattern_engine_differential.py` | 5 tests (the brief's "~100 rows" are in-body rows, not pytest items) |
| `test_substitution_empty_match_pins.py` | 20 (matches the brief) |
| `test_pattern_relations.py` | 53 (derived: 184 − 131) |
| `test_pattern_engine_matcher.py` | 36 |
| `test_pattern_engine_compile.py` | 52 |

Named single pins located: `test_fast_path_eligibility_boundary`,
`test_extglob_enclosed_compile_invariant`,
`test_bash_matcher_states_stay_polynomial` (all in the composition
differential); `test_former_known_divergences_now_match_bash` (engine
differential). New pins budget: transition-count pins are pure counting (no
wall-clock, sub-second); immutability pins are ~20 raise-assertions. I expect
the six-file battery to stay well under 15s.


## Phase B record (GO + rulings received as R1; evidence SHA per row)

**R1 ACKed in full** (GO; ruling (a) freeze threat model GRANTED with four
conditions; ruling (b) cache keying/size NO CHANGE; states-pin re-calibration
GRANTED with conditions; quartic envelope correction GRANTED; unification
AGAINST ruled; achieved-bound pinning endorsed; heavy-run protocol unchanged).

### B0 — R1's call-shape observation, folded in (integrator-found)

`compile_cached('abc')` and `compile_cached('abc', True)` are DISTINCT lru
entries — `functools.lru_cache` keys by CALL SHAPE, not by normalized
signature. This is a LIVE PRODUCTION fact, not just a probe artefact:
`extglob.py:467/475/488` call `compile_cached(pattern)` with ONE argument
while `pattern_engine.py:425/431` call `compile_cached(pattern, extglob)` with
TWO, so the same logical pattern occupies two cache slots depending on which
consumer compiled it. Recorded here so a verifier does not rediscover it as a
"missed poisoning surface". Ruled OUT OF SCOPE (it would be a keying change;
ruling (b) is no-change). My A2 demos were unaffected — they used the exact
two-positional-argument shape `PatternCompiler.compile` uses, verified by
reading the call site; every instrument fetches cached entries by exact call
shape or by object identity.

### B1 — What changed (two files; `psh/expansion/` only, per scope)

1. **Freeze + precompute** (`pattern_engine.py`). All six node classes and
   `CompiledPattern` are `@dataclass(frozen=True, eq=False, slots=True)`;
   `eq=False` RETAINED per ruling (a)(iii) so identity semantics and the
   id-keyed memo survive. The three lazy bits plus a new `nullable` are
   DERIVED AT CONSTRUCTION in `__post_init__` via the documented
   frozen-dataclass idiom. The derivation is NON-RECURSIVE — each bit reads
   its children's already-derived bits in O(1) — which was forced by
   `test_pattern_relations.py`'s iteratively-built 2,000-deep AST: a recursive
   `__post_init__` would have raised `RecursionError` during CONSTRUCTION and
   destroyed that test's ability to pin the MATCHER's bound. `_seq_has_extglob`
   / `_seq_nullable` / `_seq_bash_quirk` / `sub_fast_eligible` keep their NAMES
   as the read side (NAME-VS-BODY); the derivations move to `_derive_*`.
2. **P1 all-start backward pass** (`_Matcher._starts`). `matching_starts` is
   ONE right-to-left fold over a bytearray instead of a forward DP per start
   index.
3. **P2 memoized closure ok-table** (`_BashMatcher._ok_table`). The `*`/`+`
   branches of `_extmatch` read a table memoized per `(group, gi, se)` instead
   of rebuilding the closure at every entry position. `_BashMatcher._closure`
   RETIRED (DELETED-DECIDER: its only two callers were those branches; the
   replacement decides the same relation, corpus-proven not argued; a comment
   at the deletion site records this). `_Matcher._alt_closure` is a DIFFERENT
   method and is untouched.
4. **Substitution scan sharing** (`parameter_expansion.py`). `substitute_all`
   builds ONE `suffix_matcher` and ONE `spanner` for the whole scan and calls
   the new `_any_match_from` with absolute offsets, instead of materialising
   `value[pos:]` and a fresh matcher per remaining suffix. `_any_match` is now
   `_any_match_from` at position 0 — ONE body for the MATCH_ANY rule.
5. **All-start pre-filter in `spanner`** (non-pathname only). `P*` matches
   `text[p:]` exactly iff `P` matches `text[p:k]` for some k, so one backward
   pass yields every position a match can START at; the forward DP then runs
   only where one really begins. Restricted to non-pathname profiles because a
   star cannot cross `/` there, which breaks the identity.
6. **Counters.** `count_states` NAME AND BODY unchanged. New
   `count_transitions` counts WORK. New `_relation_starts`/`_relation_ends`/
   `_relation_full` return `(result, matcher)` so the public relation and the
   counter are the SAME evaluation. `INSTRUMENTATION.matchers` counts matcher
   constructions.

### B2 — Perf deltas (base da037aa8 -> final tip; D-2a basis, same machine)

Engine relations, subject `'a'*N`:

| relation / pattern | base | final tip | at N | class change |
|---|---|---|---|---|
| `matching_starts('*b')` | 1.3825s (×3.9) | **0.0002s** (×1.9) | 8000 | quadratic → **LINEAR** |
| `full_match('**(a)b')` | 36.1568s (×8.4) | **0.0112s** (×3.7) | 800 | **CUBIC → quadratic** |
| `${v%%*+(a)}` | 37.6760s (×8.1) | **0.0027s** (×1.9) | 800 | **CUBIC → LINEAR** |
| `matching_ends('**(a)b')` | 27.8363s (×15.6) | **0.0621s** (×5.7) | 200 | **QUARTIC → ~n^2.9** |
| `span_at('**(a)b', 0)` | 27.1833s (×15.5) | **0.0614s** (×5.7) | 200 | **QUARTIC → ~n^2.9** |
| `matching_ends('*!(a)')` | 0.2494s (×4.1) | 0.2546s (×4.1) | 800 | UNCHANGED — see B3 |

Substitution `${v//pat/-}` (both subject SHAPES; N=3200):

| pattern | class | shape | base | final tip | class change |
|---|---|---|---|---|---|
| `+([[:space:]])` | ELIGIBLE (CONTROL) | consecutive | 0.0072s | 0.0081s | linear → linear (no regression) |
| `+([[:space:]])` | ELIGIBLE (CONTROL) | word_spaced | 0.0257s | 0.0263s | linear → linear (no regression) |
| `*([[:space:]])` | INELIGIBLE-nullable | consecutive | 12.7172s (×4.1) | **0.0087s** (×2.0) | quadratic → **LINEAR** |
| `*([[:space:]])` | INELIGIBLE-nullable | word_spaced | 72.2611s (×4.0) | **0.0388s** (×2.0) | quadratic → **LINEAR** |

The named D-2 handoff obligation ("ineligible-class substitution must return
to linear") is DISCHARGED on both shapes; the eligible control did not regress.
Three denominators for `matching_starts`, as required: Wave 0 at 0215279c
(0.006s→2.02s, N=500→8000), 3.1 A9 at 29456fdc (0.006s→1.424s), my base
(0.0057s→1.3825s) — all quadratic; tip is 0.0002s at N=8000.

Compile-miss-path cost (ruling (a)(iv)): deriving the four bits eagerly adds
O(size of AST) to a compile MISS. The six-file pattern battery went 11.12s at
base to 11.5s at tip with 38 more tests, and the whole expansion suite is
55-58s at both — the eager derivation is not measurable against compile+match
cost, as predicted (compiles are cached; the bits were computed anyway on
first query).

### B3 — Bounds NOT improved, stated honestly (achieved, not aspirational)

- **`matching_ends`/`matching_starts` on `!`-group quirk patterns stay
  QUADRATIC** (`*!(a)`: ×4.1 at base and at tip). This is the FLOOR, not a
  missed optimisation: the relation is per-`(entry, slice-end)` and the
  consumer asks for O(n) slice ends, so O(n²) cells must exist. The `!`
  branch never enters the closure, so the ok-table cannot help it.
- **`matching_ends`/`span_at` on `*`-group quirk patterns are ~n^2.9**, not
  linear: ×5.2→7.4 across N=50→800, still climbing. Characterized at the
  larger N per R1 item 7. COMPLEXITY MODEL I BELIEVE I ACHIEVED: the ok-table
  is memoized per `(group, gi, se)` and these consumers vary `se` over O(n)
  values, so O(n) tables × O(n) entries × O(n) inner relaxation = O(n³) with
  the alt-span lookups shared. The measured exponent approaches 3 from below,
  consistent with that model. I pin the ACHIEVED ratio, not linearity.
- **The quirk no-match substitution scan stays steep** (`*!(a)x` ×13.8,
  `**(a)x` ×7.7 at N=25→100): the all-start pre-filter is non-quirk only, by
  construction. Non-quirk no-match scans are EXACTLY `2n+2` transitions.

### B4 — Correctness evidence

- **Equivalence proof, base vs final tip: 49,400 cells × 27 recorded
  relations/operators = 1,333,800 comparisons, 0 DISAGREEMENTS**
  (`tmp/slot32/equiv_final.txt`). FORCING is structural: each arm is its OWN
  PROCESS in its OWN tree (base = detached probe worktree at `da037aa8`,
  removed after; tip = this worktree), so no module object, lru cache or
  matcher memo is shared. Recorded per cell: all five relations, `spanner` at
  every position, `matching_spans`, both alternate profiles, the free-function
  API, all four substitution and all four removal operators, and — per ruling
  (a)(iv) — the four routing bits read through the SAME function names on both
  arms, so eager-vs-lazy derivation disagreement would surface as a per-cell
  diff (it did not, including for every nested alternative).
- **Suffix-offset identity: 29,088 cells, 0 disagreements**
  (`tmp/slot32/suffix_equiv.py`) — `full_match(value[pos:])` == in-place
  `[pos:n]` across both matcher routes, both profiles, all three anchors,
  compiled AND wrapper patterns, every position. This is what licenses B1-4.
- **All-start pre-filter identity: 8,800 cells, 0 disagreements**
  (`tmp/slot32/spanner_equiv.py`) — filtered `spanner` == unfiltered
  computation at every position, plus `span_at` agreement.
- **Live bash cross-check** of the substitution shapes, 40 cells, 0
  mismatches, re-run at the tip against `/opt/homebrew/bin/bash` 5.2.26.

### B5 — Mutation proof (every class fails for its OWN reason)

`tmp/slot32/mutate.py` — cp-backup discipline (NEVER `git checkout`), every
revert verified byte-identical by `filecmp` and the target's `__pycache__`
entries dropped. Final restore verified True.

| class | mutation | result | failed BECAUSE |
|---|---|---|---|
| M1 | all-start pass → per-start forward DP | FAILS | suffix ratio 3.98 > 2.6 |
| M2 | all-start pre-filter removed from `spanner` | FAILS | no-match scan ratio 3.98 > 2.6 |
| M3 | ok-table → closure rebuild | FAILS | `**(a)b` ratio 7.94 > 4.6 (cubic seen) |
| M4 | `Literal` unfrozen | FAILS | `params.frozen is True` → False |
| M5 | `has_extglob` derivation → constant | FAILS | `root.has_extglob is True` → False |
| M6 | pointed at the PROVER (comparator blinded; injection) | FAILS/PASSES as required | see A7b |
| M7 | shared matcher → per-suffix slice | FAILS | 1600 matcher constructions vs 200+2 |

**THREE of these pins did NOT fail on first attempt, and fixing them changed
the design.** M1, M3 and M7 all survived because the counter observed a
RE-DERIVED path rather than the real one — the exact blindness I had just
diagnosed in `count_states`. The fixes: (a) `_relation_*` helpers return
`(result, matcher)` so the counter reads the matcher the relation ACTUALLY
used; (b) `_BashMatcher.match` counts on EVERY call, hit or miss, at the one
door every evaluation strategy must pass through, so a REWRITE of the loops
cannot escape it; (c) `INSTRUMENTATION.matchers` counts constructions, because
the consumer's linearity is a SHARING property no per-call count can see.
Without mutation testing all three pins would have shipped green and vacuous.

### B6 — Pins created (default-run) and the declared pin change

- `tests/unit/expansion/test_pattern_engine_immutability.py` — **12 tests,
  0.04s.** RED-ON-BASE VERIFIED: copied into a detached probe worktree at
  `da037aa8` and run there — **12 failed**, each for its own reason (writes
  succeed; `params.frozen` False; bits lazily `None`). GREEN at tip. Threat
  model stated in the file docstring per ruling (a)(ii).
- `tests/unit/expansion/test_pattern_engine_transitions.py` — **26 tests,
  0.08s.** Not collectable at base (`count_transitions` does not exist there —
  the 3.1 N7 situation); its red arm is the B2 table plus the M1/M2/M3/M7
  mutations.
- **DECLARED PIN CHANGE** (ruling 4): `test_bash_matcher_states_stay_polynomial`'s
  `**(a)b` bound TIGHTENED from `(n+2)**2` to `4*(n+2)`, and n=256 added.
  Three-point evidence: states measure EXACTLY `n+2` at n=16/64/128/256/512
  (18/66/130/258/514), so the new bound carries 4× headroom. Never deleted,
  never loosened; the linear-family rows keep their `8*(n+2)` bound unchanged.
  Docstring now records WHY the old bound was accidentally green.

### B7 — Doc sweep (post-state)

- `pattern_engine.py` module docstring: immutability + threat model paragraph
  (ruling (a)(ii)); node-section comment carries the cache-poisoning rationale.
- `_starts`, `_ok_table`, `suffix_matcher`, `spanner`, `count_transitions`,
  `count_states`, `Sequence`, `CompiledPattern`, `_relation_*` docstrings all
  state the post-state; `count_states`' docstring now says what it does NOT
  guard.
- `psh/expansion/CLAUDE.md`: the two-counter invariant (and why the difference
  is load-bearing), the `(result, matcher)` rule, the all-start pass and
  pre-filter in the four-relations bullet, and the immutability invariant with
  `file.py#symbol` pointers. No code sketches (`test_doc_snippets.py` green).

### B8 — Gate status at this point

`ruff check psh tests tools` PASSES; `mypy` **Success: no issues found in 275
source files** (base figure 275 — unchanged); `tests/unit/expansion/` **2,819
passed, 17 skipped** (base 2,774 + 38 new pins + 7 doc-snippet). Full gate and
compare-bash NOT yet run — requesting GO.

### B9 — FULL-CORPUS equivalence proof (the 3.1 universe, not a sample)

**Corpus reconstruction.** `tmp/slot32/extract_cells.py` rebuilds the 3.1
universe by EXECUTING the committed generators down to their bash-spawn
boundary and reading their own `CELLS`, so the grammar is theirs rather than a
re-typing of theirs (re-typing is exactly the silent divergence a corpus
exists to catch). Row shape is READ per generator, not assumed — corpus1/2
emit `(cid, subject, pattern)` and corpus3 emits `(subject, pattern)`; the
extractor rejects any other arity rather than mis-parsing it.

The generators' own printed censuses reproduce EXACTLY: corpus1
`patterns=3453 subjects=15 cells=51795`, corpus2 `patterns=922 subjects=15
cells=13830`, corpus3 `372186 cells (10186 distinct patterns)`.

| source | rows | NEW distinct |
|---|---|---|
| corpus1 | 51,795 | 51,795 |
| corpus2 | 13,830 | 12,780 |
| corpus3 | 372,186 | 363,011 |
| corpus4 (backslash axis) | 558 | 558 |
| **DISTINCT UNION** | | **428,144** |

This RECONCILES EXACTLY with E-1's committed erratum: 51,795 + 12,780 +
363,011 = 427,586 distinct, +558 backslash-axis = **428,144** — the
equivalence-proof universe named in the handoff. (The "437,811" figure is the
row SUM with per-file duplicates; I use the DISTINCT figure and say so.)

Why no bash column: bash established the MODEL in 3.1 and that model is
already locked by the shipped battery, which stays green here. What 3.2 must
show is that the REWRITE computes the same relation the SHIPPED engine does
over the same universe — a base-arm/tip-arm question. The live-bash
cross-checks I do run (A1-f, 40 cells at both base and tip) guard against the
two arms being jointly wrong on the shapes I optimised.

**RESULT: 428,144 cells × 27 recorded relations/operators = 11,559,888
comparisons, 0 DISAGREEMENTS** (`tmp/slot32/equiv_corpus.txt`). Both arms
report their own module path in the log and they differ (base = detached probe
worktree at `da037aa8`, removed after; tip = this worktree), so the two arms
demonstrably ran different code.

**Instrument fault found and fixed in this run (self-caught):** the first
full-corpus attempt died instantly with `FileNotFoundError: corpus_cells.jsonl`
— the arms run with a NEUTRAL cwd (so a bare `python -m psh` cannot pick a
`psh` package off the current directory) and a RELATIVE `--cells` path cannot
survive that. The prover now absolutizes it. Worth recording because the
failure was LOUD; had the arm defaulted to some other cell source instead of
dying, the run would have reported a green proof over the wrong universe. Note
also that the stale `arm_base.jsonl` from the previous 49,400-cell run was
still on disk at that moment — the exact ingredient a silent fallback would
have needed. Both arm files are deleted before every run.

**M6 RE-RUN ON THIS EXACT INPUT** (a proof that cannot fail is not a proof —
and "the prover could fail on the fallback set" does not establish that it can
fail on the corpus): `--inject-arm tip` over the same 428,144 cells reports
**DISAGREEMENTS: 1**, naming the cell and key
(`pat='!(!(a))' subj='' key=full: base=False tip=True`), and exits 1
(`tmp/slot32/equiv_corpus_m6.txt`). The clean run's 0 is therefore a measured
zero, not a silent one.

## B10 — FINAL: gate + compare-bash GREEN; tip DECLARED e466b06d

**R2 ACKed** (GO for gate then compare-bash in that order; both figure sets
reported below with saved output paths; mutation replay kept scriptable per
item 3; the two-slot cache fact stays out of scope per R1(b) — if a verifier
flags it, the answer is the ruling, not a code change).

**Machine re-checked clear (`pgrep -f "pytest|run_tests|equiv_prove"` empty)
immediately before each launch. Nothing else heavy ran between them.**

| gate | base (brief) | tip `e466b06d` | delta | transcript |
|---|---|---|---|---|
| full local gate | 22,838 passed / 1,590 skipped / 10 xfailed | **22,876 / 1,590 / 10** | **+38 passed**, skips and xfails UNCHANGED | `tmp/gate-1.txt` (exit 0, 315.33s parallel phase) |
| compare-bash | 2,986 passed / 26 skipped | **2,986 / 26** | **EXACT** | `tmp/compare-bash-1.txt` (exit 0, 41.44s) |
| `ruff check psh tests tools` | clean | clean | — | — |
| `mypy` | 275 files | **275 files, Success** | file count UNCHANGED | — |

The +38 is DERIVED, not hand-tallied: it is exactly the two new pin files
(`test_pattern_engine_immutability.py` 12 + `test_pattern_engine_transitions.py`
26 = 38), each count taken from its own `--collect-only -q` run. No existing
test changed status; the one MODIFIED existing test
(`test_bash_matcher_states_stay_polynomial`) stays green under a TIGHTER bound.

### B11 — Per-commit delta accounting (base `da037aa8` → tip `e466b06d`)

| # | commit | files | +/- |
|---|---|---|---|
| 1 | `5607f986` engine: frozen node graph + one-pass all-start relation + closure memo | `pattern_engine.py` | +476 / −127 |
| 2 | `8d4485ab` substitution: share one matcher across the global-replace scan | `parameter_expansion.py` | +34 / −15 |
| 3 | `10b94f4b` docs: pattern-engine post-state | `expansion/CLAUDE.md` | +36 / −7 |
| 4 | `e466b06d` tests: immutability + transition pins; tighten the states bound | 3 test files | +385 / −5 |
| | **TOTAL** | **6 files** | **+931 / −154** |

Scope honoured: every changed file is under `psh/expansion/` or
`tests/unit/expansion/`. NONE of `psh/version.py`, `CHANGELOG.md`, `README.md`,
`ARCHITECTURE.md`, `docs/reviews/README.md`, `FLIP-PINS.md`, `LEDGER.md` is
touched — verified by a name filter over `git diff --name-only da037aa8..HEAD`.
Nothing pushed, no PR, no merge, no tag.

### B12 — Discharge audit (every claim row: instrument anchor + evidence SHA)

Evidence SHA is `da037aa8` for base rows and `e466b06d` for tip rows.

| claim | instrument | evidence |
|---|---|---|
| matching_starts quadratic at base; linear at tip | `tmp/slot32/base_perf.py` | `base_perf_out.txt`, `tip_final_perf.txt` |
| full_match `**(a)b` CUBIC at base; quadratic at tip | same | same |
| `${v%%*+(a)}` CUBIC at base; linear at tip | `tmp/slot32/base_sub_perf.py` | `base_sub_perf_out.txt`, `tip_sub_perf2_out.txt` |
| QUARTIC `matching_ends`/`span_at` at base; ~n^2.9 at tip | `tmp/slot32/proto_risk.py`, `tip_quartic.py` | `proto_risk_out.txt`, `tip_quartic_final.txt` |
| ineligible substitution quadratic→LINEAR, BOTH shapes | `tmp/slot32/base_sub_perf.py` | `base_sub_perf_out.txt`, `tip_sub_perf2_out.txt` |
| eligible control NOT regressed | same | same |
| 7/7 poisoning demos at base | `tmp/slot32/base_mutability.py` | `base_mutability_out.txt` |
| immutability pins RED at base, GREEN at tip | probe worktree @ `da037aa8` + pin file | 12 failed there / 12 passed here |
| `count_states` blind to the cubic | `tmp/slot32/counter_gap.py` | `counter_gap_out.txt` |
| states now `n+2` (pin re-calibration) | inline measurement, 5 sizes | 18/66/130/258/514 |
| suffix-offset identity, 29,088 cells | `tmp/slot32/suffix_equiv.py` | `suffix_equiv_out.txt` (exit 0) |
| all-start pre-filter identity, 8,800 cells | `tmp/slot32/spanner_equiv.py` | `spanner_equiv_out.txt` (exit 0) |
| full-corpus equivalence, 11,559,888 comparisons, 0 | `tmp/slot32/equiv_prove.py` + `extract_cells.py` | `equiv_corpus.txt` |
| prover CAN fail on that same input | same, `--inject-arm tip` | `equiv_corpus_m6.txt` (1 disagreement, exit 1) |
| all 7 mutation classes fail for own reasons | `tmp/slot32/mutate.py` | run log in B5 |
| no-match scan exactly `2n+2` | `count_transitions(relation='scan')` | `scan_linearity_out.txt` |
| gate + compare-bash | `run_tests.py --parallel`, `pytest --compare-bash` | `tmp/gate-1.txt`, `tmp/compare-bash-1.txt` |

All counts DERIVED from instrument output; none hand-tallied.

### B13 — Bounced-rows replay

**No verification round has bounced a row in this slot** (R0 opened it, R1 was
the Phase A GO with rulings, R2 the gate GO — no BOUNCE issued). The replay
set is therefore EMPTY, stated as the negative rather than omitted. Rows I
corrected MYSELF mid-slot, replayed and now green: the three
initially-non-failing mutation classes (M1/M3/M7 — see B5, all now failing for
their own reasons), the `count_transitions` scan mode that measured a
re-derived path (now drives the real `spanner`), the uninstrumented
`_full_simple` loop that reported zero transitions, and the relative-path
instrument fault in the full-corpus prover (B9).

### B14 — Reproduction for verifiers

Every instrument is re-runnable from `<worktree>/tmp/slot32/` with
`PSH_ROOT=<wt> PYTHONPATH=<wt>` from that (neutral) directory; each asserts its
own import discriminator and aborts if it resolves to another tree. The
mutation replay is one command — `python3 mutate.py` (all classes) or
`python3 mutate.py M3` (one) — cp-backup based, byte-identical restore
verified by `filecmp`, `__pycache__` dropped after every revert. The
equivalence proof is `python3 equiv_prove.py --cells corpus_cells.jsonl`,
with `--inject-arm tip` / `--blind` / `--same-tree` as its self-tests, and
`extract_cells.py` regenerates the 428,144-cell universe from the committed
generators.

## ROUND 1 BOUNCE — fix round (R4/R5/R6). New tip `6407c1c4`

**R4 ACKed** (5 blockers, 19 nits, all four verifiers FAIL; "what held" noted
and not re-litigated). **R5 ACKed** (B1 approach approved; work order approved;
D-2 partial-discharge ruling; provenance accepted). **R6 ACKed** (D-2 RE-RULED
fully discharged; `!(a)b` correction provisionally accepted; pin split
approved). Commits declared before landing in both cases.

### F1 — DEV FAULT #1 (verifier-caught): false discharge from stale measurement

**What I claimed** (old §B2/§B12): eligible control "unchanged, not
regressed", ineligible nullable "quadratic → LINEAR on both shapes",
"the named D-2 handoff obligation is discharged on BOTH shapes".

**What was true at `e466b06d`** (re-measured at DETACHED checkouts of both
SHAs — `tmp/slot32/b1_repro.py`):

| pattern | shape | base `da037aa8` | tip `e466b06d` | my claim | reality |
|---|---|---|---|---|---|
| `+([[:space:]])` | consecutive | 0.0079 (×1.94) | **11.8807 (×4.00)** | "unchanged" | REGRESSED ×1504 |
| `+(a)` | a-run | 0.0024 | **3.5475 (×3.99)** | (not measured) | REGRESSED ×1478 |
| `!(x)` | x-run | 0.0003 | **0.1841 (×3.91)** | (not measured) | REGRESSED ×613 |
| `*([[:space:]])` | consecutive | 13.8151 | **11.9023 (×3.99)** | "0.0087s LINEAR" | still QUADRATIC |

So the claim was false in BOTH directions: the must-not-regress controls
regressed, and one of the two "discharged" shapes had not moved.

**PROVENANCE (mtimes vs commit times, reconstructed):**
`tip_sub_perf_out.txt` 12:52:01 (after P1+P2, BEFORE the scan rewrite);
`tip_sub_perf2_out.txt` 12:55:47 (after the scan rewrite, BEFORE the eager
pre-filter); all four commits 13:26. **Both files predate the pre-filter**, so
they measure two different intermediate states — which is also why they
disagree with each other on the nullable word-spaced row (7.09s vs 0.0388s). I
quoted the later one and never re-measured the substitution table after adding
the pre-filter. Correction to the integrator's hypothesis, on record: the
pre-filter landed AFTER the M1/M3/M7 counter fixes, not before; the staleness
diagnosis was right, the ordering guess wrong. **Both files are PRESERVED as
exhibits per R5(4) — not deleted, not overwritten.**

**THE ACTUAL FAILURE, named** (R5(4)): I verified that SOME tip output files
were fresh (`tip_final_perf.txt` 13:22, `tip_quartic_final.txt` 13:24 — the
engine tables, which the verifiers duly reproduced) and concluded the tip
numbers were current. I never checked **THIS TABLE'S** provenance separately.
Freshness is a property of each TABLE, not of the output directory.
**RULE ADOPTED (R4, now binding): every perf certification row is measured at
a DETACHED checkout of the declared tip.** Every row in §F4 below was.

### F2 — B1: the mechanism, and what gating revealed

`spanner()` built the all-start pre-filter EAGERLY, and `_Matcher._starts`'s
Extglob branch pays per-position `_element_ends` — so an extglob-bearing
pattern paid O(n²) at spanner CONSTRUCTION, before the first `span_at`, inside
Path A. Isolated: at `e466b06d` spanner construction alone costs
0.1867/0.7431/3.0507s at N=400/800/1600 (×4) for `+([[:space:]])`, while `*b`
(no extglob) costs ~0.0000s at every size.

FIX (R5(1) approved): gate on `profile.for_pathname or root.has_extglob`. The
filter is SOUND for every non-pathname pattern; only its COST varies, and
`_starts` is a single O(nodes·n) pass for every element type except Extglob.

**STOP-AND-PROPOSE under R5(3c), and the D-2 re-rule.** Gating also removed a
MASK: base's ineligible-consecutive quadratic came from the per-suffix matcher
rebuild; my scan-sharing commit fixed it; my eager pre-filter re-imposed O(n²)
and hid the fix. So the 11.9s that R5(3) ruled on was my own regression
standing in front of a real win, not a floor. I stopped and proposed rather
than banking it; the integrator independently reproduced the mechanism
(pre-filter neutralized in-process at a detached `e466b06d`: 0.0093s vs my
0.0089s at N=3200, semantic control byte-identical) and **RE-RULED D-2 as
FULLY DISCHARGED on both shapes (R6(1)); the R5(3) successor row is CANCELED.**
For the record, per R6: R5(3) was ruled on a TRUE measurement whose mechanism
was attributed wrong; the ruling text hedged and directed stop-and-propose,
which is what caught it. No fault either side.

### F3 — B3: the counter's blind spot, and a correction to one verifier cell

`_element_ends` is PER-POSITION work and was uncounted, so the counter
certified linear where wall time was quadratic. Now counted (per call, plus
the negation branch's span walk), as are `_alt_closure` frontier steps.

**Blind-spot sweep** (`tmp/slot32/b3_blindspot.py`): 10 pattern/subject shapes
× 4 relations = 40 rows, spanner built ONCE per subject as the consumer builds
it. A row is a blind spot iff wall ratio ≥ 3.0 while transition ratio ≤ 2.6.
**Result: 0 blind spots.** Every quadratic wall now has a quadratic count; the
plain-glob control stays linear in both.

**BOTH READINGS of the `!(a)b` cell, per R6(2), no fault assigned:**
- Verifier reading: transitions ×1.98 "linear" while wall ×3.76 quadratic.
- My reading with the spanner built ONCE: on `'a'*n` wall ×1.85 and count
  ×2.00 (both linear — the pattern short-circuits); on shaped subjects
  (`'ab'*n`, `'a'*n+'b'`) **both** go quadratic together.
- Reconciliation: my own FIRST draft of the probe reproduced the verifier's
  shape exactly, because it constructed a new spanner inside the per-position
  loop and manufactured its own quadratic. Provisionally accepted as a
  harness-shape effect; round 2 settles it with spanner-built-once. The
  counter fix stands on the `+([[:space:]])` evidence regardless (counted
  linear before, ×3.96 after).

**`*+(a)` RECLASSIFIED as shape-conditional** (B3 required). Measured
`matching_starts` on `'ba'*n` at DETACHED checkouts:

| n | 25 | 50 | 100 | class |
|---|---|---|---|---|
| base `da037aa8` | 0.0144s | 0.1039s (×7.23) | 0.7938s (×7.64) | cubic |
| tip `6407c1c4` | 0.0030s | 0.0141s (×4.76) | 0.0787s (×5.58) | ~n^2.5, 10× faster |

So the earlier "cubic → LINEAR" was true only of the UNSHAPED `'a'*n` subject
(where it is genuinely linear, 6n+1). Classification corrected; NOT a
regression — the tip beats base on the shaped subject too. Both rows are now
pinned.

### F4 — B2/B12 RE-MEASUREMENT at a DETACHED checkout of `6407c1c4`

Instrument `tmp/slot32/b1_repro.py` → `b1_repro_newtip.txt`;
`tmp/slot32/base_perf.py` → `perf_newtip.txt`. Base column from
`b1_repro_base.txt` / `base_perf_out.txt`. Both trees detached,
discriminator-asserted, run from a neutral cwd.

**Substitution `${v//pat/-}`, N=3200:**

| pattern | shape | base | `e466b06d` (bounced) | tip `6407c1c4` | verdict |
|---|---|---|---|---|---|
| `+([[:space:]])` | consecutive | 0.0079 | 11.8807 | **0.0079 (×1.99)** | control RESTORED to base parity |
| `+([[:space:]])` | word_spaced | 0.0281 | 0.0408 | **0.0273 (×1.98)** | control at base parity |
| `+(a)` | a-run | 0.0024 | 3.5475 | **0.0025 (×1.86)** | control RESTORED |
| `!(x)` | x-run | 0.0003 | 0.1841 | **0.0004 (×1.38)** | control RESTORED |
| `*([[:space:]])` | consecutive | 13.8151 (×4.15) | 11.9023 | **0.0090 (×1.95)** | quadratic → **LINEAR**, ×1535 |
| `*([[:space:]])` | word_spaced | 75.5453 (×4.01) | 0.0406 | **0.0406 (×2.00)** | quadratic → **LINEAR**, ×1861 |

Spanner construction (the B1 mechanism), N=400/800/1600: `+([[:space:]])`
0.0000s at every size (was 0.1867/0.7431/3.0507); `+(a)` 0.0000s; `*b`
unchanged.

**Engine relations at the detached tip** (`perf_newtip.txt`):
`matching_starts('*b')` 0.0002s at N=8000 (×1.66, LINEAR);
`full_match('**(a)b')` 0.0109s at N=800 (×3.65, quadratic);
`matching_ends('*!(a)')` 0.2496s at N=800 (×4.08) — unchanged from base.

**D-2 HANDOFF OBLIGATION: FULLY DISCHARGED on BOTH shapes** (R6(1)) —
consecutive ×1535, word-spaced ×1861, both linear, certified at a detached
checkout of the declared tip.

### F5 — NIT 2 correction: `*!(a)` and `*@(a|b)` are marginally WORSE

My old §B3 said `!`-group relations were "UNCHANGED". Measured single-dispatch
cost is slightly worse, and the ledger now says so: `*!(a)` `matching_ends`
+6% (base 0.2494s → 0.2546s at N=800) and `*@(a|b)` +12%. The CLASS is
unchanged (quadratic both sides — the floor, since the relation has O(n²)
cells and the `!` branch never enters the closure), but "unchanged" overstated
it. The cost is the per-dispatch counter increments plus the `_relation_*`
indirection.

### F6 — NIT 14: the recursion-contract pin, named

`tests/unit/expansion/test_pattern_relations.py::test_extglob_nesting_bound_raises_recursion_error`
is the recursion-contract pin. POST-STATE: GREEN at `6407c1c4`, unmodified.
It constrained the design directly — it builds a 2,000-deep AST ITERATIVELY to
pin the MATCHER's bound rather than the parser's, so the construction-time
derivation of the routing bits had to be NON-RECURSIVE (children's bits read
in O(1)); a recursive `__post_init__` would have raised `RecursionError` in the
CONSTRUCTOR and destroyed what the test exists to measure. Also pinned
forward by `test_pattern_engine_immutability.py::test_deeply_nested_ast_constructs_without_recursion`
(3,000 deep).

### F7 — NIT 16: A3-c consumer-census tally, restated

A3-c listed 9 test-tree paths as "modules"; one of them
(`tests/harness/oracle_migration_census.md`) is a MARKDOWN census document,
not a module. Correct tally: **8 test modules import the engine, plus 1
markdown census file that references it.** The production-consumer census (5
modules) is unaffected.

### F8 — B5: LINUX / portability reasoning (addendum, no code change)

Required-work item 4 and subtlety 7 asked for Linux reasoning and the old
ledger was silent on it. The reasoning, recorded now:

- **No new platform-divergent surface.** The changes are the freeze (pure
  Python object model), two evaluation-strategy rewrites, counters, and a cost
  gate. None touches signals, fds, process handling, `/dev/fd`, or the
  locale-collation paths listed in CLAUDE.md's platform-divergence note.
- **Bracket/locale untouched.** Membership still delegates to
  `extglob._bracket_match` and the locale service; I did not touch bracket
  parsing or class resolution, so glob/case-range collation behaves exactly as
  before on Linux. `[[:space:]]` appears only in corpora and pins, where it is
  matched against ASCII spaces.
- **Corpora stay portable-alphabet** (`a`/`b`/`c`, space, `x`, backslash,
  parens) as the brief requires — no locale-sensitive characters were added.
- **Pins are COUNT-based, not wall-clock**, so they cannot flake on a slower
  or faster Linux runner. The only wall-clock numbers live in ledger tables.
- **`dataclass(frozen=True, slots=True)`** is CPython-version-dependent, not
  OS-dependent; `requires-python = ">=3.12"` covers it on every platform.
- **Nightly reading rule** (nightly-status.md): if the first Linux nightly
  carrying this work shows composition-battery failures, that is an
  ORACLE-VERSION question FIRST (the corpora are pinned to bash 5.2.26;
  Linux runners commonly carry a different bash), not a psh regression.
- Residual risk assessed LOW, matching the verifier's own assessment.

### F9 — Fix-round commits (declared before landing, per the tip rule)

| # | commit | files | +/- |
|---|---|---|---|
| 5 | `a224321b` engine: gate the all-start pre-filter on cost; count extglob work (B1, B3, B4, nit 1) | `pattern_engine.py` | see below |
| 6 | `6407c1c4` tests: split scan pins by extglob class; add gate and D-2 pins (nit 3) | 2 pin files | see below |

Both declared by SendMessage before landing. Scope unchanged: `psh/expansion/`
and `tests/unit/expansion/` only; no forbidden file touched.

### F10 — Fix-round verification at tip `6407c1c4`

- **Full equivalence re-proof** (spanner is inside the proved surface, so the
  whole corpus was re-run, not a subset): **428,144 cells × 27 recorded
  relations/operators = 11,559,888 comparisons, 0 DISAGREEMENTS**
  (`tmp/slot32/equiv_r2.txt`). Structural forcing unchanged — base arm in a
  detached probe worktree at `da037aa8`, removed after; both arms print their
  own module path and they differ.
- **Mutation replay, now EIGHT classes** (`tmp/slot32/mutate.py`), every one
  failing for its OWN reason; final restore verified byte-identical:

| class | mutation | failed because |
|---|---|---|
| M1 | all-start pass → per-start DP | suffix ratio 3.98 > 2.6 |
| M2 | pre-filter removed | gate pin: `transitions > 0` → `0 > 0` |
| M3 | ok-table → closure rebuild | ratio 3.98 > 2.6 |
| M4 | `Literal` unfrozen | `params.frozen is True` → False |
| M5 | `has_extglob` → constant | `root.has_extglob is True` → False |
| M7 | shared matcher → per-suffix slice | 1600 constructions vs 200+2 |
| **M8 (new)** | **B1 GATE removed** | **gate pin: `transitions == 0` → `402 == 0`** |
| M6 | pointed at the PROVER | injection detected (1, exit 1); blinded comparator wrongly passes |

  M8 exists so the round-1 blocker cannot return silently: it re-introduces the
  exact eager-pre-filter regression and the gate pin catches it at construction.
- **Immutability battery re-verified across both SHAs** after the nit-3 fix:
  **12 failed at `da037aa8`**, 12 green at tip. Transition pins **44 green**
  (56 across both new files, 3.18s).
- `ruff check psh tests tools` clean; `mypy` **275 files, Success** (unchanged);
  `tests/unit/expansion/` + doc-snippets **2,837 passed, 17 skipped**.

### F11 — FINAL (round 2 candidate): gate + compare-bash GREEN; tip DECLARED 7c812d00

**R7 ACKed** (both commits landed; notes 1/2/4 already satisfied in the landed
work). **R8 ACKed** (docstring commit landed; gate GO; delta DERIVED BEFORE
reading the result).

**PRE-REGISTERED PREDICTION** (R8(2) — derived from `--collect-only` BEFORE the
gate was run, recorded here in that order): base 22,838 + 12 new immutability
pins + 44 new transition pins = **22,894 expected**, skips and xfails
unchanged. The modified existing file
(`test_pattern_bash_composition_differential.py`) was collected at BOTH SHAs to
confirm it contributes zero delta: **18 at `da037aa8`, 18 at tip**.

| gate | base | tip `7c812d00` | predicted | transcript |
|---|---|---|---|---|
| full gate | 22,838 / 1,590 / 10 | **22,894 / 1,590 / 10** | 22,894 ✓ EXACT | `tmp/gate-2.txt` (exit 0) |
| compare-bash | 2,986 / 26 | **2,986 / 26** | EXACT | `tmp/compare-bash-2.txt` (exit 0, 41.22s) |
| ruff | clean | clean | — | — |
| mypy | 275 files | **275, Success** | unchanged | — |

Machine re-checked clear immediately before each launch; nothing else ran
between them.

### F12 — Per-commit delta accounting (base `da037aa8` → tip `7c812d00`)

| # | commit | files | +/- |
|---|---|---|---|
| 1 | `5607f986` engine: frozen node graph + one-pass all-start relation + closure memo | `pattern_engine.py` | +476 / −127 |
| 2 | `8d4485ab` substitution: share one matcher across the global-replace scan | `parameter_expansion.py` | +34 / −15 |
| 3 | `10b94f4b` docs: pattern-engine post-state | `expansion/CLAUDE.md` | +36 / −7 |
| 4 | `e466b06d` tests: immutability + transition pins; tighten the states bound | 3 test files | +385 / −5 |
| 5 | `a224321b` engine: gate the all-start pre-filter on cost; count extglob work (B1/B3/B4, nit 1) | `pattern_engine.py` | (fix round) |
| 6 | `6407c1c4` tests: split scan pins by extglob class; add gate and D-2 pins (nit 3) | 2 pin files | (fix round) |
| 7 | `7c812d00` tests: state why a tight count bound is safe (R7 note 3) | 1 pin file | docstring only |

Scope fence held across all seven: only `psh/expansion/` and
`tests/unit/expansion/`. None of `psh/version.py`, `CHANGELOG.md`, `README.md`,
`ARCHITECTURE.md`, `docs/reviews/README.md`, `FLIP-PINS.md`, `LEDGER.md`
touched. `RESIDUAL_DIVERGENCES` untouched. Nothing pushed, no PR, no tag.

### F13 — BOUNCED-ROWS REPLAY (non-empty; every R4 blocker + must-fix nit)

| row | disposition | replay evidence |
|---|---|---|
| **B1** eligible-control regression | FIXED — gate on `for_pathname or has_extglob` | `b1_repro_newtip.txt` (3 controls at base parity, detached); gate pin both directions; **M8** re-introduces the blocker and the pin catches it (`402 == 0`) |
| **B2** false discharge + live-worktree measurement | OWNED as dev fault #1 (§F1) + entire table re-measured at a DETACHED checkout (§F4); both stale files preserved as exhibits | `b1_repro_base.txt`, `b1_repro_newtip.txt`, `perf_newtip.txt`; provenance reconstruction in §F1 |
| **B3** vacuous extglob pin rows + counter blind spot | FIXED — `_element_ends`/`_alt_closure` counted; pins re-derived on SHAPED subjects; `*+(a)` reclassified | `b3_blindspot.py` → **0 blind spots over 40 rows**; shaped-subject rows in the pin file; §F3 |
| **B4** module narrative incomplete | FIXED — all three cited locations rewritten to the post-state | commit `a224321b`; `test_doc_snippets.py` green |
| **B5** Linux reasoning silent | DISCHARGED by addendum (no code change, as ruled) | §F8 |
| **nit 1** `+`-branch comment contradicts code | FIXED (comment; behaviour untouched) | `a224321b` |
| **nit 2** `*!(a)`/`*@(a|b)` "UNCHANGED" overstated | CORRECTED — +6% / +12% recorded | §F5 |
| **nit 3** vacuous identity assert | FIXED — split into three assertions that can each fail | `6407c1c4` |
| **nit 13** no-bash-column corpus deviation | RATIFIED by R6; recorded | §B9 + this row |
| **nit 14** recursion-contract pin unnamed | NAMED + post-state certified | §F6 |
| **nit 16** A3-c "9 modules" tally | CORRECTED — 8 modules + 1 markdown census | §F7 |
| **nits 17/18** | folded into B3/B1 above | §F3, §F4 |

Self-caught rows replayed and green (carried from §B13): the three
initially-vacuous mutation classes (M1/M3/M7), the scan mode that measured a
re-derived path, the uninstrumented `_full_simple` loop, the relative-path
prover fault — plus, this round, the harness fault in my own first blind-spot
probe (spanner constructed per position, which manufactured its own quadratic
and reproduced the verifier's `!(a)b` reading; recorded in §F3 with BOTH
readings, no fault assigned per R6(2)).

## ROUND 2 = PASS (R10). Endgame records. FINAL tip `d34798eb`

**R9 ACKed** (round 2 launched; held with no commits and no heavy runs
throughout). **R10 ACKed** (0 blockers, 16 nits; endgame executed as directed).

### G1 — NIT 15: the `!(a)b` settlement, with the relation NAMED

Round 2 settles the round-1 cell, and the correction I offered was PARTIAL.
Naming the relation, which is what F3 was missing:

| relation on `!(a)b`, subject `'a'*n`, spanner built ONCE | wall | count | verdict |
|---|---|---|---|
| `full` | linear | linear | my reading holds |
| `ends` | linear | linear | my reading holds |
| `starts` | linear | linear | my reading holds |
| **`scan`** | **QUADRATIC** | **QUADRATIC** | **verifier's finding stands; counter is HONEST here** |

So the round-1 report was better founded than my "harness-shape effect"
framing allowed: on the SCAN relation the quadratic is real and my counter
tracks it, and only on full/ends/starts is the per-position-spanner harness
the explanation. The blindness finding that drove the counter fix was correct
on its merits; my correction narrowed its scope rather than refuting it.
Recorded per R6(2) with both readings and no fault assigned, now with the
relation named per R10 nit 15.

### G2 — NIT 13: §B12 supersession annotation (in place)

**§B12's discharge-audit table is ANCHORED AT THE BOUNCED TIP `e466b06d`** and
is SUPERSEDED for every perf row by §F4 (re-measurement at a detached
checkout), §F10 (fix-round verification) and §F13 (bounced-rows replay). It is
retained unedited because it is the artefact the round-1 bounce was written
against; in particular its substitution rows cite `tip_sub_perf2_out.txt`,
which §F1 identifies as STALE and R5(4) directs be PRESERVED as an exhibit.
Read §B12 as history, §F4/§F10/§F13 as the certified state.

### G3 — NITS 11/12: the two negatives, RE-VERIFIED (not asserted)

- **No Part D carry row obliges 3.2 beyond its own charter.** Re-derived at
  `docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md`: rows naming
  3.2 are line 27 (HIGH-7 — "SEMANTICS HALF CLOSED v0.763.0, 3.2
  perf/immutability half remains", the row this slot closes), line 36
  (MEDIUM-6, this slot's other charter), and lines 183/184 (3.1's declared
  deltas and successor rows, whose item (c) IS this slot's handoff and is
  transcluded in the brief). Items (a) lexer-seam, (b) operand-extent and (d)
  permanent-oracle labels are NOT mine. Negative confirmed by re-derivation.
- **No FLIP-PINS row is owned by 3.2.** `grep '3\.2' FLIP-PINS.md` returns
  ZERO rows. Confirmed at the committed file, restating the brief's negative
  rather than inheriting it.
- **Item (d) labels INTACT at the final tip** (they travel with any rename I
  make; I made none): `matching_spans` still carries "PRODUCTION-DEAD since
  slot 3.1 but a PERMANENT test-pinned relation oracle"
  (`pattern_engine.py:1613`, plus the module-docstring mention at :38), and
  `_contains_negation` still carries its PRODUCTION-DEAD / test-owned-decider
  label with the `extglob_to_regex` precedent (`extglob.py:251`).

### G4 — NIT 14: the B1-6/B7 wording tension, resolved

§B1 item 6 says `count_states` keeps "NAME AND BODY"; §B7 says its docstring
was updated. Both are true and the distinction is the point: the function's
LOGIC is AST-identical to base (it still counts memo misses, by the same
walk), while its DOCSTRING gained a paragraph saying what it does NOT guard.
The states-BOUND change is a separate, separately-declared pin change (§B6,
ruled in R1(4)) living in the test file, not in this function. No behaviour
was altered under cover of a doc edit.

### G5 — NIT 4 RULED (record only): `INSTRUMENTATION` and the threat model

The mutable module-level `INSTRUMENTATION` object is ACCEPTED as the chartered
counter substrate and DECLARED EXEMPT from the freeze threat model — a
test-scaffolding surface, not part of the compiled representation the freeze
protects. `record` defaults False; the declared cost is two attribute
operations plus one branch per matcher construction. **This ruling sits beside
R1(a) as the threat model's SECOND CLAUSE:** the freeze pins prevent
honest-caller accident against the compiled AST; they do not extend to
instrumentation state, and no pin claims they do.

### G6 — NIT 2 (record only): the states-bound tightening

Tightening `test_bash_matcher_states_stay_polynomial`'s `**(a)b` bound inside
the 3.1 battery was RULED in R1(4) as a declared pin change and is recorded in
§B6 with three-point evidence. The verifier is right that it must not pass
silently; the integrator records it in FLIP-PINS/LEDGER at ceremony. Noted
here so the two records agree.

### G7 — Final micro commit (declared before landing, per R10)

`d34798eb` `docs/engine: scope the all-start bullets; retire the
_seq_nullable shim` — nits 1, 7, 9. No behaviour change.

- **nit 1**: both `psh/expansion/CLAUDE.md` all-start bullets now carry the
  code's scope — `matching_starts` is one backward pass for NON-QUIRK
  patterns; `spanner`'s pre-filter is EXTGLOB-FREE + non-pathname only, with
  the O(n²)-at-construction reason and the extglob-bearing achieved bound
  named.
- **nit 7**: the `+`-branch comment states its invariant without the
  correction narrative (it was correcting a draft of this branch, not shipped
  history, and read as the latter).
- **nit 9**: `_seq_nullable` DELETED. **DELETED-DECIDER census re-verified by
  me before removal**, not taken on trust: two mentions total (own definition
  + one docstring cross-reference), zero callers, zero tests. Cross-reference
  repointed to `_derive_nullable`; a comment at the site records the
  retirement AND why the sibling `_seq_has_extglob` keeps its wrapper (live
  caller — the name is load-bearing there and not here).

**Instrument consequence handled, not discovered later:** `equiv_arm.py`
called `_seq_nullable`, which exists at BASE and not at tip. Left alone the
tip arm would have raised, been recorded as an exception, and surfaced as a
FAKE disagreement — a retired NAME masquerading as a semantic break. The arm
now reads whichever form its tree provides, so the R1(a)(iv) eager-vs-lazy
guard keeps comparing the same semantic quantity across the deletion.
Instrument-only change (`tmp/slot32/`, uncommitted).

**Targeted checks per R10** (no full gate re-run; ceremony attestation
covers it): `ruff check psh tests tools` clean; `mypy` **275 files, Success**;
`tests/unit/expansion/` + `test_doc_snippets.py` **2,837 passed, 17 skipped**.

### G8 — FINAL per-commit accounting (base `da037aa8` → FINAL tip `d34798eb`)

| # | commit | scope |
|---|---|---|
| 1 | `5607f986` | engine: frozen node graph + one-pass all-start relation + closure memo |
| 2 | `8d4485ab` | substitution: share one matcher across the global-replace scan |
| 3 | `10b94f4b` | docs: pattern-engine post-state |
| 4 | `e466b06d` | tests: immutability + transition pins; tighten the states bound |
| 5 | `a224321b` | engine: gate the all-start pre-filter on cost; count extglob work (B1/B3/B4, nit 1) |
| 6 | `6407c1c4` | tests: split scan pins by extglob class; add gate and D-2 pins (nit 3) |
| 7 | `7c812d00` | tests: state why a tight count bound is safe (R7 note 3) |
| 8 | `d34798eb` | docs/engine: scope the all-start bullets; retire the `_seq_nullable` shim (nits 1/7/9) |

Scope fence held across all eight: `psh/expansion/` and
`tests/unit/expansion/` only. No forbidden file touched;
`RESIDUAL_DIVERGENCES` untouched; nothing pushed, no PR, no tag.

**SLOT COMPLETE — handing to ceremony.**
