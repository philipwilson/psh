# Slot 3.1 — rounds, verdicts, faults, errata (integrator record)

Slot: Boundary Remediation 3.1 — pattern correctness (HIGH-7 semantics
half). Base 29456fdc (v0.762.0) → ceremony tip cced9aca (11 commits).
Dev: dev-3-1 (Fable, single dev, no handover). Integrator: session lead.
Companion files: `slot-ledger.md` (dev ledger AS-IS, sections A/B/C/D/E),
`integrator-inbox.md` (rulings R0–R15), `brief.md`, `instruments/`.

## Rounds

| Round | Workflow | Verdict | Blockers | Nits | Substance |
|---|---|---|---|---|---|
| 1 | wf_eb98cad4-c01 | **BOUNCE** (diffAudit FAIL; 3 others PASS-WITH-NITS) | 3 | 14 | Corpus `_PRE` grammar lacked star-literal-star contexts → (B-1) `_BashMatcher` end-of-subject negation shortcut ignored trailing elements = base-correct→tip-wrong REGRESSION all 5 consumers (~1,034 cells in `[[` alone); (B-2) chartered `*<lit>*!(...)` family still divergent while claims said "0 mismatches" unscoped; (B-3) consumer `*`-wrap made extglob-headed substitutions quirk-flagged → undeclared quadratic (A9 declaration false). All three integrator-replayed before ruling. |
| 2 | wf_278fd24b-a62 | **BOUNCE** (diffAudit FAIL; 3 others PASS-WITH-NITS) | 2 | 15 | Star-jump fix SURVIVED a 1.8M-cell independent assault (0 mismatches outside one class; 60k fuzz clean). (B2-1) wrap-guard docstring stated a FALSE bash mechanism (escaped `\*` tail); 45/1,520 escaped-metachar cells divergent, ZERO backslash corpus coverage. (B2-2) the R7 mitigation sentence ("tip still beats live bash on the idiom") FALSE for the consecutive-run shape — bash is FLAT there; **integrator fault #1 tallied** (unscoped generalization originated in ruling R7). B-3 discharge re-opened → Path A ordered. |
| 3 | wf_1b19aad6-f56 | **PASS** (all four PASS-WITH-NITS) | 0 | 14 | Escaped-axis three-point clean incl. the paren-pun cell; wrap-guard teaching-vs-code clean; equivalence-prover forcing verified real BY BREAKING IT + M6 own-reason; perf re-measured in-range both shapes; deleted-decider quadrants re-derived; recovery #2 byte-exact via the Phase-D patch instrument; perimeter + anchors + 10 round-2 grammar spot rows green. 14 nits dispositioned in R14; cleanup commit 11 + ledger errata E-1. |

Fix arcs: round-1 → commits 7–8 (glibc star-jump mechanism from
sm_loop.c — inter-star segments committed at LEFTMOST match, never
retried; widened grammar-v2 battery; corrected A9 declaration + 3.2
handoff). Round-2 → commits 9–10 (raw-char both-ends wrap guard incl.
the paren pun; backslash-axis corpus4 DIFF 7→0; Path-A eligibility-gated
fast path, equivalence 341,836 comparisons 0 disagreements with real
forcing; N7 rename with collected proof). Round-3 → commit 11 (R14
cleanup: guide-¶71 scoping, retired-symbol marker, battery hygiene +
per-row three-point/control labels, opx_slash residual row).

## Fault register (final)

- **Integrator: 1 tallied + 2 procedural notes.** Tallied: R7's
  unscoped perf-mitigation sentence ("the idiom" without its subject
  shape — R21-C class: cells measured, chain interpolated), falsified by
  round 2, errata in ledger D-2. Procedural: R12 mis-stated the stall
  point (dev corrected with provenance; accepted); R13 cited in channel
  before landing in the dead-drop (dev flagged per protocol; landed
  retroactively).
- **Dev: 4, all self-caught, all with hardened instruments as the
  response.** R4-C poll-before-send slip (C-10); checkout-slip #1
  (mutation-replay script `git checkout` wiped uncommitted Phase C —
  replay hardened to cp-backups, second script bug found in the same
  hardening); checkout-slip #2 (manual, caught by idempotence asserts —
  posture escalated to BINDING cp/patch-only, third slip = stop-and-talk);
  VOID equivalence proof (lru-cached gate laundered the fast arm —
  caught because mutation M6 did NOT fire; cache-clear forcing added,
  M6 made a permanent prover-proving replay class).

## Errata index

Ledger section E-1 carries the round-3 errata in full: A4 sample-count
is STATE-DEPENDENT with the formula recorded (40 stride + min(15,
divergent) — 55 at base, 40 at a clean tree); "union 437,811" re-worded
(row SUM 437,811 / distinct union 427,586; +558 backslash-axis = the
428,144 equivalence universe, reconciles exactly); matching_starts A9
wording corrected (evaluation SHAPE preserved; the routing hunk in
8713f7e0 is required for suffix-removal consumers, verified rounds 1–2);
3.2 handoff table extended with the round-3 verifier's full_match cubic
baselines (`**(a)b` ×8/doubling vs base ×4, 85× at N=400 —
script-visible, flagged 3.2 OPENER PRIORITY) and matching_ends
(`*!(a)` 17× at N=200), attributed.

## Lessons banked (into LEDGER Part D 3.1-lessons row)

1. A generated corpus's CONTEXT GRAMMAR is itself an axis — PRE/POST
   context lists must be argued for coverage, never assumed (dev battery
   + full gate + integrator spot check all shared round-1's blind spot;
   only the independent-corpus rule caught it).
2. Subject SHAPE is an axis — no measurement sentence without its shape
   scope ("the idiom" is not a measurement unit).
3. Backslash/escaping is an axis (round 2: zero backslash coverage hid
   a whole class).
4. A proof that cannot fail is not a proof — provers get forcing, and
   forcing gets its own mutation class (M6 pattern).
5. Restores go through cp/patch instruments only; `git checkout` over
   uncommitted work is how state dies (two instances, one slot).
6. Mutation-replay + assertion-rewrite caches: same-second same-size
   reverts are invisible to mtime+size .pyc validation — drop
   __pycache__ after every revert (round-1 gate false-red, B7).

## Instrument regeneration

`instruments/README.md` lists what was rescued and how to regenerate
the omitted bulk (bash-5.2 source tree/tarball, corpus TSVs, generated
one-spawn bash scripts, glob fixture dirs).
