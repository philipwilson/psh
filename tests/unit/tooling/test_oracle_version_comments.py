"""C241 census ratchet: no NEW "bash 5.2" claims (Improvement Program 2026-09, D12).

The differential oracle is bash 5.3 (D1). Hundreds of docstrings and comments
still say "verified against bash 5.2" — that is PROVENANCE (it was true when
the pin was written) and D12 rules it is rewritten only when a slot touches
the file, never in a tree-wide sweep. What must NOT happen is a NEW claim
against the old oracle: a pin written today and stamped "bash 5.2" is either
copy-paste or was verified against the wrong bash.

Counted, per file under ``tests/`` and ``psh/`` (every text file, so YAML
golden descriptions and CLAUDE.md files count too): the case-insensitive
patterns ``bash 5.2`` / ``bash-5.2`` (``\b``-terminated, so ``bash 5.2.26``
counts once and ``bash 5.20`` not at all) and the bare patch level
``5.2.26``. This file excludes itself from the walk.

RATCHET RULE: a file ABOVE its baseline count fails ("new bash 5.2 claim").
A file BELOW its baseline (a slot rewrote provenance) updates nothing and
passes — the baseline may then be LOWERED to the new count, and MAY ONLY EVER
DECREASE; a baseline entry may never be raised and a new entry may never be
added (a file with no entry has a baseline of 0). A baseline entry for a file
that no longer exists must be pruned (also a decrease).

Two rows here are deliberate SYNTHETIC OFFENDERS, not claims:
``tests/unit/tooling/test_gate_attestation.py`` (the attestation-refusal test
that names 5.2.26) and this ratchet's own pattern tests. They are in the
baseline like any other file.

Frozen 2026-09-06 at the Wave 0.1 tree: 658 occurrences in 387 files
(the base tree 788ffe41 had 653; the 5 added are the synthetic offenders in
test_gate_attestation.py).
"""
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOTS = ("tests", "psh")
# Built from pieces so this module's own source never matches its pattern
# (it is excluded from the walk anyway; this keeps the exclusion non-load-bearing).
CLAIM = re.compile(r"(?i)" + "ba" + r"sh[ -]5\.2\b|5\.2\." + "26" + r"\b")

BASELINE_TOTAL = 658
#: file -> count of "bash 5.2" claims. MAY ONLY DECREASE (see module docstring).
BASELINE = {
    "psh/builtins/core.py": 1,
    "psh/builtins/declaration_engine.py": 1,
    "psh/builtins/declare_format.py": 2,
    "psh/builtins/directory_stack.py": 1,
    "psh/builtins/environment.py": 8,
    "psh/builtins/function_support.py": 1,
    "psh/builtins/hash_builtin.py": 1,
    "psh/builtins/io.py": 1,
    "psh/builtins/job_control.py": 2,
    "psh/builtins/loop_control.py": 3,
    "psh/builtins/navigation.py": 1,
    "psh/builtins/positional.py": 2,
    "psh/builtins/shell_options.py": 1,
    "psh/builtins/shell_state.py": 1,
    "psh/builtins/source_command.py": 1,
    "psh/builtins/test_command.py": 2,
    "psh/builtins/type_builtin.py": 1,
    "psh/core/command_hash.py": 1,
    "psh/core/exceptions.py": 2,
    "psh/core/getopts_state.py": 1,
    "psh/core/internal_errors.py": 8,
    "psh/core/scope.py": 3,
    "psh/core/state.py": 4,
    "psh/core/trap_manager.py": 6,
    "psh/core/variables.py": 1,
    "psh/executor/array.py": 1,
    "psh/executor/command.py": 2,
    "psh/executor/command_assignments.py": 3,
    "psh/executor/command_resolution.py": 1,
    "psh/executor/control_flow.py": 2,
    "psh/executor/job_control.py": 3,
    "psh/executor/process_launcher.py": 1,
    "psh/executor/strategies.py": 2,
    "psh/expansion/CLAUDE.md": 3,
    "psh/expansion/arithmetic/evaluator.py": 1,
    "psh/expansion/arithmetic/tokenizer.py": 1,
    "psh/expansion/extglob.py": 1,
    "psh/expansion/glob.py": 1,
    "psh/expansion/manager.py": 2,
    "psh/expansion/operands.py": 5,
    "psh/expansion/operators.py": 2,
    "psh/expansion/param_parser.py": 3,
    "psh/expansion/parameter_expansion.py": 2,
    "psh/expansion/pattern_engine.py": 6,
    "psh/expansion/procsub_render.py": 1,
    "psh/expansion/subscript.py": 2,
    "psh/expansion/tilde.py": 1,
    "psh/expansion/variable.py": 1,
    "psh/expansion/word_expander.py": 3,
    "psh/expansion/word_expansion_types.py": 3,
    "psh/interactive/CLAUDE.md": 1,
    "psh/interactive/edit_buffer.py": 1,
    "psh/interactive/eof_policy.py": 1,
    "psh/interactive/history_manager.py": 7,
    "psh/interactive/line_editor_helpers.py": 1,
    "psh/interactive/repl_loop.py": 1,
    "psh/invocation.py": 1,
    "psh/io_redirect/file_redirect.py": 1,
    "psh/io_redirect/redirect_program.py": 1,
    "psh/lexer/cmdsub_scanner.py": 1,
    "psh/lexer/heredoc_lexer.py": 1,
    "psh/parser/recursive_descent/support/syntax_templates.py": 1,
    "psh/scripting/analysis_session.py": 3,
    "psh/scripting/input_preprocessing.py": 1,
    "psh/scripting/input_sources.py": 3,
    "psh/scripting/program_source.py": 8,
    "psh/scripting/script_validator.py": 1,
    "psh/scripting/source_processor.py": 3,
    "psh/utils/escapes.py": 5,
    "psh/utils/heredoc_detection.py": 3,
    "psh/utils/printf_formatter.py": 3,
    "psh/utils/signal_utils.py": 1,
    "psh/visitor/formatter_quoting.py": 1,
    "psh/visitor/formatter_visitor.py": 1,
    "psh/visitor/security_visitor.py": 2,
    "tests/behavioral/golden_cases.yaml": 19,
    "tests/conformance/bash/test_absent_features.py": 2,
    "tests/conformance/bash/test_ansi_c_control_escape_conformance.py": 1,
    "tests/conformance/bash/test_array_case_attr_conformance.py": 1,
    "tests/conformance/bash/test_array_init_conformance.py": 6,
    "tests/conformance/bash/test_bad_substitution_conformance.py": 1,
    "tests/conformance/bash/test_bash_compatibility.py": 1,
    "tests/conformance/bash/test_case_toggle_conformance.py": 1,
    "tests/conformance/bash/test_cmdsub_case_conformance.py": 2,
    "tests/conformance/bash/test_cmdsub_errexit_conformance.py": 1,
    "tests/conformance/bash/test_command_resolution_conformance_r3.py": 1,
    "tests/conformance/bash/test_computed_special_vars_conformance.py": 1,
    "tests/conformance/bash/test_cv_carry_characterization.py": 7,
    "tests/conformance/bash/test_declare_attributes_conformance.py": 1,
    "tests/conformance/bash/test_dynamic_special_scoping_conformance.py": 1,
    "tests/conformance/bash/test_echo_double_dash_conformance.py": 1,
    "tests/conformance/bash/test_errexit_brace_group_conformance.py": 1,
    "tests/conformance/bash/test_exec_error_message_conformance.py": 1,
    "tests/conformance/bash/test_exit_trap_status_precedence_conformance.py": 1,
    "tests/conformance/bash/test_export_env_sync_conformance.py": 1,
    "tests/conformance/bash/test_field_splicing_conformance.py": 1,
    "tests/conformance/bash/test_grammar_boundaries_conformance.py": 1,
    "tests/conformance/bash/test_hash_conformance.py": 1,
    "tests/conformance/bash/test_heredoc_delimiter_conformance.py": 1,
    "tests/conformance/bash/test_heredoc_transaction_conformance.py": 1,
    "tests/conformance/bash/test_history_p_interactive_conformance.py": 6,
    "tests/conformance/bash/test_history_state_machine_conformance.py": 1,
    "tests/conformance/bash/test_identifier_policy_conformance.py": 1,
    "tests/conformance/bash/test_keyword_word_boundary_conformance.py": 1,
    "tests/conformance/bash/test_lineno_conformance.py": 1,
    "tests/conformance/bash/test_locale_warn_trigger_conformance.py": 1,
    "tests/conformance/bash/test_nameref_array_append_conformance.py": 1,
    "tests/conformance/bash/test_nameref_attribute_conformance.py": 1,
    "tests/conformance/bash/test_nounset_arithmetic_conformance.py": 1,
    "tests/conformance/bash/test_nounset_array_conformance.py": 1,
    "tests/conformance/bash/test_opaque_environment_conformance.py": 1,
    "tests/conformance/bash/test_param_transform_keyvalue_conformance.py": 1,
    "tests/conformance/bash/test_parse_continuation_s4_conformance.py": 1,
    "tests/conformance/bash/test_posixly_correct_conformance.py": 1,
    "tests/conformance/bash/test_prefix_assignment_conformance.py": 1,
    "tests/conformance/bash/test_printf_float_format_conformance.py": 1,
    "tests/conformance/bash/test_prompt_expansion_conformance.py": 1,
    "tests/conformance/bash/test_read_escapes_conformance.py": 1,
    "tests/conformance/bash/test_read_exact_chars_conformance.py": 1,
    "tests/conformance/bash/test_read_ifs_split_conformance.py": 1,
    "tests/conformance/bash/test_resolution_timing_conformance.py": 2,
    "tests/conformance/bash/test_resolver_conformance.py": 1,
    "tests/conformance/bash/test_set_o_history_conformance.py": 1,
    "tests/conformance/bash/test_subscript_keying_conformance.py": 8,
    "tests/conformance/bash/test_syntax_template_timing_conformance.py": 2,
    "tests/conformance/bash/test_temporary_env_conformance.py": 1,
    "tests/conformance/bash/test_trap_flags_conformance.py": 1,
    "tests/conformance/bash/test_trap_signal_spec_conformance.py": 2,
    "tests/conformance/bash/test_typed_expansion_errors_conformance.py": 2,
    "tests/conformance/bash/test_unset_nameref_conformance.py": 1,
    "tests/conformance/bash/test_v_array_conformance.py": 1,
    "tests/conformance/bash/test_variable_projection_reads_conformance.py": 1,
    "tests/conformance/bash/test_variable_truth_conformance.py": 2,
    "tests/conformance/bash/test_wait_unset_conformance.py": 1,
    "tests/conformance/posix/test_posix_special_builtin_exit_conformance.py": 1,
    "tests/conformance/posix/test_readonly_conformance.py": 2,
    "tests/harness/oracle_migration_census.md": 1,
    "tests/harness/shell_oracle.py": 1,
    "tests/integration/arrays/test_array_element_word_values.py": 4,
    "tests/integration/arrays/test_array_init_word_expansion.py": 1,
    "tests/integration/arrays/test_arrays_comprehensive.py": 2,
    "tests/integration/arrays/test_associative_array_bug.py": 1,
    "tests/integration/builtins/test_bcontract_dirstack_transactions.py": 1,
    "tests/integration/command_resolution/test_command_resolution.py": 1,
    "tests/integration/command_resolution/test_exec_failure_wording.py": 1,
    "tests/integration/command_resolution/test_hash_execution.py": 1,
    "tests/integration/control_flow/test_break_continue_as_builtins.py": 1,
    "tests/integration/control_flow/test_break_continue_levels.py": 2,
    "tests/integration/control_flow/test_c_style_for_loops.py": 2,
    "tests/integration/control_flow/test_case_subject_quoting.py": 1,
    "tests/integration/control_flow/test_eval_control_flow.py": 1,
    "tests/integration/control_flow/test_for_select_item_expansion.py": 2,
    "tests/integration/control_flow/test_loop_control_scope_boundary.py": 1,
    "tests/integration/control_flow/test_tier3_executor_fixes.py": 1,
    "tests/integration/control_flow/test_while_loops.py": 1,
    "tests/integration/functions/test_funcnest.py": 1,
    "tests/integration/functions/test_recursion_depth.py": 1,
    "tests/integration/functions/test_wait_n.py": 1,
    "tests/integration/job_control/test_background_jobs.py": 1,
    "tests/integration/job_control/test_bg_child_trap_discipline.py": 2,
    "tests/integration/job_control/test_boundary_j1_lifecycle.py": 1,
    "tests/integration/job_control/test_debug_err_traps.py": 3,
    "tests/integration/job_control/test_exit_trap_paths.py": 3,
    "tests/integration/job_control/test_fg_bg_check_order.py": 1,
    "tests/integration/job_control/test_job_notice_channel.py": 5,
    "tests/integration/job_control/test_jobs_completed_listing_modes.py": 1,
    "tests/integration/job_control/test_jobs_n_changed.py": 2,
    "tests/integration/job_control/test_jobs_x_substitution.py": 1,
    "tests/integration/job_control/test_jobspec_operands.py": 1,
    "tests/integration/job_control/test_noninteractive_job_refresh.py": 1,
    "tests/integration/job_control/test_pending_signal_trap_eof.py": 1,
    "tests/integration/job_control/test_pipeline_signal_death.py": 1,
    "tests/integration/job_control/test_signal_handling.py": 3,
    "tests/integration/job_control/test_signal_killed_exit_status.py": 1,
    "tests/integration/job_control/test_stopped_job_current_marker.py": 1,
    "tests/integration/job_control/test_trap_actions.py": 2,
    "tests/integration/job_control/test_wait_disown_bg_fg.py": 2,
    "tests/integration/parser/test_heredoc_error_lineno.py": 1,
    "tests/integration/parsing/test_amp_command_position.py": 1,
    "tests/integration/parsing/test_bang_prefix_compound.py": 2,
    "tests/integration/parsing/test_brace_extent_literal_brace.py": 1,
    "tests/integration/parsing/test_cmdsub_grammar.py": 1,
    "tests/integration/parsing/test_quoting_escaping.py": 1,
    "tests/integration/parsing/test_r16_command_position.py": 1,
    "tests/integration/parsing/test_r17_parser_cluster.py": 1,
    "tests/integration/parsing/test_statement_separators.py": 2,
    "tests/integration/parsing/test_word_splitting.py": 1,
    "tests/integration/redirection/test_builtin_dup_source_reassigned.py": 2,
    "tests/integration/redirection/test_builtin_redirect_child_visibility.py": 1,
    "tests/integration/redirection/test_builtin_redirect_nesting.py": 3,
    "tests/integration/redirection/test_child_fd_inheritance.py": 1,
    "tests/integration/redirection/test_compound_redirect_failure.py": 1,
    "tests/integration/redirection/test_exec_close_output_leak.py": 1,
    "tests/integration/redirection/test_exec_permanent_redirect.py": 2,
    "tests/integration/redirection/test_external_redirect_once.py": 1,
    "tests/integration/redirection/test_fd_move_and_csh_redirect.py": 1,
    "tests/integration/redirection/test_here_string_tilde.py": 1,
    "tests/integration/redirection/test_here_string_word_quoting.py": 1,
    "tests/integration/redirection/test_heredoc_shared_cursor_r1.py": 2,
    "tests/integration/redirection/test_noclobber_targets.py": 1,
    "tests/integration/redirection/test_process_sub_closed_fds.py": 1,
    "tests/integration/redirection/test_process_sub_embedded.py": 1,
    "tests/integration/redirection/test_redirect_close_stdin_alive_r1.py": 1,
    "tests/integration/redirection/test_redirect_diagnostic_prefix_r1.py": 3,
    "tests/integration/redirection/test_redirect_failure_paths.py": 2,
    "tests/integration/redirection/test_redirect_order_r1.py": 2,
    "tests/integration/redirection/test_redirection_restore.py": 1,
    "tests/integration/redirection/test_self_dup_leniency_r1.py": 1,
    "tests/integration/shell_options/test_errexit_script_mode.py": 1,
    "tests/integration/shell_options/test_nounset_script_mode.py": 1,
    "tests/integration/subshells/test_state_inheritance.py": 1,
    "tests/integration/subshells/test_subshell_basics.py": 1,
    "tests/integration/subshells/test_subshell_implementation.py": 1,
    "tests/integration/test_arith_readonly_continue.py": 2,
    "tests/integration/test_assignment_error_abort.py": 1,
    "tests/integration/test_brace_adjacency_idioms.py": 1,
    "tests/integration/test_enhanced_test_unary_word_operand.py": 1,
    "tests/integration/test_eval_line_discard.py": 1,
    "tests/integration/test_extglob_nonfinal_path.py": 1,
    "tests/integration/test_fatal_expansion_model.py": 2,
    "tests/integration/test_posix_special_builtin_exit.py": 6,
    "tests/integration/test_ps4_expansion.py": 2,
    "tests/integration/test_scripting_idioms.py": 1,
    "tests/integration/test_time_keyword.py": 2,
    "tests/integration/test_xtrace_format.py": 1,
    "tests/integration/variables/test_variable_assignment.py": 1,
    "tests/parser_differential/test_input_contract_parity.py": 2,
    "tests/performance/benchmarks/test_pattern_engine_performance.py": 1,
    "tests/system/interactive/test_heredoc_detection_interactive_pty.py": 1,
    "tests/system/interactive/test_pty_smoke.py": 5,
    "tests/system/interactive/test_substitution_abort_interactive_pty.py": 1,
    "tests/system/invocation/test_invocation_matrix.py": 1,
    "tests/system/source_service/test_nul_channel_matrix.py": 2,
    "tests/system/source_service/test_source_service_matrix.py": 2,
    "tests/system/test_analysis_mode_line_continuation.py": 1,
    "tests/system/test_analysis_state_aware.py": 7,
    "tests/system/test_cli_argument_parsing.py": 3,
    "tests/system/test_eof_dangling_continuation.py": 2,
    "tests/system/test_r16_scripting.py": 1,
    "tests/system/test_read_malformed_bytes_i1.py": 1,
    "tests/system/test_script_input_sources.py": 1,
    "tests/system/test_source_error_rc.py": 2,
    "tests/system/test_unterminated_heredoc.py": 1,
    "tests/unit/builtins/test_alias_builtins.py": 2,
    "tests/unit/builtins/test_ansi_c_reuse_surfaces.py": 3,
    "tests/unit/builtins/test_bcontract_argument_policy.py": 2,
    "tests/unit/builtins/test_bcontract_nameref_riders.py": 1,
    "tests/unit/builtins/test_bcontract_serialization.py": 4,
    "tests/unit/builtins/test_builtin_base_helpers.py": 1,
    "tests/unit/builtins/test_candidate_banner.py": 1,
    "tests/unit/builtins/test_declaration_family_r19_t2.py": 3,
    "tests/unit/builtins/test_declare_bare_name_locality.py": 1,
    "tests/unit/builtins/test_directory_stack.py": 2,
    "tests/unit/builtins/test_disown_builtin.py": 1,
    "tests/unit/builtins/test_exec_builtin.py": 1,
    "tests/unit/builtins/test_exec_flags.py": 1,
    "tests/unit/builtins/test_export_builtin.py": 2,
    "tests/unit/builtins/test_function_builtins.py": 2,
    "tests/unit/builtins/test_hash_builtin.py": 1,
    "tests/unit/builtins/test_history_flags.py": 3,
    "tests/unit/builtins/test_io_builtins.py": 1,
    "tests/unit/builtins/test_jobs_filter_and_bg_marker.py": 1,
    "tests/unit/builtins/test_local_builtin.py": 4,
    "tests/unit/builtins/test_navigation.py": 1,
    "tests/unit/builtins/test_printf_enhanced.py": 2,
    "tests/unit/builtins/test_pwd_stack_convergence.py": 1,
    "tests/unit/builtins/test_r16t2_builtins_flags.py": 1,
    "tests/unit/builtins/test_r16t2_core_options.py": 1,
    "tests/unit/builtins/test_read_error_messages.py": 1,
    "tests/unit/builtins/test_read_mapfile_streaming.py": 1,
    "tests/unit/builtins/test_read_option_parsing.py": 1,
    "tests/unit/builtins/test_read_remainder.py": 1,
    "tests/unit/builtins/test_read_unified_quirks.py": 1,
    "tests/unit/builtins/test_readonly_export_attribute_flags.py": 1,
    "tests/unit/builtins/test_set_builtin.py": 1,
    "tests/unit/builtins/test_shopt_set_o.py": 2,
    "tests/unit/builtins/test_source_return.py": 1,
    "tests/unit/builtins/test_system_builtins.py": 1,
    "tests/unit/builtins/test_tier3_builtin_array_fixes.py": 1,
    "tests/unit/builtins/test_trap_flags.py": 1,
    "tests/unit/core/test_append_engine_characterization.py": 2,
    "tests/unit/core/test_array_scalar_overwrite.py": 1,
    "tests/unit/core/test_environ_policy.py": 1,
    "tests/unit/core/test_funcname_call_stack.py": 1,
    "tests/unit/core/test_getopts_state_p1.py": 1,
    "tests/unit/core/test_ifs_seed.py": 1,
    "tests/unit/core/test_option_reflection.py": 1,
    "tests/unit/core/test_pep538_locale.py": 1,
    "tests/unit/core/test_r18t2_corestate.py": 1,
    "tests/unit/core/test_scope_tombstones.py": 1,
    "tests/unit/core/test_special_registry.py": 3,
    "tests/unit/core/test_variable_lookup.py": 1,
    "tests/unit/core/test_variable_store_truth_table.py": 3,
    "tests/unit/executor/test_command_assignments.py": 2,
    "tests/unit/executor/test_executor_error_guards.py": 1,
    "tests/unit/executor/test_legacy_ast_fallbacks.py": 1,
    "tests/unit/executor/test_nocasematch_posix_classes.py": 1,
    "tests/unit/expansion/test_arith_compound_assign_order.py": 1,
    "tests/unit/expansion/test_arith_no_rescan_stored_value.py": 1,
    "tests/unit/expansion/test_arith_readonly_nameref.py": 1,
    "tests/unit/expansion/test_arith_recursion_variable_eval.py": 2,
    "tests/unit/expansion/test_arithmetic_characterization.py": 4,
    "tests/unit/expansion/test_arithmetic_command_form_dollar.py": 1,
    "tests/unit/expansion/test_arithmetic_comprehensive.py": 1,
    "tests/unit/expansion/test_arithmetic_division_semantics.py": 1,
    "tests/unit/expansion/test_arithmetic_dollar_expansion.py": 1,
    "tests/unit/expansion/test_arithmetic_integration.py": 2,
    "tests/unit/expansion/test_arithmetic_integration_advanced_todo.py": 1,
    "tests/unit/expansion/test_array_index_arith_errors.py": 1,
    "tests/unit/expansion/test_assignment_word_splitting.py": 3,
    "tests/unit/expansion/test_brace_budget.py": 1,
    "tests/unit/expansion/test_brace_pu_sentinels.py": 1,
    "tests/unit/expansion/test_braceexpand_option.py": 2,
    "tests/unit/expansion/test_bracket_pattern_edge_cases.py": 1,
    "tests/unit/expansion/test_case_toggle.py": 1,
    "tests/unit/expansion/test_command_sub_bytes.py": 1,
    "tests/unit/expansion/test_command_sub_closed_fds.py": 1,
    "tests/unit/expansion/test_dollar_bracket_arithmetic.py": 1,
    "tests/unit/expansion/test_expand_aliases_option.py": 1,
    "tests/unit/expansion/test_expansion_correctness_sweep.py": 1,
    "tests/unit/expansion/test_extglob_negation.py": 1,
    "tests/unit/expansion/test_globstar_symlinks.py": 1,
    "tests/unit/expansion/test_multi_field_expansion.py": 1,
    "tests/unit/expansion/test_param_parser_behavior_fixes.py": 1,
    "tests/unit/expansion/test_param_parser_differential.py": 1,
    "tests/unit/expansion/test_parameter_expansion.py": 4,
    "tests/unit/expansion/test_parameter_transform.py": 1,
    "tests/unit/expansion/test_patsub_nocase_and_anchoring.py": 4,
    "tests/unit/expansion/test_pattern_bash_composition_differential.py": 3,
    "tests/unit/expansion/test_pattern_operand_expansion.py": 4,
    "tests/unit/expansion/test_pattern_relations.py": 3,
    "tests/unit/expansion/test_posix_char_classes.py": 1,
    "tests/unit/expansion/test_process_sub_quoting.py": 1,
    "tests/unit/expansion/test_slice_semantics.py": 1,
    "tests/unit/expansion/test_special_variables.py": 1,
    "tests/unit/expansion/test_star_view_per_element_ops.py": 1,
    "tests/unit/expansion/test_subscript_evaluator.py": 2,
    "tests/unit/expansion/test_substitution_empty_match_pins.py": 1,
    "tests/unit/expansion/test_substring_lazy_arithmetic.py": 1,
    "tests/unit/expansion/test_tilde_prefix_boundary.py": 3,
    "tests/unit/expansion/test_value_operand_quoting.py": 1,
    "tests/unit/expansion/test_view_operators_joined_nullness.py": 1,
    "tests/unit/expansion/test_word_expansion_policy.py": 1,
    "tests/unit/interactive/test_edit_buffer_killring.py": 1,
    "tests/unit/interactive/test_eof_policy.py": 1,
    "tests/unit/interactive/test_histcontrol_histignore.py": 2,
    "tests/unit/interactive/test_history_nav.py": 1,
    "tests/unit/interactive/test_history_state_machine_4b3.py": 2,
    "tests/unit/io_redirect/test_named_fd_heredoc.py": 1,
    "tests/unit/io_redirect/test_redirect_predicates.py": 1,
    "tests/unit/lexer/test_ansi_c_quoting.py": 1,
    "tests/unit/lexer/test_arith_cmdsub_disambiguation.py": 1,
    "tests/unit/lexer/test_arith_gate_semantic_n2.py": 2,
    "tests/unit/lexer/test_backtick_dquote_escapes.py": 1,
    "tests/unit/lexer/test_bracket_quote_words.py": 1,
    "tests/unit/lexer/test_case_mapping.py": 1,
    "tests/unit/lexer/test_command_position_after_amp.py": 1,
    "tests/unit/lexer/test_fallback_words.py": 1,
    "tests/unit/lexer/test_heredoc_brace_expansion.py": 1,
    "tests/unit/lexer/test_heredoc_lexer.py": 1,
    "tests/unit/lexer/test_post_lex_fusion_order_b3.py": 2,
    "tests/unit/lexer/test_word_scanners.py": 1,
    "tests/unit/parser/combinators/test_composite_conditional_patterns.py": 2,
    "tests/unit/parser/test_background_lists.py": 1,
    "tests/unit/parser/test_c_style_for_body_forms.py": 1,
    "tests/unit/parser/test_case_pattern_empty_alternatives.py": 1,
    "tests/unit/parser/test_case_subject.py": 1,
    "tests/unit/parser/test_composite_headed_assignment_b1.py": 2,
    "tests/unit/parser/test_escaped_dollar_syntax.py": 2,
    "tests/unit/parser/test_misplaced_case_terminators.py": 1,
    "tests/unit/parser/test_r18t2_lexparse_fixes.py": 1,
    "tests/unit/parser/test_regex_operand_policy.py": 1,
    "tests/unit/parser/test_word_fusion_improvement_surface_n3.py": 2,
    "tests/unit/scripting/test_analysis_session.py": 2,
    "tests/unit/scripting/test_heredoc_alias_route.py": 1,
    "tests/unit/scripting/test_line_continuation_contexts.py": 1,
    "tests/unit/scripting/test_program_source_unit.py": 3,
    "tests/unit/test_line_editor_helpers.py": 2,
    "tests/unit/test_parse_invocation.py": 2,
    "tests/unit/tooling/test_gate_attestation.py": 5,
    "tests/unit/tooling/test_operand_projection_guard.py": 1,
    "tests/unit/tooling/test_shell_oracle_harness.py": 1,
    "tests/unit/utils/test_escape_dialects.py": 3,
    "tests/unit/utils/test_heredoc_detection.py": 1,
    "tests/unit/utils/test_printf_formatter.py": 4,
    "tests/unit/utils/test_signal_listing.py": 2,
    "tests/unit/visitor/test_security_missed_positions.py": 6,
}


def census():
    """``{relative file: count}`` for every text file under SCAN_ROOTS with
    at least one claim; undecodable (binary) files are skipped."""
    counts = {}
    here = Path(__file__).resolve()
    for root in SCAN_ROOTS:
        for dirpath, dirnames, filenames in os.walk(REPO_ROOT / root):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for fn in sorted(filenames):
                path = Path(dirpath) / fn
                if path == here or fn.endswith(".pyc"):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                n = len(CLAIM.findall(text))
                if n:
                    counts[path.relative_to(REPO_ROOT).as_posix()] = n
    return counts


def test_no_new_bash_5_2_claims():
    """Ratchet: no file may exceed its frozen baseline."""
    grown = {f: (BASELINE.get(f, 0), n) for f, n in census().items()
             if n > BASELINE.get(f, 0)}
    assert not grown, (
        "new " + "ba" + "sh 5.2 claim(s) — the oracle is bash 5.3 (D1); a NEW "
        "provenance stamp must say 5.3.15 (or 'empirical, 5.3.15'), and a "
        "synthetic version string belongs in a test that names it as such "
        "(D12). {file: (baseline, now)}:\n  "
        + "\n  ".join(f"{f}: {was} -> {now}" for f, (was, now) in sorted(grown.items())))


def test_baseline_entries_refer_to_existing_files():
    """A deleted/renamed file's entry must be PRUNED (the only allowed edit
    besides lowering a count)."""
    stale = [f for f in BASELINE if not (REPO_ROOT / f).is_file()]
    assert not stale, f"prune stale baseline entries: {stale}"


def test_baseline_is_internally_consistent():
    assert sum(BASELINE.values()) == BASELINE_TOTAL
    assert all(n > 0 for n in BASELINE.values()), "zero entries are just absence"


def test_census_scope_reaches_known_claim_sites():
    files = census()
    for probe in ("tests/behavioral/golden_cases.yaml",
                  "tests/conformance/bash/test_subscript_keying_conformance.py",
                  "psh/core/state.py"):
        assert probe in files, f"census scope lost {probe}"


@pytest.mark.parametrize("text, hits", [
    ("verified against " + "ba" + "sh 5.2", 1),
    ("Verified against " + "Ba" + "sh 5.2.26", 1),      # counted once, not twice
    ("ba" + "sh-5.2 patch 21", 1),
    ("5.2." + "26(1)-release", 1),
    ("probed on " + "ba" + "sh 5.2.21 and 5.2." + "26", 2),
    ("ba" + "sh 5.3.15", 0),
    ("ba" + "sh 5.20", 0),
    ("5.3.15(1)-release", 0),
    ("ba" + "sh5.2", 0),
])
def test_claim_pattern(text, hits):
    assert len(CLAIM.findall(text)) == hits
