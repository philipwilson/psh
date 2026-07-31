# Slot 2.4 verification round 9 — full issue list (overall: BOUNCE, single blocker)

## Task verdict: PASS-WITH-NITS

### NIT
Stale line citations in R9-A's signature-widening census: run_child_shell call sites cited as process_sub.py:76 and :187 are at :79 and :194 at the declared tip 71e83c35 (the citation reflects the pre-round-9 tree the survey inspected). The census substance replays (exactly 3 call sites: command_sub.py:142, process_sub.py:79, :194).

EVIDENCE:
grep -rn 'run_child_shell(' psh/ in /Users/pwilson/src/psh-r2-4 at 71e83c35 -> psh/expansion/command_sub.py:142, psh/io_redirect/process_sub.py:79, psh/io_redirect/process_sub.py:194

### NIT
The cumulative 'Files touched, restated from git diff --name-only' list (R7-D, 22 production + 11 tests) was never restated after round 9 added psh/io_redirect/process_sub.py as a 23rd production file. Not a silent scope expansion — R9-A names the file and R9-D cites its authorization (ADDENDUM 5) — but the list that claims to be 'from git diff, not memory' is now one file stale; integrator should use the 34-file list at ceremony.

EVIDENCE:
git -C /Users/pwilson/src/psh diff --name-only 1b271d77..fix/remediation-2-4 = 34 files (23 psh/ incl. io_redirect/process_sub.py + 11 tests/); ledger R7-D table lists 33

### NIT
The ledger's 'FLIP-PINS.md deliberately NOT edited — integrator-owned per ruling' cites a ruling that does not appear in the INTEGRATOR-INBOX.md dead-drop (grep -i FLIP-PINS -> no hits); the ruling predates the round-6 dead-drop convention and lives only in the message channel. Ownership is independently grounded — the brief itself records the FLIP-PINS row correction as 'owed at ceremony' — so no action needed beyond the integrator confirming the row edits at ceremony.

EVIDENCE:
grep -n -i FLIP-PINS /Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/INTEGRATOR-INBOX.md returns nothing; brief 2.4.md co-flip block: 'FLIP-PINS row correction owed at ceremony. Integrator fault, tallied.'

## Task verdict: PASS-WITH-NITS

### NIT
RESURRECTION HUNT RESULT — NO BLOCKERS. Complete AST-level symbol census of every changed .py (base origin/main=1b271d77 vs tip 71e83c35) found ZERO deleted symbols; every 'removed' line is a signature change or a chartered test rename, and every surviving reference resolves. Full inventory: (A) production signature changes — psh/executor/child_policy.py#map_child_exception(exc) -> (exc, state) [BREAKING arity; all 4 in-tree call sites updated: child_policy.py:329/420/426, process_launcher.py:367 — zero 1-arg calls survive]; run_background_shell_child(shell, body) + keyword-only sever_errexit_context; run_child_shell(...) + errexit_suppress_override; SubshellExecutor._execute_background_subshell(self, statements, redirects) + errexit_suppress=0 [both callers updated: subshell.py:105, core.py:311, both by keyword]; create_process_substitution / _create_write_process_substitution + keyword-only errexit_suppress_override [callers process_sub.py:33/323/345]. (B) test renames — test_divergence_c_mode_exit_code_is_127_in_bash -> test_c_mode_exit_code_is_127_like_bash; test_divergence_eval_source_fatality_is_i3 -> test_eval_source_frame_fatality_matches_bash; test_divergence_eval_source_procsub_joined_i3 -> test_eval_source_procsub_joined_family_matches_bash; TestMapChildException.test_taxonomy_tuple_is_the_five_families -> ..._six_families (zero surviving refs anywhere). No file deletions/renames (git diff --diff-filter=D and -M --name-status both empty). No fixtures/markers/CLI flags removed; conftest.py, PTY_REGISTRY and _EXPECTED_PTY_SITES changes are purely additive; the Q1 ratchet ALLOWLIST ('MAY ONLY SHRINK') is unchanged.

EVIDENCE:
AST symbol-diff script over all 12 changed .py files; git grep of each removed name over psh/ tests/ docs/ tools/ at fix/remediation-2-4; call-site inspection of command_sub.py:142, process_sub.py:79/194, test_child_policy.py:299 confirming error_label is passed by KEYWORD at every site (no positional shift).

### NIT
IMPORT/RUN PROOF (throwaway detached worktree at 71e83c35, created and REMOVED). Discriminator verified: psh.__file__ = <worktree>/psh/__init__.py, and branch-only symbols (SubstitutionSyntaxAbort, substitution_abort_status, substitution_child_abort_status, sync_child_status_for_exit_trap) import with len(CHILD_EXIT_EXCEPTIONS)==6. psh.version.__version__ = 0.758.0 (correctly NOT bumped — version.py is NEVER-TOUCH). `python -m psh -c 'echo ok'` -> ok rc=0; `--parser combinator -c 'echo ok2'` -> ok2 rc=0. Exhaustive import of every module: 273/273 imported, 0 failures. Full pytest collection: 22,722 tests collected, 0 collection errors (strongest dangling-import check). All 19 distinct `file.py#symbol` pointers ADDED by the diff resolve to a real def/class/assignment; tests/unit/tooling/test_doc_pointers.py + test_doc_snippets.py green. Targeted suites green: tests/unit/tooling + unit/executor + unit/scripting + unit/parser = 2,316 passed.

EVIDENCE:
git worktree add --detach <scratch>/remv-wt 71e83c35; pkgutil.walk_packages import sweep; pytest --collect-only -q (22722 collected in 7.56s); pytest tests/unit/{tooling,executor,scripting,parser} -q = 2316 passed; git worktree remove --force (verified absent from `git worktree list`).

### NIT
ROW-NOVELTY DIFFERENTIAL (rows not in the dev's suite) — 11 fresh rows x 2 parsers (rd + combinator), PSH_STRICT_ERRORS=1, one case per invocation, against PATH bash 5.2.26 at /opt/homebrew/bin/bash: ALL 11 MATCH on stdout+stderr+rc. Rows were chosen to drive EVERY changed-signature route: `{ sleep 0; } &`, `( echo sub ) &`, `true && echo x &` (the core.py:311 route the diff comment says was left on the old 2-arg signature), `for i in 1; do ...; done &`, `f &`, `exit 5 & wait`, `echo hi | { exit 7; }` (process_launcher.py:367 map_child_exception), `cat <(echo readside)`, `echo w > >(cat)` (the _create_write_process_substitution new-kwarg path), parent EXIT trap + `( exit 3 )`, child EXIT trap + `( exit 4 )`, `$( )`, and `set -e; { true | cat <(false; echo A); } || echo M-recovered`. Golden co-flip replayed byte-exact (od -c verified probe file, `: p1 / : p2 / echo $(if) <<EOF / body / EOF`): psh tip rc=127, bash rc=127 — the golden's new exit_code:127 is correct. Flip pins replayed at tip: 10 passed, including BOTH must-NOT-flip pins (test_divergence_alias_local_to_cmdsub_body, test_divergence_heredoc_body_cmdsub_stays_runtime) still present and GREEN; a base-vs-tip census of `^def test_divergence` in the two conformance files shows exactly the 3 chartered names removed and the 2 must-not-flip names untouched.

EVIDENCE:
bash --version = GNU bash 5.2.26(1)-release; per-row differential table (11/11 MATCH, both parsers); pytest of the 5 pin node-ids at tip = 10 passed in 3.49s.

### NIT
Latent positional-shift hazard: run_child_shell's new `errexit_suppress_override` is positional-or-keyword and is inserted BEFORE the pre-existing `error_label` parameter. Nothing breaks today (all four in-tree call sites pass error_label by keyword — verified), but a future positional caller would silently mis-bind. The sibling parameters added in this same slot (run_background_shell_child's sever_errexit_context, create_process_substitution's errexit_suppress_override) ARE keyword-only, so this is also an internal inconsistency. Suggest adding `*` before it.

EVIDENCE:
psh/executor/child_policy.py:433-441 — `def run_child_shell(parent_shell, body, norc=True, io_setup=None, inherit_traps=True, reset_errexit=False, errexit_suppress_override: Optional[int] = None, error_label: str = 'forked child')` vs psh/io_redirect/process_sub.py:15 `def create_process_substitution(cmd_str, direction, shell, *, errexit_suppress_override=None)`.

### NIT
Doc drift (pre-existing, made one parameter staler): psh/executor/CLAUDE.md:257 quotes `child_policy.run_child_shell(parent_shell, body, *, norc, io_setup, error_label)`. That listing already omitted `inherit_traps` and `reset_errexit` at base, and now also omits `errexit_suppress_override`. Not a dangling pointer (test_doc_pointers.py is green) — it is an incomplete signature sketch, which the project's Development Principles discourage in subsystem CLAUDE.md.

EVIDENCE:
psh/executor/CLAUDE.md:255-259 at fix/remediation-2-4 vs psh/executor/child_policy.py:433.

### NIT
Ceremony debt (integrator-owned, NOT a dev bounce): three pre-flip test names that no longer exist in the tree are still named in the governance docs carried in the branch — docs/reviews/evidence/boundary_remediation_2026-07/FLIP-PINS.md lines 13, 15, 16 and LEDGER.md lines 29 and 161. I verified NOTHING EXECUTABLE reads them: grep of the three names over tests/ and tools/ returns zero hits, and no test or tool parses FLIP-PINS.md/LEDGER.md. Per the campaign precedent these files are edited only by integrator ceremony commits (7bcf163e '2.3 ceremony', 2714b0e2 '2.2 ceremony'), so the dev correctly left them alone — but ceremony now owes 4 row updates (3 renames + the already-known wrong-file correction on FLIP-PINS line 16, which the brief's 2026-07-30 amendment already tallies as integrator fault).

EVIDENCE:
git grep -n 'test_divergence_c_mode_exit_code_is_127_in_bash|test_divergence_eval_source_fatality_is_i3|test_divergence_eval_source_procsub_joined_i3' fix/remediation-2-4 -- tests/ tools/ => no output; same grep over docs/ => FLIP-PINS.md:13,15,16 + LEDGER.md:29,161 + dated snapshot docs.

### NIT
Housekeeping observations, no action required from the dev: (a) docs/reviews/reappraisal_19_campaign_briefs_2026-07-11.md:580 quotes the now-obsolete 1-arg `map_child_exception(exc: BaseException) -> int` — a dated snapshot doc, which the campaign convention explicitly treats as frozen, so recorded only for completeness. (b) Three stale verifier worktrees from EARLIER rounds are still registered and were not created by me: /private/tmp/remv-probe-base (1b271d77), /private/tmp/remv-probe-r8 (55edb24f), /private/tmp/remv-probe-r9 (71e83c35). I did not touch them (a concurrent peer may hold one). My own worktree was removed cleanly. (c) Confirmed clean on the standing constraints: the diff touches none of psh/version.py, CHANGELOG.md, README.md, ARCHITECTURE.md, docs/reviews/**, or tests/integration/redirection/test_process_sub_closed_fds.py, and none of the parallel session's uncommitted junk files (' 1 ', b]y, d/, decomment.py) were committed.

EVIDENCE:
git diff --name-only origin/main...fix/remediation-2-4 filtered for the NEVER-TOUCH set => no matches; `git worktree list` after my removal shows remv-probe-base/r8/r9 but not remv-wt.

## Task verdict: FAIL

### BLOCKER
Regression vs base+bash at the declared final tip 71e83c35: a severed pipeline member's COMMAND-SUBSTITUTION child loses the pre-sever errexit suppression whenever the child inherits errexit (shopt -s inherit_errexit, or set -o posix). Probe: `set -e\nshopt -s inherit_errexit\n{ true | echo "x=$(false; echo A)"; } || echo GOT rc=$?\necho END` -> bash 5.2.26 prints 'x=A\nEND\n' and base 1b271d77 prints 'x=A\nEND\n' (==bash), but tip 71e83c35 prints 'x=\nEND\n' on BOTH parsers across -c/file/stdin. Identical failure with `set -o posix` instead of the shopt. Control rows isolate the seam: top-level inherit_errexit cmdsub matches everywhere (x=A), and the $- observation shows dash=ON inside the child in BOTH shells under inherit_errexit — so bash carries the pre-sever depth into a cmdsub child that inherits errexit, and psh's command_sub.py run_child_shell call (which receives NO errexit_suppress_override) does not. This falsifies both dev-flagged weakest claims: (i) the expansion-time procsub seam is NOT the only path a severed member's context reaches a substitution child — the cmdsub fork is a second, observable one; (ii) the round-9 mechanism universal in test_member_substitution_children_keep_the_pre_sever_context's docstring and ledger R9-A ('a command-substitution child runs with the errexit OPTION CLEARED — $- contains no e inside it, in bash and in psh ... so the suppression DEPTH is not observable there at all and severing it cannot change anything') is false off the default-options axis — the dev's own command_sub.py comment documents the inherit_errexit/POSIX exception (reset_errexit=not (opts.get('inherit_errexit') or opts.get('posix'))). The regression is present at r8 (55edb24f) too, i.e. it arrived with the severing machinery, but it is undeclared and unpinned anywhere on the branch (grep for inherit_errexit over the branch's conformance/unit tests and the slot ledger: zero rows) and stands at the declared final tip. Fifth instance of the slot's own lesson: the r9a instrument varied spelling/route/channel but held the OPTION axis constant at default.

EVIDENCE:
Verifier battery rows C1/C2/C3/C5 (scratchpad r9probe.py), run 2026-07-31 against worktrees at 71e83c35 (tip), 1b271d77 (base), 55edb24f (r8), PYTHONPATH-discriminator verified, one case per invocation, oracle /opt/homebrew/bin/bash 5.2.26. C1 (-c/file/stdin): bash rc=0 'x=A\nEND\n'; base-rd/base-cb identical to bash; tip-rd/tip-cb rc=0 'x=\nEND\n'; r8 same as tip. C3 (set -o posix): same split. C2: 'dash=ON' in both bash and psh (all impls) — $- HAS e in the cmdsub child under inherit_errexit. C5 (top-level control): all impls 'x=A\nEND\n'. C4 (procsub + inherit_errexit): tip==base==bash 'A\nEND\n', red at r8 — the procsub side is fixed; only the cmdsub creator (psh/expansion/command_sub.py:142 run_child_shell, no override argument) leaks the severed context.

### NIT
Ledger R9-A records the run_child_shell call sites as 'command_sub.py:142, process_sub.py:76 and :187'; at 71e83c35 the process_sub.py sites are at lines 79 and 194 (the count of 3 sites and the keyword-only/defaulted analysis are correct).

EVIDENCE:
grep -n 'run_child_shell(' at the tip worktree: psh/expansion/command_sub.py:142, psh/io_redirect/process_sub.py:79, psh/io_redirect/process_sub.py:194.

### NIT
Eval-route procsub rows moved base->tip toward bash before round 9 and land ON bash, but are not individually pinned: `set -e; { true | eval 'cat <(false; echo A)'; } || …` and the eval'd redirect spelling print 'A\nEND' at base vs 'END' at r8/tip==bash. Consistent with the one-shot deferral rule and covered by the R7-B/R8-B co-movement declarations (r8b 186-row hunt + the round-8 verifier's 576-row disjoint hunt), but the procsub-body x eval-route intersection is not among the sampled pins; worth a row when the blocker above is remediated, since that fix will again touch this family.

EVIDENCE:
Verifier rows B1/B5: bash 'END\n'; tip-rd/tip-cb/r8 'END\n' ==bash; base-rd/base-cb 'A\nEND\n'; all 3 channels.

### NIT
Everything else verified clean at 71e83c35: fix row + redirect sibling + controls + $- mechanism (default options) reproduce exactly as claimed with RED-at-55edb24f replayed both by probe and by exact-test replay; call-site widening safe; records reconcile (audit 111/111 = 87 chk + 10 nchk + 13 instrument + 1 chain; bounced 90/90 incl. the three round-8 rows; chain 121/0; gate 21,105/0/1,590/10 SHA-stamped, +90=47+33+6+3+1; compare-bash 2,986/26 SHA-stamped; r7a/r8a byte-unchanged mod header); four-round-pattern one-liner, amendment citation (R9-D), successor row (g), STILL-OPEN docstring-qualifier deferred-to-ceremony, nightly bash-version caveat all present; forbidden files/FLIP-PINS/docs untouched; version.py 0.758.0; dev worktree clean at tip; 185-test timing module + 223-test sibling batch + 10-test PTY module + must-not-flip pins + flipped 127-family + golden co-flip row all green at tip. The bounce is solely the inherit_errexit/posix cmdsub leak.

EVIDENCE:
Full battery and record checks in this session; worktrees /tmp/remv-probe-{r9,base,r8} created and removed; final SHA 71e83c359587c3d6cccae97db7e28ac6eb6adadf recorded on every differential.

## Task verdict: PASS-WITH-NITS

### NIT
AUTHORIZATION RECORD STOPS SHORT OF ROUND 9. The brief's DATED AMENDMENT (2026-07-31) enumerates the ruling chain R4-A/R4-A-REVISED, R5-A, R6-A/R6-B, R7-A/R7-B, R8-A/R8-B and declares the errexit severing/deferral machinery authorized. The branch tip commit 71e83c35 ('2.4 round 9 (R9-A/B/C/D/E): the member's expansion-time substitution child') adds a production family the amendment does not name: psh/io_redirect/process_sub.py#ProcessSubstitutionHandler._pre_sever_suppression plus the new errexit_suppress_override keyword threaded through create_process_substitution / _create_write_process_substitution / child_policy.run_child_shell. I judged it in-scope (the amendment itself refers to 'the round-8 blocker', and this is the fix for it: a severed pipeline member's severing was leaking into its expansion-time procsub child), it moves toward bash, and it is pinned. But the durable brief/ledger pair the amendment was written to create is incomplete without an R9 clause. Integrator should extend it before ceremony.

EVIDENCE:
git diff origin/main...fix/remediation-2-4 -- psh/io_redirect/process_sub.py (new _pre_sever_suppression + errexit_suppress_override on 3 signatures); brief amendment text ends at 'R8-A: substitution-route spelling split recorded and pinned.' Probe (mine): `set -e; { true | cat < <(false; echo A); } || echo R; echo DONE` -c and file: bash rc0 'DONE\n', tip rc0 'DONE\n', base(1b271d77) rc0 'A\nDONE\n' => MOVED-TO-BASH. Pinned by tests/conformance/bash/test_syntax_template_timing_conformance.py::test_member_substitution_children_keep_the_pre_sever_context (replayed RED at base 1b271d77, green at tip).

### NIT
THE CO-MOVEMENT CENSUS' UNIVERSE EXCLUDES EXTERNAL-COMMAND BODIES, AND THE FAMILY HAS A PRE-EXISTING DIVERGENCE THERE. test_ordinary_errexit_co_movements_are_declared's docstring cites tmp/r24-probes/r8b_hunt.py as 'enumerates the space' with '0 pre-existing divergences'. That file's BODIES dict is {eval_text, source_text, plain_false, func_call} — no EXTERNAL command. Adding one surfaces an unmoved divergence in exactly the 'a directly-invoked FUNCTION body carries the suppression' rule the slot implements. NOT a regression (base == tip), so not a blocker; recording it so the committed claim is read with its true domain, and as a successor-row candidate.

EVIDENCE:
Probe (mine, /private/tmp/.../scratchpad/probes/t7.py, bash 5.2.26 /opt/homebrew/bin/bash, -c and file channels, both replayed at 1b271d77 and 71e83c35): `set -e\ng(){ /usr/bin/false; echo A; }\n{ true | g; } || echo GOT rc=$?\necho END` -> bash 'A\nEND\n' | tip 'GOT rc=1\nEND\n' | base 'GOT rc=1\nEND\n'. Control with the BUILTIN false — `g(){ false; echo A; }` — matches in all three ('A\nEND\n'), as do the brace-member and subshell spellings with the external. Dev corpus: /Users/pwilson/src/psh-r2-4/tmp/r24-probes/r8b_hunt.py lines 36-42.

### NIT
SEVEN NEW PINS ARE GREEN ON THE WAVE BASE. Campaign rule makes a green-on-base pin a blocker 'unless the slot brief declares it a control row'; the brief declares none. Each of these self-declares in its docstring as a control / declared divergence / accidental-parity guard, which I take as satisfying the intent — but the ruling belongs in the ledger, not only in test prose.

EVIDENCE:
Replay: tip's two conformance files copied onto a detached worktree at 1b271d77 -> `pytest -q -p no:randomly` = 42 failed / 253 passed. The tip-added tests NOT in that failure set are: test_substitution_fatality_status_under_errexit_is_2, test_exit_trap_teardown_action_error_changes_nothing, test_exit_trap_teardown_under_errexit_is_a_declared_divergence, test_interactive_dash_c_channel_disposition, test_redirect_procsub_suppression_is_a_declared_divergence, test_new_families_agree_across_parsers (test_syntax_template_timing_conformance.py) and test_file_and_stdin_direct_status_stays_2 (test_nested_substitution_timing_conformance.py).

### NIT
INTEGRATOR-OWNED RECORDS STILL CARRY THE OLD PIN NAMES AND AN OPEN HIGH-9 ROW. Correctly untouched by the dev (they are ceremony edits, and the brief forbids the reviews index), but they are now stale against the tree and must not be forgotten at close: FLIP-PINS.md rows 13/15/16 name test_divergence_c_mode_exit_code_is_127_in_bash, test_divergence_eval_source_fatality_is_i3 and (in the wrong file) test_divergence_eval_source_procsub_joined_i3 — all three renamed in this branch; row 16's file correction is already owed per the brief's 2026-07-30 note. LEDGER.md:29 still lists HIGH-9 as CONFIRMED-open, LEDGER.md:161 leaves the 2.3 I3-WIDENED carry to 2.4, and boundary_campaign_close_2026-07.md:179/249 still describe S3->I3 and carry #22 as LIVE.

EVIDENCE:
grep -rn 'test_divergence_c_mode_exit_code_is_127_in_bash|test_divergence_eval_source_fatality_is_i3|test_divergence_eval_source_procsub_joined_i3' at 71e83c35: 12 hits, ALL under docs/reviews/ (0 under psh/ or tests/ — so no dangling reference inside the code or suite). Flips verified present: test_c_mode_exit_code_is_127_like_bash (6 params), test_eval_source_frame_fatality_matches_bash, test_eval_source_procsub_joined_family_matches_bash, and golden heredoc_nested_error_reports_absolute_line exit_code 2->127 with stdout/stderr unchanged.

### NIT
THE EXHAUSTIVE RECORD A COMMITTED DOCSTRING POINTS AT IS NOT IN THE REPO. test_ordinary_errexit_co_movements_are_declared cites tmp/r24-probes/r8b_hunt.py and r8b-hunt-TIP.txt as 'the record' behind its 60/126/0/0 numbers, and says the file is rescued to docs/reviews/evidence/2.4-rescue/ at ceremony. Until that rescue happens the committed claim is unverifiable from a clean checkout. Same applies to the r6b*/r7a/r8a chains cited by test_function_member_channel_rule_is_a_declared_divergence, test_background_fork_severing_matches_bash and test_new_families_agree_across_parsers.

EVIDENCE:
Files exist only at /Users/pwilson/src/psh-r2-4/tmp/r24-probes/ (gitignored); `git show fix/remediation-2-4:docs/reviews/evidence/boundary_remediation_2026-07/` has no 2.4-rescue directory.

### NIT
GATE-TIME BUDGET: tests/conftest.py now admits tests/system/interactive/test_substitution_abort_interactive_pty.py to the DEFAULT run (no --run-interactive needed). The module is pytestmark = pytest.mark.serial, so its ~7.5s lands in the serial phase, which is the wall-clock-dominant one. Justified by ruling R6-C (the facts exist only at a terminal) and I verified it is genuinely serial-marked, so it is xdist-safe; flagging only so the cost is a decision and not a surprise.

EVIDENCE:
tests/conftest.py hunk adds `or "test_substitution_abort_interactive_pty" in str(item.fspath)` to the always-run list; the filename does NOT match the 'test_pty' serial path-marker substring, but tests/system/interactive/test_substitution_abort_interactive_pty.py:71 sets `pytestmark = pytest.mark.serial` (confirmed: `pytest --collect-only -m serial` on that file collects all 10). Runtime measured at tip: 10 passed in 7.44s.

