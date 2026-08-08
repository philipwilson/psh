# Slot 5B.1 — dev ledger (boundary structure, first Wave 5 slot)

Base: `8af29e6d` (v0.774.0 + %P LEDGER addendum). Branch `fix/remediation-5b-1`.
Worktree `/Users/pwilson/src/psh-r5b-1`.

Import discriminator (asserted before any measurement):
`psh.__file__ = /Users/pwilson/src/psh-r5b-1/psh/__init__.py`,
`psh.__version__ = 0.774.0`,
`sys.executable = /Library/Frameworks/Python.framework/Versions/3.14/bin/python`.

Brief md5 `c958a7a95737f35c5c1cdbc8649cb3ce` (matches R0).

---

## Phase A — instrument manifest

| # | Instrument (file) | Transcript | Proof shape |
|---|---|---|---|
| 01 | `tmp/w5b1-instruments/01_protocol_census.py` | `tmp/w5b1-transcripts/01_protocol_census.out` | characterization (AST, deliberately NOT the q5 grep method) |
| 02 | `tmp/w5b1-instruments/02_ratchet_gap_enumeration.sh` | `tmp/w5b1-transcripts/02_ratchet_gap_enumeration.out` | re-derivation by git |
| 04 | `tmp/w5b1-instruments/04_ratchet_scope_mutation.sh` | `tmp/w5b1-transcripts/04_ratchet_scope_mutation.out` | **mutation-proven** (arm A/B/C) |
| 05 | `tmp/w5b1-instruments/05_live_consumer_sweep.py` | `tmp/w5b1-transcripts/05_live_consumer_sweep.out` | measurement w/ the ratchet's OWN detector |
| 06 | `tmp/w5b1-instruments/06_narrowing_cost.py` | `tmp/w5b1-transcripts/06_narrowing_cost.out` | characterization (per-param use classification) |
| 07 | `tmp/w5b1-instruments/07_collision_census.py` | `tmp/w5b1-transcripts/07_collision_census.out` | **per-definition resolution** (import provenance) |
| 08 | `tmp/w5b1-instruments/08_table_move_design.py` | `tmp/w5b1-transcripts/08_table_move_design.out` | measurement w/ the layering guard's OWN analyzer |
| 09 | `tmp/w5b1-instruments/09_protocol_consumers.py` | `tmp/w5b1-transcripts/09_protocol_consumers.out` | census + **mutation-proven** blind-spot (part 2) |
| 10 | `tmp/w5b1-instruments/10_carry_sweep.sh` | `tmp/w5b1-transcripts/10_carry_sweep.out` | scripted register sweep |
| 11 | `tmp/w5b1-instruments/11_rename_targets_and_guard.py` | `tmp/w5b1-transcripts/11_rename_targets_and_guard.out` | **red-on-base guard proof** |

Portability (CR-D5): every instrument takes ROOT from `$1`/argv, defaulting to
`git rev-parse --show-toplevel`. No hardcoded worktree paths; no pre-existing
`tmp/` assumption. Instrument 04's committed ancestor violated this — the copy
fixes it (see below).

### Instrument 04 — recorded edits to the READ-ONLY committed original

Source (never modified): `docs/reviews/evidence/boundary_remediation_2026-07/
checkpoint-r/instruments/q5/09_ratchet_scope_mutation.sh`.

1. **PATH EDIT (the sanctioned single edit):** original hardcodes
   `WT=/private/tmp/claude-501/.../ckr/q5/wt`. Copy takes `ROOT=$1`
   (default git toplevel). This is exactly the CR-D5 class; the copy
   fixes it rather than inheriting it.
2. **SAFETY EDIT:** original reverts with `git checkout -- <file>`, banned by
   the 3.x rules. Copy snapshots each victim to a `mktemp` backup and restores
   from the BACKUP under an `EXIT`/`INT`/`TERM` trap.
3. **VERIFICATION EDIT:** asserts victim files are clean BEFORE mutating
   (aborts otherwise) and re-verifies byte-identity via `cmp` after restore.
4. **ARM-C ADDED:** the original probes one unscanned module; a one-module
   probe leaves the other unscanned module's face silent (4B.3 rule 7).

---

## A1. Ratchet-gap enumeration — RE-DERIVED (instrument 02)

Reconciles with the brief EXACTLY; no differences to report.

| Range | Count | Modules |
|---|---|---|
| `v0.724.0..75ab5625` (scanned today) | 16 | == hardcoded `CREATED_MODULES`, identical both directions |
| `75ab5625..0215279c` (gap 1) | 1 | `psh/protocols/__init__.py` |
| `0215279c..HEAD` (gap 2) | 2 | `psh/expansion/procsub_render.py`, `psh/scripting/analysis_session.py` |
| `v0.724.0..HEAD` (continuous) | 19 | == union of the three; difference set empty |

All 19 EXIST at tip (no created-then-deleted entry that would break a scan
list asserting existence). `TOUCHED_PREEXISTING` (4) unaffected by any range.

## A2. The blind spot — MUTATION-PROVEN, and WIDER than recorded (instrument 04)

| Arm | Offender planted in | Expected | Observed |
|---|---|---|---|
| A | `psh/scripting/analysis_session.py` (unscanned) | PASSED (blind) | **11 passed** |
| B | `psh/parser/session.py` (scanned) | FAILED (bites) | **1 failed, 10 passed** — `assert not {('psh.parser.session','w5b1_synthetic_offender')}` |
| C | `psh/expansion/procsub_render.py` (unscanned) | PASSED (blind) | **11 passed** |

Post-state: all three victims RESTORED-IDENTICAL (`cmp`), `git status` empty.

**Arm C is new** (the committed instrument probes arm A only): the blind spot
covers BOTH unscanned production modules, not just `analysis_session.py`.

### A2b. A SECOND, INDEPENDENT blind spot (instrument 09 part 2) — NEW FINDING

`full_shell_consumers` scans function **parameters** only. A full-`Shell`
reference held as a **class-level annotated attribute** is invisible to it —
in scanned modules too.

- `def bar(self, shell: 'Shell')` → detected: `[('psh.fake','Foo.bar')]`
- `class Foo: shell: 'Shell'` → detected: `[]` (**nothing**)

The second shape is *exactly* `VariableExpanderProtocol.shell: 'Shell'`
(`psh/expansion/_protocols.py:31`) — the escape hatch the 5B exit criterion
names. Consequence for the design: **widening the scan scope alone would not
catch it.** Scope-extension and detector-shape are two different fixes.
Raised for ruling (a); I have NOT acted on it.

## A3. Live-consumer sweep (instrument 05) — ratchet's own detector

Baseline (20 scanned modules): 6 live consumers == 6 ALLOWLIST entries,
0 unrecorded, 0 stale. **Ratchet green today: True.**

Newly-scanned modules:

| Module | full-`Shell` consumers | Disposition (recommended) |
|---|---|---|
| `psh/protocols/__init__.py` | **0** | scope-only; nothing to record. Verified, not assumed: the module declares protocol MEMBERS, and the detector reads parameters — `JobRuntime.shell_state` is `ShellState`, which the detector deliberately never matches |
| `psh/expansion/procsub_render.py` | **0** | scope-only. Integrator expectation confirmed |
| `psh/scripting/analysis_session.py` | **3** | **ALLOWLIST all three** (justification below) |

## A4. analysis_session narrowing cost — MEASURED (instrument 06)

Every use of the `shell` binding in the module:

| Site | Kind | What it does |
|---|---|---|
| L382 | STORE | `self.shell = shell` |
| L390 | PASS | `self._build_carrier(shell)` |
| L396 | ATTR | `shell.analysis_mode` |
| L418/430/435 | ATTR | `shell.state...` |
| **L431** | **CONSTRUCT** | **`type(shell)(parent_shell=shell, norc=True)`** |
| L586 | PASS | `AnalysisSession(shell)` |

The whole chain terminates in ONE irreducible operation: **construction through
the shell's own type, passing the shell itself as `parent_shell`**. No protocol
can model that — a protocol describes a surface an object *has*, not a type that
is *constructible* and accepts its own kind. The module's own docstring
(L402-407) already declares this an explicit **EMBEDDER CONTRACT**.

This is precisely the existing ALLOWLIST justification shape ("forwards `shell`
to a whole-shell need"), not a punt. Recommendation: **allowlist all three**,
citing pre-ruling 5B.1-R0 (scope-extension-coupled, same-commit, justified).

Proposed entry text (quoted for the ledger, per brief §Phase A must settle 2):

- `("psh.scripting.analysis_session", "AnalysisSession._build_carrier")`:
  "builds the analysis carrier via `type(shell)(parent_shell=shell,
  norc=True)` — construction through the caller's OWN Shell subclass with the
  shell itself as parent; a protocol models a surface an object has, never a
  constructible type, so this is irreducible (the EMBEDDER CONTRACT the
  docstring declares)"
- `("psh.scripting.analysis_session", "AnalysisSession.__init__")`:
  "forwards `shell` to `_build_carrier` (the `type(shell)(parent_shell=...)`
  construction) and reads `shell.analysis_mode`; the forward forces the full
  Shell"
- `("psh.scripting.analysis_session", "parse_for_analysis")`:
  "THE one door into analysis parsing; forwards `shell` to
  `AnalysisSession(shell)` whose carrier construction needs the whole Shell"

### A4b. Incidental finding — `AnalysisSession.shell` is a DEAD STORE

`self.shell = shell` (L382) is written and **never read**: instrument 06 finds
zero `self.shell.<attr>` reads, and a tree sweep finds no external
`<session>.shell` read in `psh/` or `tests/`. Honest boundary: an out-of-tree
embedder could read the public attribute, so this is not provably dead beyond
the repo. Removing it would NOT change the ratchet outcome (`__init__` still
needs `shell` to forward). **Recorded, NOT acted on** — it is a production edit
outside this slot's named subjects. Ruling welcome; default is leave it.

## A5. Collision census — PER DEFINITION (instrument 07)

The brief's CAUTION is confirmed: a name-shaped census conflates the two.

| Definition | Kind | External importers | Resolved reference sites |
|---|---|---|---|
| `psh/lexer/expansion_parser.py:387` | CONCRETE | **1** (`modular_lexer.py`) | `modular_lexer.py:71` constructs it |
| `psh/protocols/__init__.py:119` | PROTOCOL | **0** | self only (docstring, `__all__`) |
| `psh/core/locale_service.py:90` | CONCRETE | **0** external | 4 internal sites + alias `LocaleProfile` (L111) |
| `psh/protocols/__init__.py:216` | PROTOCOL | **0** | self only (docstring, `__all__`) |

So `modular_lexer.py`'s "ExpansionContext" hit is the **concrete lexer class**,
and `locale_service.py:139`'s is its **own concrete dataclass** — neither is a
protocol consumer. Both protocol-side definitions have **zero** consumers.

**Instrument-hygiene note (self-caught):** instrument 11 §2 counts lines
mentioning the NAME, so it reports an identical total (43 / 47) for both sides
of each collision — it cannot discriminate, and is therefore NOT the cost
measure. The per-definition costs above come from instrument 07. Recording the
flaw rather than the number (4B.3 rule 6).

### Recommendation: rename the PROTOCOL side, both times

- Cost: 0 production consumer edits (0 importers each). Touch-set is the
  definition + `__all__` + docstring, plus three guards that name it:
  `test_protocol_layering_q1.py:136-138` (`__all__` set),
  `test_protocol_conformance_q1.py` (imports, `EXPECTED_MEMBERS` keys,
  `isinstance` rows), `test_shell_consumer_ratchet_q1.py` (docstring).
- The concrete sides are load-bearing: `expansion_parser.ExpansionContext` is
  live lexer code (renaming it is a behavior risk the brief fences), and
  `locale_service.LocaleContext` is **row 4 of the canonical representation
  set** in the committed `boundary_campaign_close_2026-07.md:123`, whose text
  *already* records the protocol's name reuse as deliberate. Renaming that side
  would contradict a committed close-report row.

Proposed names (both verified FREE tree-wide across `psh/`+`tests/`+`docs/`,
instrument 11 §1), chosen from the family's own role vocabulary
(`…Access` / `…Context` / `…Runtime`):

- protocol `ExpansionContext` → **`ExpansionRuntime`** (mirrors `JobRuntime`; it
  is the orchestrator that RUNS expansions)
- protocol `LocaleContext` → **`LocaleAccess`** (mirrors `VariableAccess`; a
  read surface over collation/case/class membership)

Rejected: `LocaleServices` (one character from the concrete producer
`LocaleService` — a new near-collision hazard).

### Recurrence guard — RED ON BASE (instrument 11 §3)

Proposed rule: *no class name defined under `psh/` may have more than one
definition when at least one of them is a `Protocol`.*

Measured on the current tree: 500 classes, 5 duplicated names, **2 offenders**
— exactly `ExpansionContext` and `LocaleContext`. The guard is **red on base**,
so it demonstrably can fail; it goes green on the ruled renames.

Deliberately NOT flagged (control, shown in the transcript): the three
concrete-concrete duplicates `CasePhase`, `Complete`, `Parser`. The guard is
scoped to the collision class this slot fixes and does not conscript unrelated
renames. A guard scoped to Protocol-vs-Protocol only would be **green while both
live collisions exist** — i.e. vacuous; that shape is rejected.

## A6. Per-protocol fate matrix — all 9 (ruling (b) input)

Production-consumer counts from instrument 09, with the two collision rows
corrected by instrument 07's per-definition resolution.

| # | Protocol | Defined at | Prod consumers | Recommended fate |
|---|---|---|---|---|
| 1 | `VariableAccess` | `protocols/__init__.py:91` | **0** | **adopt-with-witness in 5B.2** — keep, do not delete (witnesses named below) |
| 2 | `ExpansionContext` | `protocols/__init__.py:119` | **0** | **rename → `ExpansionRuntime`** (this slot) + adopt-with-witness in 5B.2 |
| 3 | `IOContext` | `protocols/__init__.py:149` | 2 | **keep-as-is** (migrated, witnessed) |
| 4 | `JobRuntime` | `protocols/__init__.py:175` | 1 | **keep**; member-narrow `shell_state` deferred to 5B.2 |
| 5 | `LocaleContext` | `protocols/__init__.py:216` | **0** | **rename → `LocaleAccess`** (this slot) + adopt-with-witness in 5B.2 |
| 6 | `VariableExpanderProtocol` | `expansion/_protocols.py:27` | 4 | **keep**; member-narrow `shell`/`state` deferred to 5B.2 (the named escape hatch) |
| 7 | `CommandParsersProtocol` | `parser/combinators/commands/_protocols.py:42` | 4 | **keep**; member-narrow `redirection: Any` deferred to 5B.2 |
| 8 | `ControlStructureProtocol` | `parser/combinators/control_structures/_protocols.py:29` | 3 | **keep-as-is** |
| 9 | `_TemplateCtx` | `parser/recursive_descent/support/syntax_templates.py:44` | 0 external, **7 in-module** | **keep-as-is** (module-private, fully used) |

**Correction recorded (near-false finding):** instrument 09 excludes a
protocol's own defining module, so it first reported `_TemplateCtx` as
zero-consumer. Checking the defining module found 7 annotation sites
(L68,111,175,200,210,221,246). `_TemplateCtx` is NOT unused; the census's
exclusion rule was the error. Reported here rather than silently corrected.

### Delete-vs-keep for the three zero-consumer protocols

5B's exit forbids "defined but unused"; deleting one 5B.2 would immediately
recreate is churn. Named 5B.2 witnesses (real, existing code):

- **`VariableAccess`** → witness `psh/expansion/_protocols.py`
  `VariableExpanderProtocol.state: 'ShellState'`. Narrowing that member to
  `VariableAccess` is the member-narrow 5B.2 owes, and it lands this protocol
  its first consumer. Verdict: **KEEP** (delete would be churn).
- **`ExpansionContext`/`ExpansionRuntime`** → witness
  `psh/expansion/subscript.py#SubscriptEvaluator.__init__`, which today takes
  the full `Shell` and consumes `shell.expansion_manager` (its ALLOWLIST
  justification says so verbatim). It also forwards to `evaluate_arithmetic`,
  so the entry stays — but the *expansion* half of its need is exactly this
  protocol. Verdict: **KEEP + RENAME**.
- **`LocaleContext`/`LocaleAccess`** → witnesses named in the protocol's own
  docstring: `expansion/glob.py`, `expansion/parameter_expansion.py`,
  `executor/enhanced_test_evaluator.py`, each reading `state.locale`.
  Verdict: **KEEP + RENAME**.

### Escape-hatch member targets (design now, execution 5B.2)

| Member | Today | Target (5B.2 executes) |
|---|---|---|
| `VariableExpanderProtocol.shell: 'Shell'` | full Shell on a protocol | REMOVE; consumers take the narrow surface they use |
| `VariableExpanderProtocol.state: 'ShellState'` | whole state | narrow → `VariableAccess` (lands witness #1) |
| `CommandParsersProtocol.redirection: Any` | untyped | type it at the concrete redirection-parser surface |
| `JobRuntime.shell_state: Optional[ShellState]` | whole state | narrow → `VariableAccess`, or drop if the publish path can take the pgid directly |
| `ExpansionContext.variable_expander: Any` | untyped | type → `VariableExpanderProtocol` |
| `ExpansionContext.word_expander: Any` | untyped | type at the word-expander surface |
| `LocaleContext.collate_key -> Any` | untyped return | keep `Any` **or** declare an opaque sort-key alias — the value is genuinely opaque (a libc-derived key); recommend a named alias over a false-precision type |

None of these is executed in 5B.1 (brief fence: a member change whose consumer
migration is 5B.2's).

## A7. POSIX-table move design (instrument 08)

### Deferred-import count — measured with the layering guard's OWN analyzer

`psh.core.locale_service`: **ACTUAL 5**, **CAP 5**, slack **0**. Enumerated:

| Line | Function | Import |
|---|---|---|
| 265 | `upper` | `psh.lexer.unicode_support.simple_upper` |
| 271 | `lower` | `psh.lexer.unicode_support.simple_lower` |
| 277 | `toggle` | `psh.lexer.unicode_support.toggle_case` |
| **577** | `posix_class_ranges` | **`psh.expansion.glob._POSIX_CLASSES`** ← removed |
| **592** | `_ascii_in_class` | **`psh.expansion.glob._POSIX_CLASSES`** ← removed |

**Expected cap-table diff:** `'psh.core.locale_service': 5 -> 3` — a genuine
**−2 on the ACTUAL count**, not bookkeeping (the cap has zero slack today, so
the cap moves with the actual). Lowering a cap is free by the guard's own rules.

### Consumer census (which table goes where)

- `_POSIX_CLASSES`: consumers are `locale_service.py` (the 2 deferred imports +
  prose at L431), `glob.py` (definition), and **one test** —
  `tests/unit/core/test_locale_service.py:181` imports it from
  `psh.expansion.glob` (that import updates with the move).
- `_POSIX_CLASSES_PATHNAME`: **only consumer is `glob.py` itself**
  (L41 definition, L114 use, L107 prose). **STAYS** — census-confirmed, matching
  the brief's expectation. It is derived from the base table
  (`{**_POSIX_CLASSES, 'punct': …}`), so after the move it derives from the
  imported table; the derivation stays in `glob.py` where its only consumer is.

### Recommended neutral owner: `psh/utils/posix_classes.py`

Checked against the layering rules that actually exist:

- `CORE_MODULE_IMPORT_ALLOWLIST = {psh.ast_nodes, psh.utils, psh.version}` — so
  `psh.core.locale_service` may import it at **MODULE level** (no deferred
  import at all), and there is live precedent: `psh/core/trap_manager.py:6-7`
  already imports `..utils.escapes` / `..utils.signal_utils` at module level.
- `psh.expansion` → `psh.utils` is downward; `PACKAGE_CYCLE_ALLOWLIST` is EMPTY
  and stays empty (utils imports nothing outside `psh.utils`).
- The table is pure data (a `dict[str,str]` with zero dependencies), so a leaf
  is its natural home.

Costed alternative: `psh/core/posix_classes.py` — also legal (intra-core import
for `locale_service`; `expansion→core` is already a live module-level edge at
`glob.py:6`). Rejected as *less* neutral: `core` is one of the two parties, and
the brief asks for an owner below both. Integrator may prefer it for semantic
proximity to `LocaleService`; either satisfies the layering lock.

### Content pin (byte-identical reference values, instrument 08 §4)

- `_POSIX_CLASSES`: 12 keys,
  `sha256(repr(sorted(items))) = 310b32ffae0228f5e43417141bb138a48565829a7ce7df2eadfa9a43862c5634`
- `_POSIX_CLASSES_PATHNAME`: 12 keys,
  `sha256 = 206e9c4db29640340db22da879efbd99f62d2a8269bce49e38918ec494059fc6`
- The variants differ in exactly ONE key: `punct` —
  base `':-@!-/[-`{-~'` vs pathname `':-@!-.[-`{-~'` (the `/`-free variant).

### Linux reasoning (nightly is backstop, not gate)

The move is a pure relocation of a frozen ASCII table plus an import-site
change; no matching logic is touched. The C/OTHER-mode path reads the same dict
object, and the UTF-8 path never consults it (it sweeps `iswctype`). Platform
collation divergence lives in the UTF-8 sweep and in libc, neither of which
this change reaches — so there is no macOS-vs-Linux asymmetry introduced. The
content pin is byte-identity, which is platform-independent by construction.

## A8. Carry sweep — THREE registers (instrument 10)

`LEDGER.md` md5 `d687c89a664ecbef74ed343bfc7806ab`;
`FLIP-PINS.md` md5 `cf597e5c78687d53ee05be2851dc5982` (read before any
divergence claim, per the Checkpoint R addition).

| Row | Register | Disposition |
|---|---|---|
| MEDIUM-14 protocol boundaries | **Part A** (L44) | **This slot BEGINS it; stays OPEN until 5B.2.** 5B.1 lands scope+collisions+table; consumer MIGRATION is 5B.2's |
| LOW deferred-import/Q2 debt ledgers | **Part A** (L50) | Incidental **−2** here (cap 5→3); goal-shrink remains 5B.2/5C's. Not claimed as closure |
| D-3.5-s2 (`let_builtin.py:52`) | Part D (L269) | 5C's — **verified untouched** (this slot edits no builtins) |
| D-4B.4-s3 (`IOManager.with_redirections`) | Part D (L335) | 5C's — **verified untouched** (no io_redirect edits) |
| CR-D1 … CR-D4 | Part D (L345-348) | **none touched** (bg reap / exec EXIT trap / fork RANDOM / history fd-paths — all outside this slot) |
| CR-D5 instrument portability | Part D (L349) | **Actively honoured**: all 11 instruments take ROOT from argv; instrument 04's copy FIXES the hardcoded-path class it inherited |
| CR-D6 dead-by-sweep retirement | Part D (L350) | record-only; **no ratchet added** for a structurally-retired authority. The guard I propose is for a LIVE recurring class (name collision), not a retirement |
| 1.4 carry: locale warn wider surface | Part C (L192) | **untouched.** The register states the fix seam is `psh/core/state.py`, NOT `locale_service.py`. My locale_service edits are confined to L577/592/431 + the (ruled) rename + docstrings — the reactive LC_* warn machinery (v0.688/v0.755.0) is not reached |
| FLIP-PINS | — | **No entry touches this slot's subjects.** The `glob` hits are pattern-engine extglob lexer-seam rows (3.1-declared), unrelated to the POSIX class table. No new divergence is being declared: this slot's DIVERGENCE axis is empty by design |

Term sweep over LEDGER: `Protocol` 0, `protocol` 4, `glob` 12, `POSIX class` 0,
`POSIX-class` 0, `ratchet` 14, `collision` 3, `ExpansionContext` 0,
`LocaleContext` 0.

## A9. Ratchet endpoint POLICY — options costed (ruling (a) input)

The self-check's warn-if-git-unavailable behavior must survive in every option
(it has its own test, `test_selfcheck_warns_loudly_when_git_unavailable`); all
three below preserve it unchanged.

| Option | Shape | Drift/self-check consequence | Cost |
|---|---|---|---|
| **1. Continuous pinned range** `v0.724.0..8af29e6d` | ONE list, ONE enumeration, ONE assertion | Strongest equality check: drift in either direction bites. Result is a property of the pinned range, stable across checkouts | Endpoint SHA is a maintained pin; each scope change is a visible reviewed edit |
| 2. Two ranges (keep the old, add `75ab5625..<SHA>`) | TWO lists, TWO assertions, TWO warn paths | Same protection as (1), no more | Strictly more machinery; "why two ranges" needs prose forever. **Rejected** |
| 3. Live-to-HEAD `v0.724.0..HEAD` | Always current, no SHA pin | Forces a disposition the moment any module is born | Test outcome depends on history reachable from HEAD, not on the tree — the same source gives different answers on different branches/cherry-picks, which contradicts "evidence is a property of the TREE" |

**Recommendation: option 1**, with one addition I want ruled explicitly —
a SEPARATE **coverage** assertion ("every `psh/` module created after the pinned
endpoint is either scanned or explicitly declared out-of-scope"). Option 1 alone
re-opens the identical gap the moment module #20 is born after `8af29e6d`;
the coverage check is what stops this slot from being a one-time patch of a
recurring defect.

**Proportionality question for the ruling:** that coverage check makes EVERY new
`psh/` module force a ratchet edit, which is broader than "boundary modules".
The current design already has that property for campaign-created modules, so
it is a continuation rather than a new burden — but it is a genuine design fork
and I am not choosing it unilaterally. Ruling (a) input.

---

## Pre-registration

NOT YET WRITTEN. Phase A used only targeted single-file runs; no heavy run has
been requested or performed. The binding pre-registration block will be written
into this ledger BEFORE the first Phase B heavy run, and the GO request will
cite it by file+line. The D1 sketch is explicitly NOT a pre-registration and
will not be cited as one.

## Gate hygiene log

- Before instrument 04 (the only pytest-invoking instrument): unpiped
  `pgrep -f pytest` → exit 1 (no match); unpiped `pgrep -f run_tests` → exit 1.
  Foreground, no shell-`&`.
- `--collect-only` precondition: not triggered — every pytest invocation so far
  passes a single FILE path (`tests/unit/tooling/test_shell_consumer_ratchet_q1.py`),
  which the rule exempts.
- No `run_tests.py --compare-bash` invoked (banned).
- No bash oracle used: this slot's DIVERGENCE axis is empty by design
  (internal-integrity slot), so no probe compares against
  `/opt/homebrew/bin/bash`. Stated per cell rather than invented.

---

# PHASE B — executed under R1 (rulings (a) + (b))

R1 received and ACKed in D4. Chain md5 verified on receipt
(`b2c9d84575c42c18e3be2ba2d5706c7c` = my D3 append value; the wake-up
message's quoted file md5 `82975f696f346e65541899fad83886fb` recomputed and
matched). Commit order per R1.8.

## B0. Ruling-6 reading fork — RESOLVED BY MEASUREMENT (instrument 12)

"extend to class-level AnnAssign (Shell AND ShellState annotations)" admits two
readings. Measured over the 23-module post-extension scope:

| Reading | New class-attribute hits |
|---|---|
| **A — Shell only (parameter-consistent)** | **0** — matches R1's "Expected zero new hits" |
| B — Shell OR ShellState | 1 — `JobRuntime.shell_state` (`protocols/__init__.py:188`) |

**Reading A implemented.** R1 supplied the discriminator itself. Reading B would
also collide with ruling (b), which assigns `JobRuntime.shell_state` to 5B.2 as
a member-narrow. Flagged PROSPECTIVELY in D4, before any commit built on it.

## B1. Commits

| # | SHA | Subject |
|---|---|---|
| i | `6698ae6e` | ratchet scan-scope currency |
| ii | `49e3f482` | protocol name collisions resolved + recurrence guard |
| iii | `a6b65e96` | POSIX class table moved below both readers |
| iv | `75cb9c67` | AnalysisSession.shell dead store removed + docs |

## B2. Mutation batteries (all arms named, each failing for its OWN reason)

**Instrument 13 — post-extension ratchet (7 arms, 0 mismatch).** Parameter
offender now BITES in all three newly-scanned modules (arms A/B/C — A and C were
blind at base, proven by instrument 04); class-attribute offender BITES (D4);
planted CREATED_MODULES entry BITES (D1); removed real entry BITES (D2);
undispositioned post-endpoint module BITES the COVERAGE test specifically (D3).
Control green both ends; all victims RESTORED-IDENTICAL.

**Instrument 14 — collision guard (4 arms, 0 mismatch).** Reverting either
rename BITES; a planted colliding concrete class BITES; controls (a uniquely
named Protocol; a concrete-concrete duplicate) stay GREEN.

**Instrument 15 — table move (5 arms, 0 mismatch).** Restoring the cross-layer
import BITES `test_core_no_longer_imports_the_table_from_expansion` AND the cap
ratchet; burying the new import in a function body BITES the deferral cell
specifically; changing one range BITES byte-identity; giving the leaf a
dependency BITES the leaf cell; comment-only control GREEN.

**Instrument 16 — dead-store pin (2 arms, 0 mismatch).** Reintroducing
`self.shell` BITES the named pin; an unrelated new field does NOT.

### Two instrument defects SELF-CAUGHT and fixed (recorded, not buried)

1. **Stale-`.pyc` false red (instrument 13, first run).** Arm D3's mutation
   (`8af29e6d`→`75ab5625`) is the SAME BYTE LENGTH, so Python's mtime+size
   invalidation reused cached bytecode and the post-restore control run reported
   RED on a byte-identical-to-original tree. This is banked 4B.2 lesson (2),
   which I had not applied. `PYTHONDONTWRITEBYTECODE=1` now set in every
   mutation driver. Without it the transcript lied.
2. **Arms failing for the WRONG reason (instruments 13 D3, 14 G2/G3/G4).**
   D3 moved `SCOPE_ENDPOINT` alone and went red on the ENUMERATION check, not
   coverage — a cell consistent with two mechanisms (4B.3 rule 6). Fixed by
   rolling `CREATED_MODULES` back in the same arm so only coverage can fail.
   In instrument 14, G2/G3/G4 planted `Protocol` into a module that does not
   import it (NameError) and a duplicate class that SHADOWED a live one
   (TypeError). G3/G4 were caught by their pre-declared PASSED expectations;
   **G2 was NOT, because its expectation was FAILED and it did fail — for
   entirely the wrong reason.** Caught only by reading the failure text. Both
   fixed; the lesson is that a pre-declared expectation catches a wrong-reason
   failure only when the expectation is GREEN.

## B3. Cap-table diff — LANDED AS PRE-REGISTERED

Re-measured with the layering guard's own analyzer at `49e3f482`:
`psh.core.locale_service` ACTUAL **5 → 3**, CAP **5 → 3**, module-level import
`psh.utils.posix_classes` now present, zero deferred `psh.expansion.glob`
imports remaining. The three survivors are the `lexer.unicode_support`
case-mapping imports at L267/273/279.

## B4. Suites run so far (targeted, no heavy run yet)

- `tests/unit/tooling/test_shell_consumer_ratchet_q1.py`: 11 → **20 passed**
- protocol guards + `tests/unit/protocols/`: **39 passed**
- table-move guards + layering + locale_service: **67 passed**
- `tests/unit/{expansion,core,protocols,tooling,scripting}` (5,015 collected):
  **4,998 passed, 17 skipped, 0 failed**
- doc guards + analysis suite: **166 passed**
- `ruff check psh tests tools`: clean. `mypy`: clean, **276** source files
  (275 before commit iii; +1 = `psh/utils/posix_classes.py`).

## B5. PRE-REGISTRATION (BINDING — written BEFORE the first heavy run)

Base figures from the committed attestation `01401c63` (gated `2cf9493b`):
**23,896 passed / 1,620 skipped / 10 xfail**; compare-bash **3,046 / 26 EXACT**.

Expected at tip `75cb9c67`:

| Figure | Base | Expected at tip | Delta | Why |
|---|---|---|---|---|
| passed | 23,896 | **23,916** | **+20** | +9 ratchet cells (11→20); +7 collision guard; +5 table-ownership pins; +1 dead-store pin; −2 net from the two conformance/layering cells that MOVED rather than added (renamed in place, not new) |
| skipped | 1,620 | **1,620** | 0 | no cell gains or loses a skip condition |
| xfail | 10 | **10** | 0 | none touched |
| compare-bash | 3,046 / 26 EXACT | **3,046 / 26 EXACT** | **+0** | INTERNAL-INTEGRITY slot: zero shell-observable delta. Any movement here is a FENCE, not a finding |
| ruff | clean | clean | — | |
| mypy | 274 files clean | **276 files clean** | +2 | +1 `psh/utils/posix_classes.py`; +1 pre-existing growth since the attestation (275 measured at base before my first commit) |

**Named expected-red pins: NONE.** No golden case changes; declaring one is a
fence. No conformance table changes. No new divergence — this slot's DIVERGENCE
axis is EMPTY by design and FLIP-PINS carries no entry touching its subjects.

**Counting note (honesty):** the +20 above is DERIVED from the per-file counts
measured in B4, not estimated. If the gate disagrees, the pre-registration is
what is wrong and I will say so rather than reconcile after the fact.

## B6. Fence hit — ARCHITECTURE.md (reported, NOT edited)

The renames make `ARCHITECTURE.md:98` and `:125` stale — both still list
`ExpansionContext` / `LocaleContext` among the narrow service protocols.
ARCHITECTURE.md is on this slot's **never-touch** list, so I have not edited it.
Integrator-owned; raised in D5.

## B7. Carry table (unchanged dispositions, re-verified at tip)

MEDIUM-14 **stays OPEN until 5B.2** (this slot begins it: scope + collisions +
table; consumer MIGRATION is 5B.2's, per ruling (b)). LOW deferred-import row
gets the incidental −2, NOT claimed as closure. D-3.5-s2, D-4B.4-s3, CR-D1..D4
verified untouched. CR-D5 honoured (all instruments portable). CR-D6 respected.
1.4 locale-warn carry untouched — the seam is `core/state.py`; my
`locale_service.py` edits are the two import sites, the L431 prose, and nothing
else.

## B8. R2 ruling items recorded

**R2 received; chain md5 `41b78738d7c35c50a4e241a63e73e3dc` (= my D5 append
value) verified on receipt; file md5 `8e340f094e15ba5861062d6d968bbaea`
recomputed and matched the wake-up message's quote.**

### B8.1 Three-list design one-liner (R2.2 asks it be recorded here)

The ratchet's scan scope is THREE lists because the enumeration self-check
asserts `CREATED_MODULES == git(SCOPE_BASE..SCOPE_ENDPOINT)`: a module created
by the very commit that extends the scope is, by construction, not in that
range, so adding it to `CREATED_MODULES` would make the extension commit fail
its own self-check. `POST_ENDPOINT_SCANNED` holds those, `POST_ENDPOINT_OUT_OF_
SCOPE` holds justified exclusions, and the coverage assertion requires every
post-endpoint module to be in one or the other. `psh/utils/posix_classes.py`
exercised this LIVE in commit (iii) — it is the first entry.

### B8.2 OWED-INTEGRATOR item (R2.3) — for the discharge audit

| Item | Owner | Where it lands | Status |
|---|---|---|---|
| `ARCHITECTURE.md:98` and `:125` still name `ExpansionContext` / `LocaleContext` in the narrow-service-protocol list; both need the two-name substitution to `ExpansionRuntime` / `LocaleAccess` | **INTEGRATOR** (never-touch file for this slot) | the CEREMONY version-bump commit, per sequence rule 9 (integrator-owned files update in the same release as the contract change) | **OWED — not discharged by this slot.** Ruled in R2.3 |

The discharge audit must show this row as OWED-BY-INTEGRATOR, not as a dev
omission and not as complete. No other never-touch file is affected by this
slot's changes (checked: `psh/version.py`, `CHANGELOG.md`, `README.md`,
`docs/reviews/README.md`, `FLIP-PINS.md`, `LEDGER.md` — none names the renamed
protocols or the moved table).

### B8.3 Banked lessons accepted by R2.4

1. `PYTHONDONTWRITEBYTECODE=1` in EVERY mutation driver — 4B.2 lesson (2)
   reaches same-LENGTH replacements, not just same-file edits; mtime+size
   invalidation cannot see them.
2. **NEW to the banked register:** a RED arm must assert its failure REASON,
   not merely its outcome. A pre-declared expectation catches a wrong-reason
   failure only when that expectation is GREEN; an arm expected to fail will
   swallow a NameError, an import error, or a collection error and look
   correct. Carried into 5B.2+ briefs per R2.4.

---

# B9. HEAVY-RUN RESULTS (under R2's GO) — FINAL

Oracle recorded: `/opt/homebrew/bin/bash` → GNU bash 5.2.26(1)-release
(aarch64-apple-darwin23.2.0). Unpiped `pgrep -f pytest` and `pgrep -f
run_tests` both exit 1 before each leg. Foreground. No shell-`&`. Leg 1
exceeded the 600s foreground window and was MOVED TO BACKGROUND (sanctioned),
awaited in-turn, never abandoned.

## Leg 1 — gate (`tmp/gate-1.txt`, md5 `fcb04e2a2226d74ebabfa2c6f0b94510`)

| Phase | Result |
|---|---|
| 1a parallel | 22,801 passed / 1,620 skipped / 8 xfailed (276.72s) |
| 1b serial | 1,117 passed / 24,446 deselected / 2 xfailed (481.54s) |
| **Combined** | **23,918 passed / 1,620 skipped / 10 xfailed** — ALL PHASES PASSED, exit 0 |

| Figure | Pre-registered (§B5) | Observed | Verdict |
|---|---|---|---|
| passed | 23,916 (+20) | **23,918 (+22)** | **PRE-REGISTRATION WRONG by 2** |
| skipped | 1,620 | 1,620 | exact |
| xfail | 10 | 10 | exact |

### §B5's error, named (see D6; instrument 17)

§B5 derived `+9 +7 +5 +1 −2`. The four component terms were measured and all
four were RIGHT. **The `−2` was invented**: I reasoned that the two files
touched by the rename had cells that "moved rather than added" and debited
them. A rename changes no test count —
`test_protocol_conformance_q1.py` (7→7) and `test_protocol_layering_q1.py`
(5→5) are unchanged in cardinality, confirmed by `git show` at base. Correct
delta = 9+7+5+1 = **+22**, which is exactly what the gate observed.

Re-derived by a DIFFERENT method than the one that erred (the bad number came
from hand-derived per-file runs): `git show 8af29e6d:<path>` parsed with `ast`
for BASE, the gate's own phase manifests for TIP (25,548 node IDs across
`phase-1.json` 24,429 + `phase-2.json` 1,119). The +22 closes on the touched
set alone. Transcript `tmp/w5b1-transcripts/17_plus2_account.out`.

**No backwards reconciliation performed.** The gate is right; the
pre-registration is recorded as wrong, in place, with its phantom term named.

**LESSON (offered for the banked register):** a pre-registration is a
MEASUREMENT and every term in it needs a source. Four terms were measured; the
fifth was reasoning about what a rename "ought to" do to a count — and that is
the one that was wrong, hidden inside a total that looked derived. Derive a
pre-registered count from per-file counts ONLY; never apply a correction no
file's count demonstrates.

## Leg 2 — compare-bash (`tmp/compare-bash-1.txt`, md5 `47ef915372ca699c8c56dbeabdebc248`)

`python -m pytest tests/behavioral --compare-bash -n auto -q` (the sanctioned
form; `run_tests.py --compare-bash` never invoked).

**3,046 passed / 26 skipped**, exit 0 — **EXACTLY the pre-registered
3,046 / 26, delta +0**. The DIVERGENCE axis is empty, as declared: this
internal-integrity slot moved no shell-observable behavior. Zero golden-case
changes; zero conformance-table changes; no new divergence declared.

## Leg 3 — lint / types at the final tip

`ruff check psh tests tools` → All checks passed.
`mypy` → Success, **276** source files (274 at the attestation; +1
`psh/utils/posix_classes.py`, +1 pre-existing growth measured at 275 before my
first commit).

# B10. FINAL TIP DECLARATION

**Final tip: `75cb9c67`** ("scripting: drop the unread AnalysisSession.shell
field (5B.1, commit iv)"), branch `fix/remediation-5b-1`, base `8af29e6d`.

4 commits, 15 files changed, +632/−90.

**MECHANICAL TIP RULE acknowledged:** any further commit from here — including
a comment-only one — requires a dead-drop declaration BEFORE it lands.

## Never-touch verification (instrument 18, `git diff 8af29e6d..HEAD`)

UNCHANGED, all seven: `psh/version.py`, `CHANGELOG.md`, `README.md`,
`ARCHITECTURE.md`, `docs/reviews/README.md`, `FLIP-PINS.md`, `LEDGER.md`.

## Instrument manifest

Command-generated and self-excluding: `tmp/w5b1-instruments/
18_manifest_and_discharge.sh` → `tmp/w5b1-transcripts/
18_manifest_and_discharge.out`. **16 instruments** (excluding self), each with
its own md5 and its transcript's md5, plus 2 post-state re-run transcripts
(`05_..._POSTEXT.out`, `08_..._POST.out`).

## Discharge audit

17 claim rows, each anchored to an instrument file and a NAMED proof shape
(mutation-proven / measured / census / characterization / two-source
re-derivation / re-derived-by-git). Full table in instrument 18's transcript.
Mutation arms across the slot: **4 batteries, 20 arms, 0 mismatches** (13: 7
arms; 14: 4; 15: 5; 16: 2; plus 04's 3 pre-extension baseline arms).

## Owed at close (NOT discharged by this slot)

| Item | Owner | Lands |
|---|---|---|
| `ARCHITECTURE.md:98` / `:125` two-name substitution | **INTEGRATOR** (R2.3) | ceremony version-bump commit |
| MEDIUM-14 remainder (consumer migration; the 12 campaign-added owner params) | 5B.2 | per ruling (b) |
| Escape-hatch member narrowings (§A6 table) | 5B.2 | binding design, not re-litigated |

# B11. LEDGER FREEZE

This ledger is FROZEN at the final-tip declaration above. Corrections from here
are a dead-drop entry plus a dated addendum after the verdict, or a supervised
edit under an explicit ruling.

**Chain rule:** this is the **FIRST freeze of slot 5B.1** — there is no previous
freeze md5 to quote. The freeze md5 is declared in D7; subsequent freezes (if
any) will quote it.

---

# B12. ERRATA + NIT ROUND (R4). Ledger UNFROZEN, corrected, REFROZEN.

Round wf_15ed2491-e6f verdict: **PASS, 0 blockers, 16 NITs** (9 required to me).
Every substantive claim survived independent attack; my +22 was independently
reproduced on the verifier's own selection (3,730 → 3,752).

**Freeze chain:** freeze-1 md5 was **`9328447039b7eb77de35c0d6cac62f4c`**
(declared in D7). This ledger was unfrozen under R4 item 8, corrected as below,
and REFROZEN — freeze-2 md5 declared in D9, quoting freeze-1 per the chain rule.

## B12.1 In-place errata (3), each verified by me before applying

| # | Was | Now | How I verified |
|---|---|---|---|
| 1 | §A8 "MEDIUM-14 … Part B (L44)" | **Part A** (L44) | `grep -n '^## Part'` on the committed LEDGER: Part A spans L14–51, Part B starts L52. L44 is inside Part A |
| 2 | §A8 "LOW deferred-import … Part B (L50)" | **Part A** (L50) | same boundary derivation; L50 < 52 |
| 3 | §A2b "`_protocols.py:28`" | **`:31`** | `grep -n 'shell:' psh/expansion/_protocols.py` → `31: shell: "Shell"` |

Both were real errors of mine. The register mislabel is the more embarrassing:
I read the row contents correctly and attributed them to the wrong Part, which
is exactly the kind of citation a successor would follow and not find.

## B12.2 The ALLOWLIST contract, as SHIPPED (R4 item 4 — quoted here as required)

This discharges brief §Phase A item 2 as written ("The shrink-only test may need
a sanctioned rewording to say exactly this — quote its new text in the ledger").

Module docstring, verbatim as landed in `743159ab`:

> **The contract on ``ALLOWLIST`` is shrink-only WITH ONE NARROW EXCEPTION.**
> The recorded set may only SHRINK, except that entries MAY be added when a
> module newly enters the scan scope — whether because the scope was extended
> or because the DETECTOR was taught a shape it previously missed — provided
> each addition lands in the SAME COMMIT as that extension and carries its own
> specific justification (integrator pre-ruling 5B.1-R0, extended to
> detector-shape by R1.6). Growth in any other circumstance is a contract
> breach, not a judgement call. The exception exists because the alternative is
> worse: a scope extension that cannot record what it finds either lands red or
> quietly narrows what it scans, and both defeat the ratchet. Remediation 5B.1
> used it exactly once, for the three ``analysis_session`` consumers (6 entries
> -> 9).

Header above `ALLOWLIST`, verbatim:

> CONTRACT: shrink-only, EXCEPT entries added in the SAME COMMIT as a scan-scope
> or detector-shape extension, each with its own justification (pre-ruling
> 5B.1-R0, extended to detector-shape by R1.6). Any other growth is a breach.
> See the module docstring for why the exception exists.

## B12.3 Coverage assertion — the window that stays open (R4 item 5, record-only)

Closed: a non-ancestor `SCOPE_ENDPOINT` no longer yields a silent empty-range
pass; ancestry is tested FIRST and routes to the loud
`_warn_selfcheck_unverified` path, with a RED self-test asserting the warning's
REASON (names the vacuity, the cause, the endpoint) plus a control asserting the
endpoint IS an ancestor on a normal checkout — so the warn path cannot swallow
every invocation while both cells look healthy.

**Open and RECORD-ONLY:** a module present in the working tree but not yet
COMMITTED is invisible to `git log --diff-filter=A` and therefore undispositioned
by the coverage assertion. This is inherent to enumerating by history rather than
by tree. It cannot hide a LANDED module, and gates run on committed SHAs, so the
exposure is bounded to the authoring session itself. Not fixed; registered.

## B12.4 DISCHARGE-AUDIT ROW — the flagship pin's SUBSTITUTED PROOF ROUTE (R4 item 6)

| Claim | Brief's literal wording | What actually ships | Proof shape |
|---|---|---|---|
| "the q5 arm-A offender shape planted in `analysis_session.py` FAILS the extended ratchet — committed as a permanent self-test" | a plant in the REAL module, committed | **synthetic-source detector self-tests** (`test_detector_flags_*`, incl. the class-attribute shapes) + the **enumeration** and **ALLOWLIST** anchors that keep `analysis_session.py` in scope and its three consumers recorded | **round-mutation-proven** (instrument 13 arms A/B/C/D4) + permanence by construction |

Why substituted, stated plainly: a committed test cannot hold a real full-`Shell`
offender inside a production module — the offender would BE production code, and
the ratchet would be permanently red by design. Permanence therefore comes from
two committed facts (the module is in `CREATED_MODULES`; its consumers are the
only recorded entries) plus detector self-tests over synthetic sources, with the
real-module plant proven per-round by instrument 13 rather than frozen in the
tree. The brief's literal shape is not achievable; this is the honest
substitution, recorded so the audit does not read a discharged row as matching
the literal wording.

## B12.5 §A6 witness note CORRECTED — the TRUE `state.locale` census (R4 item 7)

§A6 named "`glob.py` / `parameter_expansion.py` / `enhanced_test_evaluator.py`,
the three `state.locale` readers" (inherited from the protocol's own docstring).
**That was an undercount by half.** Re-derived MYSELF by AST census
(`tmp/w5b1-instruments/19_state_locale_census.py`, transcript alongside), NOT
adopted from the round report:

**SIX production files, 13 access sites:**

| File | Sites |
|---|---|
| `psh/core/scope.py` | 1 |
| `psh/executor/array.py` | 2 |
| `psh/executor/enhanced_test_evaluator.py` | 2 |
| `psh/expansion/glob.py` | 1 |
| `psh/expansion/operators.py` | 1 |
| `psh/expansion/parameter_expansion.py` | 6 |

The three the prose omitted are `core/scope.py`, `executor/array.py`,
`expansion/operators.py`. **`LocaleAccess`'s 5B.2 witness set is these SIX, not
three** — and note `core/scope.py` is a CORE file reading the locale service,
which a three-file migration would have missed entirely. Ledger §A6's
`LocaleAccess` row is corrected accordingly; the protocol docstring now
enumerates all six (`dc843423`).

Method note: the census counts FILES and SITES separately. The prose quantifies
over readers (files), and conflating the two is one way "three" survived.

## B12.6 FIX-ROUND PRE-REGISTRATION — per-file sources ONLY (lesson 3 applied)

Every term below is a `--collect-only` count of a specific file, taken BEFORE
the ceremony gate. **No term appears that a per-file count does not
demonstrate** — the §B5 failure mode, deliberately not repeated.

| File | before | after | delta | source |
|---|---|---|---|---|
| `test_shell_consumer_ratchet_q1.py` | 20 | **22** | **+2** | collect-only |
| `test_posix_class_table_ownership.py` | 5 | **6** | **+1** | collect-only |
| `test_protocol_conformance_q1.py` | 7 | **7** | 0 | collect-only (renames move node IDs, not counts) |
| `test_protocol_name_collision_q5.py` | 7 | 7 | 0 | collect-only |
| **fix-round delta** | | | **+3** | sum of measured per-file deltas |

**Correction against my own D8 estimate:** D8 said "+1 for the RED self-test
arm". The landed count is **+2** for that nit, because I wrote the reason-
asserting RED arm AND a control asserting the endpoint IS an ancestor — without
the control, a warn path that swallowed every invocation would leave both cells
green. D8's figure was an intention; this table is a measurement, and where they
disagree the measurement is what binds.

**Expected at the ceremony tip:** 23,918 + 3 = **23,921 passed**, 1,620 skipped,
10 xfail. compare-bash **3,046 / 26, +0** (nit round is prose, guards and test
names — no shell-observable surface). ruff clean; mypy **276** clean.

## B12.7 Commits in the nit round

| SHA | Scope |
|---|---|
| `743159ab` | guard + contract truth (nits 1, 4, 5, 6, 9) — no production code |
| `dc843423` | doc + prose truth (nits 2, 3, 7) — prose only |

Declared BEFORE landing in D8, per the mechanical tip rule.

## B12.8 Routed items — acknowledged, NOT absorbed

| Item | Owner |
|---|---|
| Twin mypy guard still pinned `v0.724.0..75ab5625` (same staleness class, the q5-F3 mechanism) | **5C.1** charter pointer |
| Instance-assignment detector shape (`self.shell = s`) | **5B.2**, with the member-narrow work |
| Pre-existing order-dependence (`test_is_clean_distinguishes_no_owner_from_no_state`; fails after analysis/locale/expansion selection at BOTH SHAs identically, green standalone) | ceremony addendum, pre-existing |
| `ARCHITECTURE.md:98/:125` | **INTEGRATOR** at ceremony bump |
| CHANGELOG old-name mentions | HISTORY — never rewritten |

## B13. LEDGER REFREEZE (freeze-2)

Frozen again at the state above. **Chain rule: freeze-1 md5 was
`9328447039b7eb77de35c0d6cac62f4c`.** Freeze-2 md5 is declared in D9 (a file
cannot contain its own hash). Final tip after the nit round: **`dc843423`**.
