# Slot 2.4 round-6 handover (continuation dev)

Predecessor (dev-2-4) exhausted its context budget and handed over CLEANLY at
round 6 partial: exact state below, no unverified claims, no declared tip.
You are the continuation dev. Governing brief: /Users/pwilson/src/psh/tmp/
remediation-ledgers/briefs/2.4.md (read in full — every dated ruling applies).
Round-5 verifier evidence: VERIFY-ROUND5-issues.md in this directory (and
ROUND1..4 for history). Slot ledger: 2.4.md in this directory — CONTINUE it,
do not restart it; mark your entries "round 6 (continuation)".

## Tree state (verified by the integrator at handover)
- Branch `fix/remediation-2-4` at **360090b2**, working tree clean, ruff
  clean, affected suites green. NOT GATED — do not treat as gated.
- Base 1b271d77 (v0.758.0). All prior declared tips are DISSOLVED; no
  declaration is in force. Mechanical-tip rules arm when YOU declare.

## Done in round 6 so far (by predecessor)
- **R6-A FIXED + VERIFIED, commit 360090b2**: `_execute_in_subshell` dropped
  the forking context's suppression depth on the background branch and
  `Shell.for_subshell` builds a fresh (seed-0) shell; now threaded and
  seeded. All three bg shapes 6/6 vs bash, 3 channels, both parsers;
  affected suites 476 passed. Commit message already narrows the old
  "structurally impossible" claim (a SEED is also a derivation site).
- **R6-E verified-real** by predecessor with the true instrument:
  collect-only says 54001334 = **+11** (ledger says +10) and 5121ec8b =
  **+0** (ledger says +1); total +47 stands. Ledger strike-and-corrects NOT
  yet written — that is yours.

## Open work (ACK each by letter to the integrator, then execute)
- **R6-B (STAGE-GATE — propose placement BEFORE implementing):** suppressed
  FINAL pipeline member: `set -e; { true | eval Q; } || recover` → bash 2 /
  psh 1 (fresh regression vs base+r4; reproduced 0/6 at 360090b2 by
  predecessor). Diagnosis banked: the final member forks through
  ProcessLauncher reusing the parent Shell by fork-copy → child inherits
  depth 1; bash gives members an UNSUPPRESSED context (seed 0). The launcher
  holds only ShellState (not shell/executor), so the seed-0 reset needs a
  deliberate placement. ProcessLauncher is SHARED machinery — send the
  integrator your proposed placement + why it cannot leak into non-member
  forks, wait for GO. Then pins red-on-5121ec8b (the regressed shape) +
  the verifier's control rows.
- **R6-C:** interactive-channel family = DECLARE + PIN with REAL PTY pins
  (PTY facts need PTY pins): fork×errexit interactive row (`( set -e;
  eval Q ) || echo SUPPRC=$?` → interactive bash 1 / psh 2, base-identical)
  and the -i -c fork shape; fix the falsified absolute in
  test_interactive_dash_c_channel_disposition ("only on the direct shape");
  write the successor-row text (per-shell is_script_mode gate ⇒ children of
  interactive shells keep legacy statuses). PLUS: pin the `-n` (noexec)
  2→127 flip (currently an UNDECLARED improvement); probe + declare the
  `--validate` asymmetry (stayed at old value).
- **R6-D:** embedding-API contract — Shell.run_command() now lets
  SubstitutionSyntaxAbort escape to callers when is_script_mode is True.
  RULED INTENDED by the integrator: declare it (API docstring + core
  CLAUDE.md note, invariant prose + file.py#symbol only) + a pin asserting
  the escape is deliberate. If you conclude it should be consumed at that
  boundary instead — STOP-and-report, do not implement.
- **R6-E:** strike-and-correct in the ledger, record-integrity style
  (visible strike + correction + cause): (1) accounting rows +11/+0 WITH
  the collect-only output pasted; (2) the COND1 "24 rows all match" claim —
  determine and state which failure it was (corpus missed suppressed×final,
  or not re-run at tip); (3) the STILL-OPEN-at-declaration inconsistencies
  (R5-F(2) dropped; R5-E item discharged only in a commit message).
- **R6-F:** map_child_exception docstring arity (cites one-arg helper, takes
  two); guard-3 single-line-regex limitation (strengthen to AST level or
  state the limit in the guard docstring AND ledger); fork×EXIT-teardown×
  errexit corner (`( set -e; trap 'echo $(fi)' EXIT; echo IN )` — probe vs
  bash, then declare+pin both-sides or write successor text); optional
  `_current_executor` getattr house-style.

## Acceptance condition at YOUR declaration (expanded audit — non-negotiable)
1. Discharge-audit table: EVERY ruling item → artifact path + the grep/replay
   that proves it, run at your declared tip.
2. Every matrix/count/condition claim anchors to a COMMITTED
   instrument-output FILE (the audit greps the file, not prose).
3. BOUNCED-ROWS REPLAY: every blocker evidence row from verify rounds 1–5
   (they are all in VERIFY-ROUND*-issues.md), replayed at the declared tip,
   outputs to files the audit checks.
4. Gate + compare-bash transcripts carry the tip SHA in their headers.
5. The ledger STILL-OPEN list is EMPTY or every entry is deferred-by-ruling
   with the ruling cited.

## Standing rules (unchanged; full text in the brief)
Byte-exact probe files, individual-run, PATH bash 5.2.26 only, both parsers;
never touch version/CHANGELOG/README/ARCHITECTURE/docs-reviews/FLIP-PINS.md;
never push/PR/merge/tag; heavy runs = ONE foreground call with timeout
600000 where it fits (~7 min gate), else R-AWAIT in-turn polling — never
end a turn with a heavy run in flight; request integrator GO before gate +
compare-bash; ACK rulings by letter; strike-and-correct never overwrite;
project tmp/ only.
