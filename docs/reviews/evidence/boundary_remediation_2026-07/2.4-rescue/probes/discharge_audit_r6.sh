#!/bin/bash
# ROUND-6 DISCHARGE AUDIT — every ruling item -> an artifact and the check that
# proves it, run at the declared tip. An item is discharged when a grep shows
# it IN THE TREE (or in an instrument's OUTPUT), never when someone believes it
# was done. Exits non-zero if any row FAILs.
#
# Usage: bash tmp/r24-probes/discharge_audit_r6.sh
# Prerequisite: bash tmp/r24-probes/run_r6_batteries.sh has been run AT THIS TIP
# (the *-TIP.txt outputs must carry this SHA in their header).
set -u
cd "$(dirname "$0")/../.." || exit 1
SHA=$(git rev-parse HEAD)
FAILS=0

echo "DISCHARGE AUDIT at $SHA"
echo "| item | status | instrument (path :: pattern that must match)"

row() { printf '| %-34s | %-8s | %s\n' "$1" "$2" "$3"; }
chk() { # name, path, pattern
  if grep -q "$3" "$2" 2>/dev/null; then row "$1" "PASS" "$2 :: /$3/"
  else row "$1" "**FAIL**" "$2 :: /$3/ NOT FOUND"; FAILS=$((FAILS+1)); fi
}
nchk() { # name, path, pattern that must NOT match
  if grep -q "$3" "$2" 2>/dev/null; then row "$1" "**FAIL**" "$2 :: /$3/ STILL PRESENT"; FAILS=$((FAILS+1))
  else row "$1" "PASS" "$2 :: /$3/ absent"; fi
}
stamped() { # name, path — the instrument output must carry THIS tip's SHA
  if head -1 "$2" 2>/dev/null | grep -q "$SHA"; then row "$1" "PASS" "$2 :: SHA $SHA"
  else row "$1" "**FAIL**" "$2 :: header does not carry $SHA"; FAILS=$((FAILS+1)); fi
}

echo "--- round 5 rows (carried forward; they must still hold) ---"
chk "R5-C1 O3 docstring fixed"      tests/conformance/bash/test_syntax_template_timing_conformance.py "RECORD CORRECTION (round 4 . 5)"
chk "R5-C1 non-fork domain"         tests/conformance/bash/test_syntax_template_timing_conformance.py "in the NON-FORK case"
chk "R5-C2 posix-fork pin"          tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_posix_option_times_fork_matrix"
chk "R5-C3 record preserved"        tests/conformance/bash/test_syntax_template_timing_conformance.py "base-identical / not mine"
chk "R5-D guard: one raise site"    tests/unit/tooling/test_substitution_abort_guards.py "def test_only_one_raise_site_for_the_abort"
chk "R5-D guard: catchers"          tests/unit/tooling/test_substitution_abort_guards.py "def test_only_the_sanctioned_non_fork_catchers_exist"
chk "R5-D guard: no re-derivation"  tests/unit/tooling/test_substitution_abort_guards.py "def test_status_mapping_is_not_re_derived_at_frames"
chk "R5-D offenders actually run"   tests/unit/tooling/test_substitution_abort_guards.py "def test_guard2_bites_on_a_synthetic_second_catcher"
chk "R5-E errexit_suppressed arm"   tests/unit/executor/test_child_policy.py "def test_substitution_syntax_abort_errexit_suppressed_arm"
chk "R5-F1 -i -c pin"               tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_interactive_dash_c_channel_disposition"

echo "--- R6-A: the background fork site carries the forking depth ---"
chk "R6-A seed threaded"            psh/executor/subshell.py "_errexit_suppress_seed = errexit_suppress"
chk "R6-A bg branch takes it"       psh/executor/subshell.py "errexit_suppress=errexit_suppress"

echo "--- R6-B: the pipeline-member suppression boundary ---"
chk "R6-B member reset"             psh/executor/pipeline.py "errexit_suppress"
chk "R6-B function-body restore"    psh/executor/function.py "errexit_suppress"
chk "R6-B pin exists"               tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_pipeline_member_suppression_matches_bash"

echo "--- R10: the option axis at the cmdsub creator ---"
chk "R10-A shared helper"           psh/executor/child_policy.py "def expansion_child_suppression"
chk "R10-A cmdsub passes it"        psh/expansion/command_sub.py "errexit_suppress_override=expansion_child_suppression"
chk "R10-A procsub delegates"       psh/io_redirect/process_sub.py "expansion_child_suppression(shell._current_executor)"
nchk "R10-A no duplicate arithmetic" psh/io_redirect/process_sub.py "def _pre_sever_suppression"
chk "R10-A option-axis pin"         tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_member_cmdsub_keeps_pre_sever_context_under_inherit_errexit"
chk "R10-A creator census"          tmp/remediation-ledgers/2.4.md "FORK-CREATOR CENSUS FIRST"
chk "R10-B mechanism scoped"        tests/conformance/bash/test_syntax_template_timing_conformance.py "THE OPTION AXIS IS THE EXCEPTION"
chk "R10-B fifth instance"          tmp/remediation-ledgers/2.4.md "FIFTH INSTANCE"
chk "R10-C successor row (h)"       tmp/remediation-ledgers/2.4.md "SUCCESSOR ROW (h)"
chk "R10-C census domain scoped"    tests/conformance/bash/test_syntax_template_timing_conformance.py "four SHELL bodies"
chk "R10-D green-on-base table"     tmp/remediation-ledgers/2.4.md "why green at base is right"
chk "R10-E amendment R9/R10 clause" tmp/remediation-ledgers/2.4.md "R9/R10 clause"
echo "--- R9: the member x substitution intersection ---"
chk "R9-A expansion-time seed"      psh/io_redirect/process_sub.py "self.shell, for_expansion=True"
chk "R9-A override forwarded"       psh/executor/child_policy.py "errexit_suppress_override"
chk "R9-A redirect NOT overridden"  psh/executor/child_policy.py "spelling is deliberately NOT overridden"
chk "R9-A/B intersection pin"       tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_member_substitution_children_keep_the_pre_sever_context"
chk "R9-A cmdsub answer pinned"     tests/conformance/bash/test_syntax_template_timing_conformance.py "WHY THE CMDSUB TWIN DOES NOT MOVE"
chk "R9-B universal corrected"      tests/conformance/bash/test_syntax_template_timing_conformance.py "MEASURED AT THE SEVERED-MEMBER ROUTE TOO"
chk "R9-C PTY invariant scoped"     tests/system/interactive/test_substitution_abort_interactive_pty.py "SCOPE OF THAT INVARIANT"
chk "R9-C successor row (g)"        tmp/remediation-ledgers/2.4.md "SUCCESSOR ROW (g)"
chk "R9-E nightly caveat"           tests/system/interactive/test_substitution_abort_interactive_pty.py "FOR A NIGHTLY READER"
chk "R9-D amendment cited"          tmp/remediation-ledgers/2.4.md "DATED AMENDMENT (2026-07-31, integrator)"
nchk "R9-E committed wording gone"  tests/conformance/bash/test_syntax_template_timing_conformance.py "its committed output"
echo "--- R8: the spelling axis, the enumeration, both parsers ---"
chk "R8-A redirect-procsub pin"     tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_redirect_procsub_suppression_is_a_declared_divergence"
chk "R8-A scope qualifier"          tests/conformance/bash/test_syntax_template_timing_conformance.py "It is NOT a route-universal"
chk "R8-A route claim corrected"    tmp/remediation-ledgers/2.4.md "FALSE for the"
chk "R8-A successor row (f)"        tmp/remediation-ledgers/2.4.md "SUCCESSOR ROW (f)"
chk "R8-A stop-and-report recorded" tmp/remediation-ledgers/2.4.md "STOP-AND-REPORT — one production docstring"
chk "R8-B hunt instrument"          tmp/r24-probes/r8b-hunt-TIP.txt "MOVED-TO-BASH"
chk "R8-B hunt has no regressions"  tmp/r24-probes/r8b-hunt-TIP.txt "ROWS: 186"
nchk "R8-B no MOVED-AWAY rows"      tmp/r24-probes/r8b-hunt-TIP.txt "^MOVED-AWAY"
chk "R8-B pin cites the hunt"       tests/conformance/bash/test_syntax_template_timing_conformance.py "r8b_hunt.py"
chk "R8-B widening rows"            tests/conformance/bash/test_syntax_template_timing_conformance.py "WIDENING (ruling R8-B)"
chk "R8-C both-parser sweep"        tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_new_families_agree_across_parsers"
chk "R8-D pointer qualified"        tests/conformance/bash/test_syntax_template_timing_conformance.py "executor/core.py#_execute_background_list"
chk "R8-D nightly note"             tmp/remediation-ledgers/2.4.md "PTY module and the Linux nightly"
chk "R8-D audit count corrected"    tmp/remediation-ledgers/2.4.md "60 .chk. + 8 .nchk. = 68"
chk "R8-D successor (e) merged-ref" tmp/remediation-ledgers/2.4.md "MERGE AT CEREMONY"
chk "R8 guard assignment aliases"   tests/unit/tooling/test_substitution_abort_guards.py "an ASSIGNMENT alias"
chk "R8 guard limit stated"         tests/unit/tooling/test_substitution_abort_guards.py "KNOWN LIMIT, stated rather than implied"
chk "R8 pin temp-dir hygiene"       tests/conformance/bash/test_syntax_template_timing_conformance.py "PRIVATE temp dir"
echo "--- R7-A: the severing rule at EVERY route ---"
chk "R7-A bg sever hook"            psh/executor/child_policy.py "sever_errexit_context"
chk "R7-A bg bare-simple severs"    psh/executor/strategies.py "sever_errexit_context=context"
chk "R7-A one-shot consumption"     psh/executor/command.py "is not DispatchKind.FUNCTION"
chk "R7-A dropped seed threaded"    psh/executor/core.py "errexit_suppress=self.context.errexit_suppress"
chk "R7-A bg pin"                   tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_background_fork_severing_matches_bash"
chk "R7-A one-shot pin"             tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_deferred_suppression_is_one_shot"
echo "--- R7-B: the ordinary-errexit co-movements ---"
chk "R7-B co-movement pin"          tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_ordinary_errexit_co_movements_are_declared"
echo "--- R7-C: production corrections ---"
chk "R7-C probe claim corrected"    psh/core/internal_errors.py "Probed per ROUTE"
nchk "R7-C false claim gone"        psh/core/internal_errors.py "probe-verified for subshell,"
chk "R7-C pointer resolves"         psh/executor/context.py "FunctionOperationExecutor._function_frame"
nchk "R7-C dangling pointer gone"   psh/executor/context.py "#FunctionExecutor\."
chk "R7-C alias resolution"         tests/unit/tooling/test_substitution_abort_guards.py "def _local_aliases"
chk "R7-C alias offenders run"      tests/unit/tooling/test_substitution_abort_guards.py "def test_guards_resolve_import_aliases"
echo "--- R6-C: the interactive family, at a real terminal ---"
chk "R6-C PTY pin module"           tests/system/interactive/test_substitution_abort_interactive_pty.py "def test_interactive_substitution_abort_disposition"
chk "R6-C PTY module registered"    tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py "test_substitution_abort_interactive_pty.py"
chk "R6-C PTY site count pinned"    tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py "test_substitution_abort_interactive_pty.py\": 2"
chk "R6-C PTY pin runs by default"  tests/conftest.py "test_substitution_abort_interactive_pty"
chk "R6-C falsified absolute fixed" tests/conformance/bash/test_syntax_template_timing_conformance.py "RECORD CORRECTION (round 5 -> 6)"
nchk "R6-C old absolute gone"       tests/conformance/bash/test_syntax_template_timing_conformance.py "and only on the direct shape\."
chk "R6-C -n / --validate pin"      tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_static_check_spellings_dash_n_and_validate"
chk "R6-C successor row written"    tmp/remediation-ledgers/2.4.md "children of interactive shells keep the legacy statuses"

echo "--- R6-D: the embedding contract ---"
chk "R6-D run_command docstring"    psh/shell.py "EMBEDDING CONTRACT"
chk "R6-D core CLAUDE.md note"      psh/core/CLAUDE.md "IN-PROCESS EMBEDDING BOUNDARY"
chk "R6-D pin exists"               tests/unit/scripting/test_embedding_abort_contract.py "def test_script_mode_lets_the_abort_escape_run_command"
chk "R6-D control pin exists"       tests/unit/scripting/test_embedding_abort_contract.py "def test_the_escape_is_not_a_generic_syntax_error_escape"

echo "--- R7-D: the round-6 record corrections ---"
chk "R7-D(1) red-on-base corrected" tmp/remediation-ledgers/2.4.md "CORRECTED: 5 of 6 fail"
chk "R7-D(1) instrument committed"  tmp/r24-probes/r7d-redonbase.txt "5 failed, 1 passed"
chk "R7-D(2) four not two"          tmp/remediation-ledgers/2.4.md "CORRECTED: there were FOUR"
nchk "R7-D(2) dies-with-1 gone"     tests/conformance/bash/test_syntax_template_timing_conformance.py "child dies with 1 and the parent"
nchk "R7-D(2) flat-1 gone"          tests/unit/executor/test_child_policy.py "Flat 1 in every channel\."
chk "R7-D(3) audit count corrected" tmp/remediation-ledgers/2.4.md "script had 55 checks; the 56th"
chk "R7-D(4) file list restated"    tmp/remediation-ledgers/2.4.md "restated from .git diff --name-only"
chk "R7-D(5) 360090b2 names file"   tmp/remediation-ledgers/2.4.md "It touched \*\*.psh/executor/subshell.py"
chk "R7-D scope accounting"         tmp/remediation-ledgers/2.4.md "SCOPE ACCOUNTING"
chk "R7 concurrency self-report"    tmp/remediation-ledgers/2.4.md "Self-reported process error this round"
echo "--- R6-E: the record corrections ---"
chk "R6-E accounting corrected"     tmp/remediation-ledgers/2.4.md "CORRECTED: 54001334 = +11, 5121ec8b = +0"
chk "R6-E collect-only pasted"      tmp/remediation-ledgers/2.4.md "340 tests collected"
chk "R6-E COND1 cause stated"       tmp/remediation-ledgers/2.4.md "the failure is a CORPUS GAP, not a stale"
chk "R6-E R5-F(2) recorded dropped" tmp/remediation-ledgers/2.4.md "R5-F(2) (the PTY fork×errexit row) — was DROPPED"
chk "R6-E R5-E closure recorded"    tmp/remediation-ledgers/2.4.md "ONLY in commit 5121ec8b.s message"

echo "--- R6-F: guards that bite, and the stale docstrings ---"
chk "R6-F raise detector symmetric" tests/unit/tooling/test_substitution_abort_guards.py "def _exc_name"
chk "R6-F rederive detector is AST" tests/unit/tooling/test_substitution_abort_guards.py "def _find_rederive_sites"
nchk "R6-F line regex gone"         tests/unit/tooling/test_substitution_abort_guards.py "_REDERIVE = re.compile"
chk "R6-F evasion offenders run"    tests/unit/tooling/test_substitution_abort_guards.py "two lines"
chk "R6-F attr-raise offender runs" tests/unit/tooling/test_substitution_abort_guards.py "def test_guard1_bites_on_an_attribute_qualified_raise_site"
chk "R6-F arity fixed"              psh/executor/child_policy.py "substitution_child_abort_status(state,"
nchk "R6-F stale launcher sentence" psh/executor/child_policy.py "passes the default"
chk "R6-F getattr claim corrected"  psh/scripting/source_processor.py "What is explicit here is the CONTEXT read"
chk "R6-F suppression unit arms"    tests/unit/scripting/test_errexit_suppressed_read.py "def test_a_live_executor_without_a_context_raises"
chk "R6-F teardown-errexit pin"     tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_exit_trap_teardown_under_errexit_is_a_declared_divergence"

echo "--- instrument outputs: stamped with THIS tip and carrying their verdict ---"
for battery in r6b r6b2 r6b3 r6b4 r6b5 r6f r7a r8a r9a r10a r6c_flags r6d_embed r6_bounced r6c_pty; do
    stamped "instrument $battery" "tmp/r24-probes/${battery}-TIP.txt"
done
stamped "chain table"               tmp/r24-probes/r6b-CHAIN-TIP.txt
chk "BOUNCED ROWS all pass"         tmp/r24-probes/r6_bounced-TIP.txt "SUMMARY: 99/99 rows PASS, 0 FAIL"
nchk "chain: no REGRESSION rows"    tmp/r24-probes/r6b-CHAIN-TIP.txt "^REGRESSION "
chk "guard-bite transcript"         tmp/r24-probes/guard-bite-TIP.txt "$SHA"

echo
if [ "$FAILS" -eq 0 ]; then echo "DISCHARGE AUDIT: ALL ROWS PASS at $SHA"; else echo "DISCHARGE AUDIT: $FAILS ROW(S) FAILED at $SHA"; fi
exit "$FAILS"
