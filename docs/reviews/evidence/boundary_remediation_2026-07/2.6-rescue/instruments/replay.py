#!/usr/bin/env python3
"""Bounced-rows replay + discharge audit for slot 2.6.

BOUNCED ROWS. No verifier round has run yet, so the replay set is every row
that FAILED at some point during this slot's own implementation and had to be
resolved — self-found blockers are still blockers, and a resolution that was
never re-checked at the final tip is a claim, not a fact. Each row records what
failed, why, and how it was resolved; the replay re-runs the exact test IDs at
the declared tip.

DISCHARGE AUDIT. Every ledger claim must name the instrument that produced it
and be reproducible at the recorded SHA. This script re-runs each instrument
and reports totals DERIVED from the run, never hand-tallied.
"""
from __future__ import annotations

import subprocess
import sys

REPO = "/Users/pwilson/src/psh-r2-6"

# (label, what failed and why, resolution, test ids to replay)
BOUNCED = [
    ("B1 stale mode-flag spelling",
     "4 convergence tests set shell.<mode>_only, which the single-mode "
     "representation removed; they pin behavior, not the flag's spelling",
     "setup updated to shell.analysis_mode = '<mode>'",
     ["tests/unit/scripting/test_lex_parse_convergence.py::test_delta_c_format_preserves_alias_word",
      "tests/unit/scripting/test_lex_parse_convergence.py::test_analysis_internal_defect_raises_under_strict",
      "tests/unit/scripting/test_lex_parse_convergence.py::test_analysis_internal_defect_reports_without_strict",
      "tests/unit/scripting/test_lex_parse_convergence.py::test_analysis_syntax_error_still_clean_under_strict"]),

    ("B2 parse-error envelope changed",
     "the session wraps a unit's parse failure in a typed AnalysisSyntaxError "
     "so the diagnostic can name the failing unit; a test expected the bare "
     "ParseError",
     "test asserts the typed wrapper AND that .error is still a ParseError — "
     "the parse verdict it pins is unchanged",
     ["tests/unit/scripting/test_lex_parse_convergence.py::test_delta_b_lexer_options_reach_nested_substitution"]),

    ("B3 declared flip",
     "test_analysis_modes_ordered pinned parse_invocation RETAINING two modes; "
     "retention was never honoured downstream",
     "replaced by test_distinct_analysis_modes_rejected over 11 flag shapes",
     ["tests/unit/test_parse_invocation.py::TestDebugAndAnalysisFlags::test_distinct_analysis_modes_rejected",
      "tests/unit/test_parse_invocation.py::TestDebugAndAnalysisFlags::test_analysis_mode_deduplicated",
      "tests/unit/test_parse_invocation.py::TestDebugAndAnalysisFlags::test_single_analysis_mode_still_accepted"]),

    ("B4 line offset not reaching the parser",
     "6 line-diagnostic rows reported line 1: the session parsed each unit "
     "without base_line, so ParseError carried unit-relative lines",
     "base_line=start_line threaded, mirroring SourceProcessor._parse_command",
     ["tests/system/test_analysis_state_aware.py::TestUnitLineDiagnostics::test_syntax_error_carries_its_line"]),

    ("B5 combinator top-level line (2.2 carry, NOT this slot's)",
     "3 combinator rows still reported line 1 after B4 — execution reports the "
     "same line, at base and at tip; the pre-existing 2.2 carry",
     "pin reshaped to compare analysis against EXECUTION per parser, plus a "
     "labelled carry tripwire that announces the carry closing",
     ["tests/system/test_analysis_state_aware.py::TestUnitLineDiagnostics::test_analysis_location_matches_execution_location",
      "tests/system/test_analysis_state_aware.py::TestUnitLineDiagnostics::test_combinator_toplevel_line_is_the_2_2_carry"]),

    ("B6 wrong reference arm in my own test",
     "the formatter-parity row compared against a whole-file parse that "
     "skipped continuation joining — the instrument was wrong, not the session",
     "reference arm applies process_line_continuations, reproducing what base "
     "analysis actually did",
     ["tests/unit/scripting/test_analysis_session.py::TestPerUnitParseMatchesWholeFileWhenNothingChanges"]),

    ("B9 heredoc BODIES lexed as command text (round-1 B-1, REGRESSION)",
     "the alias-absorption pass re-tokenized each unit's RAW text, so a body "
     "was lexed as commands: apostrophe = false rc 2 on 4/5 modes, alias text "
     "in a body absorbed as state, and the lex error escaped the envelope",
     "one lex per unit; the SAME heredoc-aware stream feeds parse AND "
     "absorption, so a body is never lexed at all",
     ["tests/system/test_analysis_state_aware.py::TestHeredocBodiesAreNotCommandText"]),

    ("B10 constant missing an option my own census found (round-1 B-2)",
     "PARSE_RELEVANT_OPTIONS shipped 2 of the 3 the census found, under a "
     "docstring claiming the instruments agreed on exactly those two; the "
     "guard scanned two packages and structurally could not see the third",
     "expand_aliases threaded with its measured (ordered, non-monotone) "
     "semantics; guard now traces the PIPELINE and compares both directions",
     ["tests/unit/scripting/test_analysis_session.py::TestParseRelevantOptionsIsDerived",
      "tests/system/test_analysis_state_aware.py::TestExpandAliasesIsOrderedNotMonotone"]),

    ("B11 six directive SPELLINGS missed (round-1 B-4)",
     "builtin/command prefixes, backslash-escaped head, assignment prefix, "
     "clustered -sq and `set -e -o extglob` all execute the enable; analysis "
     "recognized none while claiming to find every ENABLE in a unit",
     "head normalized through the transparent prefixes; clustered flags read "
     "by letter; nine spellings pinned + eight near-miss controls",
     ["tests/system/test_analysis_state_aware.py::TestDirectiveSpellingAxis"]),

    ("B12 --help/--version lost to the mode conflict (round-1 nit R8-E-1)",
     "the exclusivity rule raised before help/version were honoured, so "
     "`psh --help --validate --lint` became a usage error; base answered rc 0",
     "help and version short-circuit the conflict in any argv order; pinned "
     "at both the pure-parser and CLI levels",
     ["tests/unit/test_parse_invocation.py::TestDebugAndAnalysisFlags::test_help_and_version_outrank_the_mode_conflict",
      "tests/system/test_analysis_state_aware.py::TestModeCombinationRejected::test_help_and_version_still_answer"]),

    ("B13 alias absorption dropped the POSITION guard (round-2 D-1, REGRESSION)",
     "the round-1 fix scanned each unit's tokens for the words alias/unalias "
     "with no command-position guard: `echo unalias -a` wiped the analysis "
     "table (false red) and `echo alias x=...` created one (false green)",
     "absorption RUNS AliasManager.expand_aliases with the session table as "
     "its overlay, inheriting the position discipline instead of re-deriving "
     "it; alias-axis near-miss controls added",
     ["tests/system/test_analysis_state_aware.py::TestAliasPositionDiscipline"]),

    ("B14 user guide contradicted the branch's own pins (round-2 D-2)",
     "the limits bullets declared ALL options monotone, false for "
     "expand_aliases since R8-B and contradicted by the declared-cost pin",
     "monotone bullets scoped to extglob/posix; the ordered rule and its cost "
     "stated in user-facing words with a worked example; two pins hold the "
     "doc to the rule",
     ["tests/unit/scripting/test_analysis_session.py::TestUserGuideMatchesTheRule"]),

    ("B15 recognizer boundaries measured, not assumed (round-2 R9-C 1/2/3)",
     "`set -- -o extglob` was read as an option change; `shopt -su` was read "
     "as an enable; a backslash mid-head hid the directive",
     "-- ends scanning; a contradictory cluster changes nothing (both shells "
     "refuse it); backslashes anywhere in the head are quoting — all three "
     "measured against bash 5.2.26 then encoded",
     ["tests/system/test_analysis_state_aware.py::TestDirectiveSpellingAxis"]),

    ("B16 head normalizer was QUOTE-BLIND (round-3 R11-A, REGRESSION)",
     "backslashes were stripped unconditionally, so `'sh\\opt'` — a command "
     "of that literal name — was read as shopt: a quoted head invented an "
     "expand_aliases DISABLE (false red) and an extglob ENABLE (false green); "
     "two operand/flag mirrors were missed for the mirror-image reason",
     "_effective_words reads the lexer's per-part quoted/quote_char verdict "
     "and everything downstream consumes its output; expansion heads resolve "
     "to None (declared residual) rather than being guessed",
     ["tests/system/test_analysis_state_aware.py::TestQuotedHeadIsNotADirective",
      "tests/system/test_analysis_state_aware.py::TestDirectiveSpellingAxis"]),

    ("B17 the CLASS: three re-derivations of known facts (round-3 R11-A2)",
     "R8-A lexed heredoc bodies the lexer had set aside; R9-A re-walked tokens "
     "the alias decider walks, losing its position guard; R11-A stripped "
     "backslashes the lexer had already classified — all three passed review "
     "and a green gate",
     "sanctioned-sites guard: every string-surgery site in the session module "
     "is enumerated with a written justification, stale entries are rejected, "
     "and the scan is mutation-proven against a planted site",
     ["tests/unit/scripting/test_analysis_session.py::TestNoUnsanctionedStringSurgery"]),

    ("B18 -su refusal applied per WORD, not per command (round-4 R13-A)",
     "`shopt -s -u X` as SEPARATE words fell through to last-write-wins and "
     "invented a state change the builtin refuses; the repo's own "
     "test_shopt_set_o.py#test_s_and_u_conflict already pinned BOTH forms",
     "the whole flag-word set is aggregated before deciding; separate-word "
     "contradictory rows join the near-miss corpora on both axes",
     ["tests/system/test_analysis_state_aware.py::TestDirectiveSpellingAxis"]),

    ("B19 THREE FALSE DISCHARGE RECORDS (round-4 R13-B)",
     "the round-3 addendum claimed N1/N12/N13 done: N1 shipped ENABLE mirrors "
     "for an order about DISABLE shapes (silent substitution of a "
     "deliverable), N12's declaration line landed nowhere, and N13's record "
     "did not exist — its own sentence was its only evidence",
     "all three executed AS ORDERED and the false claims STRUCK IN PLACE; "
     "R13-C's mechanism adopted — a discharge is complete only when a "
     "certification row asserts its post-state",
     ["tests/system/test_analysis_state_aware.py::TestAliasAxisNormalizationAsymmetry",
      "tests/unit/scripting/test_analysis_session.py::TestNoUnsanctionedStringSurgery"]),

    ("B8 dead helper shipped into the branch (self-found, R5-B)",
     "unit_texts() had ZERO references in psh/ or tests/ — the zero-reference "
     "class the campaign outlawed; found by self-attack before a verifier saw it",
     "deleted in 62f2bd45; replayed as an ABSENCE check, since the fix is that "
     "the symbol is gone (a test would be the very shape that was wrong)",
     None),

    ("B7 campaign ratchet caught this slot's own code",
     "import-layering ratchet: analysis_session 9 deferred imports vs cap 0, "
     "visitor_modes 9 -> 10",
     "hoisted everything (carrier via type(shell)); caps ratcheted DOWN, zero "
     "allowlist entries",
     ["tests/unit/tooling/test_import_layering.py"]),

    # ---- ROUND-5 (R15): six distinct defects. ------------------------------
    ("B20 a pin that existed and never ran (round-5, R15-B-A)",
     "a blind substring rename turned test_offset_line_numbers_... into "
     "testoffset_line_numbers_..., which python_functions = test_* does not "
     "collect: the round-3 disclosure pin was in the tree and absent from "
     "every run, and no text-based check could tell the difference — the "
     "FIFTH blind-string-edit instance in this slot",
     "prefix restored (21 -> 22 collected in that module); certification "
     "gained a `collected` row kind asserting pytest's own collection, and a "
     "tree-wide guard now fails on the name shape in any collected file",
     ["tests/unit/visitor/test_walk_ast_schema.py::test_offset_line_numbers_reaches_stamped_template_sub_nodes",
      "tests/unit/tooling/test_no_uncollected_test_names.py"]),

    ("B21 flag letters read past the first operand (round-5, R15-B-B)",
     "_option_changes aggregated flag letters over the WHOLE argument list, "
     "so `shopt -q extglob -s` invented an enable the shell declines to make "
     "and `shopt -s extglob -u` missed one it really applies; the deciding "
     "spec was already pinned in the repo at "
     "test_shopt_set_o.py#test_flag_after_operand_is_an_operand — the third "
     "time this slot",
     "_shopt_split mirrors the builtin's own argument loop (first-operand "
     "stop, `--`, bad-letter abort, -o table selection); measured 9 "
     "analysis-vs-execution disagreements at e1113813, 0 at this tip",
     ["tests/system/test_analysis_state_aware.py::TestShoptFlagWordArrangement",
      "tests/unit/scripting/test_analysis_session.py::TestShoptTableRoutingIsDerived"]),

    ("B22 debug trace leaking into analysis (round-5, R15-B-C / R13-E7)",
     "the carrier inherited debug options, so --debug-exec --validate printed "
     "a terminal-detection line describing work that never happened; R13-E7 "
     "had been recorded as handled with only half delivered",
     "the carrier is built with every registered debug option off, in a "
     "window around the construction because one line is emitted DURING it; "
     "the scope manager's own flag rides the same window; silence pinned "
     "across all five modes WITH the execution control that the trace still "
     "fires where it belongs",
     ["tests/system/test_analysis_state_aware.py::TestDebugTraceDoesNotLeakIntoAnalysis",
      "tests/unit/scripting/test_analysis_session.py::TestCarrierDoesNotInheritDebugOptions"]),

    ("B23 five-mode parity ordered and not delivered (round-5, R13-E9)",
     "the no-option-change byte-identical claim was ordered extended to ALL "
     "FIVE modes and was not",
     "65 cells (13 scripts x 5 modes) driving the REAL mode runner over both "
     "programs, with the F7 exclusion itself pinned as a required DIFFERENCE "
     "— which is also the proof the comparison can fail at all",
     ["tests/unit/scripting/test_analysis_session.py::TestPerUnitParseMatchesWholeFileWhenNothingChanges"]),

    ("B24 a cert row anchored where it could not bite (round-5, R15-B-F)",
     "the R13-A row anchored the extglob corpus row `shopt -s -u extglob`, "
     "which was GREEN at 9b78098a: the per-word rule it replaced happened to "
     "give the right answer for that spelling, so the pin never detected the "
     "defect it pinned",
     "measured at 9b78098a with today's module — the row actually RED there "
     "is the alias-axis `shopt -s -u expand_aliases`, green at e1113813 — and "
     "the cert row is re-anchored to it",
     ["tests/system/test_analysis_state_aware.py::TestShoptFlagWordArrangement::test_analysis_agrees_with_execution_about_expand_aliases"]),

    ("B26 the twin sentence, and the family it belonged to (round-6, R21-A)",
     "tests/conformance/bash/test_identifier_policy_conformance.py carried the "
     "VERBATIM twin of the false whole-file-parse sentence the guide "
     "correction fixed — probe-false at every commit, and contradicting the "
     "corrected guide since. The first fix corrected one copy of a sentence "
     "that had already reproduced once",
     "the REASON corrected against measurement (runtime `set -o posix` DOES "
     "reach the parse of later commands); the verifier's grep PROMOTED to a "
     "certification row asserting the whole phrase FAMILY absent tree-wide, so "
     "a third twin cannot survive",
     ["tests/conformance/bash/test_identifier_policy_conformance.py"]),

    ("B25 structural paths around the envelope and the guards (round-5, R15-B-G)",
     "absorption ran OUTSIDE the AnalysisSyntaxError envelope (an exception "
     "there would escape unlabelled); the conflicting-mode error was a bare "
     "ValueError; the isolation guard enumerated CompoundCommand subclasses "
     "while the code classifies by type name over everything walk_ast reaches "
     "— two of the three isolating shapes are not CompoundCommands, so the "
     "guard's universe did not contain the answers the code was giving",
     "absorption moved inside the envelope and pinned by making it fail on "
     "purpose; AnalysisModeConflictError typed next to InvocationError; the "
     "guard's universe is now the 37-type traversal schema plus the two "
     "conditional rules; invocation error precedence pinned whole",
     ["tests/unit/scripting/test_analysis_session.py::TestEveryPerUnitFailureReachesTheEnvelope",
      "tests/unit/scripting/test_analysis_session.py::TestIsolationClassificationIsTotal",
      "tests/unit/scripting/test_analysis_session.py::TestSingleAnalysisMode",
      "tests/unit/test_parse_invocation.py::TestDebugAndAnalysisFlags"]),
]

INSTRUMENTS = [
    ("I2 harness self-check", ["python", "harness.py", "selfcheck"], "0 failure(s)"),
    ("certification (all rows)", ["python", "certify.py"], "rows pass"),
    ("certification mutation proofs", ["python", "certify.py", "--mutate"],
     "0 class(es) did not fail"),
    ("certification self-check", ["python", "certify.py", "--self-check"],
     "0 problem(s)"),
]


def main() -> int:
    tip = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    print(f"REPLAY + DISCHARGE AUDIT at tip {tip}\n")

    print("=" * 72)
    print("BOUNCED-ROWS REPLAY")
    print("=" * 72)
    total = passed = 0
    for label, what, how, ids in BOUNCED:
        if ids is None:
            # ABSENCE row: the ordered state is that a symbol no longer exists.
            grep = subprocess.run(
                ["git", "-C", REPO, "grep", "-n", "unit_texts", "--",
                 "psh", "tests"], capture_output=True, text=True)
            ok = grep.returncode != 0 and not grep.stdout.strip()
            print(f"{'PASS' if ok else 'FAIL'} {label}")
            print(f"      was: {what}")
            print(f"      fix: {how}")
            print(f"      replay: {'0 references at tip' if ok else grep.stdout}")
            total += 1
            passed += 1 if ok else 0
            continue
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", *ids],
            capture_output=True, text=True, cwd=REPO)
        line = [x for x in proc.stdout.splitlines() if " passed" in x or " failed" in x]
        summary = line[-1] if line else "(no summary)"
        n = int(summary.split(" passed")[0].split()[-1]) if " passed" in summary else 0
        ok = proc.returncode == 0
        total += n
        passed += n if ok else 0
        print(f"{'PASS' if ok else 'FAIL'} {label}")
        print(f"      was: {what}")
        print(f"      fix: {how}")
        print(f"      replay: {summary}")
    print(f"\nBOUNCED-ROWS REPLAY TOTAL: {passed}/{total} tests green "
          f"across {len(BOUNCED)} bounced rows")

    print()
    print("=" * 72)
    print("DISCHARGE AUDIT — every instrument re-run at this tip")
    print("=" * 72)
    bad = 0
    for label, cmd, expect in INSTRUMENTS:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=f"{REPO}/tmp/2.6-probes")
        ok = proc.returncode == 0 and expect in proc.stdout
        bad += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} {label:<34} (expect {expect!r})")
    print(f"\nDISCHARGE AUDIT: {len(INSTRUMENTS) - bad}/{len(INSTRUMENTS)} "
          f"instruments reproduce at {tip}")
    return 1 if (bad or passed != total) else 0


if __name__ == "__main__":
    raise SystemExit(main())
