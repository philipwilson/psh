# Slot 3.3 — Rounds, Faults, and Banked Lessons

Slot: Operand field IR (HIGH-6). Base d0f7d929 (v0.764.0). Final tip
**1f57c46e** (6 dev commits). Shipped as v0.765.0.

## Rounds

| Round | Tip | Verdict | Blockers | Nits | Notes |
|---|---|---|---|---|---|
| Phase A | — | GO + 3 rulings (R1) | — | — | 1,825-cell probe matrix (later corrected to 1,970 rows); dev self-caught+retracted a flip-pin vacuity claim BEFORE the ruling; integrator independently reproduced every decisive cell |
| mid-B | — | R2 (2 declared sites + scope + H6 in-slot) | — | — | case-pattern inventory CORRECTION (bash = first-field, not join); bare-`$@`/IFS stop-and-propose → successor; H6 ruled in-slot from integrator's 19-cell mechanism table |
| pre-gate | a8ed586e | R3 spot-check clean + gate GO | — | — | 13 headline cells reproduced at detached checkout; guard caught dev's own nested re-flatten on first run |
| gate-1 | 0bc4aa4e | 2 guard failures, both real | — | — | import ratchet + ExpandedField producer conflict (created by ruling (c); re-cut CONFIRMED R4.1) |
| **1** | 8251ed51 | **BOUNCE** (wf_3ce52d9a-bed) | 6 (5 distinct) | 13 | redirect-target unpinned+misrecorded (2 verifiers converged); array-view family unpinned (mutation-proven); false `_psh_comb` claim (originated in the BRIEF); 2 silent brief items |
| **2** | d81ae82b | **BOUNCE** (wf_b75bed27-851) | 2 | 15 | C13 typed count (+207/−16 vs derived +185/−4); false bash-semantics claim in CLAUDE.md + guard header on the R2.1-corrected cell |
| **3** | 1f57c46e | **PASS** (integrator direct) | 0 | 0 | all 9 numstat figures derive exact; false sentence greps 0 both texts; 7 probe cells red-on-base/bash-equal-at-tip; 357 pin-suite rows green at detached tip |

Blocker record: **7 distinct blockers, 7/7 real, 0 false** across both
harness rounds. Gate predictions: **three consecutive exact**
(23,001 → 23,024 → 23,032, each pre-registered from `--collect-only`).

## Fault register

Dev (all self-caught unless noted):
- Phase A flip-pin vacuity claim — retracted before ruling (self-caught).
- Hand-tally accounting ×2 (Phase A totals; "+108" delta) — self-caught.
- C1 tag-vs-raw sweep: verdict-tag comparison hid a DIFF→DIFF
  content-changed cell (VERIFIER-caught, round 1) → rawsweep rewritten
  to raw (stdout, rc) pairs.
- C5 bounded `find` (-maxdepth) reported as an unbounded absence claim
  (INTEGRATOR-caught) — wrapped in an honest-looking limitation
  disclosure, which made it MORE credible.
- E1 C13 typed count with NO instrument (VERIFIER-caught, round 2).
- Three more instances in one sitting, all self-caught while fixing E1:
  summed-vs-range cumulative; moving-reference range label
  (`..HEAD`); and an OVER-CORRECTION — annotating a CORRECT figure as
  faulty by assuming the class instead of deriving (a false FAULT
  claim, the same failure with the opposite sign).
- B3 share: repeated a false brief parenthetical unverified.

Integrator:
- Brief drafting fault #1: scope list omitted `operators.py` — the file
  containing all nine `_expand_operand` call sites (caught by dev's
  stop-and-ask).
- Brief drafting fault #2: the false "`the existing pin runs
  _psh_comb`" parenthetical (caught by round-1 ledgerCheck; propagated
  into dev ledger A2.5).
- Monitoring instrument fault (self-caught, disclosed): `pgrep -fl |
  head -4` truncated by a multi-line wrapper entry → false "no pytest
  running" during gate-2; briefly cast doubt on a clean dev run; log
  continuity + dev's independent timeline reconstruction proved one
  continuous run. Also: macOS `pgrep` has no `-c` — safe forms are
  unpiped exit-status branching or `| wc -l`.

## Banked lessons (→ LEDGER Part D)

1. **The bounded-instrument class** (dev-named, five instances + one
   over-correction in one slot): *Every number entering the durable
   record is produced by a command shown beside it, and every range is
   named by an explicit SHA, never a moving reference. A number without
   a visible instrument, or a range without a fixed endpoint, is an
   estimate — label it or derive it.* Corollaries: a bounded search
   reported without its bound is a false unbounded claim; a limitation
   disclosure is not a substitute for an exhaustive instrument (it can
   make a false claim MORE credible); fixing the instance instead of
   the class is the same mistake one level up; and an audit that
   manufactures findings (assuming the class) is no more trustworthy
   than one that misses them.
2. **Raw-pair sweeps**: mechanical base-vs-tip comparisons must diff
   RAW OUTPUT PAIRS, never verdict classifications — a DIFF→DIFF cell
   whose content changed is structurally invisible to a tag sweep. The
   corrected form also yields the strictly stronger statement
   ("away-from-bash 0").
3. **Line-budgeted filters on process checks**: never pipe a process
   check through `head`/`tail`/`sed -n` — multi-line command entries
   eat the budget (integrator's own fault). Use unpiped exit-status
   branching; note macOS `pgrep` lacks `-c`.
4. **Doc sweeps must propagate ruling corrections to every durable
   statement** — the R2.1 case-pattern amendment reached the ledger and
   an inline comment but not the committed CLAUDE.md or the guard
   header that teach (reappraisal-#19 failure mode, caught in round 2).
5. **Claim-made-true beats claim-retracted** where cheap: the false
   `_psh_comb` sentence became a real 7-row combinator pin; the false
   "SHAs inlined" disposition became actual inline SHAs.
6. **The loud-projection design pays**: `OperandValue.__str__` raising
   TypeError surfaced a consumer the probe matrix missed (case
   PATTERN) at implementation time, and the projection guard caught a
   real re-flatten in the dev's own change on its first run.

## Errata index (dev ledger corrections C1–C13 + post-R7 sections)

C1 raw-sweep rewrite · C2–C4 round-1 pin gaps (redirect, array-view,
combinator) · C5-CORRECTED bounded-find retraction (with reproduction
of the miss) · C6–C8 nit closures · C9 corpus-scoped conclusion ·
C10–C12 must-not-flip/individual-run additions · C13 per-commit table
(fully re-derived, deriving commands inline) · E1 the typed-count root
cause + the mechanical rule.

## Deliberately preserved oddities

- The dev's `[`-builtin pin row measures `too many arguments` (its cell
  shape) where the round-2 verifier's cell measured `binary operator
  expected` (3-arg form). Both are real bash behaviors of different
  shapes; the dev pinned what it measured and flagged the difference
  rather than reshaping the cell to match the ruling's wording. The
  integrator's round-3 replay confirmed BOTH shapes bash-equal at tip.
- `instruments/` contains the round-1-era transcripts with base-SHA
  headers (superseded by the `-post`-worktree re-measurement per NIT 4)
  — kept as the record of the provenance fault, per campaign practice.

## Regeneration

All instruments run against PATH bash 5.2.26 (`/opt/homebrew/bin/bash`)
with cwd inside a checkout of the SHA named in each transcript header
(discriminator asserted). `instruments/rawsweep.py` regenerates the
base-vs-tip sweep; `instruments/mutate.py` re-runs the five M8 classes
(cp-restore, sha-checked, `__pycache__`-dropped). `integrator-probes/`
holds the integrator's independent reproductions (probes.txt through
probes6.txt with driver loops inline in the session record).
