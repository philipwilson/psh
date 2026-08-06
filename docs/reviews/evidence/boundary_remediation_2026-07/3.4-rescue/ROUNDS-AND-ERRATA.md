# Slot 3.4 — Rounds and Errata (integrator-authored, at ceremony)

Slot 3.4 (resolution authority timing, HIGH-3) shipped as **v0.766.0**
from closing tip `42739f6af6a0b25620c1812f8cd597c85e7a0414`
(28 commits over base `241a923c`, branch `fix/remediation-3-4`).
This document is the navigable summary of the slot's SEVEN
verification rounds; the durable primary records are `slot-ledger.md`
(the dev's ledger, frozen + two R30-supervised edits) and
`integrator-inbox.md` (dead-drop rulings R0–R31 — the file IS the
protocol; it absorbed 10+ channel crossings).

## What shipped

Two-phase prefix transaction: `expand_prefix` (left-to-right staging
into an enumeration-invisible `is_staging` temp-env scope; each
value's in-process side effects visible to later values AND to
resolution) → exactly ONE `resolve_command` from post-side-effect
authoritative state → `commit_prefix` (kind-routed install reading
LIVE staged values; no second expansion). Refuse-before-evaluate on
readonly prefixes (bash-measured: a refused assignment's value is
NEVER evaluated). Closes **HIGH-3** (both signature cells:
`A=$((POSIXLY_CORRECT=1))` and `${POSIXLY_CORRECT:=1}` prefixes now
dispatch like bash) and **carry #7 scoped** (interleave reads +
function-target masking + seed-at-commit; the command's OWN read on
the LAYER route remains a pinned divergence — "a later prefix and the
command itself are different readers"). RO1 taken in-slot (declared-
unset readonly refused on the function route, bash skip-and-continue
shape). Generated side-effect-KIND family (44 = 26 refused + 18
control); 233-row conformance battery (100 red-on-base) + 11-test
ordering ratchet; option-(F) staging flag with exactly FIVE sanctioned
`psh/core/scope.py` edits + prose-only `state.py`.

## Round table

| round | tip | verdict | blockers (all verified real by integrator) |
|---|---|---|---|
| 1 | 7952a721 | BOUNCE 7 | temp-env enumeration regression; nameref seed-route silently lost vs ruling (b) (AMENDED from measurement); staging-scope leak on mid-expansion error; false delta-accounting rows; transclusion negative dropped; Linux row dropped; doc-sweep residue |
| 2 | 9d840d11 | BOUNCE 7 | F-family missed the FUNCTION route (the only route where base was wrong); README stale at tip; own-name axis dropped; WRONG SHA in the final-tip header; stale count in the N1 row; false RED-ON-BASE claim on the D4 pin; ledger still teaching the dead seed route |
| 3 | 4237c693 | BOUNCE 5 | COMPOSITION regression (refused-readonly × posix-flip → statement abort; fix ruled: refuse-before-evaluate); false ledger invariant + name-level-only pin; RO1 control-flow observables unpinned; SEM-2 family target-kind over-claim; $((RANDOM)) axis dropped (hid an already-flipped row) |
| 4 | 5d3b426d | BOUNCE 4 | hoist's further consequence classes undeclared (`:=`/cmd-sub/xtrace + the FATAL-EXPANSION class: a script that stopped now continues); nameref-spelled posix store flips a base-MATCH cell (N8-class, pinned not fixed); round-4 commit map absent |
| 5 | 31781e76 | BOUNCE 3 | STALE STAGED-PAIR SNAPSHOT (split-brain: later prefixes vs the command; fix ruled: live-read); last-edit sweep rule broke on first test (→ LEDGER FREEZE); round-5 pre-registration missing (mitigated by R20) |
| 6 | 43391af2 | BOUNCE 1 | nameref spelling of readonly prefix, function route: presence toward-bash unpinned; wording (target-vs-nameref) pre-existing, pinned both-sides |
| 7 | 42739f6a | **PASS w/ 1 supervised correction** | round-7 pre-registration claim UNPROVABLE — caption retracted under R30 supervision (figures independently re-derived true) |

**Scorecard: 28 blocker-class findings, 28 real, 0 false** (27 harness
+ 1 integrator-direct). Trajectory 7→7→5→4→3→1→1. Three REAL
semantics regressions, every one at a COMPOSITION cell of two
individually-correct changes; the dev's own shipped pin family caught
a fourth in-flight (the nameref staging-key miss) before any verifier
saw it.

## Fault register (disclosed, both sides)

Dev: ruling-(b) compliance recorded while the implementation diverged
(round 1 — the slot's gravest item); typed SHA in the most
load-bearing row; "ratchet = 12" written inside the paragraph banking
the lesson about unmeasured numbers; the 44-vs-45 relation error; the
N8 premise measured from an inference; vacuous cycle-leak pins
(subject shape); the round-7 pre-registration caption. Integrator:
R1's wrong root-cause caution on `_readonly_blocks` (inverted by the
dev with evidence); a faulty script-mode replay instrument (disclosed,
re-run); the round-2 harness extraChecks sharing the F-family's
external-only blind spot; pre-registration left as an ACTION on the
integrator side for three failing rounds (→ the R30 GO-binding rule).

## Banked lessons (carried to LEDGER Part D)

1. Instruments were the weakest part of the work, not the code — and
   every faulty one was corrected by an external check, never by
   self-review (the slot's actual finding).
2. An axis you contribute is the one you're least likely to walk.
3. Fixes COMPOSE: the matrix must include the composition cells of
   any two in-slot changes.
4. A rule phrased as an ACTION depends on memory; phrased as a
   PROPERTY of the artifact it is checkable (ledger freeze, RN-Cdoc
   slot, GO-binding — all instances).
5. A derived RELATION between two sourced numbers needs its own
   instrument ("an estimate wearing two citations").
6. A compliance claim needs an instrument like any number.
7. A test that passes before its fix is written proves nothing; a
   prover needs forcing on the REAL path.
8. A careful label on a vacuous probe still misleads (subject shape).
9. Publish a negative only after the cell arrives ("requesting and
   concluding in the same breath makes the request decorative").
10. A closure claim that outruns its evidence is worse than an open
    carry ("different readers, one fixed").
11. The provenance check is not "are the numbers right" but "does the
    record show WHEN they were written."
12. A pre-approval slot is read narrowly: borderline = OUT ("a slot
    that stretches is how a pre-approval quietly becomes a blank
    cheque").
13. An instrument whose evidence trail becomes its own input either
    cries wolf forever or quietly stops checking (SHA sweep →
    value-allowlist).

## Successor family (eight, all pinned both-sides; LEDGER Part D)

1. Diagnostic-wording class: readonly refusal names the TARGET where
   bash names the NAMEREF (pre-existing, both routes).
2. Posix hook over-couples on nameref write-through
   (state.py posix coupling; flips `A=$((npc=1))` dispatch cell).
3. rc 1-vs-127 shape: posix special-builtin readonly abort status
   (+ diagnostic leg).
4. Carry-#7 residue: the command's OWN read of a masked dynamic
   special on the LAYER/SEED route (`RANDOM=1 eval 'echo $RANDOM'`).
5. Option (A): LAYER-as-temporary_env masking model (would retire the
   special SEED route; property table in the slot ledger; would close
   #4 and likely #8).
6. Prefix-value arith store to a prefix-bound name: bash persists to
   the REAL variable, psh loses it with the temp binding
   (`A=1 B=$((A=9)) cmd; echo $A`).
7. `${!PREFIX*}` name-enumeration sees staged bindings (fourth
   enumeration surface, pre-existing).
8. Function-target nameref-to-element visibility (`r=NEW f` body
   read: bash NEW / psh stale; pre-existing).
Plus out-of-charter confounders X1 (posix function-name validation)
and R4 (posix special-builtin redirection fatality), both pinned
both-sides.

## Regeneration

Instruments in `instruments/` (the dev's `tmp/a8/`): A8 matrix case
files + raw pairs, prototype diffs (ALT-2, option-F), axis census
(counts COLLECTED TESTS per axis), SHA sweep (value-allowlist form),
per-round replay outputs. Harness: `remediation-branch-verify.js`
(scriptPath invocation), four agents, extraChecks per round in the
inbox rulings R10/R13/R17/R21/R25. All probe cells are three-way
(bash 5.2.26 `/opt/homebrew/bin/bash` / base 241a923c / tip) from
detached, discriminator-verified worktrees.
