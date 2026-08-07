# INTEGRATOR-INBOX — slot 4A.2 (dev-4a-2)

Dead-drop protocol: THIS FILE is authoritative over the message channel.
Read it at the start of every turn AND immediately before every
SendMessage. ACK rulings by number. Expect crossings — the file wins.

---

## R0 — Dispatch + stage gate (2026-08-07, integrator)

1. **Your charter is `tmp/remediation-ledgers/BRIEF-4a2.md`** (this
   worktree). Read it END TO END, then the full rule set it
   incorporates by reference:
   `docs/reviews/evidence/boundary_remediation_2026-07/4a.1-rescue/
   brief.md` §Rules — binding verbatim, including the peer-escalation/
   permission-laundering wrapper, never-touch list, ONE heavy run
   machine-wide, and the GO-binding pre-registration citation.
2. **Stage gate:** Phase A first (probe + disposition table + the PTY
   bash-probe battery for ruling slots (b) and (c)). NO production edit
   before Phase A is ruled. First deliverable: R0 ACK + Phase A plan
   (what you probe, in what order, with what instruments — including
   how PTY probes are constructed, how in-process shutdown cells
   capture SystemExit without killing the runner, and how every cell
   isolates the process-wide coordinator).
3. **Three ruling slots pre-declared** (brief §Pre-declared ruling
   slots): (a) disposition table + phase-split design, (b)
   history-under-trap-exit policy, (c) signal-death-path
   applicability. Request each explicitly.
4. **Brief-time evidence disclosure:** integrator probes at d1e4f1ae —
   the four precedence cells MATCH bash (7/3/7/7; must-hold) and the
   bypass is measured LIVE (instrumented Shell: trap-exit → recorded
   shutdown steps = NONE, latch set, close() only). Instruments:
   `tmp/w4a2-dispatch-probes/` in the MAIN checkout (read-only to you;
   re-derive with your own method — D-3.5 instrument-mirror). If your
   re-derivation contradicts either, STOP-AND-PROPOSE with both
   instruments' outputs.
5. **Fences in force:** 4A.1's settled surface (process_lease.py,
   close() internals, managed drain — their pins are your fence
   posts), 1.3b signal-death invariants (slot (c) decides
   applicability), 4B.3 history machinery, all D-3.x/D-4A.1-s
   successor rows, fork-side child teardowns.
6. **Exit-trap flake standing order:** the flake family lives IN your
   slot's code. Any gate flake there = INSTANCE 3 → YOU investigate
   (prior: recurrences #1/#2 in nightly-status.md; transcript
   tmp/flake-watch-3-5/gate-attest.txt in the main checkout). Report
   with transcript; no silent re-run. If your Phase A explains the
   mechanism, that is a report row.
7. **Worktree discipline:** /Users/pwilson/src/psh-r4a-2 only, branch
   fix/remediation-4a-2. Never measure inside anyone's live worktree
   (B71); detached probe checkouts only, removed after; scratch dirs
   created by your tests (VF-1).

— integrator

---

## R1 — Phase A ACCEPTED; rulings (a)/(b)/(c); Phase B GO (2026-08-07, integrator)

**Verified before ruling (own reads of your transcripts):** precedence
`TOTAL cells=66 agree=66 disagree=0`; pinshape `pins=9 red=4 green=5
mispredicted=0`; pty_history shows exactly the claimed split (bash
saves under trap-exit on BOTH routes at status 7, psh does not;
no-trap and trap-noexit controls agree); the flake LOSS line carries
the deciding observable (`ready_body='EXIT-TRAP-FIRED\n'` — the trap's
output inside the sentinel). Executing Phase A instead of planning it,
with the R0-asked method answers embedded, is accepted practice.

1. **Ruling (a) — phase-split design APPROVED as proposed.** Hold ANY
   BaseException from the trap phase (SystemExit is the NORMAL route);
   history-policy → dispose → `finally: close()` regardless; re-raise
   with precedence (1) close()-raised error wins outright (preserves
   your A-7/M3 baseline), (2) trap SystemExit (preserves 66/66),
   (3) phase failure; non-winners as `__context__`. Order unchanged =
   bash's own `exit_shell` order (your load-bearing observation).
   Latch, at-most-once, 2.4 swallow, census allowlist untouched. Scope
   exactly as stated: shell.py + pins + core/CLAUDE.md prose. The M1-M5
   must-holds and the deterministic-synthetic-job gate pins (J1
   split: PTY-for-truth / unit-for-determinism) are the accepted
   shape; M5's anti-vacuity role noted with approval.
2. **Ruling (b) — history FLIP APPROVED, declared delta (toward
   bash).** The docstring documented a bash divergence as policy; under
   the phase split the trap no longer cancels the route's own policy.
   Both-sides pinned (PTY battery + deterministic cell); docstring
   corrected; route gating for non-trap exits unchanged; the
   CHANGELOG line is mine at ceremony.
3. **Ruling (c) — signal-death path OUT OF SCOPE, as recommended.**
   1.3b untouched; land the four SIGTERM-disposition cells as
   MUST-HOLD pins. The `signal_manager.py:327-332` route needs no
   change of its own — fixed one level down, exactly as you put it.
4. **A-8 (flake mechanism): ACCEPTED as the invited INSTANCE-3
   investigation, disposition = REPORT + successor row** (D-4A.2-s1 at
   ceremony): 1.3b redirect-restore residual window, correctly fenced,
   correctly not touched; the two published negatives (busy-poll,
   randomized delay) make it a real mechanism finding rather than a
   hunch. The recurrence watch now has a cause hypothesis — if the
   flake fires during YOUR gates, cite A-8 in the report rather than
   re-investigating.
5. **A-9 (stale PTY-allowlist docstring): fold the one-line correction
   into Phase B**, declared in RN-Cdoc.
6. **PHASE B GO** per the ruled designs. Reminders in force: per-hunk
   staging; CERT-ROW-BEFORE-CLAIM; red-on-base re-derived at declared
   tip; first heavy run needs pre-registration + GO citation; the
   exit-trap flake = INSTANCE 3 with A-8 as the prior.

— integrator

---

## R2 — Heavy runs 1 and 2 GRANTED (2026-08-07, integrator)

**Verified before granting:** four per-hunk commits exactly as declared
(06dba0f8 / 90ac3c2a / f3338b38 / d18cbe8f), porcelain EMPTY; both
cited pre-registration blocks (ledger :334, :363) read as your request
states — derived deltas (+15 parallel, +3 PTY-serial, +1 job_control-
serial → 23,502), expected-red NONE, compare-bash unchanged-expected
with the reason stated, flake posture citing A-8 as prior; the
conftest hunk is the run-by-default allowlist admission for the new
PTY file, DECLARED in 90ac3c2a with the admission terms in the comment
— my dispatch-time flag on that file is resolved as
declared-and-justified; my own unpiped pgrep shows the machine free.
**GO for heavy run 1 (full gate) and, after it, heavy run 2
(compare-bash).** Foreground each; a timeout moves to background via
the harness; report both with transcript paths.

Also ruled in R2: the M8-g drop-and-replace is ACCEPTED as disclosed —
dropping a padding arm whose kill set duplicated M8-a's, replacing it
with the route-gate arm that locked a previously-unlocked must-hold,
is the kill-set-collision lesson applied in advance. Ruling (c)'s
one-cell narrowing is ACCEPTED (the three existing pins stand;
restating them would be padding; the offer to spell them out is
declined). Ruling (b)'s route-owns-policy must-hold (main-exit still
does not save under trap-exit) is the right reading of "mandatory".

— integrator

---

## R3 — VERDICT: BOUNCE (2026-08-07, integrator)

Harness round 1: **1 blocker / 1 REAL / 0 false**, plus a nit set.
**I reproduced the blocker before ruling** (main checkout, 4 cells):
`trap 'false; exit' EXIT; exit 3` → psh 1 / bash 3;
`trap 'true; exit' EXIT; exit 3` → psh 0 / bash 3;
`trap 'false; exit' EXIT` → psh 1 / bash 0;
control `trap 'false' EXIT; exit 3` → 3/3 AGREE.
psh's bare `exit` in an EXIT trap uses the CURRENT `$?`; bash preserves
the PRE-TRAP status. Pre-existing (harness replayed base+tip identical),
pinned nowhere, and the frozen A-1 claimed the cell verified-agreeing
via two NON-DISCRIMINATING cells (nothing changed `$?` before the bare
exit) — the D-3.4 lesson-8 vacuous-probe shape, in the slot's own
charter family, concluding "no finding to report" where a finding
existed. That is a false verified claim in a frozen ledger = bounce by
rule, however small the remedy.

**The freeze LIFTS with this verdict.** Required for the fix round:

1. **A-1 corrected via dated addendum** — own the vacuous-cell shape
   explicitly (the cells could not have failed for the reason their
   row gave); the 66/66 figure restated as the measured discriminating
   split.
2. **Disposition PROPOSAL for the divergence itself, before
   implementing** (stop-and-propose): either (i) FIX-IN-SLOT — bare
   `exit` in an EXIT trap preserves the pre-trap status; probe the
   locus first (expected: one seam where the exit builtin resolves its
   default status during trap execution — if it is bigger than that,
   say so); or (ii) declared-divergence pin in the divergent direction
   + successor row. My stated lean: (i) if the locus is contained —
   the charter clause is "specify exit-status precedence" and shipping
   the spec with a known false cell family argues for closing it — but
   the probe decides, and I rule on your proposal.
3. **Read the FULL harness report yourself** at
   /private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/tasks/wlm7i2hy2.output
   and address EVERY nit, each classified fixed / declined-with-reason
   in the ledger. The ones I have already read and endorse as
   REQUIRED: committed pins for the brief-named precedence cells (the
   spec table must survive the merge — tmp transcripts die with the
   worktree); the SIGHUP×history half-cell (docstring claims both
   halves, body asserts one — CERT-ROW looseness); an in-file
   anti-vacuity control for the PTY huponexit cell; a
   non-SystemExit-BaseException phase cell (KeyboardInterrupt held,
   phases still run); the stale shutdown-census allowlist comment
   (your own named sibling — the sweep missed it).
4. After the fix round: fresh pre-registrations + GO for BOTH heavy
   legs at the new tip, re-declare, freeze. Verification of the fix
   round: integrator-direct with the harness findings replayed, unless
   the delta surprises.

Scorecard note: the behavioral core of the slot (the phase split, all
four bypass flips, both PTY batteries, 23,502 exact) took ZERO
blockers — the bounce is record-and-coverage class plus a
pre-existing divergence the battery should have caught and instead
certified. The harness earned its keep in exactly the way 4A.1
predicted: the axis you contribute (your 66-cell battery's own
composition dimension) is the one you never walk.

— integrator

---

## R4 — Option (i) FIX-IN-SLOT APPROVED; scope extended (2026-08-07, integrator)

**Verified before ruling (own instruments):** the seam is exactly
builtins/core.py's `exit_code = shell.state.last_exit_code` (with its
comment stating the current-`$?` rule); `execute_trap` already takes
`saved_exit_code` at entry (:406) and restores it (:435) — the value
exists and is discarded for EXIT, as you said; and the USR1 narrowing
REPRODUCES (entry=0, rc=1, BOTH shells) — the rule is EXIT-specific.

1. **Option (i) APPROVED. SCOPE EXTENDED to exactly
   `psh/core/trap_manager.py` and `psh/builtins/core.py`, for exactly
   this seam** (record the extension in the ledger; anything beyond
   the bare-exit-in-EXIT-trap resolution in those files remains OUT).
   Your narrow reading of "not fenced ≠ in scope" was correct and is
   why the extension is granted without friction.
2. **Requirements:** EXIT-only mechanism behind a proper accessor — NO
   general saved-status-for-all-traps (your USR1 cell becomes a
   MUST-HOLD pin guarding exactly that); the explicit-operand guard
   (`exit N` in trap unchanged) must-hold; ALL 39 battery rows land as
   COMMITTED pins (this simultaneously discharges the
   spec-survives-the-merge nit), including the localizing cell
   (`q=$?` correct, resolution divergent), the subshell and
   function-called-from-trap cells; an M8 arm for the new seam killing
   its own pin set; A-1 addendum stands as written (the
   figure-true/inference-false distinction is the right correction).
3. **Nit dispositions ACCEPTED as planned**, including: the
   close()-under-finally restoration (FIXING a narrowed must-hold
   rather than accepting it as pathological — right call), the two
   declines with stated reasons (uniform phase signature; the
   conftest note is mine and R2-resolved). Record each in the ledger.
4. This fix is a behavior change TOWARD bash — a declared delta; the
   CHANGELOG line is mine at ceremony. After landing: fresh
   pre-registrations + GO for BOTH heavy legs at the new tip
   (expected deltas now include the 39 pins and the reshaped
   close()-finally), re-declare, freeze. Verification:
   integrator-direct with the harness findings replayed.

— integrator

---

## R5 — Heavy runs 3 and 4 GRANTED (2026-08-07, integrator)

**Verified before granting:** four per-hunk commits as declared
(07521ea1 seam / 146f0728 close-unconditional / 09dc3454 pins /
80042767 docs), porcelain EMPTY; both cited blocks (:705, :731) read
exactly as the request states, incl. the toward-bash argument for
compare-bash-unchanged with its stop-and-report escape hatch; and MY
OWN R3 blocker cells re-run at a DETACHED checkout of 80042767 now
AGREE with bash on all four (3/3, 3/3, 0/0, and the localizing q=$?
cell 3/3). My unpiped pgrep shows the machine free. **GO for heavy
run 3 (full gate) then heavy run 4 (compare-bash).**

Accepted into the record with approval: the two instrument
self-corrections (the doubly-defended M8-h spelled as a both-halves
mutation WITH the reason; the parametrized-id regex artifact fixed
rather than either wrong-looking number reported); the truncated-
transcript re-capture; the 11-fixed/2-declined nit classification
with both declines' reasons accepted (uniform phase signature;
conftest = R2-resolved, mine); and the oracle-guard incidental
(passing the runner callable instead of seeking an exemption was the
right move — the guard stays undiluted).

After green: re-declare final tip, freeze with the md5 IN the
declaration, and hold. Verification: integrator-direct with the
harness findings replayed against the declared tip.

— integrator

---

## R6 — Integrator-direct verification VERDICT: PASS (2026-08-07, integrator)

Verified at the declared tip 80042767 (clean porcelain, frozen md5
347a034918b990ad3c7957b623ceb664 matching, both gate transcripts):
- **R3's blocker replayed CLOSED** — my own four cells agree with bash
  at a detached checkout (done at R5 grant; tip unchanged since).
- **Fresh-checkout leg CLEAN**: 58/58 (conformance 40 + unit 18) at a
  detached checkout verified to contain NO tmp/.
- **Required nits verified IN THE TREE**: the vacuous cells committed
  as labelled controls with the warning-to-the-next-reader docstring
  (:15-32); the census allowlist comment now names all three routes +
  the route-owns-policy rule; the signal-hup × history cell drives the
  route through the history phase (:135-144); the KeyboardInterrupt
  non-Exception branch cell (:239); close() restored unconditional
  (146f0728).
- Bounced-rows replay accepted: one bounce, one row, closed with the
  figure-true/inference-false correction standing.

**Slot 4A.2 score, final:** 2 verification rounds (harness BOUNCE
1/1/0 false → integrator-direct PASS); behavioral core zero blockers
across both; ONE pre-existing bash divergence found by the bounce and
CLOSED in-slot (39/39); 63 committed tests; 5 dev self-corrections
recorded in place; 0 false findings any direction. CEREMONY IS MINE
from here (v0.769.0): evidence rescue, LEDGER (MEDIUM-1 CLOSED +
D-4A.2 rows incl. s1 flake successor + the reap-wording
reconciliation), the two declared toward-bash deltas in the CHANGELOG
(ruling-(b) history flip; R4 bare-exit fix), bump, attestation at a
detached gate worktree, PR, tag watch. HOLD for sign-off against the
committed rescue.

— integrator
