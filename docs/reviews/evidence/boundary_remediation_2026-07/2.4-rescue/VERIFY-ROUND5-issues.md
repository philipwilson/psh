# Slot 2.4 verification round 5 — full issue list (overall: BOUNCE)

## Task verdict: PASS-WITH-NITS

### NIT
Flip-pin obligations were discharged by RENAMING the divergence tests rather than converting them in place, so the governing inventories now name pin IDs that no longer exist in the tree. This is NOT a code-level dangling reference (the only survivors are under docs/reviews/**, which is integrator-owned and which the branch is correctly forbidden to touch), but the ceremony edit must record the rename mapping or the FLIP-PINS/LEDGER rows become unverifiable mechanically.

EVIDENCE:
git grep of the 4 old names in fix/remediation-2-4 -- psh/ tests/ docs/ tools/ returns hits ONLY in docs/reviews/**: FLIP-PINS.md:13 and :16, LEDGER.md:29 and :161, boundary_remediation_integrator_plan_2026-07-21.md:77, boundary_campaign_close_2026-07.md:179,249, plus the 2.2/2.3 rescue slot-ledgers. Zero hits in psh/, tests/, tools/. Rename mapping verified by collect-only in the branch worktree: test_divergence_c_mode_exit_code_is_127_in_bash -> test_c_mode_exit_code_is_127_like_bash (all 6 params preserved: 'echo $(if)', 'cat <(if)', 'x=set; echo ${x:-$(if)}', 'echo $(( $(if) + 1 ))', 'a=(1 2); echo ${a[$(if)]}', 'a[$(if)]=v'); test_divergence_eval_source_fatality_is_i3 -> test_eval_source_frame_fatality_matches_bash; test_divergence_eval_source_procsub_joined_i3 -> test_eval_source_procsub_joined_family_matches_bash; test_taxonomy_tuple_is_the_five_families -> test_taxonomy_tuple_is_the_six_families. Separately, the FLIP-PINS.md:16 row still names the WRONG FILE (test_subscript_keying_conformance.py) for the procsub co-flip — already ruled integrator fault in the brief's 2026-07-30 amendment, still open at ceremony. Must-NOT-flip rows test_divergence_alias_local_to_cmdsub_body and test_divergence_heredoc_body_cmdsub_stays_runtime both still exist under their original names and are green (285 passed across both conformance files).

### NIT
Stale arity in a new docstring cross-reference: map_child_exception's docstring cites the policy helper as substitution_child_abort_status(state), but the function it actually calls takes two arguments.

EVIDENCE:
git show fix/remediation-2-4:psh/executor/child_policy.py -> line 86: '      shell process) -> ``substitution_child_abort_status(state)``.' vs line 113: '        return substitution_child_abort_status(state, exc.errexit_suppressed)'. Definition in psh/core/internal_errors.py is 'def substitution_child_abort_status(state: \'ShellState\', errexit_suppressed: bool) -> int:'. Doc-only; test_doc_snippets.py passes (65 passed).

### NIT
psh's noexec spelling `-n` flipped 2 -> 127 in the -c channel (matching bash), but no pin in the branch covers the `-n` spelling, and psh's other static-check spelling `--validate` stayed at 2 — so the two now disagree with each other on the same input. Within the chartered -c channel and bash-correct, so not a bounce, but the integrator may want a pin row.

EVIDENCE:
Replayed both sides. BASE 1b271d77 (throwaway worktree, removed): `python -m psh -n -c 'echo $(if)'` rc=2; `'echo $(fi)'` rc=2. TIP 5121ec8b: both rc=127. bash 5.2.26 (/opt/homebrew/bin/bash, PATH bash): `bash -n -c 'echo $(if)'` rc=127, `'echo $(fi)'` rc=127 — tip matches, base did not. Control: plain `if` is rc=2 in all three. File channel agrees everywhere (psh -n file rc=2, bash -n file rc=2). psh -n is a genuine noexec (`psh -n -c 'echo hi'` prints nothing, rc 0, same as bash). --validate replayed at BOTH commits: base rc=2, tip rc=2 (unchanged). git grep for -n/noexec in the slot's three test files finds only test_syntax_template_timing_conformance.py:69 `flag = "--validate" if is_psh else "-n"` — i.e. the suite exercises --validate as psh's analogue of bash -n, and never psh -n itself.

### NIT
Pre-existing, NOT a branch defect — recorded only because the brief makes interactive parity a guard rail and I replayed it: psh's REPL enters line-continuation on `echo $(if)` where bash 5.2.26 reports a syntax error and returns to the prompt. Base and tip are byte-identical, so the chartered guard (a REPL that dies on `echo $(if)` is a bounce) is satisfied.

EVIDENCE:
PTY driver (pty.fork, PS1='P$ ', TERM=dumb) run against BOTH commits. TIP 5121ec8b `echo $(if)`: 'P$ ...echo $(if)\r\n> \r...echo ALIVE\r\n> \r...exit 0\r\n> ' (continuation, session alive). BASE 1b271d77 `echo $(if)`: identical byte-for-byte. bash: 'P$ echo $(if)\r\nbash: syntax error near unexpected token `)\'\r\nbash: syntax error\r\nP$ echo ALIVE\r\nALIVE\r\nP$ exit 0'. Complete-but-invalid body `echo $(fi)` is at parity in all three: psh tip and base both print the Parse error then run ALIVE; bash prints its syntax error then runs ALIVE.

## Task verdict: FAIL

### BLOCKER
Round-5 obligation R5-F(2) (the PTY fork-x-errexit row) was silently dropped: the dev ledger's own STILL-OPEN list (/Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/2.4.md ~lines 1140-1144) records it as open pending the R5-A outcome; R5-A was subsequently granted and implemented (commit 5121ec8b), making its expected values determinate, but no PTY-based pin exists anywhere on the branch, the item appears in no discharge-audit row, and the ledger never records it as delivered, deferred, or relieved by ruling before the final tip was declared. In a slot that was bounced in round 5 specifically for unverified checklist ticks, an integrator-round obligation left undischarged and unaddressed at final declaration is bounce-grade. (Caveat for the integrator: if the round-4 bounce message or the R5-A GO relieved this row, that relief exists only in the message thread, not the durable record - the ledger must say so either way.)

EVIDENCE:
Ledger: 'STILL OPEN at this checkpoint (not claimed as discharged): ... R5-F(2)'s PTY fork×errexit row (its expected values depend on the R5-A outcome)' - no later mention (grep 'R5-F' hits lines 1087, 1137-1138, 1141-1143, 1151 only). grep -rn 'pty|PTY|pexpect' over all 4 changed test files -> no hits; branch diff (git diff --name-only 1b271d77..fix/remediation-2-4) contains only those 4 test files + golden_cases.yaml, so no PTY test can exist elsewhere; tmp/r24-probes/ has only round-1/2 interactive probes (interactive.py, interactive_strict.py, interactive_strict_base.py), no round-5 fork×errexit PTY probe; discharge_audit.sh has no R5-F(2) row (10 rows, all other items). Neither 54001334 nor 5121ec8b commit message mentions R5-F(2).

### NIT
R5-E's 'remaining docstring qualifications' (also on the ledger's STILL-OPEN list) were actually delivered, but the closure is recorded only in commit 5121ec8b's message ('Also fixes the two R5-E docstrings that this round's own work falsified'), not in the ledger narrative, and the discharge audit carries only the R5-E unit-arm row. The durable record the harness audits is the ledger; the integrator should have the dev add a one-line R5-E closure (or fold it into the audit) at ceremony.

EVIDENCE:
git log -1 --format=%B 5121ec8b names the two R5-E docstring fixes; grep 'R5-E' in 2.4.md hits only the audit's unit-arm row (line 1137) and the STILL-OPEN entry (line 1142); no closure sentence exists after the R5-A IMPLEMENTED section.

### NIT
The FLIP-PINS obligation header's 'unit-level twins too' sweep (any tests/unit/** twin asserting the psh-divergent result) is never explicitly recorded in the ledger as a census. It is empirically discharged - the full gate is green at tip, and I swept the unit tree myself: only 3 unit files reference the divergent spellings (test_syntax_template_guards.py, test_syntax_templates.py, test_subscript_evaluator.py), none asserts an exit code (grep for '127|exit_code|returncode' empty in the untouched two), and all 178 tests pass - but the ledger should state the sweep so the record matches the obligation.

EVIDENCE:
grep -rln 'echo \$(if)|\$(fi)|<(if)' tests/unit/ -> 3 files; grep -n '127|exit_code|returncode' on the two untouched files -> no hits; pytest of all 3 files -> 178 passed. Ledger's pin-obligations sections never mention a tests/unit twin sweep (round 3's tests/ sweep was for falsified DOCS, a different universe).

## Task verdict: FAIL

### BLOCKER
Former Family B NOT fixed at the declared tip for the `( ... ) &` background-subshell spelling: a background SUBSHELL fork inside a suppressing context still exits 2 where bash (and the integrator's round-5 requirement '-> 1, the former Family B') says 1. The stamp reads the child executor context's suppression counter, but Shell.for_subshell builds a fresh shell whose _errexit_suppress_seed is 0 and _execute_background_subshell (psh/executor/subshell.py:243-291) never seeds it — so the round-5 docstring absolute in psh/core/exceptions.py ('The context's counter is already the TOTAL depth — seeded from the fork site') is falsified on this path, and the ledger's claim that 'R5-B is now structurally impossible' (2.4.md:1150-1152) is false: the bg-subshell path still effectively passes 0 unconditionally, just via the seed instead of the argument. The brace-group spelling `{ ...; } &` DOES give 1 (it reuses the forked parent executor). Base-identical (not a regression), but the bounced round-4 blocker is claimed discharged structurally without the exact bounced rows (round-4 N5b/N5c) ever being re-probed — no background-under-suppression row exists anywhere in the branch's suite (grep confirms), and the round-5 matrices (in-child 90, main-shell 144) contain no background arm.

EVIDENCE:
Replayed at 5121ec8b, both parsers, c+file channels, one case per invocation: `set -e; { ( eval 'echo $(if)' ) & wait $!; } || echo GOT rc=$?` -> bash 'GOT rc=1' / tip 'GOT rc=2' / base 'GOT rc=2'; `set -e; if ( eval 'echo $(if)' ) & wait $!; then echo T; else echo GOT rc=$?; fi` -> bash 1 / tip 2. Brace control: `set -e; { { eval 'echo $(if)'; } & wait $!; } || echo GOT rc=$?` -> bash 1 == tip 1. Unsuppressed bg control: `set -e; ( eval 'echo $(if)' ) & wait $!` -> 2 == 2. Structural: grep _errexit_suppress_seed over psh/ shows only shell.py:254 (init 0), shell.py:671 (executor seeding), child_policy.py:394 (run_child_body only — the bg-subshell path bypasses it).

### BLOCKER
FRESH REGRESSION introduced by the stamp commit, and a false ledger claim covering it: a suppressed FINAL pipeline member now exits 1 where bash, base AND round-4 tip all give 2. The launcher-leaf child inherits the parent's suppression depth by fork-copy, so the stamp reads True where bash gives pipeline members an unsuppressed context (round 4's default-False parameter matched bash; deleting the parameter regressed it). Unpinned, undeclared, away from bash — and the ledger's 'Condition 1 — launcher leaf: UNCHANGED. Re-probed bare-errexit, suppressed, non-final and final pipeline-member shapes: 24 rows, all match' (2.4.md:1154-1156) is falsified by this exact shape (suppressed x final member), which its 24 rows either missed or were not re-run at the final tip.

EVIDENCE:
Full red-claim chain, both parsers, c+file channels: `set -e\n{ true | eval 'echo $(if)'; } || echo GOT rc=$?` -> bash 'GOT rc=2' / base(1b271d77) 'GOT rc=2' / r4(f0cc466e) 'GOT rc=2' / tip(5121ec8b) 'GOT rc=1'. Controls at tip all match bash: non-final member suppressed (`{ eval Q | cat; } || ...` rc 0==0), final member unsuppressed under set -e (2==2), subshell-as-member suppressed (GOT rc=1==1), no-errexit member rows, both-sides row. No pin in the branch covers the suppressed-final-member shape (the 285-test conformance surface is green at tip with the regression present).

### BLOCKER
R5-F(2) PTY coverage claim does not reproduce, and a round-5-added absolute is falsified by the tree. The dev's claim that PTY fork x errexit coverage 'falls out of the in-child matrix' is false: at a real PTY, `( set -e; eval 'echo $(if)' ) || echo SUPPRC=$?` prints SUPPRC=1 in interactive bash but SUPPRC=2 in psh at tip (both parsers; base-identical; REPL survives, no traceback, exit 0) — the in-child matrix ran only c/file channels where psh now gives 1, so the interactive family diverges from both bash and psh's own non-interactive answer. The ledger lists R5-F(2) as 'STILL OPEN' (2.4.md:1143) and never discharges it — no PTY probe, no PTY pin, no declaration. Additionally the same fact falsifies the round-5-added docstring absolute in test_interactive_dash_c_channel_disposition ('Only the status differs, and only on the direct shape'): within its own -i -c channel, the fork x errexit shape ALSO differs (bash -i -c 'SUPPRC=1' vs psh -i -c 'SUPPRC=2', replayed, base-identical) — per the round-5 focus, a new absolute falsified by the tree is a blocker.

EVIDENCE:
PTY probe (pty.fork, TERM=dumb, --norc -i), tip both parsers + base + live interactive bash 5.2.26: bash SUPPRC=1 / psh-tip-rd SUPPRC=2 / psh-tip-comb SUPPRC=2 / psh-base SUPPRC=2; ALIVE printed after, EXIT clean, no Traceback. Non-PTY -i -c replay of the same row: bash -i -c rc=0 'SUPPRC=1\nAFTER\n' vs psh tip 'SUPPRC=2\nAFTER\n' (base identical). Ledger grep: 'R5-F(2)' appears only in the STILL-OPEN list at 2.4.md:1143; the discharge-audit table carries only R5-F1.

### BLOCKER
Ledger-integrity recurrence inside a struck-and-corrected item: the R5-C(4) per-commit accounting table claims it was 'redone from pytest --collect-only deltas per commit rather than from memory', but the two round-5 rows do not replay under that instrument — 54001334 is +11 (posix-fork pin +1, -i -c pin +1, guards file +8, unit arm +1), and 5121ec8b is +0 (the flip is a rename, net zero; its test_child_policy edit modifies the existing unit arm), where the table says +10 and +1. The +47 TOTAL is correct (293 -> 340 over the five touched test files, reconciling 21,015 -> 21,062). A correction that claims an instrument it demonstrably did not use is the exact false-record class (unverified checklist tick) round 5 was convened to purge, recurring in the correction itself.

EVIDENCE:
pytest --collect-only -q over the five touched test files at each commit (guards file absent at base/f0cc466e): base 1b271d77 = 293; f0cc466e = 329 (matches round-4 verifier's chain); 54001334 = 340; 5121ec8b = 340. Commit attribution: git show 54001334 --stat includes test_substitution_abort_guards.py (new, 8 collected tests) and '+def test_substitution_syntax_abort_errexit_suppressed_arm' in test_child_policy.py; git show 5121ec8b -- tests/ adds only the renamed 'def test_main_shell_suppressed_errexit_status_matches_bash'. Ledger table at 2.4.md:1201-1213: '54001334 ... +10', '5121ec8b ... +1'.

### BLOCKER
Checkpoint-open item silently dropped: the ledger's own 'STILL OPEN at this checkpoint' list (2.4.md:1140-1144) names 'R5-E's remaining docstring qualifications' and it is never discharged — and the tree confirms the leftover: the round-4-bounce-flagged falsified absolute in test_substitution_fatality_is_contained_by_forks ('the child dies with 1 and the parent runs on — in every channel', conformance file ~:297) survives byte-identical at 5121ec8b and remains falsified by the tree (with effective errexit the child dies with 2 — replayed, == bash), as does the 'Flat 1 in every channel' comment at test_child_policy.py:73. NOTE for grading: the two docstrings falsified in psh/ (exceptions.py fork bullet, internal_errors.py errexit bullet) WERE properly fixed in the round-5 diff — if the integrator's 'two round-5-falsified docstrings' ruling meant only that pair, this finding downgrades to the dropped-open-ledger-item plus a surviving twice-flagged falsified absolute; either way the ledger never records the R5-E qualification item as discharged.

EVIDENCE:
Tip text: 'A FORK contains the fatality ...: the child dies with 1 and the parent runs on — in every channel, including -c ...' — unchanged from f0cc466e (git diff f0cc466e..5121ec8b touches that file only in the O3/fork-pin/flip areas; grep '^[+-].*dies with 1' over the round-5 diff: no hits). Falsifying row replayed at tip: `( set -e; eval 'echo $(if)' ); echo AFTER rc=$?` -> 'AFTER rc=2' == bash, both parsers, c+file. test_child_policy.py:73 still reads 'Flat 1 in every channel'. Ledger: 'R5-E's remaining docstring qualifications' in the STILL-OPEN list; no later section or audit row discharges it (discharge audit has only 'R5-E errexit_suppressed unit arm').

### NIT
The R5-D triad guards exist, run, and BITE on the canonical shapes (verified by inserting a real three-shape offender file under psh/ in a scratch worktree: all three guards went RED; restored clean), but two evasion shapes slip through: (a) guard 1's raise detector handles only bare-Name calls, so `raise exceptions.SubstitutionSyntaxAbort(...)` (attribute-qualified, e.g. to dodge an import cycle) is invisible — asymmetric with the catch detector, which does handle ast.Attribute; (b) guard 3's re-derivation regex is single-line, so the most natural real-world offender — `if isinstance(e, SubstitutionSyntaxAbort):` newline `return 127` — evades it (verified: both evader shapes inserted into psh/ leave the guards green).

EVIDENCE:
Scratch experiment at tip worktree: psh/offender_probe.py (bare raise + except + one-line rederive) -> 3 failed; psh/offender_evade.py (attribute-qualified raise + two-line rederive) -> 2 passed (guards blind); worktree restored, git status clean both times.

### NIT
Unpinned base-identical divergence in the fork x EXIT-teardown x errexit corner, adjacent to the round-4 teardown NIT: `( set -e; trap 'echo $(fi)' EXIT; echo IN ); echo AFTER rc=$?` gives bash 'IN/AFTER rc=2' vs psh 'IN/AFTER rc=0' at base, r4 and tip alike (the teardown swallow keeps the child's 0 where bash's errexit makes the child exit 2). Not a slot regression (unchanged across the branch) and the declared teardown/O4 divergences do not cover it — successor-queue material alongside round 4's main-shell errexit x teardown row (bash 2 / psh 1).

EVIDENCE:
Chain replay, c+file channels: bash rc=0 'IN\nAFTER rc=2\n' / base 'IN\nAFTER rc=0\n' / r4 same / tip same (both parsers). The pinned composition row (`( set -e; set -T; trap 'echo $(fi)' DEBUG; echo IN )` -> both 'AFTER rc=2') and the declared O3 fork 2-vs-1 row were replayed intact at tip.

### NIT
Two minor robustness gaps in the new consumer plumbing: (a) SourceProcessor._errexit_suppressed reads `getattr(self.shell, '_current_executor', None)` — house style in that file (5 pre-existing identical reads) but the same rename-degrades-silently shape the round-4 NIT flagged, and the docstring's 'explicit rather than a getattr default' sentence is true only of the `context` attribute; (b) no dedicated unit test exercises the no-executor path or the missing-context-attr-raises claim — the executor-is-None arm is covered only end-to-end by the -c flip pins / reader-parse rows (which I replayed green: direct `echo $(fi)` / `cat <(if)` / `set -e; echo $(fi)` -> -c 127, file 2, stdin 2, all == bash, both parsers).

EVIDENCE:
psh/scripting/source_processor.py:354 getattr read vs psh/shell.py:248 unconditional `self._current_executor: Optional[...] = None`; grep tests/ for _errexit_suppressed -> only the stamp-arm unit test (constructs the exception directly) and no no-executor/missing-context test.

### NIT
Record of verified-clean items (all replayed by me at 5121ec8b): in-child suppression family FIXED and red-on-base (||, if, while, until, !, && non-final, procsub spelling, cmdsub twin -> child 1 == bash; base continued 0); errexit-in-child unsuppressed 2==2; fork-site suppression 1==1; main-shell suppressed family flipped correctly (-c 127 / file 1 / stdin 1 == bash; RED at base — replayed: posix-fork pin and flipped pin FAIL at 1b271d77, -i -c disposition pin green at base as an integrator-ordered declaration pin); nested/combined shapes match (seed+in-child depth-2, cmdsub-in-if-cond, cmdsub-in-while-cond, nested subshell ||); structural stamp claims hold (map_child_exception(exc, state) has no errexit parameter, the background-site getattr re-derivation is deleted, both consumers read exc.errexit_suppressed, no consumer re-derives); discharge audit 10/10 replayed in MY worktree with 3 rows deep-verified (O3 docstring genuinely edited vs the round-3-quoted text with the honest 'it had not' record; posix-fork pin exists/runs/red-on-base; strike-and-correct history preserved inside the flipped pin); 285 passed across the two conformance files (must-not-flip rows, teardown table, S1 pin, item-6, R4-C carried six-form pins, taxonomy included) + 55 passed unit/guards + no-direct-spawn ratchet green with zero allowlist growth (file untouched by the branch); -i -c pin routed through typed runners; golden co-flip row passes at 127 with only exit_code changed; ruff clean; mypy 274 clean; version.py 0.758.0; forbidden files, FLIP-PINS.md, LEDGER.md, plan-§3 never-touch files and test_process_sub_closed_fds.py all absent from the branch diff. Housekeeping: two detached worktrees not mine remain registered (tmp/remv-audit-base @1b271d77, tmp/remv-audit-tip @5121ec8b — likely a concurrent verifier); my three probe worktrees were removed.

EVIDENCE:
All runs at discriminator-verified worktrees (tip /tmp/remv-probe-24r5, base /tmp/remv-base-24r5, r4 /tmp/remv-r4-24r5, since removed), PATH bash 5.2.26(1)-release aarch64; probe scripts and results.json in the session scratchpad (r5battery.py, r5battery2.py, r5pty.py, r5cases/, audit_tip.sh).

## Task verdict: PASS-WITH-NITS

### NIT
Docstring/signature drift in the very text that teaches the mapping: psh/executor/child_policy.py#map_child_exception documents the arm as "SubstitutionSyntaxAbort ... -> substitution_child_abort_status(state)" (one argument), but the function is defined as substitution_child_abort_status(state, errexit_suppressed) and is called with two arguments five lines below. The errexit_suppressed half is the arm's whole subtlety, so the one-arg spelling drops the load-bearing part.

EVIDENCE:
psh/executor/child_policy.py:85-88 (docstring) vs psh/core/internal_errors.py:175 `def substitution_child_abort_status(state: 'ShellState', errexit_suppressed: bool) -> int:` and child_policy.py:112-113 `return substitution_child_abort_status(state, exc.errexit_suppressed)`.

### NIT
Anti-bypass guard 3 is weaker than its docstring claims. tests/unit/tooling/test_substitution_abort_guards.py detects a re-derived status with a SINGLE-LINE regex, so it fires only when the class name and the constant share a source line. The natural offender spread over two lines is invisible to it, and the synthetic offender run against the guard is exactly the one-line form the regex was written for. Relatedly, guard 2 matches `except SubstitutionSyntaxAbort` only by AST Name; a bare `except:` (node.type is None, skipped by _find_catch_sites) or a tuple-constant alias at a non-fork frame would pass unseen. The triad's letter is met (offenders are executed) but the guards would not bite the most plausible real regressions.

EVIDENCE:
_REDERIVE = re.compile(r"SubstitutionSyntaxAbort[^\n]*\b(127|== ?2|== ?1)\b") scanned per line; offender = "    if isinstance(e, SubstitutionSyntaxAbort): return 127\n". The two-line form `if isinstance(e, SubstitutionSyntaxAbort):` / `    return 127` does not match. _find_catch_sites guards on `isinstance(node, ast.ExceptHandler) and node.type is not None`.

### NIT
Gate transcript predates the declared final tip by ~1 minute and carries no SHA, so the ledger heading "Round-5 gates, at declared tip 5121ec8b" is not self-evidencing. I corroborated it independently and it holds; flagging only so the ceremony gate is re-run at the merge SHA rather than relying on my reconstruction.

EVIDENCE:
tmp/gate-10.txt mtime 31 Jul 01:50; commit 5121ec8b author date 2026-07-31 01:51:09. Corroboration: pytest --collect-only at tip = 22,679 vs base 1b271d77 = 22,632 (+47, matching the ledger's +47 per-commit table); gate total 21,062 + 1,590 + 10 = 22,662 = collect - 17, the identical 17-row offset the base figures show (22,632 - 21,015 - 1,590 - 10 = 17).

### NIT
PRE-EXISTING, not this branch: tests/unit/builtins/test_misc_builtins.py::TestEvalBuiltin::test_eval_redirection fails in any checkout whose repo root lacks a tmp/ directory, because it asserts a fixed relative path in the shared cwd. It surfaced in my sweep of a fresh worktree; I replayed both endpoints before reporting. Flagged so a clean-tree gate hit is not misread as a 2.4 regression; it is Wave-1 hygiene territory (parallel-safety rule 2, fixed-name file in the shared cwd).

EVIDENCE:
tests/unit/builtins/test_misc_builtins.py:243 `assert os.path.exists('tmp/evaltest.txt')`. Replay: FAILS at base 1b271d77 AND at tip 5121ec8b when tmp/ is absent (stderr "psh: line 1: tmp/evaltest.txt: No such file or directory"); PASSES at tip immediately after `mkdir -p tmp`.

### NIT
Undeclared embedding-API surface change: Shell.run_command() now lets SubstitutionSyntaxAbort (a BaseException) escape to its caller when state.is_script_mode is True, where the base returned 2. This is correct by design -- it is exactly how the eval builtin propagates, and execute_as_main is the sole sanctioned consumer -- and the suite is unaffected because the shell fixtures run with is_script_mode False. But run_command is psh's public in-process entry point, so the fact that the one non-fork frame which does NOT contain the abort is also the embedding API deserves a sentence in the ledger and the CHANGELOG entry rather than being left implicit.

EVIDENCE:
In-process replay, one Shell per interpreter to avoid the F2 lease error: base 1b271d77 -> `'echo $(fi)' -> rc: 2`, `'echo $(if)' -> rc: 2`; tip 5121ec8b -> `'echo $(fi)' -> RAISED: SubstitutionSyntaxAbort`, `'echo $(if)' -> RAISED: SubstitutionSyntaxAbort`. psh/shell.py:754 run_command calls script_manager.execute_from_source, not execute_as_main.

