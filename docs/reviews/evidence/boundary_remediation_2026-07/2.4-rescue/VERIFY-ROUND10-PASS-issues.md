# Slot 2.4 verification round 10 — PASS (zero blockers); nits recorded

## Task verdict: PASS-WITH-NITS

### NIT
Three flip-pin tests were RENAMED (not just re-asserted), leaving 10 stale references by old name in campaign-record docs the dev is not chartered to edit. Integrator must update these at ceremony or the FLIP-PINS/LEDGER rows dangle. Old -> new: test_divergence_c_mode_exit_code_is_127_in_bash -> test_c_mode_exit_code_is_127_like_bash (tests/conformance/bash/test_nested_substitution_timing_conformance.py); test_divergence_eval_source_fatality_is_i3 -> test_eval_source_frame_fatality_matches_bash; test_divergence_eval_source_procsub_joined_i3 -> test_eval_source_procsub_joined_family_matches_bash (both tests/conformance/bash/test_syntax_template_timing_conformance.py). NOT a blocker: docs/reviews/ is integrator-owned per the brief (the LEDGER edit happens at ceremony; the FLIP-PINS row correction is explicitly 'owed at ceremony'), and no live code, guard, registry or CLAIM_TESTS mapping references the old names.

EVIDENCE:
git grep -n on branch fix/remediation-2-4 hits: docs/reviews/evidence/boundary_remediation_2026-07/FLIP-PINS.md:13 and :16; .../LEDGER.md:29 and :161; docs/reviews/boundary_remediation_integrator_plan_2026-07-21.md:77; docs/reviews/boundary_campaign_close_2026-07.md:179 and :249; .../2.2-rescue/INTEGRATOR-INBOX.md:50; .../2.2-rescue/slot-ledger.md:363,496; .../2.3-rescue/slot-ledger.md:654,767. Grep of tests/ tools/ psh/ for the three old names: zero hits.

### NIT
The slot brief's dated amendment extension (2026-07-31, R9 clause) names the R9-A symbol as psh/io_redirect/process_sub.py#ProcessSubstitutionHandler._pre_sever_suppression. That symbol does NOT exist in the branch tree; the landed implementation is psh/executor/child_policy.py#expansion_child_suppression (deliberately ONE function shared by both expansion-time creators, per its docstring; consolidated in round 10). No in-tree reference dangles, so this is not a blocker, but the authorization record points at a name that never shipped and should be reconciled at ceremony so the ruling chain matches the code.

EVIDENCE:
git grep -n "_pre_sever_suppression\|expansion_child_suppression" fix/remediation-2-4 -- psh/ tests/ docs/ tools/ returns ZERO hits for _pre_sever_suppression and 9 hits for expansion_child_suppression (psh/executor/child_policy.py:434 def; psh/executor/__init__.py:25,42 export; psh/expansion/command_sub.py:131,154; psh/io_redirect/process_sub.py:61,92,143,209).

### NIT
Record-only, no action needed: psh/version.py on the branch still reads 0.758.0 while origin/main has advanced to v0.759.0 (acf3c28b). This is brief-compliant (branch base 1b271d77; version.py is on the NEVER-TOUCH list), but the import proof reports 0.758.0 so the number is recorded here to avoid it being misread as a stale-branch signal. No forbidden file was touched.

EVIDENCE:
In detached worktree at d934a3ca: python -c 'import psh.version; print(psh.version.__version__)' -> 0.758.0, with psh.__file__ resolved inside the worktree. git log origin/main -1 -> acf3c28b (v0.759.0). git diff --stat origin/main...fix/remediation-2-4 shows no psh/version.py, CHANGELOG.md, README.md, ARCHITECTURE.md, docs/reviews/README.md, or tests/integration/redirection/test_process_sub_closed_fds.py entry.

## Task verdict: PASS-WITH-NITS

### NIT
Touched-files census is stale at the declared tip and one production file is never named anywhere in the ledger. The R7-D(4) list ('restated from git diff --name-only 1b271d77, not memory') enumerates 22 production files; the actual diff at d934a3ca has 25. io_redirect/process_sub.py and expansion/command_sub.py are named in R9-A/R10-A prose and covered by the brief's dated-amendment R9/R10 clause, but psh/executor/__init__.py (2-line export of expansion_child_suppression, commit d3db95a7, load-bearing: consumed via the extended deferred imports in command_sub.py:131 and process_sub.py:61/143) appears nowhere in the 2718-line ledger, and the cumulative list was never restated after rounds 9-10. Not false-when-written (round-7 list was accurate at round 7); a currency gap the integrator should have the dev or ceremony record close.

EVIDENCE:
git diff --name-only 1b271d77..fix/remediation-2-4 → 25 production files; grep 'executor/__init__' over /Users/pwilson/src/psh-r2-4/tmp/remediation-ledgers/2.4.md → no hits; git log 1b271d77..fix/remediation-2-4 -- psh/executor/__init__.py → d3db95a7

### NIT
Round-8's main work commit 112435bc ('the axis I held constant, and records that count') is never named by SHA in the ledger — the round-8 section names only the follow-up declared tip 55edb24f, and rounds 8-10 give round-total accounting rather than the per-commit splits rounds 1-6 provided. No FLIPPED/DELETED verdict is attributed to it, so item (c) is technically satisfied; recorded for the ceremony's per-commit reconciliation.

EVIDENCE:
git log --oneline origin/main..fix/remediation-2-4 shows 22 commits; ledger round-8 section cites only 55edb24f; grep 112435bc over 2.4.md → no hits

### NIT
Ceremony transcription risk on carry #22: the committed campaign LEDGER row 22 reads unqualified 'CLOSE via slot 2.4 (= HIGH-9)', but the slot's closure is integrator-ruled QUALIFIED (R4-C): HIGH-9/carry-22 close for the producer-tagged classes only, with the scanner-classified family (case-pattern/paren/quote-defeating bodies, ParseError with substitution_origin False) CARRIED via drafted row text to the r18 lexer successor. The integrator's LEDGER edit must carry the qualification and the new carry row, not an unqualified close.

EVIDENCE:
LEDGER.md row 22 (origin/main) vs dev ledger R4-C 'CLOSURE CLAIMS QUALIFIED, as ruled' + carry row text at 2.4.md lines ~899-926; scanner-route pin present at test_syntax_template_timing_conformance.py ~:768-783 on the branch

### NIT
The ledger's 'FLIP-PINS.md deliberately NOT edited — integrator-owned per ruling' cites a ruling that is not in the current INTEGRATOR-INBOX.md (which holds only ADDENDA 3-6; rounds 1-5 rulings were message-channel per the ledger's own dead-drop note). The brief's 2026-07-30 correction block ('FLIP-PINS row correction owed at ceremony. Integrator fault, tallied.') corroborates integrator ownership, and FLIP-PINS.md is absent from the branch diff as claimed, so the claim is consistent with the durable record — but the specific ruling has no dead-drop artifact. The dev's location-error report is itself verified: test_divergence_eval_source_procsub_joined_i3 lives in test_syntax_template_timing_conformance.py at base (I ran it there), not test_subscript_keying_conformance.py as FLIP-PINS.md line 16 states.

EVIDENCE:
grep -i flip-pins INTEGRATOR-INBOX.md → no ruling text; git diff --name-only 1b271d77..fix/remediation-2-4 contains no FLIP-PINS.md; base pytest run of the joined_i3 node from test_syntax_template_timing_conformance.py → passed

## Task verdict: PASS-WITH-NITS

### NIT
The ledger's fork-creator census paragraph (ROUND 10, 'FORK-CREATOR CENSUS FIRST') states its instrument inline (grep for fork_with_signal_window()/os.fork() over psh/) but carries no explicit caveat sentence that a creator reaching the OS by another route would escape that grep. Dev self-flagged this as their weakest claim. Verifier's independent wider hunt closed it: grep over subprocess/multiprocessing/posix_spawn/spawnl/spawnv/pty.fork/forkpty/os.popen/Popen/os.exec spellings under psh/ at d934a3ca finds ZERO additional process creators (only os.execvpe in the exec builtin, which is exec-in-place after fork, not a creator). The four-site census and the 'no fourth expansion-time creator' conclusion are TRUE; suggest the ceremony rescue add the one-sentence limitation for the durable record.

EVIDENCE:
grep -rnE 'subprocess|multiprocessing|posix_spawn|spawnl|spawnv|pty\.fork|forkpty|os\.popen|Popen|os\.exec' psh/ at d934a3ca: only comments/docs + os.execvpe in psh/interactive/signal_manager.py. Fork sites exactly 4: psh/expansion/command_sub.py:132, psh/io_redirect/process_sub.py:62 and :144, psh/executor/process_launcher.py:207.

## Task verdict: PASS-WITH-NITS

### NIT
Dangling symbol reference in the GOVERNING BRIEF (integrator-owned, not the dev's code): the DATED AMENDMENT's R9/R10 clause in /Users/pwilson/src/psh/tmp/remediation-ledgers/briefs/2.4.md authorises `psh/io_redirect/process_sub.py#ProcessSubstitutionHandler._pre_sever_suppression`, a symbol that exists NOWHERE in the tree at the branch tip. Round 10 landed that logic as `psh/executor/child_policy.py#expansion_child_suppression` (called from process_sub.py:92/:209 and command_sub.py:151-155). The amendment is the durable authorisation the ledger/brief pair needs at ceremony, so it should name the symbol that actually exists. Same class of record debt: FLIP-PINS.md still files the procsub co-flip under `test_subscript_keying_conformance.py` when it lives in `test_syntax_template_timing_conformance.py` (the brief already flags this correction as owed).

EVIDENCE:
$ grep -rn "_pre_sever_suppression" psh/ tests/   ->  (no output)
$ grep -rn "expansion_child_suppression" psh/ | head
psh/executor/child_policy.py:503:def expansion_child_suppression(
psh/executor/__init__.py:25,42 (export)
psh/expansion/command_sub.py:151
psh/io_redirect/process_sub.py:92, :209
$ git grep -n test_divergence_eval_source_procsub_joined_i3 origin/main -- tests/
origin/main:tests/conformance/bash/test_syntax_template_timing_conformance.py:212

### NIT
NOVEL ROW (not in the dev's suite): the chartered simple-member severing rule moves an errexit co-movement shape the dev's enumerated body space does not contain — an eval'd `return` — and the tip lands NEAR bash but not ON it. `set -e; { true | eval 'return 1; echo A'; } || echo GOT rc=$?; echo END` gives bash `GOT rc=1`, base `A` (no failure at all), tip `GOT rc=2`. The delta base->tip IS the chartered severing (member no longer carries the suppression, so errexit becomes effective in the eval'd text — correct, and structurally bash's answer). The residual 2-vs-1 is PRE-EXISTING, not the slot's: the unsuppressed twin answers bash 1 / base 2 / tip 2. This is the same class the integrator already dispositioned in ruling R10-C (external-command body) — recommend a matching SUCCESSOR/ledger row and one more clause on the co-movement census docstring's domain (its four bodies are an eval'd text, a sourced text, `false`, and a function call; `return` is a fifth). REPLAYED, both parsers, -c and file channels.

EVIDENCE:
file channel, /opt/homebrew/bin/bash 5.2.26 vs psh@1b271d77 vs psh@d934a3ca (--parser rd AND --parser combinator, identical):
  script: set -e / { true | eval 'return 1; echo A'; } || echo GOT rc=$? / echo END
  bash : GOT rc=1 | END
  base : A | END
  tip  : GOT rc=2 | END     (both parsers)
UNSUPPRESSED twin proves the residual is pre-existing:
  script: set -e / { true | eval 'return 1; echo A'; } / echo AFTER rc=$?
  bash rc=1   base rc=2   tip rc=2   (stdout empty in all three)

### NIT
Two further novel rows land on PRE-EXISTING psh divergences that the severing work now routes traffic through; neither is moved by the slot, and one already has an integrator disposition. (1) `set -e; { true | eval 'false; echo A' | cat; } || echo GOT; echo PS=${PIPESTATUS[*]}` — bash `PS=0 1 0`, psh `PS=0` at BOTH base and tip (the `A`-suppression half correctly moved to bash). That is the brace-group PIPESTATUS collapse already carried by the integrator's crossed ruling (b) 'PIPESTATUS collapse in brace groups: SUCCESSOR-QUEUE row text' — no action beyond confirming that row is written. (2) `set -o posix; set -e; { true | eval 'set -q'; } || echo GOT rc=$?; echo AFTER` — bash `GOT rc=1`, psh 2 at base AND tip. This is the eval'd neighbour of the dev's own unmoved control `{ true | set -q; }` (which matches bash at 2) and does not appear to have a ledger row; worth one line so the special-builtin-floor family's domain is stated.

EVIDENCE:
c and file channels, bash 5.2.26 / psh@1b271d77 / psh@d934a3ca:
[DIVERGE-CHANGED] three-member-middle  bash=(0,'PS=0 1 0\n') tip=(0,'PS=0\n') base=(0,'A\nPS=0\n')
[DIVERGE-UNMOVED] posix-floor-member-eval-setq  bash=(0,'GOT rc=1\nAFTER\n') tip=(0,'GOT rc=2\nAFTER\n') base=(0,'GOT rc=2\nAFTER\n')

### NIT
AUDIT RESULT SUMMARY (no action required; recorded so the integrator has the evidence). (a) Integrator-owned files UNTOUCHED: `git diff origin/main...fix/remediation-2-4 --stat -- psh/version.py CHANGELOG.md README.md ARCHITECTURE.md docs/reviews/README.md` is empty. (d) Plan §3 never-touch set (' 1 ', b]y, bugs.txt, d/, decomment.py, docs/reviews/README.md + uncommitted review docs): none appear in the 36-file diff. (b) Every hunk maps to a brief item or a recorded ruling — the errexit severing files (pipeline/function/command/context/core/strategies/subshell) to the DATED AMENDMENT R4-A..R8-B, process_sub.py/command_sub.py to the R9/R10 clause, core/trap_manager.py to R4-E's retroactive ratification in the dev ledger, tests/conftest.py + the PTY registry entry to the crossed ruling 'PTY policy edits: BOTH APPROVED', the -n/--validate pin to 'approved as executed'. No changed diagnostic strings; no live production code deleted (all `-` lines are signature/call-site updates or superseded docstrings). ruff `All checks passed`; mypy `Success: no issues found in 274 source files` (= base figure). (c) All 4 must-flip obligations discharged (both divergence pins renamed to equality pins with their param sets intact; golden `heredoc_nested_error_reports_absolute_line` changed exit_code 2->127 and NOTHING else — the only non-comment +/- pair in golden_cases.yaml). Must-NOT-flip pins textually untouched and GREEN at the tip.

EVIDENCE:
Green at d934a3ca: test_subscript_keying_conformance.py 218 passed; test_nested_substitution_timing_conformance.py + test_cv_carry_characterization.py 126 passed; test_syntax_template_timing_conformance.py 186 passed; test_history_p_interactive + posix_compliance + user_guide_notes 145 passed; heredoc_error_lineno/syntax_templates/syntax_template_guards/syntax_bearing_ast_fields_q2/subscript_evaluator 201 passed; unit/scripting + test_child_policy + no_direct_spawn + doc_snippets 240 passed; new PTY module 10 passed in 7.6s.
RED-CLAIM REPLAYS (all confirmed): psh -n -c 'echo $(if)' base rc=2 / tip rc=127 / bash 127; psh -c 'echo $(if)' base rc=2 / tip rc=127; psh --validate -c 'echo $(if)' base 2 / tip 2; teardown-under-errexit `set -e; trap 'echo $(fi)' EXIT; echo IN` bash rc=2 / base rc=0 / tip rc=0 (base-identical, as declared).
GUARD MUTATION (independent offender, aliased import, different module than the dev's synthetic): inserting `from ..core.exceptions import SubstitutionSyntaxAbort as _SSA` + `except _SSA: return 127` into psh/executor/subshell.py FAILED test_only_the_sanctioned_non_fork_catchers_exist AND test_status_mapping_is_not_re_derived_at_frames; tree restored clean.
NOVEL-ROW BATTERIES (122 fresh rows, one case per invocation, bash 5.2.26 vs psh@1b271d77 vs psh@d934a3ca): battery 1 (-c/file, 37 rows) = 44 MOVED-TO-BASH / 24 MATCH-UNMOVED / 2 DIVERGE-UNMOVED / 4 DIVERGE-CHANGED cells; battery 2 (stdin/-c/file, 13 rows incl. triple-nested eval, double-nested source, CLI --posix, bg-subshell+wait) = 26 MOVED-TO-BASH / 11 MATCH-UNMOVED / 2 DIVERGE-CHANGED (both the DECLARED O4 EXIT-trap 257-vs-1 row, process status matching at 1). ZERO MOVED-AWAY in either battery.
INDEPENDENT PTY PROBE (own sentinel/drive loop, rows the dev's module omits: `cat <(if)`, `. badfile`, `${a[$(fi)]}`, a function call): REPL survived every row at bash, base AND tip — 0 deaths. The brief's explicit bounce condition is not tripped.

