# Slot 2.4 verification round 4 — full issue list (overall: BOUNCE)

## Task verdict: PASS-WITH-NITS

### NIT
The R4-D standing self-check's recorded result ('flagged 14 lines, of which 3 had gone STALE') does not replay under the command the ledger records. Running the exact command (git diff 1b271d77..HEAD -- psh/ tests/ | grep -nE '^\+.*\b(never|always|every|no [a-z-]+ (escapes|reaches)|all of them|cannot|uniform)\b') yields 34 lines at tip f0cc466e and 34 at 6cb57bef; the round-4-only delta (025a6a27..6cb57bef) yields 12. No universe I tried yields 14. The check's PURPOSE is served — I inspected all 34 hits and each carries an in-sentence domain qualifier or describes a measured fact — but the recorded count/universe is imprecise; the ledger should state the diff range the 14 came from.

EVIDENCE:
Counts re-run 2026-07-31 against the branch: tip=34, 6cb57bef=34, round-4-only=12 (commands in report). Spot-inspection of the 34 hits shows qualified universals (e.g. 'uniform WITHIN', 'unless effective errexit', 'channel-dependent, never uniform').

### NIT
The brief's flip-pin section says 'unit-level twins too', and the ledger is silent on whether any unit-level twins of the four flip rows existed. I verified the obligation is vacuous: no tests/unit/** twin of any of the four pin names exists at base 1b271d77, so there was nothing to flip — but the ledger should have recorded the check rather than leaving the clause unaddressed.

EVIDENCE:
git grep -nE 'c_mode_exit_code_is_127|eval_source_fatality|procsub_joined|heredoc_nested_error' 1b271d77 -- tests/unit → no hits.

### NIT
Golden co-flip letter-of-brief deviation, disclosed: the brief said update the row's exit_code 'AND ONLY THAT — the stdout/stderr fields stay'. The diff shows exit_code 2→127 with stdout/stderr byte-identical, but the row's 12-line explanatory comment block was also rewritten (the old text described the divergence as open and would have been false post-fix). The ledger discloses this explicitly (round 1, refined round 3). Comment-only, keeps the record truthful; noted for the integrator's ceremony record.

EVIDENCE:
git diff 1b271d77..fix/remediation-2-4 -- tests/behavioral/golden_cases.yaml: only data-field change is 'exit_code: 2' → 'exit_code: 127'; stdout/stderr/psh_only unchanged; comment block replaced.

## Task verdict: PASS-WITH-NITS

### NIT
Ceremony debt: FLIP-PINS.md, LEDGER.md and the integrator plan still name the three RENAMED flip-pin tests, so a ceremony grep for the flipped rows resolves to nothing. Not a dev fault — git history proves those files are only ever edited in integrator ceremony commits (7bcf163e, 2714b0e2, bf39a7ef), never in a slot branch — but the rows must be rewritten at 2.4's ceremony or the closure record dangles.

EVIDENCE:
Renames: test_divergence_c_mode_exit_code_is_127_in_bash -> test_c_mode_exit_code_is_127_like_bash; test_divergence_eval_source_fatality_is_i3 -> test_eval_source_frame_fatality_matches_bash; test_divergence_eval_source_procsub_joined_i3 -> test_eval_source_procsub_joined_family_matches_bash; TestMapChildException.test_taxonomy_tuple_is_the_five_families -> ..._six_families.

Surviving references (branch tree, `git grep -n <name> fix/remediation-2-4 -- psh/ tests/ docs/ tools/`), ALL under docs/reviews/:
  /Users/pwilson/src/psh/docs/reviews/evidence/boundary_remediation_2026-07/FLIP-PINS.md:13,15,16
  /Users/pwilson/src/psh/docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md:29,161
  /Users/pwilson/src/psh/docs/reviews/boundary_remediation_integrator_plan_2026-07-21.md:77
  (historical, do not edit) boundary_campaign_close_2026-07.md:179,249; 2.2-rescue/slot-ledger.md:363,496; 2.2-rescue/INTEGRATOR-INBOX.md:50; 2.3-rescue/slot-ledger.md:654,767

ZERO dangling references in psh/, tests/, tools/, or wave-manifest.json (repo-wide grep + `grep -c test_divergence wave-manifest.json` = 0). FLIP-PINS.md:16 additionally still carries the WRONG FILE for the procsub co-flip (test_subscript_keying_conformance.py) — the correction the brief already tallied as integrator fault.

map_child_exception resurrection check: signature changed to `map_child_exception(exc, state, errexit_suppressed=False)`. Every call site in the branch passes state — psh/executor/child_policy.py:311,404,412; psh/executor/process_launcher.py:367; tests/unit/executor/test_child_policy.py (11 sites, via a _StubState). No unupdated caller anywhere. The AST/grep guard tests/unit/tooling/test_child_exit_taxonomy_centralized.py is unaffected and green.

All new doc pointers resolve: execute_as_main (source_processor.py:66), SubstitutionSyntaxAbort (exceptions.py:112), substitution_abort_status (internal_errors.py:131), substitution_child_abort_status (:173), _substitution_syntax_abort (source_processor.py:292), TrapManager.execute_exit_trap (trap_manager.py:537), sync_child_status_for_exit_trap (child_policy.py:118), eval_command.py + source_command.py present.

### NIT
Docstring universal in test_exit_trap_teardown_action_error_changes_nothing ("REPORTED AND SWALLOWED at teardown, changing nothing — matching bash") is falsified on the errexit axis, which its corpus omits: with `set -e` in effect at teardown, bash exits 2 and psh exits 1. REPLAYED and base-identical, so NOT a regression and not this slot's — but it is the same over-claim shape round 4 was bounced for ("probed rather than assumed" on an axis that was not in the corpus), and the errexit x teardown intersection sits outside both declared O3 and O4 divergences.

EVIDENCE:
Row: `set -e\ntrap 'echo $(fi)' EXIT\necho B\nfalse\necho AFTER`, run individually per channel against PATH bash 5.2.26 (/opt/homebrew/bin/bash) and against detached worktrees at 1b271d77 (base) and f0cc466e (tip):
  ch=c    bash rc=2 out='B\n' | BASE rc=1 | TIP rc=1
  ch=file bash rc=2 out='B\n' | BASE rc=1 | TIP rc=1
  ch=stdin bash rc=2 out='B\n' | BASE rc=1 | TIP rc=1
Control in the pinned corpus (`trap 'echo $(fi)' EXIT; echo B; exit 5`) agrees at rc 5 in bash/BASE/TIP, which is why the corpus missed it.

Separately CONFIRMED by replay (dev claim, not mine): the same test's "shipped as a CLI-reachable Python traceback" claim is true. Running the tip's test file against a detached worktree at the branch's own first commit a76e93f0 fails with psh stderr ending `psh.core.exceptions.SubstitutionSyntaxAbort` — a raw interpreter traceback, rc 1 where bash gives 0. It is green on base only because base has no abort at all, so its green-on-base status is a legitimate in-branch regression guard, not a false red-claim.

### NIT
The new errexit_suppressed parameter of map_child_exception / substitution_child_abort_status has no unit-level pin — the added unit test exercises only the raw-flag and command_mode arms. The effective-errexit distinction (the whole reason round 4 added the parameter) is covered solely by the subprocess conformance row, so a regression that drops the argument at a fork site is caught only by a ~40s conformance test.

EVIDENCE:
tests/unit/executor/test_child_policy.py::test_substitution_syntax_abort_honours_errexit_in_the_child asserts only:
  map_child_exception(SubstitutionSyntaxAbort(), _StubState(errexit=True)) == 2
  map_child_exception(SubstitutionSyntaxAbort(nested=True), _StubState(errexit=True)) == 2
  map_child_exception(SubstitutionSyntaxAbort(), _StubState(command_mode=True)) == 1
No call passes errexit_suppressed=True; psh/core/internal_errors.py#substitution_child_abort_status has no direct unit test at all. `git grep -n errexit_suppressed fix/remediation-2-4 -- tests/` returns nothing.

Context for the integrator — the rest of Task 2's verification came back clean:
- Tip greens: 283 passed in the two flip-pin conformance files; 398 passed across the 5 adjacent files that use $(if)/$(fi) bodies (test_subscript_keying_conformance.py, test_heredoc_error_lineno.py, test_subscript_evaluator.py, test_syntax_templates.py, test_syntax_bearing_ast_fields_q2.py); 57 passed on test_child_policy.py + the 4 tooling guards; `ruff check psh tests tools` clean; `mypy` clean at 274 source files.
- RED-ON-BASE REPLAY: the tip's two conformance files copied into a detached 1b271d77 worktree -> 34 failed / 249 passed. All 19 new -c and frame-fatality equality pins are red on base. The 2 new pins green on base are both self-declared controls in their own docstrings (test_file_and_stdin_direct_status_stays_2 = "MUST-NOT-REGRESS twin"; test_substitution_fatality_status_under_errexit_is_2 = "psh matched this before the I3 consumer landed").
- Golden co-flip mutation-proved: reverting heredoc_nested_error_reports_absolute_line to exit_code 2 at tip fails with `assert 127 == 2`; worktree restored, git status clean.
- Must-NOT-flip pins present and green: test_divergence_alias_local_to_cmdsub_body (:537), test_divergence_heredoc_body_cmdsub_stays_runtime (:550).
- Forbidden files: none of psh/version.py, CHANGELOG.md, README.md, ARCHITECTURE.md, docs/reviews/README.md, tests/integration/redirection/test_process_sub_closed_fds.py appears in the 19-file changed list; version.py still 0.758.0.
- ~60 NOVEL differential rows the dev's suite does not contain, each run one-case-per-invocation x 3 channels vs bash 5.2.26: --posix mode, ${x=$(fi)}, ${y/$(fi)/z}, ${#x[$(fi)]}, `.`-spelling source, while/for/until-cond/case-arm bodies, 2-deep function nesting, subshell-in-function, background+wait, both-sides pipeline, backtick inner, quoted/unquoted heredoc, exit-in-eval, return-in-function, set -u, pipefail, exec 3>&1 first, doubly-nested eval, cmdsub-of-eval, procsub-arg, no-trailing-newline, exec replacement, DEBUG/INT traps, `{ } && list`, `time` keyword, `{ } &`, 2-deep nested source, invalid-EXIT-trap x3. Every row matches bash except the already-declared/pinned divergences. No `Traceback` in psh stderr on any row at tip.
- BOTH PARSERS: --parser rd vs --parser combinator, 6 shapes x 3 channels — byte-identical rc and stdout.
- PTY interactive parity: base and tip transcripts byte-identical; the REPL survives `echo $(fi)`, `eval 'echo $(if)'`, `cat <(fi)` and reports rc=2, matching base exactly.
- In-process embedding API: Shell(norc=True).run_command("eval 'echo $(fi)'") -> is_script_mode False, rc 2, no BaseException escape, next command runs; identical at base and tip.

## Task verdict: FAIL

### BLOCKER
FALSE BASE-IDENTITY CLAIM in the durable carry record. The slot ledger (/Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/2.4.md, §R4-E) records the MAIN-SHELL suppressed-context family as "Diverges AT BASE, so not mine" and the verbatim CARRY ROW TEXT the integrator will paste into LEDGER.md says "...leaves psh's substitution-abort status at 2 where bash uses its ordinary channel status (127 under -c, 1 for a file/stdin). Base-identical." I measured base vs tip and psh's observable MOVED in this shape, in both channels: it is not base-identical, and the slot did introduce the change. The behaviour change itself is correctly pinned (test_main_shell_suppressed_errexit_status_is_carried, which I replayed RED at base), so the remedy is record-only — but as written the carry row tells the successor slot that psh's behaviour here is unchanged from base, which will mis-scope it. Note the campaign vocabulary is unambiguous: the same phrase in R4-C ("Base-identical, so not a regression") IS true there (I measured the scanner-route rows identical at base and tip), which is what makes this use a genuine misstatement. Fix: correct the carry-row text and the "not mine" sentence before the ceremony LEDGER edit.

EVIDENCE:
Replay harness (individual-run protocol, PATH bash 5.2.26 = /opt/homebrew/bin/bash, discriminator-verified trees: BASE=/private/tmp worktree @1b271d77 psh.__file__ under that tree, TIP=/Users/pwilson/src/psh-r2-4):

script: "set -e\neval 'echo $(fi)' || echo GOT"
  -c    bash(rc=127,'')  BASE(rc=0,'GOT\n')  TIP(rc=2,'')   MOVED
  file  bash(rc=1,'')    BASE(rc=0,'GOT\n')  TIP(rc=2,'')   MOVED
script: "set -e\nif eval 'echo $(fi)'; then echo T; fi"
  -c    bash(rc=127,'')  BASE(rc=0,'')       TIP(rc=2,'')   MOVED
  file  bash(rc=1,'')    BASE(rc=0,'')       TIP(rc=2,'')   MOVED

Contrast — R4-C rows where "Base-identical" IS accurate:
  "echo B\necho $(case x in a) :;)\necho AFTER"  -c/file: BASE(rc=2,'B\n') TIP(rc=2,'B\n') same
  "echo B\neval 'echo $(case x in a) :;)'\n..."  -c/file: BASE(rc=0,'B\nAFTER\n') TIP(same) same

Ledger text quoted verbatim from /Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/2.4.md lines 967-977.

### BLOCKER
TRIAD THIRD LEG MISSING: the slot ships the lossless typed representation (psh/core/exceptions.py#SubstitutionSyntaxAbort) and sole authority at the correct time (psh/core/internal_errors.py#substitution_abort_status / #substitution_child_abort_status, one consumer helper psh/scripting/source_processor.py#SourceProcessor._substitution_syntax_abort), but NO executable anti-bypass guard run against a synthetic offender. Nothing structurally prevents (a) a second raise site of SubstitutionSyntaxAbort outside the one consumer helper, (b) a second deliberate catcher — the invariant that exactly ONE non-fork site may catch it (core/trap_manager.py#execute_exit_trap) is asserted only behaviourally, and within this slot the catcher count went 0→1 and was caught by a verification bounce, not by a ratchet, or (c) a re-derived status mapping at a frame. 2.3 shipped three synthetic offenders in tests/unit/tooling/test_syntax_template_guards.py for the PRODUCER side; the consumer side has none. A grep of the whole tests tree for the new symbols returns only value pins in tests/unit/executor/test_child_policy.py plus docstring mentions.

EVIDENCE:
$ grep -rn "SubstitutionSyntaxAbort|substitution_abort_status|substitution_child_abort_status" tests/
tests/unit/executor/test_child_policy.py: 6 value assertions (map_child_exception arms) + the six-families tuple pin
tests/conformance/bash/test_syntax_template_timing_conformance.py: 3 hits, all inside docstrings
tests/conformance/bash/test_nested_substitution_timing_conformance.py: 3 hits, all inside docstrings
— no static/AST guard, no synthetic-offender test. Compare tests/unit/tooling/test_syntax_template_guards.py (2.3), whose module docstring states "Three protected facts, each with a synthetic offender that is actually RUN here (so the guard is proven to BITE, not merely to pass)".

### NIT
Defensive getattr on an attribute that always exists. psh/executor/child_policy.py:311-313 reads errexit_suppressed=bool(getattr(shell, '_errexit_suppress_seed', 0)) although psh/shell.py:254 unconditionally sets self._errexit_suppress_seed: int = 0 in Shell.__init__. The campaign's Q1/Q2 ratchets penalise exactly this shape (a typo or a rename silently degrades to the 0 default, i.e. errexit never suppressed for the background-fork arm, with no failure). The sibling call two frames down uses the real parameter (errexit_suppressed=bool(errexit_suppress)).

EVIDENCE:
psh/executor/child_policy.py:311  exit_code = map_child_exception(
                e, shell.state,
                errexit_suppressed=bool(getattr(shell, '_errexit_suppress_seed', 0)))
psh/shell.py:254  self._errexit_suppress_seed: int = 0

### NIT
Unpinned, undeclared residual in the -i family. `psh -i -c` never reaches the new consumer (the gate is state.is_script_mode, which _apply_invocation sets to `not interactive`), so the direct shape keeps psh's old status where bash aborts with 1. Base-identical (replayed), interactive is explicitly not chartered, and the eval-nested shape under -i matches bash exactly — so this is a residual, not a regression. Worth one line in the carry register so the successor knows the -c fix is scoped to the non-interactive family.

EVIDENCE:
psh -i -c 'echo $(fi); echo AFTER':  BASE rc=2 out=''  TIP rc=2 out=''  bash -ic rc=1 out=''
psh -i -c 'echo $(if)':               BASE rc=2 out=''  TIP rc=2 out=''  bash -ic rc=1 out=''
(eval-nested control matches: psh -i -c 'eval "echo \$(fi)"; echo AFTER' rc=0 AFTER printed = bash -ic rc=0 AFTER printed)

### NIT
The gate predicate is is_script_mode, but the docstring frames it purely as interactivity. psh/scripting/source_processor.py#_substitution_syntax_abort says "A no-op when the shell is INTERACTIVE"; the actual test `if not self.state.is_script_mode: return` is also False for an EMBEDDED Shell() (script_name None => is_script_mode False), which is how essentially every in-process test fixture is constructed. So the entire in-process suite is blind to the new semantics and an embedder gets the old rc-2-and-continue. That is a defensible choice (it matches _posix_syntax_abort's own gate, which the docstring cites) but the sentence as written under-describes the domain — the same class of unqualified universal the dev's own round-4 self-check was created to catch.

EVIDENCE:
psh/core/state.py:244  self.is_script_mode = script_name is not None and script_name != "psh"
psh/shell.py:376-378  (only set for SourceKind.SCRIPT/COMMAND)  self.state.is_script_mode = not self.state.options.get('interactive', False)
psh/scripting/source_processor.py:324  if not self.state.is_script_mode: return

### NIT
Imprecise base-identity framing in a pin docstring. tests/conformance/bash/test_syntax_template_timing_conformance.py::test_unclosed_cmdsub_classified_bodies_are_carried says "Base-identical, so not a regression — carried to the r18 lexer successor", but the function also contains a genuinely FLIPPED equality row (`echo $(while true)`), which is why the function is RED at base. The carried scanner-route rows themselves are base-identical (I measured them), so the sentence is true of the domain paragraph it sits in but reads as a claim about the whole test.

EVIDENCE:
Replayed at BASE=1b271d77 vs TIP=f0cc466e:  "echo B\necho $(while true)\necho AFTER" -c:  BASE rc=2 'B\n'  ->  TIP rc=127 'B\n'  = bash rc=127 'B\n'.
Base run of the tip test file: FAILED ...::test_unclosed_cmdsub_classified_bodies_are_carried (one of 15 failures in that file at base).

### NIT
Housekeeping for the integrator before the gate/attestation: three detached worktrees remain registered on the main repo — /private/tmp/remv-base-24r4 (@1b271d77), /private/tmp/remv-r3-24r4 (@774111f4) and /private/tmp/remv-probe-24r4 (@f0cc466e). Their mtimes (2026-07-31 00:49-01:03) POSTDATE the dev's ledger and declared tip, so they almost certainly belong to concurrent verification agents rather than to the dev (whose ledger states "My own probe worktrees: all removed"); flagging only so the pre-gate worktree list is clean. My own throwaway worktrees and probe dirs were created and removed within this task.

EVIDENCE:
$ git -C /Users/pwilson/src/psh worktree list
/Users/pwilson/src/psh          eb00deb7 [main]
/private/tmp/remv-base-24r4     1b271d77 (detached HEAD)
/private/tmp/remv-probe-24r4    f0cc466e (detached HEAD)
/private/tmp/remv-r3-24r4       774111f4 (detached HEAD)
/Users/pwilson/src/psh-install  acf3c28b (detached HEAD)
/Users/pwilson/src/psh-r2-4     f0cc466e [fix/remediation-2-4]

## Task verdict: FAIL

### BLOCKER
R4-A RESIDUAL REGRESSION (unpinned, away from bash), Family A — suppression established INSIDE the forked child: when the suppressing context (`||`, an `if` condition, `!`) is inside the child body around the failing eval, bash exits the child 1 but tip f0cc466e exits 2. The effective-errexit fix consults only the FORK-SITE suppression depth plus the raw flag, so a context entered inside the child is invisible to it, while bash consults effective errexit AT THE ABORT POINT. Round-3 tip 774111f4 matched bash (flat 1) on every one of these rows; 6cb57bef moved them to 2 — the same offense class (regression away from bash, unpinned, undeclared) that bounced round 3, on the exact intersection the integrator directed this round's probe at. Not covered by the 112-row matrix (its 7 contexts are all fork-site contexts), not by the main-shell-suppressed carry (that row is 'MAIN shell' and base-identical; these rows changed from base 0 to tip 2). Also falsifies the shipped pin docstring's design claim ('a fix that consults only the flag regresses the suppressed row, and one that consults only the state cannot tell them apart' — the shipped fix consults only the flag for in-child contexts).

EVIDENCE:
Byte-exact probe files, one case per invocation, PATH bash 5.2.26(1) aarch64 (/opt/homebrew/bin/bash), both parsers, discriminator-verified detached worktrees (tip f0cc466e, r3 774111f4, base 1b271d77), file AND -c channels: (N2) `( set -e; eval 'echo $(if)' || echo in-child ); echo AFTER rc=$?` -> bash 'AFTER rc=1' / base 'in-child\nAFTER rc=0' / r3 'AFTER rc=1' / tip 'AFTER rc=2'. (N2b) if-cond inside child: bash 1 / base 0 / r3 1 / tip 2. (N2d) `( set -e; ! eval 'echo $(if)' )`: bash 1 / base 0 / r3 1 / tip 2. (N2c cmdsub twin) `x=$( set -e; eval 'echo $(if)' || echo sub )`: bash 'AFTER rc=1 x=' / base 'AFTER rc=0 x=sub' / r3 1 / tip 2. No test in the branch covers any in-child-suppression shape (round-4 conformance test's suppressed rows all place the context OUTSIDE the fork). Control: fork-site suppression `( set -e; eval Q ) || echo GOT` is 1 at tip == bash (pinned equality row) — the miss is specifically the in-child axis.

### BLOCKER
R4-A RESIDUAL REGRESSION (unpinned, away from bash), Family B — the BACKGROUND fork site passes a stale suppression value: run_background_shell_child (psh/executor/child_policy.py:313) reads `getattr(shell, '_errexit_suppress_seed', 0)` — a seed that is 0 on any top-level parent shell — instead of the forking executor context's errexit_suppress depth. A background fork inside a suppressing context therefore exits 2 where bash (and round-3 tip) exit 1. This is precisely the integrator-predicted failure mode ('a site passing 0 unconditionally would silently give 2 in suppressed contexts'), and it falsifies the round-4-authored absolute in map_child_exception's docstring: 'Fork sites pass their own suppression depth.' Fork-site audit for the record: subshell (context depth, correct), cmdsub/backtick/procsub via run_child_shell (parent executor context depth, correct), launcher leaf (default False — matches measured bash on pipeline-member rows: bash itself does not suppress for builtin pipe members), background (stale seed — WRONG).

EVIDENCE:
Same probe rig as Family A: (N5b) `set -e; if ( eval 'echo $(if)' ) & wait $!; then echo T; else echo GOT rc=$?; fi` -> bash 'GOT rc=1' / base 'GOT rc=2' / r3 'GOT rc=1' / tip 'GOT rc=2' (both parsers). (N5c) `set -e; { ( eval 'echo $(if)' ) & wait $!; } || echo GOT rc=$?` -> bash 1 / base 2 / r3 1 / tip 2. Base's 2 came from different machinery (non-fatal eval rc 2), r3's own mapping matched bash, 6cb57bef regressed it. Unsuppressed background control (N5) `set -e; ( eval Q ) & wait $! || echo GOT` -> GOT rc=2 in bash AND tip (match) — the delta is specifically the suppressed-context axis. Pipeline controls at tip all match bash: `set -e; cat /dev/null | eval Q` rc 2==2; `{ cat /dev/null | eval Q; } || echo GOT` -> GOT rc=2==2 (bash does not suppress there); subshell-member `{ cat /dev/null | ( eval Q ); } || ...` -> GOT rc=1==1.

### BLOCKER
R4-B NOT DISCHARGED AS CLAIMED — the O3 docstring was never corrected, and the ledger says it was: test_substitution_fatality_from_a_trap_action's docstring (the exact artifact round 3 quoted as the falsified census) is byte-identical between 774111f4 and f0cc466e and still asserts 'the status differs in the FILE/STDIN channels — bash 2, psh 1 ... the -c channel and all stdout agree' and 'DOMAIN — the declaration's universe, probed rather than assumed: the divergence is UNIFORM across every action-bearing trap kind that fires MID-SCRIPT' — both false on the fork axis at tip (fork rows diverge in the -c channel too, and the errexit composition row breaks uniformity). The slot ledger's R4-B section claims 'corrected in place in the O3 docstring, record-integrity style' (FALSE — no hunk touches it), and the new test's docstring says 'Corrected here and in the O3 paragraph above' — nothing above it in that file changed (the round-4 diff to the file is additions-only from line 537). The integrator's focus item (2) explicitly required 'O3 docstring domain corrected (fork axis stated)'. The parser/CLAUDE.md twin WAS corrected ('uniform WITHIN the non-fork case'), proving the needed qualification was known.

EVIDENCE:
git show 774111f4:tests/conformance/bash/test_syntax_template_timing_conformance.py lines 382-402 diffed against tip: IDENTICAL (verified with diff, no output). Round-4 diff for the file contains only the four appended tests (git diff 774111f4..f0cc466e starts at @@ line 537, additions only). Falsifying probe at tip: `( set -T; trap 'echo $(fi)' DEBUG; echo IN ); echo AFTER rc=$?` in the -c channel -> bash stdout 'AFTER rc=2' vs psh 'AFTER rc=1' (both parsers) — a mid-script trap-action row where the -c channel and stdout do NOT agree. Ledger claim at /Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/2.4.md R4-B section: 'corrected in place in the O3 docstring'.

### BLOCKER
FALSIFIED ABSOLUTES SURVIVE THE R4-D SWEEP (the round-3 bounce class, and the integrator's focus item 4): (1) psh/core/exceptions.py:141 — 'a subshell, command/process substitution, a pipeline member and a background job all die with status 1 while the parent continues' — false since 6cb57bef (with effective errexit in the child they die with 2); this very docstring was edited by 6cb57bef (the teardown-catcher qualification lands in the adjacent bullet) yet the absolute stands, missed because the self-check grep has 'all of them' but not bare 'all'. (2) tests/conformance/bash/test_syntax_template_timing_conformance.py:297 (test_substitution_fatality_is_contained_by_forks docstring) — 'the child dies with 1 and the parent runs on — in every channel' — same falsification; round 3 explicitly extended the sweep universe to tests/ after round 2 missed it there. (3) minor: tests/unit/executor/test_child_policy.py old-pin comment still reads 'Flat 1 in every channel' one test above the new pin that says 'NOT a flat constant'.

EVIDENCE:
grep at tip: psh/core/exceptions.py:141 'background job all die with status 1 while the parent continues'; conformance file :297 'child dies with 1 and the parent runs on — in every channel'. Falsifying rows at tip (== bash, both parsers, file+-c): `( set -e; eval 'echo $(if)' )` -> AFTER rc=2; `x=$( set -e; eval Q )` -> 2; backticks -> 2; `( set -e; eval 'cat <(if)' )` -> 2; `set -e; ( eval Q ) & wait $!` -> 2. git diff 6cb57bef -- psh/core/exceptions.py shows the docstring was edited this round with the 'all die with status 1' line kept as context. The dev's own standing self-check regex (ledger R4-D) does not match bare 'all'/'in every channel', which is how these survived.

### BLOCKER
FALSE 'PINNED' CLAIM on a declared behavior change: the ledger (R4-E) says 'posix-in-fork is covered by the 18/18 option x fork matrix and pinned' — no pin exists anywhere in the branch. The row `( set -o posix; eval 'echo $(if)' ); echo AFTER rc=$?` moved base 2 -> tip 1 (toward bash's 1): a real, declared behavior change whose only test-suite coverage claim is false; the standing rule makes an unpinned behavior change a bounce and the campaign treats a false coverage claim as a false record claim. One-test fix: add the posix-in-fork row (ideally the option x fork matrix rows) to the round-4 conformance test.

EVIDENCE:
git diff 1b271d77..f0cc466e -- tests/ | grep posix -> only test_posix_relative_source_divergence_and_its_abort_status (the S1 source pin; no fork). grep 'set -o posix' over the three touched test files: no fork-shape row. Spot-run replay: bash 'AFTER rc=1' / base 1b271d77 'AFTER rc=2' / tip f0cc466e 'AFTER rc=1'. Ledger claim at 2.4.md R4-E: 'posix-in-fork is covered by the 18/18 option × fork matrix and pinned'.

### NIT
Per-commit test accounting misattributes the round-4 unit pin: the ledger table credits f0cc466e with '+1 (errexit-child unit pin)' and 6cb57bef with +4, but test_substitution_syntax_abort_honours_errexit_in_the_child lands in 6cb57bef and f0cc466e touches zero test files (its stat: internal_errors.py, child_policy.py, parser/CLAUDE.md only). The TOTAL is right: collect-only chain over the four touched test files is 293 (base) -> 324 (774111f4, +31 matching round-3 accounting) -> 329 (6cb57bef, +5) -> 329 (f0cc466e, +0), i.e. +36 = 21,015 -> 21,051. Fix the two rows before the ceremony LEDGER edit.

EVIDENCE:
git show f0cc466e --stat (3 files, no tests); git show 6cb57bef -- tests/unit/executor/test_child_policy.py | grep '^+.*def test' -> test_substitution_syntax_abort_honours_errexit_in_the_child. pytest --collect-only -q on the four files at each of the four commits: 293/324/329/329 (6cb57bef snapshot obtained via git checkout 6cb57bef -- <test files> in a throwaway worktree, then restored).

### NIT
R4-C carry-row text overstates the observable across its declared six-form domain: 'the pre-2.4 behaviour survives (-c 2 vs bash 127...)' holds for the paren-balancing subset (case-pattern-closing-paren, bare `case x in`, nested `(` — all bash 127 / psh 2) but NOT for nested `$((` and the two unterminated-quote forms, where live bash is ALSO 2, so there is no observable -c divergence to carry for those three. The untypedness census may still be true for all six; the carry's divergence parenthetical should be scoped to the paren-balancing subset before the ceremony LEDGER edit. The pinned forms in test_unclosed_cmdsub_classified_bodies_are_carried are all genuinely-divergent rows (verified: both case forms and procsub-case bash 127 / psh 2; typed control `$(while true)` 127==127), so the pins themselves are sound.

EVIDENCE:
-c probes at tip vs bash 5.2.26: `echo $(case)` bash 127/psh 2; `cat <(case x in a) :;)` bash 127/psh 2; `echo $( ( )` bash 127/psh 2; BUT `echo $(a=$((1+2)` bash 2/psh 2, `echo $(echo "abc)` bash 2/psh 2, `echo $(echo 'abc)` bash 2/psh 2 (both parsers). Carry text in 2.4.md R4-C names all six forms under the '-c 2 vs bash 127' framing.

### NIT
Interactive-channel divergence in the new fork x errexit family, unprobed and undeclared: at a PTY prompt, `( set -e; eval 'echo $(if)' ) || echo SUPP-OK rc=$?` prints rc=2 in psh vs rc=1 in interactive bash. BASE-IDENTICAL (rc=2 at base, r3, and tip — interactively SubstitutionSyntaxAbort is never raised, the child inherits interactive-ness, eval fails non-fatally rc 2 and the child's own errexit exits 2), so it is NOT a branch regression and interactive behavior is outside the slot charter; but the dev's 112-row matrix ran only c/file channels, so psh now has an internal channel inconsistency (non-interactive 1, interactive 2) in a family the slot just pinned. The chartered interactive parity guard itself HOLDS: REPL survives `echo $(fi)`, eval errors, and the suppressed-errexit row; EXIT trap fires at interactive exit; clean exit 0; zero tracebacks (both parsers). Successor-queue material.

EVIDENCE:
PTY probes (pty.fork, TERM=dumb, --norc -i), tip + base + r3 trees, discriminator-verified: SUPP-OK rc=2 at all three psh trees; interactive bash 5.2.26 prints SUPP-OK rc=1. Survival transcript at tip: ALIVE printed after the error rows, BYE (EXIT trap) on exit, exit-status 0, no Traceback, both parsers. Non-interactive same row: bash 1 == tip 1 (file and -c).

### NIT
Record notes for the integrator, all verified: (a) claims REPLAYED green by me at f0cc466e — slot test surface 329 passed (two conformance files + test_child_policy + guards; includes the 4 new round-4 tests, must-not-flip rows, six-family taxonomy pin, S1 pin), R4-F exclusion run-claim reproduces EXACTLY (229 passed), ruff 'All checks passed', mypy 'Success: no issues found in 274 source files', red-on-774111f4 replayed at pin level (3 round-4 pins FAIL at r3, unit pin via TypeError on the old 1-arg signature) and at behavior level (fork/cmdsub/backtick/procsub errexit-inside rows r3=1 -> tip=2==bash==base); teardown table, item-6 cmdsub trap $?=1, golden 127, frame fatality, errexit main-shell one-liner ordering pins, and the three self-caught pin corrections all match live bash; forbidden files EMPTY (no version.py/CHANGELOG/README/ARCHITECTURE/docs/** in the branch diff — FLIP-PINS.md and docs/reviews/README.md untouched; test_process_sub_closed_fds.py untouched); R4-E 'Touched EXACTLY' set matches git diff --name-only 1b271d77..f0cc466e; trap_manager ratification, carry texts (scanner six-form family + main-shell suppressed family), instrument-discrepancy record, and qualified closure wording all present in the ledger. (b) NOT replayed (heavy, GO-gated): full-gate 21,051 figures and compare-bash 2,986/26 — corroborated indirectly by the exact +36 collect chain. (c) Wording nit for the ceremony sweep: exceptions.py's new '(b) there is exactly ONE deliberate catcher' is literally false (scripting/source_processor.py:100 is a second deliberate `except SubstitutionSyntaxAbort` — the consumption point named one bullet later; fork sites catch it too), reconcilable in context.

EVIDENCE:
All runs at tip f0cc466e in discriminator-verified worktree /tmp/remv-probe-24r4 (psh.__file__ inside, version 0.758.0), bash 5.2.26(1)-release aarch64 at /opt/homebrew/bin/bash, r3=774111f4 and base=1b271d77 legs in their own detached worktrees, all removed after (git worktree list clean). Probe scripts and outputs in the session scratchpad (r4v_battery.py, r4v-cases/, PTY harnesses).

