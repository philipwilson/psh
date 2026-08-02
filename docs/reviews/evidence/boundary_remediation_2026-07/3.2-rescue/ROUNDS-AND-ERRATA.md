# Slot 3.2 — rounds, faults, and errata (integrator record, written at ceremony)

Slot: pattern engine integrity/perf (HIGH-7 perf half + MEDIUM-6).
Base `da037aa8` (v0.763.0) → final tip `d34798eb` (8 commits).
Companion files: `slot-ledger.md` (dev's ledger, 1,248 lines, as-is),
`integrator-inbox.md` (rulings R0–R11, as-is), `brief.md`,
`instruments/` (43 files + README).

## Rounds table

| round | run | verdict | blockers (distinct) | nits |
|---|---|---|---|---|
| 1 | wf_fda068d8-424 | **BOUNCE** (all 4 verifiers FAIL) | 5 (7 reports) | 19 |
| 2 | wf_39709027-afd | **PASS** (all 4 PASS-WITH-NITS) | 0 | 16 |

Round-1 blockers, all real, none false: B1 eligible-control perf
regression (eager all-start pre-filter in `spanner()`: O(n²) at
construction inside Path A; ~1,600× at N=3200; NO shipped pin could
see it); B2 false discharge claims (ledger tip cells ~3 orders off —
measured in the live worktree against pre-final tree states); B3
transition pins vacuous on their extglob rows (fixed `'a'*n` subject
short-circuits before the group) + counter blind to negation-group
`_element_ends` work; B4 module narrative taught the pre-rewrite
architecture; B5 Linux reasoning absent from the ledger.

Fixes: `a224321b` (has_extglob gate on the pre-filter; counter counts
`_element_ends` + `_alt_closure`; new `operation_transitions`
end-to-end instrument; narrative rewrite), `6407c1c4` (pin split
extglob-free linear / extglob-bearing achieved-bound on shaped
subjects; gate pin 402-vs-exactly-0 both directions; D-2 pin on the
real consumer; `*+(a)` reclassified shape-conditional), `7c812d00`
(tight-bound-safety docstring), `d34798eb` (round-2 nits 1/7/9:
CLAUDE.md scope, comment de-narrativized, `_seq_nullable` shim deleted
with re-verified census).

## Fault register

**Dev faults: 1 verifier-caught + 1 self-caught-in-phase.**
- Fault #1 (VERIFIER-CAUGHT — the campaign's first dev fault not
  self-caught): the round-1 ledger's B2/B12 tip perf cells were STALE
  live-worktree measurements predating the eager pre-filter (mtime
  proof in `slot-ledger.md` §F1; both exhibits preserved in
  `instruments/`). Not a wrong measurement — a stale one believed
  current. NEW BINDING RULE issued (R4): every perf certification row
  is measured at a DETACHED checkout of the declared tip; per-table
  provenance, not per-run.
- Self-caught (Phase B, disclosed unprompted): three of seven mutation
  classes (M1/M3/M7) initially failed to fail — the counter observed a
  re-derived path, not the consumer path (the same class as the
  accidentally-green pin the dev itself found in Phase A). Fixed in
  the ENGINE (relations return the matcher they used; count at the one
  door; construction counting), not in the tests.

**Integrator faults: 0 tallied; 1 superseded ruling on the record.**
R5(3) excused the ineligible-consecutive quadratic as a family floor —
the mechanism attribution was wrong (it was the dev's own pre-filter
regression masking a real win). The ruling text hedged on mechanism
and directed stop-and-propose; the dev used exactly that route and R6
re-ruled with both sides' measurements agreeing (0.0089s dev /
0.0093s integrator, independent instruments). No fault either side;
recorded as the stop-and-propose clause working as designed.

**Verifier record:** round-1's `!(a)b` "wall quadratic / counter
linear" cell settled in round 2 as PARTLY harness-shape: the
per-position spanner construction manufactured its own quadratic for
`full`/`ends`/`starts`, but the SCAN relation is genuinely quadratic
in both wall and count — the verifiers' half was the better-founded
one (dev conceded on the record, `slot-ledger.md` §G1, both figure
sets, no fault assigned).

## Banked lessons (carried into LEDGER Part D)

1. A complexity pin that counts the wrong quantity is accidentally
   green twice: the shipped `count_states` pin could not see the cubic
   it guarded, AND three fresh mutation classes failed to fail for the
   same reason one level down. The lock is M8: the round-1 blocker
   itself is a permanent mutation class, caught by the gate pin at
   construction.
2. Stale-not-wrong is its own fault class: "some tip files are fresh"
   does not certify THIS table. Per-table provenance; detached
   checkouts for every perf certification row (B71 extended to devs).
3. Tight count bounds are safe ONLY because transition counts are
   deterministic integers; the same margin on wall clock is a flake
   generator (recorded in the pin file's docstring).
4. An instrument that calls a symbol the change deletes turns a
   retirement into a fake semantic disagreement — prover arms read
   whichever form their tree provides (R11-sanctioned adaptation).
5. Subject SHAPE remains the axis that catches everyone: round-1's
   vacuous pins (fixed `'a'*n` short-circuits before the group) are
   the 3.1-fault-#1 class recurring in pin-row selection.

## Errata index (into `slot-ledger.md`)

- §F1 fault #1 + exhibits; §F3/G1 the `!(a)b` both-readings settlement;
  §F13 non-empty bounced-rows replay (every B and must-fix nit);
  §G2 B12 supersession annotation; §G3 re-derived negatives;
  §G4 count_states logic-vs-docstring resolution; §G5 INSTRUMENTATION
  exemption (threat model second clause, ruled R10); §G6 states-bound
  declared pin change record; §G7 micro-commit census + prover
  adaptation.
