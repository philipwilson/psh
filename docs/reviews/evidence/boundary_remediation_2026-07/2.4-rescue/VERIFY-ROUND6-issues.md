# Slot 2.4 verification round 6 — full issue list (overall: BOUNCE)

## Task verdict: PASS-WITH-NITS

### NIT
The R4-E "Corrected 'Touched EXACTLY' set (cumulative, all rounds)" list in the slot ledger is stale at the final tip: it omits the round-6 production touches (psh/executor/context.py, psh/executor/pipeline.py, psh/executor/function.py, psh/executor/subshell.py, and the psh/shell.py docstring). Nothing is silent — each edit IS declared individually in its round-6 section (R6-A/R6-B/R6-D) and every file maps to a granted ruling — but a list labeled 'cumulative, all rounds' that stops at round 4 could mislead the ceremony read. Integrator should treat the round-6 sections as authoritative for the touched set.

EVIDENCE:
git diff --name-only 1b271d77..fix/remediation-2-4 lists 19 psh/ files; R4-E's set (ledger ~line 957) names only the rounds-1..5 files. Round-6 commits: 360090b2 (subshell.py only), d64a3294 (context/function/pipeline), 0fed0d04 (shell.py docstring-only, verified in diff).

### NIT
R6-A's accounting row says only 'production only (bg-subshell seeding)' without naming the file; the ledger never explicitly states that commit 360090b2 touched psh/executor/subshell.py. Unambiguous from the commit title and stat, but the durable record should name files for production edits.

EVIDENCE:
git show --stat 360090b2 → psh/executor/subshell.py, 19 insertions/3 deletions, sole file.

### NIT
The round-1 pin-obligations table records FLIPPED verdicts without per-row commit SHAs; attribution flows only from the enclosing 'What landed (commit a76e93f0)' section header. Verified correct (a76e93f0's stat covers both conformance files + golden_cases.yaml), so this is presentation, not substance.

EVIDENCE:
git show --stat a76e93f0 includes tests/behavioral/golden_cases.yaml, test_nested_substitution_timing_conformance.py, test_syntax_template_timing_conformance.py.

## Task verdict: FAIL

### BLOCKER
SLOT-INTRODUCED DIVERGENCE in the slot's own family, unpinned and undeclared: a shell FUNCTION reached through a simple pipeline member's `eval`/`.` text gets the deferred errexit suppression re-applied at body entry, so the substitution abort answers 1 where bash answers 2 — and where psh MATCHED bash at the wave base. Root cause is the R6-B triad (psh/executor/pipeline.py zeroes `errexit_suppress` for a SimpleCommand member and parks it in `errexit_suppress_deferred`; psh/executor/function.py#FunctionOperationExecutor._function_frame re-applies that parked depth for ANY function body entered anywhere inside the member, not only when the member's own node resolves to a function). The dev's pin `test_pipeline_member_suppression_matches_bash` varies the function axis only as `{ true | f; }` / `{ true | $Q; }` (member IS the function); the eval-reached spelling is in no test in the branch (grep for `eval 'f'` over tests/ returns nothing).

EVIDENCE:
REPLAYED, individual-run, byte-exact script file, PATH bash /opt/homebrew/bin/bash 5.2.26.
Script: "f(){ eval 'echo $(if)'; }\nset -e\n{ true | eval 'f'; } || echo GOT rc=$?\necho END"
  bash            -> rc=0 out='GOT rc=2\nEND\n'   (c, file, stdin)
  psh @1b271d77   -> rc=0 out='GOT rc=2\nEND\n'   (c, file, stdin; rd AND combinator)  == bash
  psh @d64a3294   -> rc=0 out='GOT rc=1\nEND\n'   (c, file, stdin; rd AND combinator)  != bash
Same split for: $(fi) error kind; `if true | eval 'f'; then...` suppression source; function via expansion `eval '$Q'`. Bisect: already present at bf2a7d00 (pre-R6-B), still present at tip.
CONTROLS that behave correctly: `{ true | eval 'echo $(if)'; }` -> tip 2 = bash (the row the pin covers); `{ true | f; }` -> tip 1 (the declared channel-rule row).
Production @1b271d77 is identical to origin/main (`git diff 1b271d77 acf3c28b -- psh/` = psh/version.py only), so the base is the merge base for behavior purposes.

### BLOCKER
UNPINNED BEHAVIOR DELTA outside the chartered flips (brief: "an unpinned improvement is still a bounce"): psh/executor/pipeline.py's SimpleCommand-member change also moves ORDINARY errexit for a failing command inside a member's eval'd/sourced text — a family with no substitution syntax error anywhere. base != bash, tip == bash. Every row of `test_pipeline_member_suppression_matches_bash` puts a substitution-body syntax error in the member; its two "OTHER readers of the suppression depth are unmoved" controls (`{ true | set -q; }` under posix, `{ true | false; }`) are precisely the shapes that do NOT move, so the pin's control set positively conceals this delta. Nothing in tests/ or golden_cases.yaml covers it.

EVIDENCE:
Script: "set -e\n{ true | eval 'false; echo A'; } || echo GOT rc=$?\necho END"
  bash          -> out='GOT rc=1\nEND\n'
  psh@1b271d77  -> out='A\nEND\n'        (c, file, stdin; rd AND combinator)
  psh@d64a3294  -> out='GOT rc=1\nEND\n' (c, file, stdin; rd AND combinator)
Same move for `{ true | . ./f.sh; }` (f.sh = "false\necho A\n") and for the if-condition suppression source `if true | eval 'false; echo A'; then ... else echo GOT rc=$?; fi`.
CONTROLS confirming the pin's claim is true but narrow: `{ true | { eval 'false; echo A'; }; }` (compound member) tip==base==bash; `set -o posix; set -e; { true | set -q; }` tip==base==bash; `set -e; { true | false; }` tip==base==bash.

### BLOCKER
UNPINNED BEHAVIOR DELTA outside the chartered flips: psh/executor/subshell.py's new `errexit_suppress` threading into `_execute_background_subshell` (+ `subshell._errexit_suppress_seed`) changes ordinary errexit for a BACKGROUND subshell in a suppressing context — again with no substitution error involved. base != bash, tip == bash. The dev's own ledger records commit 360090b2 as "production only (bg-subshell seeding) | 0" net-new tests, and its discharge row cites only substitution `bg_*` probe rows. golden_cases.yaml has `subshell_errexit_suppressed_in_if_condition`, `cmdsub_errexit_suppression_crosses_fork`, `procsub_errexit_suppression_crosses_fork` — all FOREGROUND; no `&` row exists anywhere for this family.

EVIDENCE:
Script: "set -e\n{ ( false; echo A ) & wait $!; } || echo GOT rc=$?\necho END"
  bash          -> out='A\nEND\n'
  psh@1b271d77  -> out='GOT rc=1\nEND\n'  (c, file, stdin; rd AND combinator)
  psh@d64a3294  -> out='A\nEND\n'         (c, file, stdin; rd AND combinator)
Same move with an if-condition suppression source: "set -e\nif { ( false; echo A ) & wait $!; }; then echo T; else echo GOT rc=$?; fi\necho END" -> bash 'A\nT\nEND\n', base 'GOT rc=1\nEND\n', tip 'A\nT\nEND\n'.
UNSUPPRESSED control unmoved: "set -e\n( false; echo A ) & wait $!\necho END" -> rc=1, out='' in all three.

### NIT
tests/conftest.py (shared test infrastructure, outside the brief's named scope of psh/executor + the -c entry path + eval/source builtins + psh/expansion raise-site plumbing) is edited to opt the new PTY differential module into the DEFAULT gate run, bypassing --run-interactive. Ruling R6-C is cited in the ledger, so this is a note rather than a bounce, but it changes gate composition/duration for every future slot and is a policy edit a dev normally STOPs on.

EVIDENCE:
tests/conftest.py pytest_runtest_setup: `+ or "test_substitution_abort_interactive_pty" in str(item.fspath)):` added to the always-run allowlist beside test_pty_smoke / test_pty_shutdown_route_f2 / test_multiline_immediate_error_i3 / test_pty_huponexit_j1. The module is 5 rows x 2 parsers, each spawning a real bash and a real psh over a PTY.

### NIT
psh/parser/recursive_descent/helpers.py and psh/parser/recursive_descent/support/nested_parse.py are edited in a tree the brief lists as STOP-and-report ("lexer, parser grammar"). Both edits are comment/docstring-only (producer-contract prose, tagged-domain bounds) with zero behavior change, and psh/parser/CLAUDE.md is updated consistently — so this is a scope note, not a violation.

EVIDENCE:
git diff origin/main...fix/remediation-2-4 -- psh/parser/ shows only `#:` comment lines, class/function docstrings and a block comment; no executable statement changed (confirmed by filtering the diff for non-comment `-`/`+` lines: none in psh/parser/).

### NIT
Adjacent PRE-EXISTING divergence (base == tip, NOT the slot's doing) in the same mechanism as the first BLOCKER, offered as fix-design input: a simple pipeline member whose eval'd/sourced text calls a function keeps psh's suppression for ORDINARY errexit too. Fixing the first BLOCKER by scoping the deferred re-apply to "the member's own resolved node" would close this row as a side effect; a fix that only special-cases the substitution abort would leave it.

EVIDENCE:
"f(){ false; echo A; }\nset -e\n{ true | eval 'f'; } || echo GOT rc=$?\necho END" -> bash 'GOT rc=1\nEND\n'; psh@1b271d77 'A\nEND\n'; psh@d64a3294 'A\nEND\n' (c and file). Same for the `. ./g.sh` spelling with g.sh calling f.

## Task verdict: FAIL

### BLOCKER
REGRESSION (behavior change away from bash, unpinned, undeclared): a BACKGROUNDED BARE SIMPLE COMMAND that hits the substitution abort inside an errexit-SUPPRESSING context now exits 1 where bash 5.2.26 and psh-at-base both exit 2. Base MATCHED bash; the tip breaks it. Reproduced on 4 independent suppression spellings (`||`, `!`, if-condition, `&&`), in all 3 channels (-c / file / stdin) and on BOTH parsers. Bash's rule (the one the dev itself quotes at psh/executor/context.py#errexit_suppress_deferred) is that a SIMPLE command introduces no compound body, so `set -e` stays EFFECTIVE — the dev implemented exactly that for pipeline members (psh/executor/pipeline.py, commit d64a3294) but the background fork site still stamps the inherited suppression onto a simple command. Bisected: correct at 6cb57bef/f0cc466e/54001334, broken from 5121ec8b ("stamp effective-errexit on the error at raise") onward. No test in the branch exercises any background (`&`) fork for this family — grep for a bare `&` in tests/conformance/bash/test_syntax_template_timing_conformance.py returns nothing — so the suite is green over the defect.

EVIDENCE:
Probe file (od -c verified) /tmp probe body:
set -e\n{ eval 'echo $(if)' & } || true\np=$!\nif wait $p; then echo child=0; else echo child=$?; fi\n
od -c: 0000000 s e t   - e \n {   e v a l   ' e c h o   $ ( i f ) '   &   }   | |   t r u e \n p = $ ! \n i f   w a i t   $ p ; ...

ORACLE /opt/homebrew/bin/bash = GNU bash 5.2.26(1)-release. Discriminators: base worktree psh.__file__=/private/tmp/remv-base-t2/psh/__init__.py @1b271d77; tip worktree psh.__file__=/private/tmp/remv-wt-t2/psh/__init__.py @d64a3294.

REPLAYED MATRIX (one case per invocation, script-file channel):
  D1 `eval '…' &` UNsuppressed      bash child=2 | BASE child=2 | TIP child=2   (match)
  D2 `{ eval '…' & } || true`       bash child=2 | BASE child=2 | TIP child=1   <-- REGRESSION
  E1 `! { eval '…' & true; }`       bash child=2 | BASE child=2 | TIP child=1   <-- REGRESSION
  E2 `if { eval '…' & true; }; ...` bash child=2 | BASE child=2 | TIP child=1   <-- REGRESSION
  E5 `{ eval '…' & } && true`       bash child=2 | BASE child=2 | TIP child=1   <-- REGRESSION
  D3 `( eval '…' ) &` UNsuppressed  bash child=2 | BASE child=2 | TIP child=2   (match)
  D4 `{ ( eval '…' ) & } || true`   bash child=1 | BASE child=2 | TIP child=1   (dev fix, correct)
  E3 function member `{ f & } || true`   bash 1 | BASE 2 | TIP 1  (correct)
  E4 brace-group `{ { …; } & } || true`  bash 1 | BASE 2 | TIP 1  (correct)

D2 across channels/parsers:  -c: bash=2 TIP(rd)=1 TIP(combinator)=1 BASE=2 ; stdin: bash=2 TIP=1 BASE=2

BISECT of D2 (script-file, tip worktree checked out per commit):
  774111f4=1  6cb57bef=2  f0cc466e=2  54001334=2  5121ec8b=1  360090b2=1  d64a3294=1

Corpus gap proof: `grep -n " & \| &$" tests/conformance/bash/test_syntax_template_timing_conformance.py | grep -v '&&'` -> no output. Dev's own ledger (/Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/2.4.md:886) states the errexit x fork matrix was "2 fork shapes" and the option x fork matrix "subshell/cmdsub/pipeline" — background is absent.

### BLOCKER
FALSE CLAIM shipped in production docstrings + unpinned family gap: `psh/core/internal_errors.py#substitution_child_abort_status` states the child mapping is "probe-verified for subshell, command substitution, backticks, pipeline members and background jobs", and `psh/core/exceptions.py#SubstitutionSyntaxAbort` states "a subshell, command/process substitution, a pipeline member and a background job all die … with status 1, or 2 when EFFECTIVE errexit applies". Background jobs are demonstrably WRONG at the tip in 2 of the 3 background spellings (bare simple command, and-or list / compound list), and the branch contains ZERO background-job test rows for this family. The dev's own per-commit accounting for 360090b2 reads "production only (bg-subshell seeding) | 0" — i.e. the `( ) &` behavior change (BASE child=2 -> TIP child=1, replayed) landed with no pin at all, which the slot typology grades an unpinned behavior change.

EVIDENCE:
psh/core/internal_errors.py (tip): "A forked child does NOT use the channel rule … (probe-verified for subshell, command substitution, backticks, pipeline members and background jobs)."

Counter-evidence, replayed at /opt/homebrew/bin/bash 5.2.26 vs BASE@1b271d77 vs TIP@d64a3294:
  bare `&`  suppressed: bash 2 / BASE 2 / TIP 1  (wrong at tip)
  `a && b &` suppressed: bash 1 / BASE 2 / TIP 2  (wrong at tip)
  `for … done &` suppressed: bash 1 / BASE 2 / TIP 2 (wrong at tip)
  `( ) &` suppressed:   bash 1 / BASE 2 / TIP 1  (fixed — but unpinned)

Unpinned proof: /Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/2.4.md:1606 and :1784 — "| 360090b2 (R6-A) | production only (bg-subshell seeding) | 0 |" (0 tests added). No `&` row exists in tests/conformance/bash/test_syntax_template_timing_conformance.py, tests/conformance/bash/test_nested_substitution_timing_conformance.py, tests/unit/scripting/test_embedding_abort_contract.py or tests/system/interactive/test_substitution_abort_interactive_pty.py.

### BLOCKER
WIDENED-SIGNATURE CALLER LEFT BEHIND (found by the resurrection hunt): the branch widens `SubshellExecutor._execute_background_subshell(self, statements, redirects)` to take `errexit_suppress: int = 0` and threads it from psh/executor/subshell.py:105, but the OTHER caller — `ExecutionVisitor._execute_background_list` at psh/executor/core.py:305 — was not updated and still calls it with two positional args, silently taking the default 0. That route serves `a && b &` and backgrounded compound commands (`for/while … done &`), so the seed the commit was written to deliver is dropped there. Live, replayed divergence at the tip: bash 1 vs psh 2. It is not a regression (base was also 2) but it is an undeclared, unpinned residual sitting inside the exact fork x effective-errexit family this slot claims to close, and it is an asymmetry created by the same commit that fixed the `( ) &` sibling.

EVIDENCE:
git grep -n "_execute_background_subshell" fix/remediation-2-4 -- psh/:
  psh/executor/subshell.py:105   return self._execute_background_subshell(statements, redirects, errexit_suppress=errexit_suppress)   <-- updated
  psh/executor/subshell.py:244   def _execute_background_subshell(self, statements, redirects, errexit_suppress: int = 0)
  psh/executor/core.py:305       return self.subshell_executor._execute_background_subshell(statements, [])   <-- NOT updated

Replayed (probe files, od -c verified; oracle /opt/homebrew/bin/bash 5.2.26):
  D6  set -e; { : && eval 'echo $(if)' & } || true; p=$!; if wait $p; then echo child=0; else echo child=$?; fi
      bash child=1 | BASE@1b271d77 child=2 | TIP@d64a3294 child=2
  G1  set -e; { for i in 1; do eval 'echo $(fi)'; done & } || true; …
      bash child=1 | BASE child=2 | TIP child=2
  G2 (unsuppressed control) bash child=2 | BASE 2 | TIP 2  (match — isolates the dropped seed as the cause)

Contrast, same wrapper, route that WAS threaded:
  D4  set -e; { ( eval 'echo $(if)' ) & } || true …   bash 1 | BASE 2 | TIP 1

### BLOCKER
DANGLING `file.py#symbol` POINTER in the load-bearing ONE-WRITER/ONE-READER invariant comment the branch adds for the new `errexit_suppress_deferred` field. It names `executor/function.py#FunctionExecutor._function_frame`, but the class in psh/executor/function.py is `FunctionOperationExecutor`; the identifier `FunctionExecutor` does not exist anywhere under psh/. One-word fix, but the pointer is the only thing telling a reader where the field is consumed, and pointer resolution is the campaign's standing doc rule.

EVIDENCE:
psh/executor/context.py:52 (added by this branch):
  #   ONE READER — executor/function.py#FunctionExecutor._function_frame,

grep -n "^class \|def _function_frame" psh/executor/function.py:
  21:class FunctionOperationExecutor:
  197:    def _function_frame(self, name: str, args: List[str],

grep -rn "\bFunctionExecutor\b" psh/  ->  exactly one hit, the dangling comment itself (psh/executor/context.py:52). Every OTHER added pointer in the branch was checked and resolves (18/19: SubstitutionSyntaxAbort, substitution_abort_status, substitution_child_abort_status, TrapManager.execute_exit_trap, TopLevelAbort, CHILD_EXIT_EXCEPTIONS, map_child_exception, sync_child_status_for_exit_trap, SubstitutionSyntaxError, parse_nested_command, SourceProcessor._substitution_syntax_abort, Shell.for_subshell, execute_as_main, Shell.run_command, resolve_bash, errexit_suppress_deferred, posix_syntax_exit, SourceProcessor#_errexit_suppressed).

### NIT
RESURRECTION HUNT ITSELF IS CLEAN — reported for the record. No files deleted or renamed (git diff --name-status -M shows only 4 A entries, all new test files). Two production signatures widened, all call sites accounted for: `map_child_exception(exc)` -> `(exc, state)` (no default) has 5 call sites in the branch (psh/executor/child_policy.py:312,403,409; psh/executor/process_launcher.py:367; plus tests/unit/executor/test_child_policy.py) and every one passes 2 args; `_execute_background_subshell` gained a defaulted param (see the separate BLOCKER on its stale caller). Four test symbols were renamed and have ZERO surviving references in psh/, tests/ or tools/. The branch imports and runs: python -c 'import psh, psh.version' -> 0.758.0 with psh.__file__=/private/tmp/remv-wt-t2/psh/__init__.py (discriminator confirms the worktree tree, not the editable install); `python -m psh -c 'echo ok'`, `--parser combinator -c`, script-file and stdin channels all rc=0. Structural guards green at the tip: tests/unit/tooling/test_doc_snippets.py, test_child_exit_taxonomy_centralized.py, test_no_direct_spawn_in_oracle_modules.py, test_mypy_scope.py, tests/unit/executor/test_child_policy.py (75 passed) and tests/unit/tooling/test_substitution_abort_guards.py + tests/unit/scripting/ (181 passed). Throwaway worktrees /tmp/remv-wt-t2 and /tmp/remv-base-t2 were created and removed.

EVIDENCE:
Renames and their new names: test_divergence_c_mode_exit_code_is_127_in_bash -> test_c_mode_exit_code_is_127_like_bash; test_divergence_eval_source_fatality_is_i3 -> test_eval_source_frame_fatality_matches_bash; test_divergence_eval_source_procsub_joined_i3 -> test_eval_source_procsub_joined_family_matches_bash; test_taxonomy_tuple_is_the_five_families -> test_taxonomy_tuple_is_the_six_families. `git grep -n <old-name> fix/remediation-2-4 -- psh/ tests/ tools/` returns nothing for all four.

### NIT
INTEGRATOR CEREMONY ITEMS (dev correctly did NOT touch these — integrator plan §3 / brief). The four renamed pin names still appear in the LIVE governing docs and must be updated at ceremony, otherwise the flip-pin inventory points at tests that no longer exist: docs/reviews/evidence/boundary_remediation_2026-07/FLIP-PINS.md lines 13, 15, 16; docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md lines 29 and 161; docs/reviews/boundary_remediation_integrator_plan_2026-07-21.md line 77 (amendment A3). Note FLIP-PINS.md:16 also still carries the WRONG FILE for the procsub co-flip (`test_subscript_keying_conformance.py`; the test actually lives in test_syntax_template_timing_conformance.py) — the correction the brief already records as owed. Historical records (docs/reviews/boundary_campaign_close_2026-07.md:179,249; the 2.2-rescue and 2.3-rescue slot ledgers; reappraisal #14/#19 docs) legitimately keep the old names and need no edit. No file on the §3 NEVER-TOUCH list (" 1 ", b]y, bugs.txt, d/, decomment.py, docs/reviews/README.md) is touched by the branch.

EVIDENCE:
git grep -n test_divergence_c_mode_exit_code_is_127_in_bash fix/remediation-2-4 -- docs/ ->
  docs/reviews/boundary_remediation_integrator_plan_2026-07-21.md:77
  docs/reviews/evidence/boundary_remediation_2026-07/FLIP-PINS.md:13
  docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md:29
  (+ historical: boundary_campaign_close_2026-07.md:179,249; 2.2-rescue/slot-ledger.md:363,496; 2.2-rescue/INTEGRATOR-INBOX.md:50)
git diff origin/main...fix/remediation-2-4 --stat -- docs/  ->  (empty; the branch touches no docs/reviews file)

## Task verdict: FAIL

### BLOCKER
False replay claim in the round-6 ledger (R6-F section, /Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/2.4.md ~line 1376): 'RED-ON-BASE: 2 of its 6 arms fail at 1b271d77 (replayed in tmp/r6b-base)' for tests/unit/scripting/test_errexit_suppressed_read.py. The true count at base is 5 of 6, and it is deterministic: SourceProcessor._errexit_suppressed does not exist at 1b271d77 at all (grep count 0 in base psh/scripting/source_processor.py), so every arm that calls it fails with AttributeError; the single passing arm (the without-a-context RAISES arm) passes at base for the WRONG reason (AttributeError from the missing method, not the pinned missing-context raise). The claimed count cannot be produced by the claimed instrument at the claimed commit — the exact non-replaying-claim class rounds 4-6 were convened over, in a round-6-added sentence. Direction of the claim (red-on-base) is true and the production fix is unaffected; this is a record-integrity blocker, not a behavior one.

EVIDENCE:
Replayed at my detached base worktree @1b271d77 (discriminator /private/tmp/remv-base-24r6/psh/__init__.py): copied the tip test file in, ran pytest -q -> '5 failed, 1 passed' (FAILED: test_no_live_executor_reads_as_unsuppressed, test_missing_current_executor_attribute_reads_as_unsuppressed, test_live_executor_reports_the_total_depth[0-False]/[1-True]/[2-True]); failure text 'AttributeError: SourceProcessor object has no attribute _errexit_suppressed'. grep -c _errexit_suppressed psh/scripting/source_processor.py at base = 0. At tip d64a3294 the module is 6/6 green (in my 386-test no-regression run). Base worktree restored clean and removed.

### BLOCKER
A round-6 ledger absolute is falsified by the tree, and it covers two silently-surviving round-5-flagged items: R6-E(3) (2.4.md ~lines 1329-1332) states 'Two OTHER falsified absolutes flagged alongside them survived to round 6 and are handled here' (the map_child_exception arity text and the -i -c pin's absolute — both genuinely fixed). But the round-5 record (VERIFY-ROUND5-issues.md blocker 'Checkpoint-open item silently dropped') flagged TWO MORE falsified absolutes that survive BYTE-IDENTICAL at declared tip d64a3294: (a) tests/conformance/bash/test_syntax_template_timing_conformance.py:296-299 test_substitution_fatality_is_contained_by_forks docstring 'the child dies with 1 and the parent runs on — in every channel, including -c' — falsified by the tree: with effective errexit the forked child dies with 2 (replayed at tip: psh AND bash both print 'AFTER rc=2' for "( set -e; eval 'echo $(if)' ); echo AFTER rc=$?"), and the file's own test_substitution_fatality_status_under_errexit_is_2 pins that 2; (b) tests/unit/executor/test_child_policy.py:73 'Flat 1 in every channel', contradicted three lines later by its neighbour's 'NOT a flat constant'. Round 6 touched neither text (git diff 5121ec8b..d64a3294 has 0 hits for 'dies with 1' and 'Flat 1' in those files), no discharge-audit row covers them, and no ruling in INTEGRATOR-INBOX.md defers them — so the round-6 'handled here' enumeration is an absolute falsified by the tree (blocker per this round's rule 6). DEGRADE PATH for the integrator: the round-5 bounce list you transmitted did not include the R5-E leftover item, so if you previously graded these two test-prose absolutes non-bounce, this reduces to: fix the two docstrings + correct the R6-E(3) enumeration at ceremony.

EVIDENCE:
Tip text at d64a3294 (my detached worktree, discriminator verified): sed -n 288,330p of the conformance file shows the unqualified 'child dies with 1 ... in every channel' prose (its rows only cover no-errexit shapes, so the TEST is green while the PROSE is false); test_child_policy.py:73 unchanged. Falsifying behavior replayed at tip and against PATH bash 5.2.26: both shells 'AFTER rc=2'. git diff 5121ec8b..d64a3294 -- <both files> | grep -c 'dies with 1' / 'Flat 1' -> 0/0. INTEGRATOR-INBOX.md read in full: rulings (a)-(d), PTY approvals, R6-B GO, R6-E(2) corpus-gap approval present; nothing deferring these two texts.

### NIT
Discharge-audit row count is 55, not the claimed 'ALL 56 ROWS PASS' (2.4.md ~1793): the script has 46 top-level chk/nchk/stamped calls + 9 loop-stamped battery rows = 55 checks; the 56th '|'-prefixed line is the table's column header. All 55 checks PASS in my worktree; exit code 0. An off-by-one in the accounting instrument's own headline, in a slot where counts are load-bearing — worth a one-line ceremony correction.

EVIDENCE:
Ran bash tmp/r24-probes/discharge_audit_r6.sh in MY detached tip worktree @d64a3294 (probes copied from the dev worktree): grep -cE '^\| ' = 56 total lines incl. header; grep -c '| PASS' = 55; 0 FAIL. Audit-the-audit both legs passed: 4 sampled anchors (pipeline.py errexit_suppress, child_policy 'substitution_child_abort_status(state,', subshell.py '_errexit_suppress_seed = errexit_suppress', no-direct-spawn '": 2' site count) are real at tip and 0-hit at base, so each proves its edit; doctoring r6b-TIP.txt's header SHA made the 'instrument r6b' row FAIL and the script exit non-zero, restored -> all pass.

### NIT
Novel guard evasion, limit UNSTATED: an aliased-import raise ('from psh.core.exceptions import SubstitutionSyntaxAbort as SSA; raise SSA(...)') passes ALL 12 guards green when inserted under psh/ (the catch twin 'except SSA:' shares the blindness — _exc_name resolves Name/Attribute but not import aliases), and the word 'alias' appears nowhere in tests/unit/tooling/test_substitution_abort_guards.py, so unlike guard 3's laundered-constant limit this one is not stated. The strengthened guards otherwise bite exactly as claimed: a catcher inside a NESTED function/method IS caught (my offender file turned test_only_the_sanctioned_non_fork_catchers_exist RED), and the laundered-constant miss ('return _ABORT_STATUS' in a keyed branch) is inside guard 3's explicitly stated limit.

EVIDENCE:
Offender experiments in my detached tip worktree: psh/voffender.py with nested-function catcher + method catcher + laundered constant + aliased raise -> 1 failed (guard 2 RED on the nested catcher); reduced to aliased raise only -> 12 passed (all green); grep -ci alias on the guards file = 0; offender removed, git status clean.

### NIT
VERIFIED-CLEAN RECORD (all replayed by me at d64a3294 in discriminator-verified detached worktrees, PATH bash 5.2.26(1)-release, all four probe worktrees since removed). R6-B: my FRESH 59-run battery (29 novel rows x channels: IFS/quoting/redirect/prefix variants, !/while/until/elif suppression sources, procsub+source spellings, top-level PIPESTATUS, plus compound kinds BEYOND the five — [[ ]], (( )), C-style for, select, group/subshell+redirect, function-calling-function, eval-running-compound-body, nested pipe-in-compound, case-word) = 0 regressions, 0 parser splits, all rc/flow MATCH bash (one apparent BASE-DIV was my instrument comparing diagnostic wording under 2>&1 — rc/flow match); 4 deep-nesting rows (pipeline-inside-suppressed-function/compound body) all MATCH at 2 — bash re-applies the simple-member rule at depth and psh's park-again architecture matches; compound member confirmed already 1 at pre-fix bf2a7d00 (fix moved only the simple half); R6-B pin replayed RED at bf2a7d00 AND at base. Bounced-rows replay independently re-run: 64/64 PASS; DECLARED scanner-case values cross-checked against the committed R4-C pin — no mis-encoding found; function-member -c chain replayed across all four commits incl. INFUNC form: base INFUNC/no-abort, r4 2, tip 1, bash 127 — pin docstring tells it straight. Successor rows spot-verified: (b) PIPESTATUS collapse base-identical (bash '1 0' vs psh '0'); (c) member EXIT-trap silence incl. CLEAN member (bash OK+BYE vs psh OK), subshell control runs the trap, all base-identical; (d) _EXPECTED_PTY_REGISTRY = frozenset(PTY_REGISTRY) at line 227 confirmed derived-not-literal. PTY: module runs 10/10 in a BARE default pytest invocation (conftest allowlist verified in diff); 2 rows replayed at a real PTY with my own raw-pty driver (different instrument from dev's pexpect): fork x errexit SUPPRC bash=1/psh=2 both parsers, eval-frame AFTERRC bash=1/psh=2, REPL alive (ALIVE-0 after every row), no tracebacks — pinned values exact. Teardown-errexit pin values replayed at base (psh rc=0 both shapes — base-identical claim holds). No-regression: 386 passed across both conformance files + embedding/errexit-read/child-policy/no-direct-spawn/template-guards; must-not-flip rows pass under original names; golden co-flip diff is exit_code 2->127 ONLY (stdout/stderr untouched) and the row passes. Accounting: my own collect-only base=22,632 tip=22,712 (+80 = +47 r5 + +33 r6); gate transcript header SHA d64a3294, 21,095/0/1,590/10; compare-bash transcript header SHA d64a3294, 2,986/26 UNCHANGED; ruff 'All checks passed'; mypy 'no issues in 274 source files' — both re-run by me at tip. Forbidden files: version.py/CHANGELOG/README/ARCHITECTURE/docs-reviews (incl. FLIP-PINS.md, LEDGER.md)/test_process_sub_closed_fds.py all absent from the base..tip diff; version.py 0.758.0. Ledger: FINAL STILL-OPEN table rows each discharged-with-row or deferred by a ruling that EXISTS in INTEGRATOR-INBOX.md; strike-and-corrects carry cause statements; corpus-gap record verified byte-exact (the four work-r5impl pipe_*.sh files exist and the suppressed x final intersection is genuinely absent). Round-6 production prose (context.py field docstring, pipeline.py closure comment — confirmed child-side, function.py frame docstring, subshell.py seed docstring, shell.py EMBEDDING CONTRACT, core/CLAUDE.md — the only round-6 CLAUDE.md edit): no falsified absolutes found beyond the two blockers above.

EVIDENCE:
Branch FINAL SHA d64a3294ea5f187840f0e75a5898f5c327dbaeaf; base 1b271d776b; r4 f0cc466e; pre-fix bf2a7d00. My battery + PTY driver + outputs in the session scratchpad (vbattery.py, vpty.py, vwork/); dev evidence read from /Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/ and tmp/r24-probes/ (read-only; audit and bounced-replay re-run from COPIES inside my own worktree).

