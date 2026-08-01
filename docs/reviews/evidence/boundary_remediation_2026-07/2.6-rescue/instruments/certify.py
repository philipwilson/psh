#!/usr/bin/env python3
"""Slot 2.6 certification instrument (R0-5).

Certifies that each RULING in R1 produced its ORDERED CHANGE in the committed
tree. Built to the 2.5 end-state from birth:

* rows anchor to ORDERED CHANGES — a committed TEST NAME or the ABSENCE of
  superseded text — never to production prose I happened to write;
* SINCE-SHA BOTH ENDS: a row passes only if the ordered state is ABSENT at
  base AND PRESENT at tip, so a row cannot be satisfied by something that was
  already true;
* POST-STATE predicates: each row asserts the state the ruling ORDERED. Ask of
  every row "would this pass if the ordered change were absent but my edit
  present?" — it must not, which is why no row greps production prose;
* content is read from the COMMIT via `git show <sha>:<path>`, never from the
  working tree, so an uncommitted edit cannot certify anything;
* `self_check` rejects malformed rows;
* `--mutate` breaks the instrument on purpose, one class at a time, and each
  class must fail FOR ITS OWN REASON.

Usage:
    certify.py                 # certify base..tip
    certify.py --self-check    # malformed-row rejection
    certify.py --mutate        # mutation proofs
"""
from __future__ import annotations

import subprocess
import sys

REPO = "/Users/pwilson/src/psh-r2-6"
BASE = "42f75591"
DISSOLVED = "62f2bd45"   # round-1 tip
DISSOLVED2 = "053750e5"  # round-2 tip
DISSOLVED3 = "b254ca52"  # round-3 tip
DISSOLVED4 = "9b78098a"  # round-4 tip; the "before" for round-4 fix rows
DISSOLVED5 = "e1113813"  # round-5 tip; the "before" for round-5 fix rows
DISSOLVED6 = "9d3a0e25"  # round-6 tip; the "before" for round-6 fix rows
TIP = "HEAD"

# kind semantics:
#   test_present  — a committed test/class NAME that must exist at tip and not
#                   at base (the ruling ordered a NEW pin)
#   text_absent   — text that must exist at base and NOT at tip (the ruling
#                   ordered a REMOVAL: superseded pin or false prose)
#   text_present  — non-prose ordered state (a cap value, a declared label)
#   collected     — a test node id pytest must actually COLLECT at tip. The
#                   post-state of the SUITE, not of a file: R15-B-A's defect
#                   was a test that existed in the tree and did not run, which
#                   every text-based row above would have certified as present.
ROWS = [
    # ---- R1-A: reject combined analysis modes at invocation parsing --------
    dict(ruling="R1-A", kind="test_present",
         path="tests/unit/test_parse_invocation.py",
         needle="def test_distinct_analysis_modes_rejected"),
    dict(ruling="R1-A", kind="text_absent",
         path="tests/unit/test_parse_invocation.py",
         needle="def test_analysis_modes_ordered"),
    dict(ruling="R1-A", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_distinct_modes_are_a_usage_error"),
    dict(ruling="R1-A", kind="test_present",
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_two_modes_is_a_construction_error"),
    # the priority chain that picked a silent winner must be GONE
    dict(ruling="R1-A", kind="text_absent",
         path="psh/scripting/visitor_modes.py",
         needle="if shell.validate_only:"),

    # ---- R1-B: per-unit line diagnostics -----------------------------------
    dict(ruling="R1-B", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_syntax_error_carries_its_line"),

    # ---- ROUND-1 FIX ORDERS (measured against the DISSOLVED tip) ----
    # R8-A: heredoc bodies are never lexed as command text
    dict(ruling="R8-A", kind="test_present", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_quote_bearing_heredoc_body_analyzes_clean"),
    dict(ruling="R8-A", kind="test_present", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_alias_inside_a_heredoc_body_is_data_not_state"),
    dict(ruling="R8-A", kind="test_present", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_every_unit_error_carries_a_line_prefix"),
    # the second raw-text tokenize is GONE
    dict(ruling="R8-A", kind="text_absent", since=DISSOLVED,
         path="psh/scripting/analysis_session.py",
         needle="tokens = [t for t in tokenize(text"),
    # R8-B: the third option, its semantics, and the struck false sentence
    dict(ruling="R8-B", kind="text_present", since=DISSOLVED,
         path="psh/scripting/analysis_session.py",
         needle="PARSE_RELEVANT_OPTIONS: Tuple[str, ...] = ('extglob', 'posix', 'expand_aliases')"),
    dict(ruling="R8-B", kind="text_absent", since=DISSOLVED,
         path="psh/scripting/analysis_session.py",
         needle="agreed on exactly"),
    dict(ruling="R8-B", kind="text_present", since=DISSOLVED,
         path="psh/scripting/analysis_session.py",
         needle="ORDERED_OPTIONS: Tuple[str, ...] = ('expand_aliases',)"),
    # R8-B(5): the constant is certified against the PIPELINE, both ways
    dict(ruling="R8-B5", kind="test_present", since=DISSOLVED,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_declared_set_equals_what_the_pipeline_reads"),
    dict(ruling="R8-B5", kind="test_present", since=DISSOLVED,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_every_declared_option_has_declared_semantics"),
    dict(ruling="R8-B5", kind="text_absent", since=DISSOLVED,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_declared_set_matches_what_the_lexer_reads"),
    dict(ruling="R8-B", kind="test_present", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_unreached_conditional_disable_is_the_declared_cost"),
    # R8-D: the spelling axis, and its near-miss controls
    dict(ruling="R8-D", kind="test_present", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_spelling_is_recognized"),
    dict(ruling="R8-D", kind="test_present", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_near_miss_is_not_mistaken_for_a_directive"),
    dict(ruling="R8-D", kind="text_present", since=DISSOLVED,
         path="psh/scripting/analysis_session.py",
         needle="def _normalize_head"),
    # R8-E: the itemized nits
    dict(ruling="R8-E1", kind="test_present", since=DISSOLVED,
         path="tests/unit/test_parse_invocation.py",
         needle="def test_help_and_version_outrank_the_mode_conflict"),
    dict(ruling="R8-E1", kind="test_present", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_help_and_version_still_answer"),
    dict(ruling="R8-E2", kind="test_present", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_metrics_counted_the_corrupted_word_as_a_variable"),
    dict(ruling="R8-E2", kind="test_present", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_validate_stops_reporting_issues_about_a_literal"),
    dict(ruling="R8-E2", kind="test_present", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_posix_named_fd_is_a_word_not_a_redirect"),
    dict(ruling="R8-E3", kind="text_absent", since=DISSOLVED,
         path="psh/scripting/analysis_session.py",
         needle="self.source_text = source_text"),
    dict(ruling="R8-E4", kind="text_present", since=DISSOLVED,
         path="psh/scripting/visitor_modes.py",
         needle="it is an internal defect"),
    dict(ruling="R8-E7", kind="text_absent", since=DISSOLVED,
         path="tests/system/test_analysis_state_aware.py",
         needle="assert cwd  # the script file"),
    # R8-F: the generated corpus is IN THE SUITE, exception stated
    dict(ruling="R8-F", kind="test_present", since=DISSOLVED,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_no_monotone_enable_turns_a_parsing_input_into_a_failing_one"),
    dict(ruling="R8-F", kind="test_present", since=DISSOLVED,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_search_detects_asymmetry_when_it_exists"),
    dict(ruling="R8-F", kind="text_present", since=DISSOLVED,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="THE EXCEPTION, stated rather than implied"),
    dict(ruling="R1-B", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_analysis_location_matches_execution_location"),
    # the docstring rationale that is now FALSE prose
    dict(ruling="R1-B", kind="text_absent",
         path="psh/scripting/visitor_modes.py",
         needle="the whole content was parsed at once"),

    # ---- R1-C: declared eval/source residual -------------------------------
    dict(ruling="R1-C", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_declared_residual_eval_and_source_stay_blind"),
    dict(ruling="R1-C", kind="text_present",
         path="docs/user_guide/17_differences_from_bash.md",
         needle="is invisible to"),

    # ---- R1-D: F7 co-land, pin + BOTH controls + fencing -------------------
    dict(ruling="R1-D", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_word_after_heredoc_body_is_intact"),
    dict(ruling="R1-D", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_validator_sees_the_real_loop_variable"),
    dict(ruling="R1-D", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_execution_control_unchanged"),
    # the fencing statement must be STATED, not implied
    dict(ruling="R1-D", kind="text_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="NOT the r18 lexer no-progress crash"),

    # ---- R1-E: two static surfaces -----------------------------------------
    dict(ruling="R1-E", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_two_static_surfaces_split"),
    dict(ruling="R1-E", kind="text_present",
         path="docs/user_guide/17_differences_from_bash.md",
         needle="`psh -n` and `bash -n` agree"),

    # ---- R1-F: rule R3 incl. the disable direction -------------------------
    dict(ruling="R1-F", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_isolation_decides_whether_a_change_applies"),
    dict(ruling="R1-F", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_disable_is_permissive_by_design"),

    # ---- R1-G: alias overlay, guards LABELLED as declared ------------------
    dict(ruling="R1-G", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_alias_defined_then_used_still_analyzes"),
    dict(ruling="R1-G", kind="text_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="DECLARED REGRESSION GUARDS — GREEN AT BASE"),
    dict(ruling="R1-G", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_format_still_does_not_expand_aliases"),

    # ---- R1-H: Shape M ------------------------------------------------------
    dict(ruling="R1-H", kind="test_present",
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_same_statements_as_a_whole_file_parse"),
    dict(ruling="R1-H", kind="test_present",
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_formatter_output_is_unchanged"),

    # ---- R1-J: --format posix mis-render ------------------------------------
    dict(ruling="R1-J", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_posix_literal_is_not_reprinted_as_an_expansion"),

    # ---- drift guards the session's claims rest on --------------------------
    dict(ruling="guards", kind="test_present",
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_declared_set_equals_what_the_pipeline_reads"),
    dict(ruling="guards", kind="test_present",
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_every_compound_command_is_classified"),
    dict(ruling="guards", kind="test_present",
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_analysis_does_not_leak_state_into_the_caller"),

    # ---- R2-A: carry citation + labelled tripwire (R3-C) --------------------
    dict(ruling="R2-A", kind="text_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="2.2 carry: combinator ignores line_offset for TOP-LEVEL statements"),
    dict(ruling="R2-A", kind="test_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_combinator_toplevel_line_is_the_2_2_carry"),
    dict(ruling="R2-A", kind="text_present",
         path="tests/system/test_analysis_state_aware.py",
         needle="CARRY TRIPWIRE — EXPECTED TO FLIP"),

    # ---- R3-A: embedder-subclass behavior claim carries a test --------------
    dict(ruling="R3-A", kind="test_present",
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_carrier_keeps_an_embedders_shell_subclass"),

    # ---- R3-D: command_accumulator cap taken in-slot ------------------------
    # R3-D ordered the cap to 0; R11-B N9 then ruled 0 ≡ absent by the
    # enforcement's own .get default and had the dead key deleted. The durable
    # post-state of BOTH rulings is that the 2-slack entry is gone.
    dict(ruling="R3-D", kind="text_absent",
         path="tests/unit/tooling/test_import_layering.py",
         needle="'psh.scripting.command_accumulator': 2,",
         superseded_by="R11-B N9"),
    dict(ruling="R3-D", kind="text_absent",
         path="tests/unit/tooling/test_import_layering.py",
         needle="'psh.scripting.command_accumulator': 2,"),

    # ---- ROUND-2 FIX ORDERS (measured against the round-2 DISSOLVED tip) ----
    # R9-A: the position guard is inherited, not re-derived
    dict(ruling="R9-A", kind="test_present", since=DISSOLVED2,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_argument_position_unalias_does_not_wipe_the_table"),
    dict(ruling="R9-A", kind="test_present", since=DISSOLVED2,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_argument_position_alias_does_not_define"),
    dict(ruling="R9-A", kind="test_present", since=DISSOLVED2,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_analysis_agrees_with_execution_about_alias_state"),
    # the hand-rolled position-blind walk is GONE
    dict(ruling="R9-A", kind="text_absent", since=DISSOLVED2,
         path="psh/scripting/analysis_session.py",
         needle="index = self.carrier.alias_manager._absorb_alias_command("),
    dict(ruling="R9-A", kind="text_present", since=DISSOLVED2,
         path="psh/scripting/analysis_session.py",
         needle="self.carrier.alias_manager.expand_aliases("),
    # R9-B: the doc carve-out, and pins holding the doc to the rule
    dict(ruling="R9-B", kind="text_present", since=DISSOLVED2,
         path="docs/user_guide/17_differences_from_bash.md",
         needle="For `extglob` and `posix`, analysis errs toward accepting:"),
    dict(ruling="R9-B", kind="text_absent", since=DISSOLVED2,
         path="docs/user_guide/17_differences_from_bash.md",
         needle="Turning an option back off does not narrow the analysis"),
    dict(ruling="R9-B", kind="test_present", since=DISSOLVED2,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_monotone_claim_is_scoped_to_the_monotone_options"),
    dict(ruling="R9-B", kind="test_present", since=DISSOLVED2,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_declared_cost_is_stated_in_user_facing_words"),
    # R9-C: the measured boundary resolutions
    dict(ruling="R9-C", kind="text_present", since=DISSOLVED2,
         path="psh/scripting/analysis_session.py",
         needle="if word == '--':"),
    # R9-C-2 ordered the contradictory-cluster refusal to be MODELLED as the
    # builtin measurably behaves. R15-B-B moved where the letters come from
    # (the builtin's own split, which stops at the first operand) but not the
    # rule itself, so the surviving post-state is the same refusal over the
    # new spelling of its input.
    dict(ruling="R9-C", kind="text_present", since=DISSOLVED2,
         path="psh/scripting/analysis_session.py",
         needle="if 's' in flags and 'u' in flags:",
         superseded_by="R15-B-B"),
    # R9-C widened the head normalizer to strip backslashes anywhere; R11-A
    # then ruled that unconditional stripping WRONG (a quoted backslash is
    # text) and replaced it with the lexer's own per-part verdict. The
    # surviving requirement — every backslash spelling that runs the builtin is
    # recognized — is carried by the R11-A rows and the corpus.
    dict(ruling="R9-C", kind="text_absent", since=DISSOLVED3,
         path="psh/scripting/analysis_session.py",
         needle="if '\\\\' in words[0]:",
         superseded_by="R11-A"),
    dict(ruling="R9-C4", kind="test_present", since=DISSOLVED2,
         path="tests/conformance/bash/test_noexec_state_blindness_conformance.py",
         needle="def test_noexec_is_blind_to_a_mid_script_shopt_like_bash"),
    # R9-C-6 ordered the perf cost RECORDED (not optimized). R16-3 re-measured
    # it with a stated basis, so the exact figure moved 3.2x -> ~3.3x; the
    # surviving post-state is that the cost is recorded with its disposition.
    dict(ruling="R9-C6", kind="text_present", since=DISSOLVED2,
         path="psh/scripting/analysis_session.py",
         needle="Analysis modes are one-shot CLI tools, not an inner loop",
         superseded_by="R16-3"),

    # ---- ROUND-3 FIX ORDERS (measured against the round-3 DISSOLVED tip) ----
    # R11-A(1): the instance — quoting resolved from the lexer's own context
    dict(ruling="R11-A", kind="test_present", since=DISSOLVED3,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_quoted_head_does_not_invent_a_disable"),
    dict(ruling="R11-A", kind="test_present", since=DISSOLVED3,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_quoted_head_does_not_invent_an_enable"),
    dict(ruling="R11-A", kind="test_present", since=DISSOLVED3,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_expansion_head_is_a_declared_residual"),
    dict(ruling="R11-A", kind="text_present", since=DISSOLVED3,
         path="psh/scripting/analysis_session.py",
         needle="def _effective_words"),
    # the unconditional strip is GONE
    dict(ruling="R11-A", kind="text_absent", since=DISSOLVED3,
         path="psh/scripting/analysis_session.py",
         needle="words[0] = words[0].replace('\\\\', '')"),
    # R11-A(2): the CLASS guard
    dict(ruling="R11-A2", kind="test_present", since=DISSOLVED3,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_every_string_surgery_site_is_sanctioned"),
    dict(ruling="R11-A2", kind="test_present", since=DISSOLVED3,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_scan_detects_a_planted_site"),
    dict(ruling="R11-A2", kind="test_present", since=DISSOLVED3,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_no_sanctioned_entry_has_gone_stale"),
    # R11-B nits
    dict(ruling="R11-B", kind="test_present", since=DISSOLVED3,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_combinator_error_detail_line_is_unit_relative"),
    dict(ruling="R11-B", kind="test_present", since=DISSOLVED3,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_alias_defined_then_used_across_a_heredoc"),
    dict(ruling="R11-B", kind="test_present", since=DISSOLVED3,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_function_shadowed_shopt_is_absorbed_anyway"),
    dict(ruling="R11-B", kind="text_absent", since=DISSOLVED3,
         path="docs/user_guide/17_differences_from_bash.md",
         needle="entire program before executing, so a runtime"),
    dict(ruling="R11-B", kind="text_present", since=DISSOLVED3,
         path="docs/user_guide/13_shell_scripts.md",
         needle="Only one analysis mode may be given per run"),
    dict(ruling="R11-B", kind="text_present", since=DISSOLVED3,
         path="psh/scripting/lex_parse.py",
         needle="WHOLE-FILE-PARSE ORACLE"),
    dict(ruling="R11-B", kind="text_absent", since=DISSOLVED3,
         path="psh/scripting/visitor_modes.py",
         needle="Each unit goes through ``lex_parse.lex_and_parse``"),
    dict(ruling="R11-B", kind="text_absent", since=DISSOLVED3,
         path="tests/unit/tooling/test_import_layering.py",
         needle="'psh.scripting.command_accumulator': 0,"),

    # ---- ROUND-4 FIX ORDERS (R13). Per R13-C a discharge is COMPLETE only
    # ---- when a cert row asserts its post-state — "the addendum says done"
    # ---- is a process claim; this is the tree claim.
    # R15-B-F RE-ANCHOR. The original anchor was the extglob corpus row
    # `"shopt -s -u extglob",` — which was GREEN at 9b78098a: the per-word
    # last-write-wins it replaced happened to give the right answer for that
    # spelling, so the row never detected the defect it was meant to pin.
    # MEASURED at 9b78098a with today's module: the row that is actually RED
    # there is the ALIAS-axis separate-word contradiction, and it is green at
    # e1113813 — i.e. it is the row R13-A's fix moved.
    dict(ruling="R13-A", kind="text_present", since=DISSOLVED4,
         path="tests/system/test_analysis_state_aware.py",
         needle='"shopt -s -u expand_aliases",'),
    # The production half. R13-A ordered the WHOLE flag set aggregated before
    # deciding; R15-B-B replaced the aggregation with the builtin's own split,
    # which stops at the first operand. The SURVIVING post-state of R13-A's
    # rule is that both letters, however spelled, still cancel to no change.
    dict(ruling="R13-A", kind="text_present", since=DISSOLVED4,
         path="psh/scripting/analysis_session.py",
         needle="if 's' in flags and 'u' in flags:",
         superseded_by="R15-B-B"),
    # R13-B(1): N1 executed AS ORDERED — the DISABLE shapes
    dict(ruling="R13-B1", kind="text_present", since=DISSOLVED4,
         path="tests/system/test_analysis_state_aware.py",
         needle="R11-B N1 AS ORDERED, DISABLE direction"),
    # R13-B(2): N12 in BOTH enumerations
    dict(ruling="R13-B2", kind="text_present", since=DISSOLVED4,
         path="docs/user_guide/17_differences_from_bash.md",
         needle="`shopt` that a shell function of the same name would shadow"),
    dict(ruling="R13-B2", kind="text_present", since=DISSOLVED4,
         path="psh/scripting/analysis_session.py",
         needle="command resolution, so a ``shopt`` shadowed by a shell function"),
    # R13-B(3): N13 written for real, and pinned
    dict(ruling="R13-B3", kind="test_present", since=DISSOLVED4,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_normalized_alias_spellings_are_not_absorbed"),
    dict(ruling="R13-B3", kind="test_present", since=DISSOLVED4,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_the_bare_spelling_is_absorbed"),
    # R13-E nits
    dict(ruling="R13-E1", kind="test_present", since=DISSOLVED4,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_mirrored_line_is_not_inside_a_code_fence"),
    dict(ruling="R13-E2", kind="text_present", since=DISSOLVED4,
         path="psh/scripting/lex_parse.py",
         needle="called by the three active-parser callers."),
    dict(ruling="R13-E3", kind="text_present", since=DISSOLVED4,
         path="psh/scripting/analysis_session.py",
         needle="while len(remaining) > 1 and remaining[0] == '-p':"),
    dict(ruling="R13-E5", kind="test_present", since=DISSOLVED4,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_a_second_site_of_a_sanctioned_shape_is_visible"),
    dict(ruling="R13-E6", kind="test_present", since=DISSOLVED4,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_every_justification_is_substantive_and_tagged"),
    dict(ruling="R13-E7", kind="text_present", since=DISSOLVED4,
         path="psh/scripting/source_processor.py",
         needle="if trace and shell.state.options.get('debug-exec', False):"),
    dict(ruling="R13-E8", kind="text_absent", since=DISSOLVED4,
         path="psh/scripting/source_processor.py",
         needle="def _offset_line_numbers"),
    dict(ruling="R13-E8", kind="text_present", since=DISSOLVED4,
         path="psh/scripting/source_processor.py",
         needle="def offset_line_numbers"),
    # ---- R11-B items now carry cert rows too (R13-C, retroactive) ----
    dict(ruling="R11-B-N4", kind="text_present", since=DISSOLVED3,
         path="docs/user_guide/17_differences_from_bash.md",
         needle="(PSH parses one command at a time, so"),
    dict(ruling="R11-B-N5", kind="text_present", since=DISSOLVED3,
         path="docs/user_guide/13_shell_scripts.md",
         needle="Only one analysis mode may be given per run"),
    dict(ruling="R11-B-N9", kind="text_absent", since=DISSOLVED3,
         path="tests/unit/tooling/test_import_layering.py",
         needle="'psh.scripting.command_accumulator'"),
    dict(ruling="R11-B-N14", kind="text_present", since=DISSOLVED3,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="the unqualified all-options-monotone sentence has returned"),

    # ---- ratchet moved DOWN (not raised) ------------------------------------
    dict(ruling="ratchet", kind="text_present",
         path="tests/unit/tooling/test_import_layering.py",
         needle="'psh.scripting.visitor_modes': 7,"),
    dict(ruling="ratchet", kind="text_absent",
         path="tests/unit/tooling/test_import_layering.py",
         needle="'psh.scripting.visitor_modes': 9,"),
    dict(ruling="ratchet", kind="text_present",
         path="tests/unit/tooling/test_import_layering.py",
         needle="'psh.scripting.source_processor': 5,"),

    # ---- the shared chunker is SHARED, not forked ---------------------------
    dict(ruling="R1-H", kind="text_present",
         path="psh/scripting/source_processor.py",
         needle="def iter_command_units"),
    # R1-H ordered the chunker SHARED, not forked; R13-E8 then made the
    # line-offset seam public, changing this import's spelling. The surviving
    # post-state is that the session imports the shared generator at all.
    dict(ruling="R1-H", kind="text_present",
         path="psh/scripting/analysis_session.py",
         needle='from .source_processor import iter_command_units, offset_line_numbers',
         superseded_by="R13-E8"),

    # ---- ROUND-5 FIX ORDERS (R15-B/C). Measured against DISSOLVED5.
    # ---- Per R15-B-I, an item with a CODE half and a PIN half gets a row
    # ---- for each: E7/E8 shipped one half and were recorded as complete.

    # A — the de-collected test. The rename is a file fact; being COLLECTED is
    # a suite fact, and only the second one is the defect.
    dict(ruling="R15-B-A", kind="text_absent", since=DISSOLVED5,
         path="tests/unit/visitor/test_walk_ast_schema.py",
         needle="def testoffset_line_numbers_reaches_stamped_template_sub_nodes"),
    dict(ruling="R15-B-A", kind="collected",
         path="tests/unit/visitor/test_walk_ast_schema.py",
         needle="tests/unit/visitor/test_walk_ast_schema.py::"
                "test_offset_line_numbers_reaches_stamped_template_sub_nodes"),

    # B — flag parsing stops at the first operand. CODE half.
    dict(ruling="R15-B-B", kind="text_absent", since=DISSOLVED5,
         path="psh/scripting/analysis_session.py",
         needle="letters = ''.join(word[1:] for word in rest"),
    dict(ruling="R15-B-B", kind="text_present", since=DISSOLVED5,
         path="psh/scripting/analysis_session.py",
         needle="def _shopt_split"),
    dict(ruling="R15-B-B", kind="text_present", since=DISSOLVED5,
         path="psh/scripting/analysis_session.py",
         needle="SHOPT_TABLE_OPTIONS: Tuple[str, ...] = ('extglob', 'expand_aliases')"),
    # B — PIN half: both named faces, plus the corpus rows on both axes.
    dict(ruling="R15-B-B", kind="test_present", since=DISSOLVED5,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_false_red_face_is_an_incomplete_fix_not_a_regression"),
    dict(ruling="R15-B-B", kind="test_present", since=DISSOLVED5,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_false_green_face_no_longer_invents_an_enable"),
    dict(ruling="R15-B-B", kind="test_present", since=DISSOLVED5,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_analysis_agrees_with_execution_about_extglob"),
    dict(ruling="R15-B-B", kind="text_present", since=DISSOLVED5,
         path="tests/system/test_analysis_state_aware.py",
         needle='"shopt -q extglob -s",'),
    dict(ruling="R15-B-B", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_routing_constants_match_the_builtins_own_tables"),
    # R17-A's condition: the routing constants duplicate knowledge the builtin
    # owns (the cited-copy drift class), so the guard anchors to the builtin's
    # MEASURED behavior — six cells that run the real builtin — not only to
    # the tables, which could agree with the copy and both be wrong.
    dict(ruling="R17-A", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_constants_predict_the_builtins_measured_behavior"),

    # C — the carrier's debug options. CODE half.
    dict(ruling="R15-B-C", kind="text_present", since=DISSOLVED5,
         path="psh/scripting/analysis_session.py",
         needle="DEBUG_OPTIONS: Tuple[str, ...] = tuple("),
    dict(ruling="R15-B-C", kind="text_absent", since=DISSOLVED5,
         path="psh/scripting/analysis_session.py",
         needle="self.carrier = type(shell)(parent_shell=shell, norc=True)"),
    # C — PIN half: silence across all five modes, AND the execution control.
    dict(ruling="R15-B-C", kind="test_present", since=DISSOLVED5,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_debug_flag_writes_nothing_on_an_analysis_run"),
    dict(ruling="R15-B-C", kind="test_present", since=DISSOLVED5,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_execution_control_the_trace_still_fires"),
    dict(ruling="R15-B-C", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_parent_is_restored_even_when_construction_raises"),

    # D — five-mode byte-identical parity, and the proof it can fail.
    dict(ruling="R15-B-D", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_every_mode_renders_byte_identically"),
    dict(ruling="R15-B-D", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_parity_comparison_can_actually_fail"),

    # E — the `command -p` widening's missing pin half (the CODE half landed
    # in round 4, so only the pins are new here — stated, not implied).
    dict(ruling="R15-B-E", kind="text_present", since=DISSOLVED5,
         path="tests/system/test_analysis_state_aware.py",
         needle='"command -p shopt -s extglob",'),
    dict(ruling="R15-B-E", kind="text_present", since=DISSOLVED5,
         path="tests/system/test_analysis_state_aware.py",
         needle='"builtin -p shopt -s extglob",'),

    # F — the alias-axis separate-word contradiction rows.
    dict(ruling="R15-B-F", kind="test_present", since=DISSOLVED5,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_analysis_agrees_with_execution_about_expand_aliases"),
    dict(ruling="R15-B-F", kind="text_present", since=DISSOLVED5,
         path="tests/system/test_analysis_state_aware.py",
         needle='"shopt -u expand_aliases -s",'),

    # G — the five structural items, each with its half.
    dict(ruling="R15-B-G", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_an_absorption_failure_is_wrapped_with_the_units_line"),
    dict(ruling="R15-B-G", kind="text_present", since=DISSOLVED5,
         path="psh/invocation.py",
         needle="class AnalysisModeConflictError(ValueError):"),
    # The raise site itself. A text_absent row on the old `raise ValueError(`
    # line would be UNSOUND here: shell.py has another, deeper-indented
    # ValueError whose line CONTAINS that needle as a substring, so the row
    # would report a removal that did not happen. The post-state is the typed
    # raise, asserted directly.
    dict(ruling="R15-B-G", kind="text_present", since=DISSOLVED5,
         path="psh/shell.py",
         needle="raise AnalysisModeConflictError("),
    dict(ruling="R15-B-G", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_construction_error_is_typed"),
    dict(ruling="R15-B-G", kind="text_present", since=DISSOLVED5,
         path="psh/scripting/analysis_session.py",
         needle="EMBEDDER CONTRACT for the ``type(shell)`` construction"),
    dict(ruling="R15-B-G", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_every_walkable_node_type_is_classified"),
    dict(ruling="R15-B-G", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_every_isolating_name_is_a_real_node_type"),
    dict(ruling="R15-B-G", kind="test_present", since=DISSOLVED5,
         path="tests/unit/test_parse_invocation.py",
         needle="def test_the_precedence_order_is_stated_whole"),
    dict(ruling="R15-B-G", kind="test_present", since=DISSOLVED5,
         path="tests/unit/test_parse_invocation.py",
         needle="def test_an_invalid_option_outranks_help_and_version"),

    # H — the one record repair that is a TREE fact rather than ledger prose.
    dict(ruling="R15-B-H", kind="text_present", since=DISSOLVED5,
         path="docs/user_guide/02_getting_started.md",
         needle="the five analysis modes are mutually exclusive"),
    dict(ruling="R15-B-H", kind="test_present", since=DISSOLVED5,
         path="tests/unit/tooling/test_help_transcript_matches_guide.py",
         needle="def test_the_guide_block_is_the_programs_own_help_output"),

    # ---- R16: the stand-down note's ranked re-verify list, adopted as
    # ---- binding where it intersects R15-B work.
    # Item 1 (score_rules.py's hand-modelled FACTS table) gets NO row, stated
    # rather than faked: re-deriving 19/8/2 from the shipped code CONFIRMED
    # the figures, so there is no ordered change and no post-state to assert.
    # The instrument is tmp/2.6-probes/rederive_rule_outcomes.py; the ledger
    # records the result. A row here would be certifying a verification, not a
    # change — the R1-I distinction.
    # Item 2: the interactive-leg census becomes a GUARD instead of prose.
    dict(ruling="R16-2", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_no_analysis_mode_is_reachable_as_a_shell_option"),
    dict(ruling="R16-2", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_analysis_entry_points_are_called_only_from_main"),
    # Item 3: the perf figure gains its basis (n, warm-up, statistic).
    dict(ruling="R16-3", kind="text_absent", since=DISSOLVED5,
         path="psh/scripting/analysis_session.py",
         needle="measured **3.2x** on a 4,000-line script"),
    dict(ruling="R16-3", kind="text_present", since=DISSOLVED5,
         path="psh/scripting/analysis_session.py",
         needle="over 5 runs after a discarded warm-up"),
    # Item 4: "execution untouched" gains a structural argument, both halves.
    dict(ruling="R16-4", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_the_generator_body_acquires_nothing"),
    dict(ruling="R16-4", kind="test_present", since=DISSOLVED5,
         path="tests/unit/scripting/test_analysis_session.py",
         needle="def test_abandoning_it_midway_raises_nothing_and_leaves_the_source_usable"),

    # ---- ROUND-6 FIX ORDERS (R21). Measured against DISSOLVED6.
    # R21-A: the twin sentence, and the family it belongs to. The blocker was
    # not one sentence but a FAMILY that had already reproduced once, so the
    # row is the verifier's own grep rather than a single needle.
    dict(ruling="R21-A", kind="text_absent", since=DISSOLVED6,
         path="tests/conformance/bash/test_identifier_policy_conformance.py",
         needle="entire program before executing, so runtime"),
    dict(ruling="R21-A", kind="text_present", since=DISSOLVED6,
         path="tests/conformance/bash/test_identifier_policy_conformance.py",
         needle="parses ONE COMMAND AT A TIME"),
    dict(ruling="R21-A", kind="phrase_family_absent",
         path="<tree-wide>", needle="the false whole-file-parse phrase family",
         family=["cannot influence parsing",
                 "entire program before executing",
                 "parses the entire input",
                 "whole program before executing"]),

    # R21-B: the two declared-but-unpinned alias-axis limitations.
    dict(ruling="R21-B", kind="test_present", since=DISSOLVED6,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_alias_absorption_ignores_state_isolation"),
    dict(ruling="R21-B", kind="test_present", since=DISSOLVED6,
         path="tests/system/test_analysis_state_aware.py",
         needle="def test_a_substitution_definition_is_not_absorbed"),
    dict(ruling="R21-B", kind="text_present", since=DISSOLVED6,
         path="tests/system/test_analysis_state_aware.py",
         needle="\"'alias' iff='if true; then'\","),
    dict(ruling="R21-B", kind="text_absent", since=DISSOLVED6,
         path="tests/system/test_analysis_state_aware.py",
         needle="So four spellings that DEFINE an alias"),

    # R21-C: the precedence pin states the measured truth, including the
    # three-way cell the simpler ranking gets wrong.
    dict(ruling="R21-C", kind="text_present", since=DISSOLVED6,
         path="tests/unit/test_parse_invocation.py",
         needle="THE DECISIVE CELL: all three present"),

    # R21-D: the one drift shape with no committed row on its own suite.
    dict(ruling="R21-D", kind="test_present", since=DISSOLVED6,
         path="tests/unit/builtins/test_shopt_set_o.py",
         needle="def test_ddash_ends_flags_and_the_operand_still_applies"),

    # R21-E: one door. The pass-through is GONE and its consumers moved.
    dict(ruling="R21-E", kind="text_absent", since=DISSOLVED6,
         path="psh/scripting/visitor_modes.py",
         needle="def _parse_for_analysis"),
    dict(ruling="R21-E", kind="text_absent", since=DISSOLVED6,
         path="psh/scripting/lex_parse.py",
         needle="visitor_modes._parse_for_analysis"),

    # R21-G: the ruling is cited where the question keeps getting asked.
    dict(ruling="R21-G", kind="text_present", since=DISSOLVED6,
         path="psh/scripting/lex_parse.py",
         needle="IT STAYS IN ``psh/`` BY RULING (remediation 2.6 R21-G)"),

    # C (R15-C) — the tree-wide collection backstop, and its mutation proof.
    dict(ruling="R15-C", kind="test_present", since=DISSOLVED5,
         path="tests/unit/tooling/test_no_uncollected_test_names.py",
         needle="def test_no_test_function_is_missing_its_underscore"),
    dict(ruling="R15-C", kind="test_present", since=DISSOLVED5,
         path="tests/unit/tooling/test_no_uncollected_test_names.py",
         needle="def test_the_scan_detects_a_planted_name"),
]

VALID_KINDS = {"test_present", "text_absent", "text_present", "collected",
               "phrase_family_absent"}


def collected_ids(path: str) -> set[str]:
    """Node ids pytest ACTUALLY collects from *path*, in the working tree.

    This is the one row kind that cannot read from a commit: whether a test
    runs is a property of the suite as pytest sees it, and the R15-B-A defect
    was precisely a test that was present in the file and absent from the run.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", path, "--collect-only", "-q"],
        capture_output=True, text=True, cwd=REPO)
    return {line.strip() for line in proc.stdout.splitlines()
            if "::" in line and not line.startswith(" ")}


def show(sha: str, path: str) -> str | None:
    proc = subprocess.run(["git", "-C", REPO, "show", f"{sha}:{path}"],
                          capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def self_check(rows) -> list[str]:
    """Reject malformed rows BEFORE any of them can certify anything."""
    problems = []
    for i, row in enumerate(rows):
        for field in ("ruling", "kind", "path", "needle"):
            if field not in row or not isinstance(row[field], str) or not row[field]:
                problems.append(f"row {i}: missing/empty field {field!r}")
        if row.get("kind") not in VALID_KINDS:
            problems.append(f"row {i}: unknown kind {row.get('kind')!r}")
        if "\n" in row.get("needle", ""):
            problems.append(f"row {i}: needle must be single-line (audit anchor)")
        if row.get("kind") == "test_present" and not row.get("needle", "").startswith("def "):
            problems.append(f"row {i}: test_present needle must name a def")
        if row.get("kind") == "collected" and "::" not in row.get("needle", ""):
            problems.append(f"row {i}: collected needle must be a pytest node id")
        if row.get("kind") == "phrase_family_absent":
            fam = row.get("family")
            if not isinstance(fam, (list, tuple)) or not fam:
                problems.append(f"row {i}: phrase_family_absent needs a non-empty family")
            elif any(not isinstance(x, str) or not x for x in fam):
                problems.append(f"row {i}: family entries must be non-empty strings")
    return problems


def evaluate(row) -> tuple[bool, str]:
    """POST-STATE + since-SHA both ends.

    ``since`` names the SHA a row is measured against: base for the original
    slot work, the DISSOLVED round-1 tip for fix-round rows (whose "before"
    state is what the verifiers actually saw, not what base had).
    """
    if row["kind"] == "phrase_family_absent":
        # The verifier's own instrument, promoted to a row: the whole FAMILY
        # of the false sentence must be absent tree-wide, so a third twin
        # cannot survive the way the second one did. docs/reviews/ is excluded
        # by design — those are historical records of what was once believed,
        # and rewriting them would destroy the audit trail.
        hits = []
        for phrase in row["family"]:
            proc = subprocess.run(
                ["git", "-C", REPO, "grep", "-rn", "--fixed-strings", phrase,
                 "--", ":(exclude)docs/reviews", ":(exclude)tmp"],
                capture_output=True, text=True)
            hits += [ln for ln in proc.stdout.splitlines() if ln.strip()]
        if hits:
            return False, ("phrase family still present tree-wide: "
                           + "; ".join(hits[:3]))
        return True, f"all {len(row['family'])} phrases absent tree-wide"

    if row["kind"] == "collected":
        ids = collected_ids(row["path"])
        if row["needle"] in ids:
            return True, f"pytest collects it ({len(ids)} ids in the module)"
        return False, ("pytest does NOT collect this node id — the test is in "
                       "the tree and absent from the run")
    base_text = show(row.get("since", BASE), row["path"])
    tip_text = show(TIP, row["path"])
    if tip_text is None:
        return False, f"path missing at tip: {row['path']}"
    needle = row["needle"]
    at_base = needle in (base_text or "")
    at_tip = needle in tip_text
    since = row.get("since", BASE)[:8]
    if row["kind"] in ("test_present", "text_present"):
        if not at_tip:
            return False, "ordered state ABSENT at tip"
        if at_base:
            return False, f"already true at {since} — row certifies nothing"
        return True, f"absent at {since}, present at tip"
    # text_absent
    if at_tip:
        return False, "superseded text STILL PRESENT at tip"
    if not at_base:
        return False, f"was not present at {since} — row certifies nothing"
    return True, f"present at {since}, removed at tip"


def certify(rows=None) -> int:
    rows = ROWS if rows is None else rows
    problems = self_check(rows)
    if problems:
        print("SELF-CHECK REJECTED THE ROW SET:")
        for p in problems:
            print(f"  {p}")
        return 2
    failed = 0
    by_ruling: dict[str, list[str]] = {}
    for row in rows:
        ok, why = evaluate(row)
        by_ruling.setdefault(row["ruling"], []).append("PASS" if ok else "FAIL")
        if not ok:
            failed += 1
            print(f"FAIL [{row['ruling']}] {row['path']} :: {row['needle'][:60]}"
                  f"\n       {why}")
    superseded = [r for r in rows if r.get("superseded_by")]
    if superseded:
        print("\nSUPERSEDED ordered changes (a later ruling replaced the "
              "earlier one; the row now asserts the surviving post-state):")
        for r in superseded:
            print(f"   {r['ruling']} -> {r['superseded_by']}: {r['needle'][:52]}")
    tip_sha = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
    print(f"\ncertification base={BASE} tip={tip_sha}: "
          f"{len(rows) - failed}/{len(rows)} rows pass")
    for ruling in sorted(by_ruling):
        results = by_ruling[ruling]
        print(f"   {ruling:<8} {results.count('PASS')}/{len(results)}")
    return 1 if failed else 0


def mutate() -> int:
    """Break the instrument on purpose; each class must fail for ITS OWN reason."""
    classes = [
        ("ordered test renamed away",
         dict(ruling="X", kind="test_present", path="tests/system/test_analysis_state_aware.py",
              needle="def test_this_pin_was_never_written"),
         "ordered state ABSENT at tip"),
        ("row already true at base (certifies nothing)",
         dict(ruling="X", kind="text_present", path="psh/scripting/visitor_modes.py",
              needle="def apply_visitor_mode"),
         "row certifies nothing"),
        ("removal row whose text is still there",
         dict(ruling="X", kind="text_absent", path="psh/scripting/visitor_modes.py",
              needle="def handle_visitor_mode_for_content"),
         "superseded text STILL PRESENT at tip"),
        ("removal row for text that never existed",
         dict(ruling="X", kind="text_absent", path="psh/scripting/visitor_modes.py",
              needle="zzz_never_in_this_file_zzz"),
         "was not present at"),
        ("row citing a nonexistent file",
         dict(ruling="X", kind="test_present", path="tests/system/no_such_module.py",
              needle="def test_anything"),
         "path missing at tip"),
        # The `collected` kind gets its own class: a row kind that has never
        # been shown to FAIL is not evidence of anything. This is the exact
        # shape of the R15-B-A defect — a node id that is not collected.
        # The phrase-family kind gets its own class too: a family row that
        # cannot fail would silently bless the very recurrence it exists to
        # prevent. The planted phrase must be present in a TRACKED file --
        # git grep never sees this instrument, which sits under tmp/ and is
        # excluded by the row's own pathspec (the first attempt at this
        # class planted a phrase only in here, and passed for that reason).
        ("phrase-family row for a phrase that is still present",
         dict(ruling="X", kind="phrase_family_absent", path="<tree-wide>",
              needle="a family with a phrase that is still there",
              family=["parses ONE COMMAND AT A TIME"]),
         "phrase family still present tree-wide"),
        ("collected row for a test pytest does not collect",
         dict(ruling="X", kind="collected",
              path="tests/unit/visitor/test_walk_ast_schema.py",
              needle="tests/unit/visitor/test_walk_ast_schema.py::"
                     "testoffset_line_numbers_reaches_stamped_template_sub_nodes"),
         "does NOT collect this node id"),
    ]
    failures = 0
    for label, row, expected in classes:
        ok, why = evaluate(row)
        good = (not ok) and expected in why
        print(f"  {'OK ' if good else 'BAD'} {label:<44} -> {why}")
        if not good:
            failures += 1

    print("\n  malformed-row classes (self_check must reject each):")
    malformed = [
        ("missing field", {"ruling": "X", "kind": "test_present",
                           "path": "tests/system/test_analysis_state_aware.py"}),
        ("unknown kind", dict(ruling="X", kind="vibes", path="p", needle="n")),
        ("multi-line needle", dict(ruling="X", kind="text_present", path="p",
                                   needle="a\nb")),
        ("test_present not naming a def", dict(ruling="X", kind="test_present",
                                               path="p", needle="TestThing")),
        ("collected needle that is not a node id",
         dict(ruling="X", kind="collected", path="p",
              needle="test_offset_line_numbers_reaches")),
    ]
    for label, row in malformed:
        problems = self_check([row])
        print(f"  {'OK ' if problems else 'BAD'} {label:<44} -> "
              f"{problems[0] if problems else 'ACCEPTED (bad)'}")
        if not problems:
            failures += 1

    print(f"\nmutation proof: {failures} class(es) did not fail for their own reason")
    return 1 if failures else 0


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        problems = self_check(ROWS)
        print(f"self-check: {len(problems)} problem(s) in {len(ROWS)} rows")
        for p in problems:
            print(f"  {p}")
        raise SystemExit(1 if problems else 0)
    if "--mutate" in sys.argv:
        raise SystemExit(mutate())
    raise SystemExit(certify())
