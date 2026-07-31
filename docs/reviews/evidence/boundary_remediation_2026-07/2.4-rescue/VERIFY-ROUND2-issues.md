# Slot 2.4 verification round 2 — full issue list (overall: BOUNCE)

## Task verdict: PASS-WITH-NITS

### NIT
FLIP-PINS.md still names all three RENAMED conformance tests, so every flip-pin row is now a dangling reference. Rows: line 13 `test_divergence_c_mode_exit_code_is_127_in_bash`, line 15 `test_divergence_eval_source_fatality_is_i3`, line 16 `test_subscript_keying_conformance.py::test_divergence_eval_source_procsub_joined_i3`. Line 16 ALSO still carries the wrong FILE PATH the brief already flagged (it lives in test_syntax_template_timing_conformance.py). NOT scored a blocker: the brief's dated amendment block assigns this explicitly to the integrator ("FLIP-PINS row correction owed at ceremony. Integrator fault, tallied."), so the dev correctly left it alone. Integrator owes name+path+closed-status on all three rows at ceremony. Flagging the ambiguity: brief item 4 says '2 divergence pins -> equality + closed rows', which a strict reader could have read as dev-owned.

EVIDENCE:
git -C /Users/pwilson/src/psh grep -n "test_divergence_c_mode_exit_code_is_127_in_bash\|test_divergence_eval_source_fatality_is_i3\|test_divergence_eval_source_procsub_joined_i3" fix/remediation-2-4 -- docs/reviews/evidence/boundary_remediation_2026-07/FLIP-PINS.md
->
FLIP-PINS.md:13:| `tests/conformance/bash/test_nested_substitution_timing_conformance.py::test_divergence_c_mode_exit_code_is_127_in_bash` (6 params: ...) | 2.4 |
FLIP-PINS.md:15:| `tests/conformance/bash/test_syntax_template_timing_conformance.py::test_divergence_eval_source_fatality_is_i3` | 2.4 |
FLIP-PINS.md:16:| **CO-FLIP (added v0.758.0):** `test_subscript_keying_conformance.py::test_divergence_eval_source_procsub_joined_i3` ... | 2.4 |

New names (present exactly once each, in the right files):
  tests/conformance/bash/test_nested_substitution_timing_conformance.py -> test_c_mode_exit_code_is_127_like_bash
  tests/conformance/bash/test_syntax_template_timing_conformance.py -> test_eval_source_frame_fatality_matches_bash, test_eval_source_procsub_joined_family_matches_bash
  tests/unit/executor/test_child_policy.py -> test_taxonomy_tuple_is_the_six_families

### NIT
LEDGER.md and the integrator plan's A3 flip-pin inventory also still name the old test symbols. Same integrator-ceremony class as above (the brief says 'the integrator's LEDGER edit at ceremony has your confirmation'), so not a dev bounce — but they are live governing docs, not archives, so they should be updated in the same ceremony as FLIP-PINS.md.

EVIDENCE:
docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md:29  -> `flip the 6-way test_divergence_c_mode_exit_code_is_127_in_bash`
docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md:161 -> `Pin test_divergence_eval_source_procsub_joined_i3 co-flips with 2.4's test_divergence_eval_source_fatality_is_i3`
docs/reviews/boundary_remediation_integrator_plan_2026-07-21.md:77 -> A3 bullet `...::test_divergence_c_mode_exit_code_is_127_in_bash (6 params) -> Wave 2 slot 2.4`

### NIT
Three ARCHIVED campaign records also name the old symbols. Recommend LEAVING these as-is: they are point-in-time historical records (the predecessor close report and two completed slot ledgers), and rewriting them would falsify the record. Listing them only so the integrator's ceremony sweep does not mistake them for missed work.

EVIDENCE:
docs/reviews/boundary_campaign_close_2026-07.md:179, :249 (predecessor S3->I3 row + carry #22 row)
docs/reviews/evidence/boundary_remediation_2026-07/2.2-rescue/INTEGRATOR-INBOX.md:50
docs/reviews/evidence/boundary_remediation_2026-07/2.2-rescue/slot-ledger.md:363, :496
docs/reviews/evidence/boundary_remediation_2026-07/2.3-rescue/slot-ledger.md:654, :767

### NIT
psh/executor/process_launcher.py:356 is a THIRD fork site that catches CHILD_EXIT_EXCEPTIONS and calls map_child_exception(e) but does NOT call the new sync_child_status_for_exit_trap(). I verified this is BENIGN, not a gap: that path goes straight to flush_child_streams(...) + os._exit(exit_code) with no execute_exit_trap(), so there is no EXIT trap to observe a stale $?. The two sites that DO run an exit trap (child_policy.run_background_shell_child:300-303 and run_child_body:392-394) are both wired. Recorded so a later reader does not read the asymmetry as a missed call site.

EVIDENCE:
psh/executor/process_launcher.py:356 `except CHILD_EXIT_EXCEPTIONS as e:` ... :367 `exit_code = map_child_exception(e)` ... finally: `flush_child_streams(sys.stdout, sys.stderr); os._exit(exit_code)` — no execute_exit_trap() anywhere in that function.
Contrast psh/executor/child_policy.py:392-397: `except CHILD_EXIT_EXCEPTIONS as e: exit_code = map_child_exception(e); sync_child_status_for_exit_trap(child_shell.state, e, exit_code)` then `child_shell.trap_manager.execute_exit_trap()`.

### NIT
REPLAYED, both directions, not asserted: for the UNTERMINATED body kind (`echo $(if)`) an interactive psh REPL drops to PS2 and swallows every subsequent line, where bash reports the error and continues. This is IDENTICAL at base 1b271d77 and tip 025a6a27 (byte-identical PTY transcripts), so it is PRE-EXISTING and NOT introduced by this branch — the must-not-flip guardrail ('a REPL that dies on echo $(if) is a bounce') HOLDS: psh does not die, and for the COMPLETE-but-invalid kind ($(fi), eval '$(fi)', cat <(fi)) tip==base and both match bash's report-and-continue. Noted as H15/resumable-parser territory, not slot 2.4's charter.

EVIDENCE:
PTY probe, PS1='P1> ' PS2='P2> ', script `echo BEFORE / echo $(if) / echo ALIVE1 / exit 7`:
BASE(1b271d77): '...P1> echo $(if)\r\nP2> echo ALIVE1\r\nP2> exit 7\r\nP2> '
TIP (025a6a27): '...P1> echo $(if)\r\nP2> echo ALIVE1\r\nP2> exit 7\r\nP2> '   (identical)
bash 5.2.26 -i: '...P1> echo $(if)\r\nbash: syntax error near unexpected token `)'\r\nP1> echo ALIVE1\r\nALIVE1\r\n...'
Complete-but-invalid script (`$(fi)`, eval, `<(fi)`): BASE and TIP transcripts identical, ALIVE1/ALIVE2/ALIVE3 all printed in psh and bash.

## Task verdict: PASS-WITH-NITS

### NIT
Ledger Phase A 'Design corroboration' misattributes function names for two base catch-site citations: child_policy.py:261 is inside run_background_shell_child (ledger says run_child_body) and :353 is inside run_child_body (ledger says run_child_shell; run_child_shell delegates to run_child_body). Line numbers and the three-site/one-taxonomy substance are correct — verified at 1b271d77.

EVIDENCE:
git show 1b271d77:psh/executor/child_policy.py: defs at 224 (run_background_shell_child), 288 (run_child_body), 366 (run_child_shell); except CHILD_EXIT_EXCEPTIONS at 261 and 353; run_child_shell docstring: 'delegates the shared middle to run_child_body'.

### NIT
Ledger O1 row wording says executor/strategies.py 'catches the shared CHILD_EXIT_EXCEPTIONS tuple' — strategies.py never catches it; it delegates to child_policy.run_background_shell_child, which does. The conclusion (no strategies.py edit needed; the tuple entry covers it) is verified TRUE.

EVIDENCE:
grep CHILD_EXIT_EXCEPTIONS psh/executor/strategies.py at tip: 0 hits; strategies.py:445 and :519 call run_background_shell_child(shell, body).

### NIT
Pin-obligations table says the golden co-flip changed 'exit_code 2 -> 127 (ONLY that field)'. True for data fields (stdout/stderr/command/name/psh_only unchanged, verified), but commit a76e93f0 also rewrote the row's 12-line explanatory comment block — necessary (the old comment described the divergence as open and would have been falsified), but the ledger's 'only that field' undersells the diff.

EVIDENCE:
git diff 1b271d77..fix/remediation-2-4 -- tests/behavioral/golden_cases.yaml: exit_code 2->127 plus comment-block rewrite; all YAML data fields except exit_code byte-identical.

### NIT
Ledger closes with 'git worktree list clean' — the dev's own probe worktrees (psh-r24-base and the ca1377b7 replay tree) ARE gone, but the repo currently carries six verifier-/harness-side worktrees (remv-24v2-base/-old/-tip, psh-v24-base/-tip, psh-install). Not a dev fault; flagging so the integrator's ceremony cleanup sweeps them.

EVIDENCE:
git -C /Users/pwilson/src/psh worktree list: /private/tmp/remv-24v2-{base,old,tip}, /Users/pwilson/src/psh-v24-{base,tip}, /Users/pwilson/src/psh-install remain; no psh-r24-* entries.

## Task verdict: FAIL

### BLOCKER
Branch-introduced, unpinned, undeclared behavior break in the trap-EXIT-teardown family, including a CLI-reachable uncaught Python traceback: when an EXIT trap ACTION's own text contains a substitution-body syntax error and the trap fires at shell teardown, psh at tip 025a6a27 crashes (raw SubstitutionSyntaxAbort traceback on stderr, rc 1) where bash 5.2.26 prints a diagnostic and exits 0; the same family clobbers an explicit exit status (bash/base 5 -> tip 127) and changes forked-child statuses (subshell RC 0->1; cmdsub RC 0->127, violating the branch's own 'a child is always 1' policy). All rows matched bash byte-for-byte at base 1b271d77. The $(if) kind broke at round-1 tip ca1377b7 (missed then); round 2's second consumer site extended it to the $(fi) kind — so the crash is live at the declared tip on BOTH parsers and all three channels. Root cause: source_processor.py execute_as_main line ~111 calls trap_manager.execute_exit_trap() OUTSIDE the except-SubstitutionSyntaxAbort consumption, and the exit-builtin trap-fire path consumes the abort but lets its 127 override the intended status. This also falsifies (a) the dev's differential claim that exactly 2 mismatches (declared O4 in-trap-257) remain — their errorkind.py corpus has only a VALID-action trap row, no invalid-action-at-teardown row — and (b) round 2's new parser/CLAUDE.md absolute 'A TRAP ACTION string whose own parse fails: both shells abort' (bash does NOT abort in this shape) plus _substitution_syntax_abort's docstring claim that execute_as_main resolves the abort into the process status. Not covered by ruling O3 (that declared divergence is the USR1 mid-script shape with different pinned observables). Interactive REPL is protected (PTY-verified, no crash at interactive exit). Bounce: consume the abort around the EXIT-trap teardown call (and the exit-builtin + child teardown paths) to bash's observables, and pin the family red-on-tip.

EVIDENCE:
Replayed at base 1b271d77 / old tip ca1377b7 / tip 025a6a27, PATH bash 5.2.26 (/opt/homebrew/bin/bash), discriminator-verified worktrees, one case per invocation, rd+combinator. Row 1 `trap 'echo $(fi)' EXIT; echo B` (-c/file/stdin identical): bash rc=0; base rc=0 tb=0; old $(if) rc=1 tb=2, old $(fi) rc=0 tb=0; tip BOTH kinds rc=1 with 'Traceback ... psh.core.exceptions.SubstitutionSyntaxAbort' escaping __main__ via source_processor.py:111 execute_exit_trap -> trap_manager.execute_trap -> _run_from_source:229. Row 2 `trap 'echo $(fi)' EXIT; exit 5`: bash 5 / base 5 / old $(if) 127 / tip 127 both kinds. Row 3 `( trap "echo $(fi)" EXIT; echo B ); echo RC=$?`: bash RC=0, base RC=0, tip RC=1. Row 4 `x=$(trap "echo $(fi)" EXIT; echo B); echo got=$x RC=$?`: bash got=B RC=0, base got=B RC=0, tip got=B RC=127. Dev battery gap: grep of /Users/pwilson/src/psh-r2-4/tmp/r24-probes/errorkind.py shows one trap row (m5_exit_trap, valid action `trap 'echo T rc=$?' EXIT` + eval body). Combinator parser reproduces all rows. PTY: `trap 'echo $(fi)' EXIT` then exit at a prompt -> survives, no traceback (is_script_mode guard).

### NIT
Pre-existing (NOT branch-introduced) divergence found by a novel row on the round-2 error-kind axis: `cat <<EOF` with `$(fi)` in the heredoc BODY — bash's runtime expansion failure aborts the redirection (cat never runs, next $? is 1, stdout 'AFTER rc=1'), psh runs cat with the empty expansion (stdout '\nAFTER rc=0'). psh behavior is byte-identical at base 1b271d77, ca1377b7, and 025a6a27, so it is out of this slot's scope; same family as the declared heredoc-body runtime divergence (must-not-flip pin) but a different observable and error kind, currently unpinned. Recommend recording as a successor/carry row.

EVIDENCE:
Probe file 'cat <<EOF\n$(fi)\nEOF\necho AFTER rc=$?\n' run -c/file/stdin, rd+combinator: bash rc=0 out='AFTER rc=1\n' (stderr 'command substitution: ... syntax error'); psh rc=0 out='\nAFTER rc=0\n' at base, old tip, and tip identically.

### NIT
Ceremony leftovers standing from round 1, confirmed still true at 025a6a27: (a) FLIP-PINS.md rows not closed in-branch (file untouched by the diff; ledger records the integrator-owned-at-ceremony ruling, consistent with the brief's 2026-07-30 amendment) — the 4 rows plus the test_divergence_eval_source_procsub_joined_i3 location correction are owed at ceremony; (b) the four renamed flip-pin test symbols' surviving references live only in integrator-owned committed campaign records (close report, integrator plan, LEDGER.md, FLIP-PINS.md, 2.2/2.3 rescue ledgers) and need the ceremony strike-through per 2.3 precedent.

EVIDENCE:
git diff --name-only 1b271d77..025a6a27 contains no docs/reviews/ path (FLIP-PINS.md untouched); round-1 issue list in /Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/VERIFY-ROUND1-issues.md enumerates the exact surviving reference lines, unchanged since.

### NIT
Accounting caveat, for the record: the +30 per-commit test deltas (+13 a76e93f0, +1 49a80738, +1 ca1377b7, +15 3905ad72, +0 025a6a27), the 1,506-row golden composition at both ends, ruff clean, and mypy 274 files were independently reproduced; the absolute gate totals (21,015 -> 21,045, skips 1,590, xfails 10) and compare-bash 2,986/26 are taken from the dev's transcripts (tmp/gate-4.txt, tmp/compare-bash-2.txt) — I did not run the full gate or compare-bash (heavy-run rule; the deltas and the 302-passed conformance-file run make the totals arithmetically consistent).

EVIDENCE:
pytest --collect-only -q on the changed test files at each commit pair: 249->262, 165->166, 23->24, 263->278, no test files in 025a6a27; git show <sha>:tests/behavioral/golden_cases.yaml | grep -c '^- name:' = 1506 at 1b271d77 and 025a6a27; ruff 'All checks passed!'; mypy 'Success: no issues found in 274 source files' at tip.

## Task verdict: FAIL

### BLOCKER
UNCAUGHT SubstitutionSyntaxAbort escapes to the Python top level when the abort is raised from an EXIT-TRAP ACTION: psh prints a full Python traceback and exits 1 where bash and the base both exit 0. `psh/scripting/source_processor.py#execute_as_main` consumes the outcome in a try/except but then calls `self.shell.trap_manager.execute_exit_trap()` OUTSIDE that try, so an abort raised while the EXIT trap's own action string is parsed is unguarded. The same gap exists at the fork boundary: `executor/child_policy.py#run_child_body` wraps `execute_exit_trap()` in `except SystemExit` / `except Exception`, neither of which catches a BaseException. Consequences: (1) an internal-defect traceback on a shape bash handles cleanly; (2) an explicit `exit 3` status is CLOBBERED by the abort status; (3) forked children change exit status. All are behavior changes vs base AND divergences from bash, none declared in the slot ledger (which discusses only 'the EXIT trap runs and OBSERVES the abort status', never an EXIT trap that CONTAINS the error), and none pinned — `grep -rn "trap.*EXIT.*[$](fi)|[$](if)" tests/` returns zero hits, so the green gate is blind to it.

EVIDENCE:
REPLAYED one-case-per-invocation, PATH bash /opt/homebrew/bin/bash 5.2.26, detached discriminator-verified worktrees at base 1b271d77 and tip 025a6a27 (psh.__file__ under each tree, __version__ 0.758.0 both). Script: `trap 'echo T; echo $(fi); echo T2' EXIT; echo B`
  -c    : bash rc=0 out='B\n' | base rc=0 out='B\n' | tip rc=1 out='B\n' + TRACEBACK
  file  : bash rc=0            | base rc=0            | tip rc=1 + TRACEBACK
  stdin : bash rc=0            | base rc=0            | tip rc=1 + TRACEBACK
Identical with the $(if) error kind, and with `eval "echo \$(fi)"` inside the action.
Tip stderr tail:
  File ".../psh/scripting/source_processor.py", line 229, in _run_from_source
    self._substitution_syntax_abort(
  File ".../psh/scripting/source_processor.py", line 322, in _substitution_syntax_abort
    raise SubstitutionSyntaxAbort(nested=nested)
  psh.core.exceptions.SubstitutionSyntaxAbort
bash stderr for the same row: "exit trap: line 1: syntax error near unexpected token `fi'" then rc 0.

STATUS CLOBBER (no traceback — this one IS caught, by the new except): `trap 'echo T; echo $(fi)' EXIT; echo B; exit 3`
  -c    : bash rc=3 | base rc=3 | tip rc=127
  stdin : bash rc=3 | base rc=3 | tip rc=1

FORKED CHILDREN whose EXIT trap carries the error (-c channel):
  ( trap 'echo CT; echo $(fi)' EXIT; echo IN ); echo AFTER rc=$?   bash 'AFTER rc=0' | base 'AFTER rc=0' | tip 'AFTER rc=1'
  x=$( trap 'echo $(fi)' EXIT; echo IN ); echo AFTER rc=$? x=$x    bash 'AFTER rc=0 x=IN' | base 'AFTER rc=0 x=IN' | tip 'AFTER rc=127 x=IN' (file channel: tip 2)
Full rows: tmp/verify-2-4/b5.txt.

### BLOCKER
The branch ships FALSIFIED doc statements in its own two flip-pin conformance files — the same class round 1 bounced, and the ledger's round-2 'BLOCKER 2 — falsified docs, all fixed' table is incomplete: it covers psh/ docstrings and the four subsystem CLAUDE.md files but misses four statements in tests/. Each of the two files now self-contradicts itself: the module header says the divergence is still open while a function docstring 150–350 lines below says the same divergence is CLOSED by slot 2.4. A reader (and the next slot) landing on the header is told the fix has not happened.

EVIDENCE:
All four verified false against tip 025a6a27 (replayed, see tmp/verify-2-4/b1.txt / b3.txt: psh -c 'echo $(if)' -> 127 both parsers; psh -c "echo B; eval 'echo \$(fi)'; echo AFTER" -> rc 127, AFTER absent):
1) tests/conformance/bash/test_nested_substitution_timing_conformance.py:25-27 (module docstring) — "The exit-CODE divergence (bash 127 vs psh's uniform 2 in string channels) and the heredoc-body case remain documented divergences at the bottom (the 127 mapping is I3's job...)" — contradicted by the same file's line 374 "CLOSED S3->I3 divergence".
2) same file:511, in the LIVE docstring of test_param_expansion_word_cmdsub_now_rejects_at_read_time — "(rc differs: bash 127 in -c, psh's uniform 2 — see the 127 family pin above.)" Replay of that exact shape: `x=set; echo ${x:-$(fi)}` -c -> bash 127 / tip 127 (base 2).
3) tests/conformance/bash/test_syntax_template_timing_conformance.py:17-18 — "The exact code differs (bash 127 in string channels, psh's uniform 2); that is a documented divergence owned by I3, not asserted here."
4) same file:22-24 — "eval/source FATALITY (bash aborts the enclosing frame on a substitution-body error; psh continues) is a separate pre-existing divergence carried to I3 and is pinned as a divergence at the bottom, not in the match matrix." — contradicted by line 184 "---- CLOSED (slot 2.4): eval/source frame fatality" in the same file.
Instrument: `grep -rn "uniform 2|owned by I3|carried to I3|psh continues|I3's job" tests/ --include=*.py`.

### NIT
Same doc-drift family, in a file the branch did NOT touch (so lower severity, but it now teaches a superseded fact): tests/unit/tooling/test_syntax_template_guards.py still calls the producer contract inert, directly contradicting the branch's own psh/parser/CLAUDE.md edit ('it is no longer inert').

EVIDENCE:
tests/unit/tooling/test_syntax_template_guards.py:199 `assert isinstance(exc.value, ParseError)  # behaviorally inert: still a ParseError`; :203 docstring "A NON-substitution syntax error stays untagged (the flag is inert)."

### NIT
Golden co-flip deviates from the brief's literal 'update its exit_code (AND ONLY THAT — the stdout/stderr fields stay)': the dev also rewrote the 12-line YAML comment block above the row. The DATA fields are correct — exit_code 2 -> 127, stdout/stderr byte-identical — and the new comment is accurate, so this is a process note, not a defect.

EVIDENCE:
git diff origin/main...fix/remediation-2-4 -- tests/behavioral/golden_cases.yaml: 10 comment lines replaced plus `exit_code: 2` -> `exit_code: 127`. Replayed the row's psh side at base vs tip: stderr byte-identical ('psh: -c:3: Parse error (line 3, column 3): syntax error: unexpected end of file...'), stdout '' both, rc 2 -> 127 (tmp/verify-2-4/b3.txt).

### NIT
FLIP-PINS.md rows are not closed in-branch, deviating from the brief's literal 'flip to equality IN-SLOT and close the row'. The slot ledger records this as deliberate per an integrator ruling (the file is integrator-owned at ceremony), consistent with the brief's own 2026-07-30 amendment ('FLIP-PINS row correction owed at ceremony'). Also still owed at ceremony: the location correction (test_divergence_eval_source_procsub_joined_i3 lives in test_syntax_template_timing_conformance.py, not test_subscript_keying_conformance.py) and the four renamed symbols, which survive only in integrator-owned campaign records.

EVIDENCE:
git diff --name-only origin/main...fix/remediation-2-4 contains no docs/ path at all (0 hits). Ledger line: 'FLIP-PINS.md deliberately NOT edited — integrator-owned per ruling.' All four owned flip obligations ARE otherwise discharged and green: targeted run of the two flip-pin files + test_subscript_keying_conformance.py + test_cv_carry_characterization.py + tests/unit/{parser,scripting,tooling,executor} + tests/integration/parser at tip 025a6a27 -> 2936 passed, 0 failed (tmp/verify-2-4/targeted.txt). `ruff check psh tests tools` at tip -> All checks passed.

### NIT
The declared O3 trap-action divergence (file/stdin: bash 2 vs psh 1) is WIDER than its pin's corpus: test_substitution_fatality_from_a_trap_action exercises only a USR1 action. DEBUG, ERR and RETURN actions carrying the same error show the identical face and are unpinned, so a future change could move three of the four faces silently.

EVIDENCE:
Replayed at tip 025a6a27 vs bash 5.2.26 (tmp/verify-2-4/b5.txt), file channel, action string `echo $(fi)`:
  DEBUG  trap: bash rc=2 out='' | tip rc=1 out=''
  ERR    trap: bash rc=2 out='B\n' | tip rc=1 out='B\n'
  RETURN trap: bash rc=2 out='B\nIN\n' | tip rc=1 out='B\nIN\n'
  USR1   trap (the pinned one): bash rc=2 | tip rc=1
-c channel agrees at 127 for all four.

### NIT
Two PRE-EXISTING divergences in this family (base == tip, byte-identical, so NOT introduced by the branch and out of the slot charter) are absent from the ledger's successor list (which records S1 and S2 only). Recommend recording them as successor rows while the family is fresh.

EVIDENCE:
Replayed base 1b271d77 vs tip 025a6a27 vs bash 5.2.26:
(a) `psh -i script.sh` where the script has `echo $(fi)` (or `$(if)`): bash rc=0 out='B\nAFTER\n' | base rc=2 out='B\n' | tip rc=2 out='B\n' — psh stops the -i script run where bash continues (tmp/verify-2-4/b2.txt).
(b) A brace group in a pipeline never runs its EXIT trap in psh: `{ trap 'echo CT rc=$? >&2' EXIT; eval 'echo $(if)'; } | cat` -> bash prints 'CT rc=257', base and tip print nothing (tmp/verify-2-4/b4.txt).

### NIT
CLEAN CHECKS, recorded so the integrator need not re-derive them. (a) psh/version.py, CHANGELOG.md, README.md, ARCHITECTURE.md untouched. (d) No plan-§3 never-touch file appears in the diff, and the parallel v0.759.0 file is untouched. Interactive REPL parity is PRESERVED (the brief's bounce condition does not trigger). Both parsers agree on every non-interactive row. Fork containment matches bash across every fork path. Scope: the implementation lives in psh/scripting/ + psh/core/ + psh/executor/, which the ledger records as granted by integrator ruling O1.

EVIDENCE:
Diff is 15 files: 4 subsystem CLAUDE.md, psh/core/{__init__,exceptions,internal_errors}.py, psh/executor/child_policy.py, psh/parser/recursive_descent/helpers.py (DOCSTRING-ONLY — verified by stripping comment/blank lines from the hunk), psh/scripting/source_processor.py, 3 test files, golden_cases.yaml. Forbidden-name filter over `git diff --name-only origin/main...fix/remediation-2-4` -> empty.
PTY probe (tmp/verify-2-4/pty.txt), 6 scenarios x {bash, base, tip} x {rd, combinator}: SURV42 marker present in EVERY psh run at base AND tip (direct/eval/source x both error kinds) — the REPL never dies.
Both parsers at tip, -c channel: all 6 flip-pin spellings plus the $(fi) twins give rd == combinator == bash == 127 (tmp/verify-2-4/b3.txt).
Fork containment vs bash, both error kinds, all channels: subshell, cmdsub, backtick, pipeline member, background job, procsub — child dies 1, parent continues, child EXIT trap sees 1 (tmp/verify-2-4/b4.txt).
MUST-NOT-FLIP replayed independently: heredoc-body cmdsub and alias-local-to-cmdsub-body are byte-identical at base and tip (b1.txt), and test_subscript_keying_conformance.py's 9 declared 'I3/s2 frame fatality' cmdsub_if cells are still divergent (targeted.txt, 0 failures).
Ordinary (non-substitution) syntax errors unchanged: `if`, `echo )`, `for`, `case`, `while do`, `fi` -> 2 at bash, base and tip.

