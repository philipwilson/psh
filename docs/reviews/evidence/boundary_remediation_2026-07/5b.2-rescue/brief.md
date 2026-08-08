# Slot 5B.2 — Consumer migration + caps — second Wave 5 slot

**Charter:** sequence §11 Package 5B + Checkpoint R ruling CR-R1
(LEDGER Part C) + Wave 5 slot map W5-R1 + **5B.1 ruling (b)** (LEDGER
Part C "Wave 5 rulings", evidence `5b.1-rescue/ledger.md` §A6 —
BINDING, carried verbatim below, NOT re-litigated). This slot owns the
MIGRATION half of MEDIUM-14 (the row CLOSES with this slot if its exit
is met) plus the LOW deferred-import goal-shrink:

1. **Escape-hatch member narrowings** — execute the seven-row §A6
   member-target table (design frozen in 5B.1; execution is yours).
2. **Zero-consumer protocol adoption** — land the three named
   witnesses so no protocol is defined-but-unused: `VariableAccess` ←
   the `VariableExpanderProtocol.state` narrowing; `ExpansionRuntime`
   ← `SubscriptEvaluator`; `LocaleAccess` ← the SIX `state.locale`
   readers (corrected census below — six FILES, 13 sites, NOT the
   three the old prose named).
3. **The 12 campaign-added owner params** (CR-R1 reshape 2: "IN 5B's
   migration set — mostly narrow status helpers, none
   protocol-shaped") — enumeration below; per-param disposition
   matrix, migrate-or-justify, my ruling on your Phase A matrix.
4. **Deferred-import caps goal-shrink** (LOW row): from the 5B.1 base
   of 198 cap total / 71 entries in `FUNC_IMPORT_CAPS`
   (`tests/unit/tooling/test_import_layering.py:224`; integrator
   re-measured at dispatch base) — actual expected ~177 (q4's 179 −
   5B.1's −2), slack ~21. Goal = genuine actual-count reduction
   (hoist-to-module-level where layering-legal, delete dead) + slack
   trim toward actual. Target figure = ruling slot (d).
5. **D-5B.1-s3** — extend the shell-consumer ratchet's detector to
   the `self.shell = s` INSTANCE-ASSIGNMENT shape (the exact shape
   5B.1's commit iv removed; a bespoke pin covers that one site
   today). Extension forces a tree sweep + dispositions. ALLOWLIST
   additions coupled to this detector extension are sanctioned under
   the 5B.1-R0 extended shape (same-commit, individually justified —
   the contract text shipped in 5B.1 already says exactly this).
6. Truthful docs (protocol docstrings, ratchet prose, any module
   docstring describing pre-migration ownership).

NOT this slot's: hub decomposition / typed errors / boundary
signatures / the untyped-defs ratchet endpoints (5C.1/5C.2 — the twin
mypy-guard stale endpoint D-5B.1-s2 is **5C.1's**, MUST-NOT-ABSORB);
printf %a/%A (rider 5R); re-opening ANY 5B.1 ruling-(b) fate (a
deviation you believe necessary = fence, stop-and-propose); the
broader 255-param full-Shell surface beyond the ruled migration set
(see "scope discipline" below).

**Base:** 1c70dfbf (v0.775.0 + 5B.1 addendum; local main ==
origin/main). Branch `fix/remediation-5b-2`, worktree
`/Users/pwilson/src/psh-r5b-2`. **Base figures (you RE-DERIVE in your
first gate run):** attestation 93c47edb-committed (gated a8c5de8f):
23,921 passed / 1,620 skipped / 10 xfail; ruff clean; mypy clean;
compare-bash 3,046/26 EXACT. Ratchet at base: 22 tests, ALLOWLIST 9
entries (6 pre-5B.1 + 3 analysis_session per 5B.1-R0).

**Slot shape: INTERNAL-INTEGRITY.** Expected shell-observable delta =
ZERO (compare-bash EXACT +0 pre-registered; conformance untouched).
Migration and adoption are annotation/signature/narrowing work; every
read the six locale readers perform, every status helper's returned
value, every builtin's behavior is IDENTICAL before and after. 4B.1
and 5B.1 are your model precedents.

**Scope discipline (read twice):** the tree-wide census figure is 255
Shell / 19 ShellState params (checkpoint-r report; the ratchet is the
inventory). 5B.2 does NOT migrate 255 params. The ruled migration set
= (i) the 12 campaign-added params (undoing the campaign's own
regression — wave-touched-file census 147→157 at Checkpoint R; both
figures below, don't conflate the denominators), (ii) the §A6
member-narrow consumers, (iii) the witness adoptions, (iv) whatever
the D-5B.1-s3 sweep surfaces, each dispositioned. The exit criterion
is the ratchet + ALLOWLIST + caps MOVING IN THE RIGHT DIRECTION by
measured, pre-registered amounts (ruling (d) fixes the numbers), with
the remainder still inventoried — not a boiled ocean.

## 5B.1 ruling (b) — carried VERBATIM (committed `5b.1-rescue/ledger.md` §A6)

> ## A6. Per-protocol fate matrix — all 9 (ruling (b) input)
>
> | # | Protocol | Defined at | Prod consumers | Recommended fate |
> |---|---|---|---|---|
> | 1 | `VariableAccess` | `protocols/__init__.py:91` | **0** | **adopt-with-witness in 5B.2** — keep, do not delete (witnesses named below) |
> | 2 | `ExpansionContext` | `protocols/__init__.py:119` | **0** | **rename → `ExpansionRuntime`** (this slot) + adopt-with-witness in 5B.2 |
> | 3 | `IOContext` | `protocols/__init__.py:149` | 2 | **keep-as-is** (migrated, witnessed) |
> | 4 | `JobRuntime` | `protocols/__init__.py:175` | 1 | **keep**; member-narrow `shell_state` deferred to 5B.2 |
> | 5 | `LocaleContext` | `protocols/__init__.py:216` | **0** | **rename → `LocaleAccess`** (this slot) + adopt-with-witness in 5B.2 |
> | 6 | `VariableExpanderProtocol` | `expansion/_protocols.py:27` | 4 | **keep**; member-narrow `shell`/`state` deferred to 5B.2 (the named escape hatch) |
> | 7 | `CommandParsersProtocol` | `parser/combinators/commands/_protocols.py:42` | 4 | **keep**; member-narrow `redirection: Any` deferred to 5B.2 |
> | 8 | `ControlStructureProtocol` | `parser/combinators/control_structures/_protocols.py:29` | 3 | **keep-as-is** |
> | 9 | `_TemplateCtx` | `parser/recursive_descent/support/syntax_templates.py:44` | 0 external, **7 in-module** | **keep-as-is** (module-private, fully used) |
>
> ### Escape-hatch member targets (design now, execution 5B.2)
>
> | Member | Today | Target (5B.2 executes) |
> |---|---|---|
> | `VariableExpanderProtocol.shell: 'Shell'` | full Shell on a protocol | REMOVE; consumers take the narrow surface they use |
> | `VariableExpanderProtocol.state: 'ShellState'` | whole state | narrow → `VariableAccess` (lands witness #1) |
> | `CommandParsersProtocol.redirection: Any` | untyped | type it at the concrete redirection-parser surface |
> | `JobRuntime.shell_state: Optional[ShellState]` | whole state | narrow → `VariableAccess`, or drop if the publish path can take the pgid directly |
> | `ExpansionContext.variable_expander: Any` | untyped | type → `VariableExpanderProtocol` |
> | `ExpansionContext.word_expander: Any` | untyped | type at the word-expander surface |
> | `LocaleContext.collate_key -> Any` | untyped return | keep `Any` **or** declare an opaque sort-key alias — the value is genuinely opaque (a libc-derived key); recommend a named alias over a false-precision type |

(Rename rows executed in 5B.1: the protocol sides are now
`ExpansionRuntime` and `LocaleAccess`; the member table's
`ExpansionContext.*`/`LocaleContext.*` rows therefore read as
`ExpansionRuntime.*`/`LocaleAccess.*` at your base. Witness notes for
rows 1/2 in §A6's delete-vs-keep section: `VariableAccess` ←
`VariableExpanderProtocol.state: 'ShellState'` narrowing;
`ExpansionRuntime` ← `psh/expansion/subscript.py#SubscriptEvaluator.
__init__`, which today takes full `Shell` and consumes
`shell.expansion_manager` per its own ALLOWLIST justification, and
also forwards to `evaluate_arithmetic` — the expansion HALF of its
need is the protocol; design its narrowing accordingly.)

**§A6's LocaleAccess witness note was CORRECTED by ledger §B12.5 (R4
item 7) — the TRUE census is BINDING here:** SIX production files, 13
sites (AST census, instrument `19_state_locale_census.py`, dev
re-derived + verifier-confirmed):

| File | Sites |
|---|---|
| `psh/core/scope.py` | 1 |
| `psh/executor/array.py` | 2 |
| `psh/executor/enhanced_test_evaluator.py` | 2 |
| `psh/expansion/glob.py` | 1 |
| `psh/expansion/operators.py` | 1 |
| `psh/expansion/parameter_expansion.py` | 6 |

`core/scope.py` is the layering-critical reader: a CORE file. Note
`CORE_MODULE_IMPORT_ALLOWLIST = {psh.ast_nodes, psh.utils,
psh.version}` does NOT include `psh.protocols` — Phase A must settle
the adoption route for that file (TYPE_CHECKING-only annotation
import vs other; probe the layering lock's own analyzer for what it
exempts, don't argue). The protocol docstring already enumerates all
six (5B.1 `dc843423`).

## The 12 campaign-added owner params (q4_08 census, integrator-quoted at dispatch)

NEW at Checkpoint R tip vs campaign base (wave-touched-file census
147→157 owner-params; −2 removed, +12 added; this is a DIFFERENT
denominator from the 255/19 tree-wide figure):

In functions NEW at tip (11):
- `psh/builtins/shell_state.py::HistoryBuiltin._dispatch_options(shell)` ['Shell']
- `psh/builtins/shell_state.py::HistoryBuiltin._display_operand(shell)` ['Shell']
- `psh/builtins/shell_state.py::HistoryBuiltin._parse_options(shell)` ['Shell']
- `psh/core/internal_errors.py::fatal_expansion_child_status(state)` ['ShellState']
- `psh/core/internal_errors.py::substitution_abort_status(state)` ['ShellState']
- `psh/core/internal_errors.py::substitution_child_abort_status(state)` ['ShellState']
- `psh/executor/child_policy.py::sync_child_status_for_exit_trap(state)` ['ShellState']
- `psh/scripting/analysis_session.py::AnalysisSession.__init__(shell)` ['Shell']
- `psh/scripting/analysis_session.py::AnalysisSession._build_carrier(shell)` ['Shell']
- `psh/scripting/analysis_session.py::parse_for_analysis(shell)` ['Shell']
- `psh/scripting/source_processor.py::iter_command_units(shell)` [name-based, unannotated]

Added to a pre-existing function (1):
- `psh/executor/child_policy.py::map_child_exception(state)` ['ShellState']

**Known tension, Phase A resolves (don't pre-judge in either
direction):** the three `analysis_session` params carry 5B.1-R0
ALLOWLIST entries with a recorded justification ("construction through
the caller's own Shell subclass is not protocol-shaped" — the
embedder-contract chain), while CR-R1 reshape 2 puts all 12 IN the
migration set. Your matrix presents, per param, what it ACTUALLY
touches (measured, not asserted), the narrow-now cost, and whether the
recorded justification survives contact with that measurement. My
ruling on the matrix decides migrate-vs-justified-keep per param.

## Phase A must settle (probe, don't argue)

1. **Per-member migration design for all seven §A6 member rows.**
   Enumerate each protocol's ACTUAL consumers per definition
   (instrument-mirror caution from 5B.1 point 4: name-hits ≠
   consumers; resolve per definition). For `VariableExpanderProtocol`
   (4 consumers — the arrays/fields/operands/operators family): what
   does each consumer actually reach through `.shell` / `.state`?
   The REMOVE row (`.shell`) only lands if every consumer's need is
   met by a narrower surface — enumerate need per consumer. For
   `JobRuntime.shell_state`: probe BOTH §A6 options (narrow →
   `VariableAccess` vs drop-for-pgid) with the single consumer
   (`executor/foreground_session.py`) and recommend one with the
   measurement. For the two `ExpansionRuntime` Any members: the
   typed targets exist (`VariableExpanderProtocol`; the word-expander
   surface) — verify mypy accepts the tightened types at every use
   site. For `collate_key`: propose the alias name + location.
2. **Witness adoptions.** `VariableAccess`: does
   `VariableExpanderProtocol.state → VariableAccess` satisfy all 4
   consumers' state usage, or does a consumer read state members
   outside `VariableAccess`'s surface? (If outside: matrix row with
   the exact member list — widening `VariableAccess` is a ruling,
   not a default.) `ExpansionRuntime` ← SubscriptEvaluator: narrow
   the __init__; the ALLOWLIST entry for subscript.py should then
   SHRINK AWAY — pre-register that. `LocaleAccess` ← six readers:
   per-file adoption route (annotation site, import route,
   TYPE_CHECKING or not), with `core/scope.py`'s layering route
   settled by probe (item above).
3. **The 12-param disposition matrix** (per-param: what it touches →
   narrow-now design or justification text). Include the removed-2
   for the net figure. `iter_command_units` is name-based/unannotated
   — the detector's name-based arm sees it; disposition it too.
4. **Caps enumeration + target.** Regenerate the actuals with the
   file's own analyzer (`test_import_layering.py` regeneration
   helper); classify every entry with slack or hoist potential:
   hoistable (layering-legal at module level — cite the rule that
   makes it legal), cycle-required (stays), dead (delete). Propose
   the target actual/cap/slack triple for ruling (d). Sweep the LOW
   row's wording for any second cap ledger in its scope (Q2 debt) and
   disposition it.
5. **D-5B.1-s3 detector extension.** Design the instance-assignment
   detector arm (`self.shell = s` and shape variants — settle the
   shape grammar: attribute names? annotated assigns? aliasing?);
   run the sweep over the scanned scope BEFORE building, so the
   expected new-hit set is enumerated in the matrix with per-hit
   dispositions (narrow / ALLOWLIST-with-justification under 5B.1-R0
   / false-positive with the detector refinement that excludes it).
   Mutation arms planned per 5B.1's shape: synthetic-source
   self-tests + per-round real-module plant; PYTHONDONTWRITEBYTECODE
   =1 in every driver; RED arms assert failure REASON.
6. **Carry sweep (THREE registers — Part B carries, Part C rulings,
   Part D successors).** Rows touching this slot: MEDIUM-14 (this
   slot ENDS it if exit met — say what closure requires), LOW
   deferred-import row (goal-shrink is THIS slot's), D-5B.1-s1
   (order-dependence flake — MUST-NOT-ABSORB, but your selections
   may trip it: know it exists, `test_is_clean_distinguishes_no_
   owner_from_no_state` after analysis/locale/expansion selections,
   pre-existing at BOTH 5B.1 SHAs), D-5B.1-s2 (5C.1's —
   verify untouched), D-5B.1-s3 (THIS slot discharges it),
   D-3.5-s2/D-4B.4-s3 (5C's — verify untouched), CR-D1..D6 (none
   touched — verify), locale carries (v0.688 reactive LC_* must not
   change), plus a grep sweep for protocol/locale/owner-param rows.
   Dispositions in the D2 table.

## Pins YOU create

- **Member narrowings:** per §A6 row — the widened shape is
  offender-proven dead (re-widening `VariableExpanderProtocol` with
  `shell: 'Shell'` bites a guard — the protocol-layering guard, the
  ratchet, or a new named pin; state WHICH); mypy green at every
  consumer; each consumer's suite green.
- **Witness adoptions:** each formerly-zero-consumer protocol has ≥1
  production consumer, pinned by census (the 5B exit "no protocol
  defined but unused" — make the census a committed self-test, not
  prose); subscript.py ALLOWLIST entry removal lands in the same
  commit as its narrowing.
- **12-param migrations:** per migrated param — signature narrowed,
  mypy green, callers updated, behavior cells green; per
  justified-keep — the justification text quoted in the ledger.
- **Detector extension:** offender-proven both directions (synthetic
  `self.shell = s` variants bite; refined exclusions DON'T bite on
  legal shapes — control arms); enumeration/coverage self-checks
  still loud; ALLOWLIST net movement pre-registered (additions under
  5B.1-R0 same-commit rule, removals from migrations — state the
  expected final entry count BEFORE the commit).
- **Caps:** the cap-table diff pre-declared in the ledger, derived by
  the analyzer (per-module terms with sources — lesson 3: every term
  a per-module measurement, no reasoned-to terms); layering lock
  green; each hoisted import's module still imports clean (the
  import-time side effects question — probe, per module).
- **Must-hold:** ALL locale suites (reactive LC_*, provenance),
  expansion suites (arrays/fields/operands/operators territory),
  job-control suites (foreground_session), history builtin suites,
  analysis suites (2.6 derivation guard), the ratchet's 22 (extension
  adds, never weakens), protocol-layering guard, import-layering
  lock, every 4B.x suite. compare-bash 3,046/26 EXACT +0
  (pre-registered BEFORE any run). NO golden-case changes expected;
  declaring one = fence.

## Must-NOT-flip

- Any shell-observable behavior anywhere (internal-integrity slot).
- The six locale readers' READ BEHAVIOR (adoption = typing/annotation
  work; every `state.locale` read returns what it returned before).
- Reactive LC_* machinery (v0.688) and locale provenance.
- `analysis_session.py` BEHAVIOR (2.6's guard + suites green
  regardless of the param ruling).
- History builtin behavior (the three `HistoryBuiltin` helpers).
- Child-status/exit-trap semantics (`internal_errors`/`child_policy`
  helpers return the same statuses — these feed 1.3b territory;
  narrowing must be signature-only).
- The ratchet's existing guarantees (22 tests; extension adds, never
  weakens; NAME-VS-BODY on your own edit).

## FENCES (stop-and-report BEFORE touching)

- **Any deviation from a ruling-(b) fate or member target** — the
  design is BINDING; if measurement shows a target can't land as
  ruled (e.g. a consumer needs state members outside
  `VariableAccess`), STOP with the census row; do not improvise a
  wider protocol or a new fate.
- **Widening ANY protocol surface** (adding members to
  `VariableAccess`/`ExpansionRuntime`/`LocaleAccess`/any other) —
  ruling required.
- **ALLOWLIST growth outside the 5B.1-R0 extended shape**
  (same-commit detector/scope-extension-coupled, individually
  justified — anything else is a breach, not a judgement call).
- **`CORE_MODULE_IMPORT_ALLOWLIST` changes** — if core/scope.py's
  adoption route seems to need one, that's a stop-and-propose with
  the probe transcript, not an edit.
- **5C surfaces:** hub bodies, typed-error handlers, untyped-defs
  ratchet endpoints (D-5B.1-s2), signature census tooling —
  MUST-NOT-ABSORB.
- **D-5B.1-s1** (the order-dependence flake): if your selections trip
  it, RECORD (SHA, selection, both-SHA replay) and route to the
  registered row — do NOT fix it in this slot.
- Golden cases, conformance tables, user guide (no user-visible
  change exists to document — needing one = you've left the slot's
  shape, stop).
- CR-D1..D6, all D-4B.x/D-3.x successor rows: MUST-NOT-ABSORB.

## Slot-specific test hygiene

- Tooling-heavy again: every new/extended guard self-tests its
  scanner offender-proven, with control arms for the exclusions.
- `PYTHONDONTWRITEBYTECODE=1` in EVERY mutation driver (5B.1 lesson 1
  — same-length edits defeat pyc mtime+size invalidation).
- RED arms assert failure REASON, not just outcome (lesson 2).
- Pre-registration terms from per-file `--collect-only` counts ONLY
  (lesson 3 — the §B5 phantom term).
- collect-only count FIRST for any pytest arg that isn't a file/node
  ID.
- Fresh-checkout leg standing; the ratchet's git-less warn-path must
  survive your extension.
- No PTY, no serial cells expected; in-process only; xdist-safe.
- Instruments are FILES from the start under `tmp/w5b2-instruments/`
  in YOUR worktree; committed 5b.1-rescue + checkpoint-r instruments
  are READ-ONLY (copy, record the single path edit).

## Pre-declared ruling slots

- **(a)** Phase A matrix (per-member designs + witness-adoption
  routes incl. core/scope.py + 12-param dispositions + caps
  enumeration + detector-sweep dispositions + carry sweep) = GO gate
  for Phase B.
- **(b)** ALREADY RULED (5B.1 ruling (b), carried above) — cite it,
  never re-open it; deviations discovered by measurement = fence
  route.
- **(c)** fence pulls = stop-and-propose with the census row.
- **(d)** caps target ratification (actual/cap/slack triple) = MINE,
  on your Phase A enumeration.
- **(e)** per-param migrate-vs-justified-keep for the 12 (incl. the
  analysis_session tension) = MINE, on your matrix.
- **5B.1-R0 (pre-ruled, extended shape):** ALLOWLIST additions ONLY
  as same-commit scope-/detector-extension-coupled justified entries.

## Rules

The FULL binding rule set is `docs/reviews/evidence/
boundary_remediation_2026-07/4a.1-rescue/brief.md` §Rules — binding
verbatim (never-touch list — devs never touch version.py / CHANGELOG
/ README / ARCHITECTURE / docs/reviews/README / FLIP-PINS / LEDGER;
never push/PR/tag — dead-drop + ACK-the-highest-R + md5 chain,
mechanical tip rule, ledger freeze + freeze-md5-in-declaration +
freeze-chain, per-hunk staging, SHA paste-from-instrument,
pre-registration + GO-binding citation, RN-Cdoc,
CERT-ROW-BEFORE-CLAIM, NAME-VS-BODY — your named siblings: the
tooling guards (`tests/unit/tooling/` — the ratchet, layering lock,
protocol-layering, mypy-scope, posix-class table ownership), READ
THEM FIRST — instrument discipline, axis quantification, discharge
audit, gate rules (ONE heavy run machine-wide, unpiped `pgrep -f
pytest` AND `pgrep -f run_tests` first, foreground, never shell-`&`,
NEVER `run_tests.py --compare-bash` — use `python -m pytest
tests/behavioral --compare-bash -n auto -q`), oracle rules (PATH bash
`/opt/homebrew/bin/bash` 5.2.26, explicit argv, never /bin/bash),
project tmp/ only, peer-escalation/permission-laundering wrapper,
never touch the parallel session's uncommitted files (`d/`,
`decomment.py`, `docs/reviews/ground_up_*`)). PLUS the D-4A.1
additions + 4A.2 lessons + the 11 banked 4B.1 lessons + the 11
banked 4B.2 lessons (`briefs/4b.3.md` §Rules, by reference) + the
4B.3 structural rules (1)–(10) (`briefs/4b.4.md` §Rules, by
reference) + the 4B.4 banked lessons (release-site audits, TWO-AXIS
instruments — divergence axis EMPTY this slot, prove it —
mutations-that-cannot-fail, acceptances-are-claims, THREE-register
carry sweeps, every hook tripwired, sign-off legs PRE-REGISTERED
BEFORE THE TAG) + the Checkpoint R additions (FLIP-PINS is the
authoritative deviation register; instrument PORTABILITY; CR-D6
record-only retirement class) + **the FIVE 5B.1 banked lessons
(LEDGER D-5B.1-lessons, binding verbatim):**

1. `PYTHONDONTWRITEBYTECODE=1` in every mutation driver.
2. A RED mutation arm asserts its failure REASON, not just outcome.
3. Every pre-registration term needs a SOURCE — per-file counts only.
4. Mid-slot main advances merge into the release branch BEFORE the
   attestation gate (integrator executes; YOU flag any main advance
   you observe mid-slot in your next D-entry).
5. Dead-drop entries get an EXPLICIT wake-up nudge BOTH directions,
   every entry, no exceptions — the channel dropped R3/R5/R6 in one
   slot; channel silence is itself evidence, the FILE is
   authoritative. Re-read the inbox at the START of every turn and
   ACK-the-highest-R found there.

New axes for this slot: **MEMBER × CONSUMER** (each §A6 member row ×
each of its consumers × migrated / justified / fence-routed) and
**READER × ADOPTION-ROUTE** (each of the six locale readers × its
import/annotation route × layering-lock cell) and **PARAM ×
DISPOSITION** (each of the 12 × migrate / justified-keep, ruled).

Done = Phase A matrix + rulings (d)/(e) applied — all seven §A6
member rows executed or fence-resolved + three witness adoptions
landed with census pins + the 12 params dispositioned per ruling +
D-5B.1-s3 detector extension landed offender-proven with the sweep
dispositioned + caps at the ruled target with analyzer-derived diff +
ALLOWLIST net movement as pre-registered — + truthful docs +
must-not-flip green + compare-bash at the pre-registered figure +
green gate + ruff + mypy + discharge audit + complete ledger →
completion report with declared final tip + frozen ledger (chain
rule) + instrument manifest (self-excluding, command-generated).
