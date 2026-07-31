# Slot 2.4 verification round 3 — full issue list (overall: BOUNCE)

## Task verdict: FAIL

### BLOCKER
HIGH-9/carry-#22 closure claim is over-broad: the chartered HIGH-9 signature is still alive at tip 774111f4 for the $(case ...) error-kind family, undeclared, unpinned, and uncarried. psh's cmdsub scanner classifies incomplete case bodies as 'unclosed command substitution' and raises plain ParseError with sub_origin=False (verified with the dev's own spy instrument), so neither the 2.3 producer typing nor either of 2.4's consumer sites fires — a THIRD route the round-2 error-kind enlargement (fi/;/;;/done/|x) still missed. Base-identical (tip==base on every row), so this is not a branch regression, but the slot ledger's 'Carry #22 — CLOSED' / 'HIGH-9 is closed' claims are absolute, the campaign LEDGER row would close on them at ceremony, and the branch's own new docs assert universals the family contradicts (helpers.py: 'no substitution-body syntax error escapes untagged'; 'the fatality does not depend on WHICH syntax error the body has'). Round-2 precedent treated the identical shape of miss ('HIGH-9 was only HALF consumed') as a bounce. Disposition is the integrator's — in-slot consumption likely needs lexer/scanner scope (out of the O1 grant), else declare+pin+carry — but the closure claim must be qualified and the family pinned either way.

EVIDENCE:
Fresh rows, PATH bash 5.2.26(1) aarch64 (/opt/homebrew/bin/bash), psh import-discriminated to /Users/pwilson/src/psh-r2-4, both parsers, one case per invocation, byte-exact probe files: (1) `echo $(case)` -c: bash rc 127 / psh rd+combinator rc 2 — the verbatim 6-way-pin signature; (2) `eval 'echo $(case)'; echo AFTER` file AND stdin: bash rc 1, no AFTER / psh rc 0, prints AFTER — the verbatim frame-continuation signature (also `case x`, `case x in`); (3) sourced file with `echo $(case x in)`: bash aborts rc 1 / psh continues, prints OUTER-AFTER. Spy on SourceProcessor._report_syntax_error at tip: `$(case)`/`$(case x)`/`$(case x in)` arrive as `type=ParseError sub_origin=False` ('unclosed command substitution'), vs `$(if)`/`$(fi)`/`$(while)`/`$(until)`/`$(select)` = `type=SubstitutionSyntaxError sub_origin=True` → rc 127. Base replay via `git archive 1b271d77` tree: every psh row byte-identical to tip. No coverage found: `git grep '\$(case' fix/remediation-2-4 -- tests/` shows only VALID-construct pins (test_cmdsub_case_conformance.py etc.); no divergence pin or LEDGER carry names the invalid-case-body fatality family (2.3's lexer carries cover different shapes).

### NIT
The O1 ruling-discharge row still reads 'Touched EXACTLY: core/exceptions.py, core/internal_errors.py, core/__init__.py, scripting/source_processor.py, executor/child_policy.py ... No spread beyond the grant', but the final branch also touches psh/core/trap_manager.py (774111f4, round-3 teardown fix) and psh/parser/recursive_descent/helpers.py (3905ad72, doc-only — verified no code change in the diff). Both are openly declared in the round-2/round-3 sections, so nothing is silent, but the O1 row as written is now false about the branch and should be amended before the ceremony LEDGER edit.

EVIDENCE:
git diff --name-only 1b271d77..fix/remediation-2-4 includes psh/core/trap_manager.py and psh/parser/recursive_descent/helpers.py; the O1 table row in /Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/2.4.md was written at round 1 and never updated.

### NIT
The 'Pin obligations' table does not name a commit SHA per FLIPPED row; attribution rides the enclosing 'What landed (commit a76e93f0)' section heading plus the per-commit accounting tables. I verified in-diff that all three pin renames and the golden co-flip do land in a76e93f0, so the record is accurate — but for the ceremony edit, inlining the SHA per flipped row would make the table self-contained.

EVIDENCE:
git show a76e93f0 shows the rename test_divergence_c_mode_exit_code_is_127_in_bash -> test_c_mode_exit_code_is_127_like_bash, both test_syntax_template renames, and golden_cases.yaml exit_code 2->127 with data fields otherwise identical (comment block rewritten, as the ledger discloses).

### NIT
Not replayed by me (out of Task 3 scope; heavy runs are integrator-GO-gated): the full-gate figures (21,046/1,590/10 at 774111f4), compare-bash composition (2,986/26), mypy 274, and the interactive PTY parity batteries. I instead replayed the slot's own test surface: 303 passed / 0 skipped / 0 xfailed across the two conformance files + test_child_policy.py at tip, and the golden-row instrument (1 passed / 1 skipped, skip reasons matching the ledger's recorded instrument in both modes). All red/green splits I assert in this report were run by me on both sides.

EVIDENCE:
python -B -m pytest -p no:cacheprovider tests/conformance/bash/test_nested_substitution_timing_conformance.py tests/conformance/bash/test_syntax_template_timing_conformance.py tests/unit/executor/test_child_policy.py -q -> 303 passed in 85.44s; tests/behavioral -k heredoc_nested_error_reports_absolute_line -> 1 passed, 1 skipped (--compare-bash not specified).

## Task verdict: FAIL

### BLOCKER
Falsified absolutes survive round 3's doc sweep: three branch-authored statements are now contradicted by the round-3 teardown swallow (psh/core/trap_manager.py:564-567 'except SubstitutionSyntaxAbort: pass'). (1) psh/core/exceptions.py SubstitutionSyntaxAbort class docstring still says 'the one consumption point is scripting/source_processor.py#execute_as_main' and 'NO frame contains it — not a function, ... a trap action, nor any nesting of those; ... propagation is automatic and no frame needs to know about it' — TrapManager.execute_exit_trap is now a second consumption point that knows about and contains it on the EXIT-trap-action-at-teardown path. (2) psh/core/CLAUDE.md (~line 430, added by this branch): 'SubstitutionSyntaxAbort ends the shell PROCESS and is contained only by a fork (executor/child_policy.py#map_child_exception)' — false, the teardown swallow is a non-fork containment site. (3) psh/executor/CLAUDE.md (~line 278, added by this branch): 'The SubstitutionSyntaxAbort arm is what makes a FORK the only thing that contains a substitution-origin shell abort' — same falsified 'only'. This is precisely the statement the dev DID fix in source_processor.py:299-306 ('the ONE exception is an EXIT trap firing at TEARDOWN... swallows it instead') and parser/CLAUDE.md, so the contradiction is intra-branch and load-bearing; it is the same offense class as the round-2 bounce (b) (falsified doc statements) and the item the integrator's FOCUS(5) directed the hunt at. Fix is three doc edits; everything behavioral is green.

EVIDENCE:
At tip 774111f4: grep -rn 'SubstitutionSyntaxAbort' psh/ shows catch sites source_processor.py:100 AND trap_manager.py:566; exceptions.py:128-142 and the two CLAUDE.md passages read as quoted; git diff 1b271d77..774111f4 confirms all three passages are branch-authored; dev ledger (psh-r2-4/tmp/remediation-ledgers/2.4.md:783-786) records fixing only source_processor + parser/CLAUDE.md for this exact claim.

### NIT
Dev ledger run-claim for the two doc-sweep exclusions does not reproduce: '(218 + 335 passed)' (2.4.md:779). Replay at tip: tests/conformance/bash/test_subscript_keying_conformance.py = 218 passed (matches) but tests/unit/core/test_array_mutation_invariants_p1.py = 11 passed; no visible selection of either file yields 335, and no command is recorded (instrument-discipline gap). The exclusion SUBSTANCE holds — I independently verified both families are untouched by this branch and both files pass at 774111f4.

EVIDENCE:
pytest runs at 774111f4: 11 passed (array_mutation), 218 passed in 145s (subscript_keying); collect-only 11 and 218; tests/unit/core/ whole-dir = 750, so no obvious 335 candidate.

### NIT
New trap_manager.py execute_exit_trap docstring overgeneralizes its historical-cause claim: 'the teardown callers guard SystemExit/Exception, neither of which catches it, so it reached the CLI as a raw Python traceback' — true for 4 of the 5 callers, but the interactive signal-death caller (psh/interactive/signal_manager.py:297-305, pre-existing at base) guards SystemExit + BaseException and would have swallowed the abort without a traceback. Behavior-irrelevant now (the swallow happens one level deeper), but the absolute is inaccurate for one caller.

EVIDENCE:
signal_manager.py:299-305 at base 1b271d77 and tip 774111f4 both show 'except SystemExit: pass / except BaseException: pass' around execute_exit_trap().

## Task verdict: FAIL

### BLOCKER
UNPINNED BEHAVIOR CHANGE + FALSIFIED DECLARED DOMAIN: a MID-SCRIPT trap ACTION whose own text carries a substitution-body syntax error now aborts inside a FORK (correct, matches bash's timing) but exits the subshell with 1 where bash 5.2.26 exits 2 — and the divergence is visible in STDOUT in the -c channel. Nothing in the branch pins any mid-script trap action inside a fork (the suite pins only EXIT traps inside forks, tests/conformance/bash/test_syntax_template_timing_conformance.py:447 and :449). Worse, the shipped declaration in test_substitution_fatality_from_a_trap_action (same file, :382) states the opposite as a probed CENSUS: 'the status differs in the FILE/STDIN channels — bash 2, psh 1 ... the -c channel and all stdout agree', and its DOMAIN paragraph claims 'the declaration's universe, probed rather than assumed ... UNIFORM across every action-bearing trap kind that fires MID-SCRIPT'. The fork axis was never in that corpus; on that axis the claim is false. Per the brief ('Any behavior delta beyond your chartered flips ... DECLARED + PINNED — an unpinned improvement is still a bounce') and the campaign INSTRUMENT DISCIPLINE rule ('the instrument must match the claim's UNIVERSE'), this must be re-probed over the fork axis, declared correctly, and pinned. The integrator may reasonably rule this a declare+pin amendment rather than a redesign — the timing half already matches bash.

EVIDENCE:
Byte-exact probe FILE (od -c verified: `( s e t   - T ;   t r a p   '   e c h o   $ ( f i ) '   D E B U G ;   e c h o   I N ) \n e c h o   A F T E R   r c = $ ? \n`), PATH bash /opt/homebrew/bin/bash 5.2.26(1)-release, both parsers, replayed base-vs-tip in detached worktrees (discriminator: psh.__file__ under the tree under test, version 0.758.0 both):
  bash            rc=0 stdout='AFTER rc=2\n'
  psh @1b271d77   rc=0 stdout='IN\nAFTER rc=0\n'      (base: trap error non-fatal, subshell continued)
  psh @774111f4 --parser rd         rc=0 stdout='AFTER rc=1\n'
  psh @774111f4 --parser combinator rc=0 stdout='AFTER rc=1\n'

Domain census over the trap-kind x channel x fork axes (all rows: base='IN\nAFTER rc=0', bash='AFTER rc=2', tip='AFTER rc=1'; uniform in c / file / stdin):
  ( trap 'echo TA; echo $(fi)' USR1; kill -USR1 $BASHPID; sleep 0.3; echo IN ); echo AFTER rc=$?
  ( trap 'echo TA; echo $(if)' USR1; ... )                    same
  ( set -T; trap 'echo $(fi)' DEBUG; echo IN ); echo AFTER rc=$?
  ( set -E; trap 'echo $(fi)' ERR; false; echo IN ); echo AFTER rc=$?
  ( set -T; trap 'echo $(fi)' RETURN; f() { echo INF; }; f; echo IN ); echo AFTER rc=$?   (bash 'INF\nAFTER rc=2', tip 'INF\nAFTER rc=1')

CONTROLS that prove the finding is specific and NEW (not conflation):
  - x=$( set -T; trap 'echo $(fi)' DEBUG; echo IN ); echo AFTER rc=$? x=[$x]  -> bash 'AFTER rc=1 x=[]' == tip 'AFTER rc=1 x=[]'  (cmdsub child MATCHES; base was 'AFTER rc=0 x=[IN]')
  - { set -T; trap 'echo $(fi)' DEBUG; echo IN; } | cat; echo AFTER rc=$?     -> bash == tip 'AFTER rc=0'
  - ( trap ... TERM; kill -TERM $BASHPID; ...)                                -> bash 2 / psh 143 at BOTH base AND tip = PRE-EXISTING, unchanged
  - ( eval 'echo $(if)' ); echo AFTER rc=$?                                   -> bash == tip (already pinned by test_substitution_fatality_is_contained_by_forks)

So the delta is specific to the explicit `( ... )` subshell, where bash reports 2 for a trap-action parse error while psh's flat map_child_exception -> 1 (psh/executor/child_policy.py:105-106) applies.

### NIT
CEREMONY DEBT (not a branch defect — precedent confirms these files are integrator-owned and edited at ceremony commits, e.g. 7bcf163e 'remediation 2.3 ceremony' and 2714b0e2 'remediation 2.2 ceremony'): every surviving reference to the four renamed symbols lives in integrator-owned campaign records, so the LEDGER/FLIP-PINS rows are still worded against the OLD test IDs. Also carries the FLIP-PINS location correction the brief already tallied as integrator fault.

EVIDENCE:
git grep -n <symbol> fix/remediation-2-4 -- psh/ tests/ docs/ tools/ — ZERO hits in live code; all hits under docs/reviews/:
  test_divergence_c_mode_exit_code_is_127_in_bash  -> FLIP-PINS.md:13, LEDGER.md:29, boundary_remediation_integrator_plan_2026-07-21.md:77, boundary_campaign_close_2026-07.md:179 and :249, 2.2-rescue/INTEGRATOR-INBOX.md:50, 2.2-rescue/slot-ledger.md:363 and :496
  test_divergence_eval_source_fatality_is_i3       -> FLIP-PINS.md:15, LEDGER.md:161
  test_divergence_eval_source_procsub_joined_i3    -> FLIP-PINS.md:16, LEDGER.md:161, 2.3-rescue/slot-ledger.md:654 and :767
  test_taxonomy_tuple_is_the_five_families         -> no hits anywhere
New names in the branch: test_c_mode_exit_code_is_127_like_bash, test_eval_source_frame_fatality_matches_bash, test_eval_source_procsub_joined_family_matches_bash, test_taxonomy_tuple_is_the_six_families.
FLIP-PINS.md:16 additionally still says the procsub co-flip lives in test_subscript_keying_conformance.py; it is in tests/conformance/bash/test_syntax_template_timing_conformance.py:501 (the correction the 2.4 brief's 2026-07-30 amendment already owed).

### NIT
Doc pointer touched by this branch resolves only through the file's local shorthand: psh/parser/CLAUDE.md says `support/nested_parse.py#parse_nested_command`, but the file is at psh/parser/recursive_descent/support/nested_parse.py. This is PRE-EXISTING on origin/main (identical text on the removed line of the dev's hunk) and consistent with the file's own convention (line 43 declares '### Support Infrastructure (`recursive_descent/support/`)'; the same shorthand is used at :214, :499, :527, :561, :589). Not introduced here — flagged only so a future doc-pointer guard does not blame slot 2.4.

EVIDENCE:
find psh -name 'nested_parse*' -> psh/parser/recursive_descent/support/nested_parse.py (parse_nested_command at :43). `ls psh/parser/support/` -> no such directory. git show origin/main:psh/parser/CLAUDE.md | grep -n support/nested_parse -> :527 and :599 (both pre-existing).

### NIT
ENVIRONMENT OBSERVATION, not attributable to this branch and not caused by this verifier: two of the integrator plan §3 NEVER-TOUCH files from the parallel session were present as untracked entries in the main checkout at the start of this session and are now ABSENT from /Users/pwilson/src/psh. This verifier's only writes were inside two throwaway worktrees under /Users/pwilson/src/psh/tmp/ (remv-wt-t2 at 774111f4 and remv-wt-base at 1b271d77), both removed with `git worktree remove --force`; no rm ran in the repo root. Surfacing so the integrator can confirm with the parallel session before Ceremony C.

EVIDENCE:
Session-start gitStatus untracked list included `" 1 "` and `b]y`. After my work: `for f in " 1 " "b]y" "bugs.txt"; do [ -e "$f" ] && echo PRESENT || echo ABSENT; done` -> ABSENT: [ 1 ] / ABSENT: [b]y] / ABSENT: [bugs.txt]. `d/`, `decomment.py`, and the modified `docs/reviews/README.md` are still present and untouched. `git -C /Users/pwilson/src/psh worktree list` shows both of my worktrees gone; main still at eb00deb7 [main].

## Task verdict: FAIL

### BLOCKER
REGRESSION AWAY FROM BASH, unpinned: in a FORKED child with `set -e` active, a substitution-body syntax error now exits the child 1 where bash — and psh at the wave base — exit 2. `psh/executor/child_policy.py#map_child_exception` maps `SubstitutionSyntaxAbort` to a FLAT 1 and deliberately does not consult `substitution_abort_status`, whose FIRST branch is the errexit rule the dev themselves established (`if state.options.get('errexit'): return 2`). The dev's fork corpus held `set -e` OFF, so the fork x errexit intersection is untested: `test_substitution_fatality_is_contained_by_forks` has no errexit, and `test_substitution_fatality_status_under_errexit_is_2` has no fork. This also falsifies three production claims shipped in this diff: child_policy.py:279-282 'The status is 1 in EVERY channel ... (probe-verified for subshell, command substitution, backticks, pipeline members and background jobs)'; internal_errors.py:160-162 'A FORKED child never comes here: it exits 1 in every channel ..., matching bash'; psh/executor/CLAUDE.md:239 'its 1 is channel-independent'. The unit pin `test_substitution_syntax_abort_maps_to_one` pins the wrong constant.

EVIDENCE:
REPLAYED, one case per invocation, PATH bash /opt/homebrew/bin/bash 5.2.26 vs psh TIP=774111f4 vs psh BASE=1b271d77 (both detached worktrees, discriminator-verified via psh.__file__/__version__, removed after).

(1) `( set -e; eval 'echo $(if)' ); echo AFTER rc=$?`
    -c   : bash out='AFTER rc=2'  BASE out='AFTER rc=2'  TIP out='AFTER rc=1'
    file : bash out='AFTER rc=2'  BASE out='AFTER rc=2'  TIP out='AFTER rc=1'
    --parser combinator, -c: bash 'AFTER rc=2', BASE 'AFTER rc=2', TIP 'AFTER rc=1'
(2) `( set -e; eval 'echo $(fi)' ); echo AFTER rc=$?`   (other error kind)
    -c and file: bash 'AFTER rc=2', BASE 'AFTER rc=2', TIP 'AFTER rc=1'
(3) `x=$( set -e; eval 'echo $(if)' ); echo AFTER rc=$? x=$x`  (command substitution)
    -c and file: bash 'AFTER rc=2 x=', BASE 'AFTER rc=2 x=', TIP 'AFTER rc=1 x='
(4) x=`set -e; eval 'echo $(if)'`; echo AFTER rc=$?   (backticks)
    -c: bash 'AFTER rc=2 x=', BASE 'AFTER rc=2 x=', TIP 'AFTER rc=1 x='
(5) `{ set -e; eval 'echo $(if)'; } & wait $!; echo AFTER rc=$?`  (background job)
    -c: bash 'AFTER rc=2', BASE 'AFTER rc=2', TIP 'AFTER rc=1'
(6) `( set -e; eval 'cat <(if)' ); echo AFTER rc=$?`  (procsub spelling)
    -c: bash 'AFTER rc=2', BASE 'AFTER rc=2', TIP 'AFTER rc=1'

No test in the branch covers this axis: grep of the two conformance files shows `set -e` only in test_substitution_fatality_status_under_errexit_is_2 / test_same_line_set_e_does_not_reach_the_read_time_error, both main-shell-only. Confirms 'unpinned' as well as 'regression'.

### NIT
Scope: `psh/core/trap_manager.py` is edited (execute_exit_trap swallows SubstitutionSyntaxAbort) but is NOT in the integrator's O1 scope grant as recorded in the dev ledger, which enumerates source_processor.py + core/exceptions.py + core/internal_errors.py + child_policy.py + strategies.py. The brief's Rules line puts 'core/state beyond the outcome type's home' behind a STOP-and-report. The edit is a correct fix for a CLI-reachable traceback (round-3 blocker A) and is pinned, but the integrator should confirm the grant covers it rather than let it land unruled.

EVIDENCE:
Ledger /Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/2.4.md:254-259 lists only O1-O4; O1 row: 'Touched EXACTLY: core/exceptions.py, core/internal_errors.py, core/__init__.py (export only), scripting/source_processor.py, executor/child_policy.py'. Round-3 section :721 then says 'FIX (one place): core/trap_manager.py#TrapManager.execute_exit_trap', with no recorded ruling extending the grant.

### NIT
Two further UNPINNED behavior moves on the same missing fork/option axis, both toward bash (improvements, which the brief still classes as bounce-worthy if undeclared): `set -o posix` inside a forked child, and errexit suppressed by a `||` context. Whatever the ruling on the blocker, the pin added for it should cover the option x fork matrix rather than a single row.

EVIDENCE:
REPLAYED (bash 5.2.26 / TIP 774111f4 / BASE 1b271d77):
`( set -o posix; eval 'echo $(if)' ); echo AFTER rc=$?`  -c: bash 'AFTER rc=1', BASE 'AFTER rc=2', TIP 'AFTER rc=1'
`set -e` + `( eval 'echo $(if)' ) || echo GOTrc=$?`  -c and file: bash 'GOTrc=1', BASE 'GOTrc=2', TIP 'GOTrc=1'
Also main-shell posix (matches bash at tip, unpinned for the eval route): `set -o posix; echo B; eval 'echo $(if)'; echo AFTER` -> c: bash 127 / BASE 2 / TIP 127; file+stdin: bash 1 / BASE 2 / TIP 1.

### NIT
Adjacent PRE-EXISTING divergence surfaced while testing the dev's 'process_launcher needs no sync' answer: psh never runs a pipeline member's EXIT trap on normal completion, where bash does. Base == tip, so it is NOT introduced by this slot, but it means the third fork site's exemption is true only because psh already drops that trap. Worth a successor-queue row.

EVIDENCE:
REPLAYED: `{ trap 'echo T rc=$? >&2' EXIT; true; } | cat; echo RC=$?`  -c: bash stderr 'T rc=0\n'; psh TIP stderr ''; psh BASE stderr ''. CONTROL `{ trap 'echo T rc=$? >&2' EXIT; exit 5; } | cat` gives 'T rc=5' in bash, TIP and BASE alike, so psh does fire it on the explicit-exit path only.

### NIT
Task-1 checks (a)-(d) all PASS, recorded for the integrator: (a) psh/version.py, CHANGELOG.md, README.md, ARCHITECTURE.md, docs/reviews/README.md untouched — branch version.py still reads 0.758.0; (b) every hunk maps to a brief item (typed outcome, two consumer sites, fork containment, EXIT-trap teardown, 4 pin obligations, 5 subsystem CLAUDE.md prose-only edits with no code sketches — no test_doc_snippets registry fragment is touched); (c) all four flip obligations discharged and green, must-NOT-flip rows green; (d) no parallel-session never-touch file touched.

EVIDENCE:
git diff origin/main...fix/remediation-2-4 --stat = 17 files, none of the integrator-owned or never-touch set. Flips: test_divergence_c_mode_exit_code_is_127_in_bash -> test_c_mode_exit_code_is_127_like_bash (6 params, equality); test_divergence_eval_source_fatality_is_i3 -> test_eval_source_frame_fatality_matches_bash; test_divergence_eval_source_procsub_joined_i3 -> test_eval_source_procsub_joined_family_matches_bash (in test_syntax_template_timing_conformance.py, per the 2026-07-30 location correction); golden heredoc_nested_error_reports_absolute_line exit_code 2 -> 127 with every other YAML data field byte-identical. No dangling references: git grep of the three old names over fix/remediation-2-4 hits only docs/evidence history (FLIP-PINS/LEDGER, integrator-owned).
RUNS at tip 774111f4: tests/conformance/bash/test_nested_substitution_timing_conformance.py + test_syntax_template_timing_conformance.py = 279 passed; tests/conformance/bash/test_subscript_keying_conformance.py = 218 passed (covers the must-NOT-flip keying pins).
Interactive must-NOT-flip guard rail PTY-probed by me (pty.fork, TERM=dumb, --norc -i): typing `echo $(fi)`, `eval 'echo $(fi)'` then `echo ALIVE2` — bash, psh TIP and psh BASE all report the diagnostic and stay alive, exit status 0 on `exit`; TIP transcript identical to BASE.
Broad 15-shape x 2-channel sweep (DEBUG/RETURN/EXIT traps, nested eval-in-eval, `.` spelling, source-from-function, while-condition, case word, subshell-in-function, bg+wait, here-string, heredoc body, `time`, brace group): zero Python tracebacks at tip; every row matches bash except the declared O3 mid-script trap-action status (RETURN trap, file channel: bash 2 / psh 1) and the pre-existing heredoc-body stdout shape (identical at base and tip).

