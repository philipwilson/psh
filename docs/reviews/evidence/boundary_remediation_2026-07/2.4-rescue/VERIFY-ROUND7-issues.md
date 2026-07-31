# Slot 2.4 verification round 7 — full issue list (overall: BOUNCE, single blocker)

## Task verdict: PASS-WITH-NITS

### NIT
R7-D scope-accounting table ('the three edits outside the brief's named scope') omits psh/shell.py, a fourth file outside the brief's named scope list. The edit is docstring-only (run_command embedding-contract declaration), landed in 0fed0d04 under ruling R6-D, and IS accounted for in the ledger's R6-D prose — only the scope table misses it. Integrator may want the table completed at ceremony.

EVIDENCE:
git diff 1b271d77..fix/remediation-2-4 -- psh/shell.py shows a single 15-line docstring addition to Shell.run_command; git log shows only commit 0fed0d04 (R6-D) touched it; ledger R6-D section names 'the run_command docstring' as one of its two declaration sites but the R7-D 'SCOPE ACCOUNTING' table lists only tests/conftest.py, helpers.py, nested_parse.py.

### NIT
Golden co-flip deviates from the FLIP-PINS/brief instruction 'update its exit_code (AND ONLY THAT)': the row's 12-line explanatory comment block was also rewritten. All YAML DATA fields (command, stdout, stderr, psh_only) are byte-identical; the rewrite was necessary (the old comment described the divergence as open and would have been falsified) and is explicitly declared in the ledger (round-1 pin table + round-3 correction). Recording so the FLIP-PINS row wording can be reconciled at ceremony; not a bounce.

EVIDENCE:
git diff 1b271d77..fix/remediation-2-4 -- tests/behavioral/golden_cases.yaml: exit_code 2->127 plus comment-block rewrite only; stdout/stderr/command unchanged. Row passes in both modes (1 passed, 1 skipped; skip reason 'case marked psh_only' under --compare-bash).

### NIT
Ceremony reminder (already integrator-tallied, confirmed against the tree): the FLIP-PINS.md row for the procsub co-flip still names test_subscript_keying_conformance.py, but the pin lives (and was flipped) in test_syntax_template_timing_conformance.py — the flipped equality pin test_eval_source_procsub_joined_family_matches_bash is at line 579 of that file and no such test exists in the keying file. Brief amendment 2026-07-30 records this as integrator fault with the FLIP-PINS correction owed at ceremony.

EVIDENCE:
grep at tip: tests/conformance/bash/test_syntax_template_timing_conformance.py:579:def test_eval_source_procsub_joined_family_matches_bash; zero hits in test_subscript_keying_conformance.py. FLIP-PINS.md (origin/main) row 16 still cites the keying file.

## Task verdict: PASS-WITH-NITS

### NIT
Three renamed flip-pin test names still appear in LIVE campaign tracking docs, which the branch (correctly) does not touch. Ceremony must rewrite them or the ledger points at names that no longer exist in the tree. Mapping: test_divergence_c_mode_exit_code_is_127_in_bash -> test_c_mode_exit_code_is_127_like_bash (tests/conformance/bash/test_nested_substitution_timing_conformance.py); test_divergence_eval_source_fatality_is_i3 -> test_eval_source_frame_fatality_matches_bash (tests/conformance/bash/test_syntax_template_timing_conformance.py:188); test_divergence_eval_source_procsub_joined_i3 -> test_eval_source_procsub_joined_family_matches_bash (same file, :579). Not a dev fault: the brief assigns FLIP-PINS/LEDGER edits to the integrator at ceremony ('FLIP-PINS row correction owed at ceremony', 'the integrator's LEDGER edit at ceremony'), and the branch touches zero docs/ files.

EVIDENCE:
git grep -n '<old name>' fix/remediation-2-4 hits, docs-only: docs/reviews/evidence/boundary_remediation_2026-07/FLIP-PINS.md:13,15,16; docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md:29,161; docs/reviews/boundary_remediation_integrator_plan_2026-07-21.md:77. Historical-record hits (no action needed): docs/reviews/boundary_campaign_close_2026-07.md:179,249; .../2.2-rescue/INTEGRATOR-INBOX.md:50; .../2.2-rescue/slot-ledger.md:363,496; .../2.3-rescue/slot-ledger.md:654,767. Zero hits under psh/ tests/ tools/ or in any .py/.yaml/.json/.toml file. Replacement names confirmed present: grep -n '^def test_eval_source_frame_fatality_matches_bash|^def test_eval_source_procsub_joined_family_matches_bash' -> 188, 579; and all 292 tests in the two conformance files pass at tip 4ea3df9c.

### NIT
Two new production docstrings in psh/core/internal_errors.py cite the dev's UNCOMMITTED scratch probe paths, which vanish when the slot worktree is reclaimed, leaving a pointer a clean checkout cannot follow. There is in-tree precedent for this style (source_processor.py#_posix_syntax_abort says 'probe tmp/posixexit'), so it is a convention question for the integrator, not a defect: if these batteries are worth citing they should be promoted into the evidence tree at ceremony.

EVIDENCE:
psh/core/internal_errors.py: substitution_abort_status docstring — 'Probe-verified (slot 2.4 batteries under ``tmp/r24-probes/``, PATH bash 5.2.26 ...)'; substitution_child_abort_status docstring — 'Probed per ROUTE (slot 2.4 batteries ``tmp/r24-probes/r7a.py`` and ``r6b*.py``)'. Neither path is tracked on fix/remediation-2-4 (git diff --name-status shows no tmp/ files). Precedent: psh/scripting/source_processor.py#_posix_syntax_abort — 'POSIX-mode fatal SYNTAX error (bash 5.2, probe tmp/posixexit).'

## Task verdict: PASS-WITH-NITS

### NIT
R7-B co-movement pinning is representative, not exhaustive. My base-vs-tip differential over 334 ordinary-errexit shapes x 2 channels found 72 moved rows; `test_ordinary_errexit_co_movements_are_declared` pins 7 of them. The unpinned-but-moved shapes are: pipeline-member suppression sources `&&`-non-final / `!` / `while`-condition; the `command`-prefix and assignment-prefix member spellings; and the background spellings other than `( ) &` — `{ } &`, `a && b &`, `a || b &`, `for…done &`, `while…done &`, `if…fi &` — under `||`, `!` and if-condition suppression. All 72 moved rows land ON bash (0 rows where tip disagrees with bash), and all fall inside the three families the docstring declares, so this is a sampling-width question rather than an undeclared delta. Flagging because the campaign standard is 'an unpinned improvement is still a bounce' and the integrator may want the enumeration in the ledger or a widened sample.

EVIDENCE:
Replayed with /private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/v24audit/hunt_errexit.py (base worktree @1b271d77 vs tip @4ea3df9c vs /opt/homebrew/bin/bash 5.2.26, one subprocess per case, PYTHONPATH+cwd discriminator verified). Example unpinned moved row: `set -e\n{ true | X=1 eval 'false; echo A'; } || echo GOT rc=$?\necho END` -> base=(0,'A\nEND\n') tip=(0,'GOT rc=1\nEND\n') bash=(0,'GOT rc=1\nEND\n'). Example unpinned background row: `set -e\n{ for i in 1; do eval 'false; echo A'; done & } || true` + wait -> base=(0,'child=1\n') tip=(0,'A\nchild=0\n') bash=(0,'A\nchild=0\n'). Post-check across all 72: 0 rows where tip != bash.

### NIT
The new/flipped conformance pins run only the DEFAULT parser. `_psh`/`run_psh` in tests/conformance/bash/test_syntax_template_timing_conformance.py and test_nested_substitution_timing_conformance.py never pass `--parser`, so the ~180 new rows pin recursive-descent only; only the new PTY module parametrizes rd+combinator. The brief's Required-work item 1 asks for BOTH parsers. I ran ~380 independent observations on both parsers and found no rd/combinator divergence, so the risk is low — but the durable pinned record is single-parser.

EVIDENCE:
grep of the helper: `def _psh(script, channel): return _run_channel(run_psh, script, channel, is_psh=True)` with `run_psh(["-c", script], ...)` — no --parser anywhere in either conformance file. Independent both-parser sweeps: hunt_novel.py (46 shapes x 3 channels x rd/combinator = 276 obs, 10 diffs, all pre-existing or the declared O4 row) and the nested-proxy probe (9 shapes x 3 channels x 2 parsers = 54 obs, 0 diffs).

### NIT
Under-qualified doc pointer introduced by the R7-C pointer-fix work. `test_background_fork_severing_matches_bash`'s docstring names the widened-signature caller as ``core.py#_execute_background_list``. The repo has both a `psh/core/` package and `psh/executor/core.py`; the symbol lives in the latter. It resolves, but `executor/core.py#_execute_background_list` would match the campaign's file.py#symbol discipline (and R7-C explicitly called out a dangling pointer in this same area).

EVIDENCE:
tests/conformance/bash/test_syntax_template_timing_conformance.py, docstring of test_background_fork_severing_matches_bash: "a widened signature's other caller (``core.py#_execute_background_list``) still took the default seed". `grep -n _execute_background_list psh/executor/core.py` -> lines 229, 297. No `psh/core.py` exists. (The other R7-C pointer, executor/function.py#FunctionOperationExecutor._function_frame, verified present at function.py:21/197.)

### NIT
tests/conftest.py now admits tests/system/interactive/test_substitution_abort_interactive_pty.py to the default (non --run-interactive) run, and that module resolves the bash oracle at MODULE scope (`_ORACLE = resolve_bash()` at import). Cost measured at 7.48s for 10 params, matching the dev's ~8s claim, and it is @pytest.mark.serial so it lands in the serial phase. Flagging for the integrator's Linux-nightly awareness: the module spawns a real interactive bash through pexpect on every default run, so an oracle-less or PS1-hostile host turns a previously opt-in pin into a collection-time failure.

EVIDENCE:
tests/conftest.py pytest_runtest_setup: `or "test_substitution_abort_interactive_pty" in str(item.fspath)` added to the always-run list. Module head: `pexpect = pytest.importorskip("pexpect")` then `_ORACLE = resolve_bash()` (comment: "a missing oracle must be LOUD at import"). Timed at tip: `10 passed in 7.48s`.

## Task verdict: FAIL

### BLOCKER
FALSE R7-A RECORD CLAIM (dev-flagged weakest claim (i), probed over the space as directed): the ledger's substitution-route domain statement — 'command substitution, backticks and process substitution do NOT sever — bash carries the suppression into them and psh already matched (r7a.py rows c1-c6, MATCH at base and at this tip, including their ordinary-errexit twins)' (2.4.md ~line 1941) — is measured FALSE for REDIRECTION-SPELLED process substitution, read AND write sides. Bash 5.2.26 runs a `< <(...)` / `> >(...)` child with errexit EFFECTIVE in a suppressed context (does NOT carry the suppression), while psh carries it — at base AND tip, both parsers, -c and file channels. The dev's corpus (c4/c5) sampled only the ARGUMENT spelling (`cat <(...)`), which does carry in bash (verified matching). The behavior itself is base-identical (pre-existing, NOT slot-introduced, no chartered flip implicated, no production change required) — the defect is the false route-level universal answering ruling R7-A's direct question ('state what bash does'), plus the same unqualified rule sentence in test_background_fork_severing_matches_bash's docstring ('reaches through a COMPOUND body ... and through nothing else' — the redirect-procsub child body IS compound and bash does not reach through it). Needs strike-and-correct in the ledger, a declared/pinned divergence row or successor row for the redirect-procsub family, and a docstring qualifier.

EVIDENCE:
Probe files od -c verified, one case per invocation, oracle /opt/homebrew/bin/bash = GNU bash 5.2.26(1)-release, tip worktree discriminator /tmp/remv-probe-24r7/psh/__init__.py @4ea3df9c, base /tmp/remv-base-24r7 @1b271d77. READ SIDE u3.sh: 'set -e\nif read -r line < <(false; echo A); then echo got:$line; else echo F:$?; fi\necho END' -> bash 'F:1\nEND' | tip-rd AND tip-combinator 'got:A\nEND' | base 'got:A\nEND' (same split in -c channel and for the eval-spelled body t2.sh, and for the `|| true` context u1.sh/u4.sh). WRITE SIDE w1.sh: 'set -e\nif : > >(false; echo A > wout.txt); then :; fi...' -> bash NOFILE | tip got:A | base got:A. MECHANISM CONTROL: same script without set -e -> bash got:A (so errexit is the operative mechanism). ARGUMENT-SPELLING CONTROLS (dev's c4/c5 corpus, re-run byte-exact): 'set -e\n{ cat <(eval \'false; echo A\'); } || ...' and '{ cat <(false; echo A); } || ...' -> bash A == tip A == base A (the dev's rows genuinely match — the claim fails only outside its corpus, which is what the ledger sentence generalizes over). cmdsub/backtick attack rows S1-S6, S9-S11 (incl. pipeline-inside-cmdsub, nested cmdsub, bg-inside-cmdsub): all MATCH — the falsification is procsub-redirect-specific.

### NIT
Audit composition sub-count in the final ledger is wrong and internally inconsistent — the exact numeric-record class R7-D(3) was correcting. The DISCHARGE AUDIT headline says '80 = 69 chk/nchk + 11 loop-stamped instrument rows + 1 chain-table row' — 69+11+1=81, and the actual script/transcript composition is 60 chk + 8 nchk = 68 chk/nchk + 11 loop-stamped + 1 chain-table stamped = 80. Additionally the R7-D(3) paragraph ('The round-7 script has 70 checks (58 chk/nchk + 11 + 1)') stands uncorrected in the final ledger beside the 80 headline. The TOTAL (80) is correct and the audit itself is genuine: I replayed it in the dev worktree — exit 0, ALL 80 ROWS PASS at 4ea3df9c — and re-proved the header-SHA bite on a doctored instrument copy (row 'instrument r7a ... header does not carry', exit 14). One-line strike-and-correct.

EVIDENCE:
Counted from discharge_audit_r6.sh: grep -cE '^[[:space:]]*chk ' = 60; nchk = 8; stamped loop lists 11 batteries + 1 explicit 'chain table' stamped call. Cross-counted from the dev's own discharge-audit-TIP.txt: 81 '| ' lines = 1 header + 80 rows; ':: SHA' rows = 12; 'absent$' (nchk) = 8; remaining chk = 60. Ledger 2.4.md lines ~2102-2107 ('69 chk/nchk') and ~2029-2033 ('70 checks (58 chk/nchk...').

### NIT
Successor row (e) ('doc-pointer guard cannot see a dangling SYMBOL') duplicates rather than cross-references the SAME successor row already carried by 2.3 — committed LEDGER.md line 162: '(2) #symbol DOC-GUARD GAP: test_doc_pointers validates only the PATH half...' — and a third copy exists in the 1.3b row (LEDGER.md line 133 'doc-pointer guard validates only the PATH half of file#symbol cites'). The integrator asked me to verify (e) cross-references for a MERGE at ceremony; it does not (row (e) mentions neither 2.3 nor 1.3b). The dev was not told about the earlier rows in any inbox ruling, so this is a ceremony-merge note, not a dev fault: three slots have now independently generated the identical tooling successor row — merge to one at ceremony.

EVIDENCE:
2.4.md lines 2133-2142 (row (e), no cross-reference; grep for '2.3' in that region returns nothing); git show origin/main:docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md lines 133 and 162.

### NIT
Guard residual-evasion class exists and is unstated: an ASSIGNMENT alias evades all 15 guards silently. The ruling's named evasion (import alias) is genuinely closed — my live insertion of 'from psh.core.exceptions import SubstitutionSyntaxAbort as SSA' under psh/ tripped 3 guards — and the dev chose the ruling's 'strengthen' branch legitimately. But _local_aliases' docstring claims 'Every local name that REFERS to the abort in this module', which my counterexample falsifies (a fresh universal), and the residual limit is stated neither in the guard docstring (the only KNOWN LIMIT stated is the laundered-status-constant one) nor the ledger. Successor-row / docstring-qualifier material.

EVIDENCE:
Offender inserted at tip worktree psh/expansion/_verifier_evasion2.py: 'from psh.core import exceptions as _exc\n_SSA2 = _exc.SubstitutionSyntaxAbort\ndef sneaky_raise2(): raise _SSA2(nested=True)' -> pytest tests/unit/tooling/test_substitution_abort_guards.py = 15 passed (guard blind). Contrast import-alias offender -> 3 FAILED (test_only_one_raise_site_for_the_abort, test_only_the_sanctioned_non_fork_catchers_exist, test_status_mapping_is_not_re_derived_at_frames). _local_aliases docstring at tests/unit/tooling/test_substitution_abort_guards.py ~line 70; stated KNOWN LIMIT at ~line 224 covers a different detector limit.

### NIT
The context.py ONE-WRITER/ONE-READER invariant comment for errexit_suppress_deferred is letter-stale after round 7's own changes: the same round added two new zeroing writers (command.py#_dispatch_resolved one-shot discard; child_policy.py#run_background_shell_child sever hook) and the comment mentions neither — a reader auditing 'who can zero this field' from the invariant comment misses the one-shot mechanism that is now load-bearing. Defensible in spirit (pipeline.py remains the only NONZERO setter and _function_frame the only value READER; the cross-reference exists in the command.py comment in one direction), but the comment edited by R7-C in the same commit did not absorb the R7-A machinery.

EVIDENCE:
psh/executor/context.py ~lines 50-62 ('ONE WRITER — the pipeline member closure ... ONE READER — executor/function.py#FunctionOperationExecutor._function_frame'); assignment sites at tip: pipeline.py (set), function.py:246-248 (+ restore :310), command.py:783 'context.errexit_suppress_deferred = 0', child_policy.py:317 'sever_errexit_context.errexit_suppress_deferred = 0' (round-7 diff d64a3294..4ea3df9c).

### NIT
Micro-absolute in the R7-B pin docstring: 'Base 1b271d77 differed from bash on every row below; this tip matches' — contradicted by the pin's own two CONTROL rows 30 lines later, which are deliberately the unmoved shapes (base == bash on them, per the round-6 evidence and my replays). The controls section explicitly says 'CONTROLS, unmoved', so no reader is actually misled, but 'every row below' should read 'every MOVED row'. Also for the record: the isolation-leg of the concurrency incident (the '68 passed' figure) has no preserved transcript — only ledger prose; I replayed it at tip (68 passed in 12.58s), so the figure is true.

EVIDENCE:
tests/conformance/bash/test_syntax_template_timing_conformance.py lines 1156 vs 1183-1192; grep -rln '68 passed' over the dev worktree tmp/ hits only the ledger. My replay: pytest tests/conformance/bash/test_reappraisal6_builtin_state_conformance.py tests/conformance/bash/test_trap_signal_spec_conformance.py at 4ea3df9c -> 68 passed.

