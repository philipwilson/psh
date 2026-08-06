# Slot 3.5 — Rounds and Errata (integrator-authored, at ceremony)

Slot 3.5 (typed expansion/arithmetic user-errors, MEDIUM-12b; absorbed
A10.1; ruled-in errexit `-c` family) shipped as **v0.767.0** from final
tip `81d1799672eac6b163d6f5dc7f7393545e405994` (8 commits over base
`963c6eab`, branch `fix/remediation-3-5`). Primary records:
`slot-ledger.md` (frozen twice; addenda below each declaration, never
edits above) and `integrator-inbox.md` (dead-drop rulings R0–R7).

## What shipped

The typed hierarchy already existed (`ExpansionError`/
`FatalExpansionError`/`BadSubstitutionError` + `fatal_expansion_status`
/`substitution_child_abort_status`); the slot fixed the CATCH SITES and
the status seams. (a) The `arithmetic_expansion_value` VT net
(evaluator.py:797) DELETED — its ValueError leg proven dead by forcing,
its TypeError leg the charter's core internal-defect masker; PS4
fallback narrowed `Exception`→`PshError` (user observable byte-identical,
7/7 dry-run); operators.py:90 dead-VE dropped; substring failure typed
at its detection point (`parameter_expansion.py#extract_substring` →
`ExpansionError`, R2 scope grant); four-site dead-VE class narrowed
(core.py:517 + control_flow.py:416/:432/:457). (b) `[[ ]]` net
`(ValueError, TypeError, OSError)` → `(TestExpressionError, OSError)` —
new `TestExpressionError(PshError)`; the three can't-happen bare-VE
raisers → `RuntimeError`; the OSError leg KEPT (member of
`_EXPECTED_SHELL_ERRORS` — deleting it buys an observable change for
zero defect-visibility gain; I8 both-halves instrument). (c) A10.1:
subshell/cmdsub children of a fatal expansion now exit **1** like bash
(was: the `-c` channel's 127 leaked through the fork) — via a
`fatal_expansion_channel` STAMP set in exactly ONE function
(`fatal_expansion_status`, BOTH carriers: `TopLevelAbort` and the
script-mode `SystemExit`) and consumed by one arm each in
`map_child_exception`; `fatal_expansion_child_status` sits beside its
sibling documenting the probed FLAT-1 model (no errexit branch — the
sibling's analogy would have been wrong). (d) The unpredicted errexit
family (Phase A discovery): under `set -e`, bash exits **1** from a
fatal expansion even in `-c` (flag-not-effectiveness: suppression
shapes still 1, `set +e` restores 127) — fixed in
`fatal_expansion_status`'s channel branch. Guards: 98-row conformance
battery (43 red-on-base), ratchet GROW (`manager.py` +
`arithmetic/evaluator.py` enter the 2.3 no-broad-except GUARDED set),
Q2 ledger SHRUNK by 3 entries (two with corrected false reasons), 7 M8
mutation locks (incl. un-stamp-one-carrier and stamp-check-by-status
collision), 3 default-mode border pins (incl. the counter-pin that a
shell-reason PS4 failure still falls back), 9 behavioral goldens.

## Round table

| round | tip | verdict | findings |
|---|---|---|---|
| stage gate | (Phase A, no commits) | GO + 4 rulings | matrix found TWO families (A10.1 + the errexit `-c` family, ruled IN as (d)); I8 closed the OSError leg in Phase A; census disposition table ruled row-by-row |
| mid-slot | 3 commits | stop-and-report RULED completion | Phase A route trace WRONG (`-c` = script mode = SystemExit carrier); ruled the two-carrier stamp the COMPLETION of ruling (c); `( exit 127 )` collision row + carrier-unstamp M8 added as conditions |
| 1 | 791ebf0c | harness BOUNCE — 8 reported / **7 distinct / 7 real / 0 false** | dangling doc pointer (`#_expand_ps4`); FALSE UNIVERSAL falsified by let_builtin.py:52 (two agents converged); Linux/parser-interactive/transclusion record gaps; §4e registry count false (BOTH sides' instruments failed — see errata); undeclared default-mode delta (injection-only) |
| 2 | 81d17996 | integrator-direct **PASS** | delta confined (2 doc + 1 test, zero production code); all bounced rows replayed by integrator; both gates EXACT on PRE-REG-3 |

**Behavioral core NEVER bounced:** the harness's independent replays —
78/78 novel cross-mode rows tip==bash, 24/24 catch-site rows base==tip,
red-on-base replayed 43/55 (tip battery), resurrection ZERO, every
fence held (s3's exact pinned command, posix readonly special-builtin,
FUNCNEST, failglob, discard family, exit-127 collisions).

## Fault register (disclosed, both sides — ZERO code faults)

Dev (5): single-line grep blind on multi-line except tuples
(self-corrected by planned AST re-derivation); vacuous PS4 dry-run
measuring a NameError (self-caught, guarded); the Phase-A channel trace
from a hand-built in-process Shell — reproduced the wrong route, then
confirmed the wrong belief with real output (caught by the observable
matrix AFTER implementing); stale PRE-REG-2 line citation + commit
count; registry count read off a `| head`-truncated display.
Integrator (2): the brief's `[[ ]]` pointer was the Q2 TEST FILE's dict
line mis-cited as a source location; the R2b "verification" of the
registry-count claim used the SAME truncated-grep method as the claim
and confirmed it — **a verification instrument that mirrors the
claim's method cannot find the claim's error** (joint lesson, co-signed
in R6).

## Banked lessons (to LEDGER Part D)

1. Every fault in the slot, both sides, lived in an instrument or a
   record — none in the code (D-3.4 lesson 1, now twice confirmed).
2. The instrument-mirror lesson (above) — verification must vary the
   METHOD, not just the actor.
3. A hand-built in-process state object is not the real path: channel
   claims get subprocess probes on the real entry (R3 binding rule).
4. A universal quantifier in PROSE needs an instrument covering its
   whole range, exactly like a corpus claim (the false-universal
   blocker = AXIS-QUANTIFICATION appearing as documentation).
5. Sibling models are measured, not analogized: the child status is
   FLAT here where the sibling branches on errexit; the errexit family
   keys on the FLAG where suppression governs the sibling.
6. A pin pair needs its counter-pin: without "a shell-reason PS4
   failure still falls back", the default-mode pins reward deleting
   the fallback.
7. A pre-registration revised for late conditions keeps BOTH figure
   sets labelled; a GO citation re-derives its line numbers at request
   time (fault #4's rule, property-bound).
8. A sweep whose only history is PASS teaches nothing — record when it
   bites (round-1 SHA sweep correctly rejected a CPython build id).

## Successor rows (to LEDGER Part D; none absorbed)

1. `test_doc_pointers.py` has no rule for the `file.py#symbol` form —
   the form the campaign's own doc rule mandates (round-1 B1 escaped a
   green gate through exactly this hole).
2. let_builtin.py:52 VT leg — 5C's half of MEDIUM-12; the deadness
   argument transfers.
3. Builtin-`ArithmeticError`-vs-module-alias breadth at core.py:517 +
   control_flow.py legs (covers ZeroDivisionError/OverflowError/
   FloatingPointError; unproven as masking; R3 §4).
4. PS4 + bad-subscript: `TopLevelAbort` (BaseException) escapes the
   narrowed net — bash falls back rc 0, psh aborts rc 1 (pinned
   both-sides `test_ps4_bad_subscript_aborts_in_psh_but_not_bash`).
5. `[[` invalid-regex diagnostic: psh prints `psh: [[: invalid regex:`
   rc 2 where bash is silent at rc 2 (pinned both-sides).
6. Redirect-target fatal expansion (`( cat < ${x?boom} )`):
   double-printed diagnostic + direct-channel rc 1 vs bash 127
   (pre-existing, byte-identical base/tip; harness fresh-probe find).
7. Out-of-charter probe finds, report-only: `(( 1<<-1 ))` bash 0 /
   psh 1; `${a[]}` bash error / psh accepts; `a[]=9` bash error /
   psh accepts.

## Regeneration

Instruments under `instruments/`: A8-style matrix (`a10/matrix.py`,
216 cells, + `matrix.json`), errexit probe (25 cases), census via the
ratchets' OWN detectors (`census-3-5/derive_census.py`), per-leg
forcing + 200-cell deadness sweep, I8 OSError two-halves probe, parser
+ interactive axis probe, PS4 default-mode and dry-run probes, the SHA
sweep (value-allowlist form; fired once, correctly). All probe cells
three-way (bash 5.2.26 `/opt/homebrew/bin/bash` / base 963c6eab / tip)
from detached, discriminator-verified worktrees. Harness:
`remediation-branch-verify.js` (scriptPath invocation), extraChecks in
R5's launch record; per-agent results in the workflow journal.
