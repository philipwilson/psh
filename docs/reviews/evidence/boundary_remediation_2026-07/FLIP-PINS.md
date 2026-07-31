# Flip-pin inventory (integrator plan amendment A3)

Tests that PIN a psh↔bash divergence this campaign intends to CLOSE. Each goes
RED when its fix lands; the owning slot must flip it to an equality pin IN THE
SAME SLOT and close the ledger row. Enumerated at `0215279c` via
`grep -rn "def test_divergence_\|KNOWN_DIVERGENCES\|assert_documented_difference" tests/`.

## Must-flip (a wave owns the fix)

| Pin | Owning slot |
|---|---|
| `tests/conformance/bash/test_subscript_keying_conformance.py::test_divergence_operand_at_flattens` (4 params) | 3.3 |
| ~~`test_nested_substitution_timing_conformance.py::test_divergence_c_mode_exit_code_is_127_in_bash` (6 params)~~ | **2.4 — FLIPPED v0.760.0** (renamed `test_c_mode_exit_code_is_127_like_bash`, same 6 params, equality vs bash; complete-but-invalid twin `test_c_mode_127_for_complete_but_invalid_bodies` + other-kinds sweep added beside it) |
| ~~**CO-FLIP:** golden `heredoc_nested_error_reports_absolute_line` exit_code 2~~ | **2.4 — FLIPPED v0.760.0** (exit_code 2→127, ONLY that data field — verified in-diff; the row is psh_only so compare-bash composition unchanged) |
| ~~`test_syntax_template_timing_conformance.py::test_divergence_eval_source_fatality_is_i3`~~ | **2.4 — FLIPPED v0.760.0** (renamed `test_eval_source_frame_fatality_matches_bash`; frame table equality vs bash) |
| ~~**CO-FLIP:** `test_divergence_eval_source_procsub_joined_i3`~~ | **2.4 — FLIPPED v0.760.0** (renamed `test_eval_source_procsub_joined_family_matches_bash`; LOCATION CORRECTED: this pin always lived in `test_syntax_template_timing_conformance.py`, not `test_subscript_keying_conformance.py` as this row previously said — integrator transcription error at the v0.758.0 ceremony, caught by dev-2-4 Phase A) |
| ~~`test_subscript_keying_conformance.py::test_divergence_procsub_in_subscript_read_time` (+ adjacent family)~~ | **2.3 — FLIPPED v0.758.0** (equality/parity pins: literal keying + read-time rejection = bash; family superseded by the per-route matrix + render-tier pins) |
| ~~`test_subscript_keying_conformance.py::test_divergence_quote_blind_extent_in_assignment_word` (K1 extent)~~ | **2.3 — FLIPPED v0.758.0** (`test_quote_aware_extent_in_assignment_word` + read-side + whole-string arg validation; = bash) |
| ~~`test_subscript_keying_conformance.py::test_divergence_sq_inside_dq_subscript`~~ | **2.3 — CLOSED v0.758.0 as NEVER-A-LIVE-DIVERGENCE** (basis stale at 0215279c — both shells defer to runtime; replaced by `test_sq_inside_dq_subscript_runtime_stage_parity`, a full parity row; findings-integrity note in LEDGER) |
| 2.4-declared divergence pins (successor-owned if ever flipped): `test_redirect_procsub_suppression_is_a_declared_divergence`, `test_function_member_channel_rule_is_a_declared_divergence`, `test_exit_trap_teardown_under_errexit_is_a_declared_divergence`, `test_interactive_dash_c_channel_disposition`, the O3/O4 declared rows and `--validate` half of `test_static_check_spellings_dash_n_and_validate` — each flips ONLY with a ruling; domains in their docstrings + LEDGER Part D. | successors |
| `tests/unit/expansion/test_pattern_engine_differential.py` `KNOWN_DIVERGENCES` = {q4_sub1, q4_sub2, q4_sub3, neg7_sub3} + `test_known_divergences_are_still_divergent` | 3.1 |

Plus (unit-level, same slots): any `tests/unit/**` twins of the above that
assert the psh-divergent result — the owning slot sweeps its own files.

## Successor-owned (carry pins added v0.757.0+; no chartered wave slot yet)

| Pin | Owner |
|---|---|
| 2.3 lexer word-extent family: `test_divergence_lexer_splits_quoted_space_subscript`, `test_divergence_procsub_compound_dollar_body_lexer_blocked`, `test_divergence_doubled_open_unclosed_family`, `test_divergence_A1_doubled_open_unclosed_family` | successor lexer slot (LEDGER "2.3 carry: LEXER word-extent family"); the r18 NO-PROGRESS CRASH in the same area is UNPINNED by design — priority row |
| 2.3 residual pins: `test_divergence_unset_nonbracket_arg_silent`, `test_divergence_assignment_prefix_element_split`, `test_divergence_procsub_separated_subshell_residual`, `test_divergence_procsub_compound_render_residual` (4 params), `test_divergence_pipe_amp_body_render`, `test_divergence_comment_in_body` | successor queue (LEDGER 2.3 carry rows; render residuals flip only with a faithful compound/`|&` re-render) |
| `tests/parser_differential/test_input_contract_parity.py::test_CARRY_array_init_nested_substitution_still_diverges_on_combinator` + its redirect-target twin (combinator arrays.py word-builder seam — array init, element assignment, redirect targets) | successor (LEDGER "2.2 carry: arrays.py word-builder seam"); both co-flip ONLY when the whole seam is threaded at once |

| 2.5-declared divergence pins (v0.761.0; successor-owned if ever flipped): `test_divergence_alias_heredoc_body_is_not_collected` (tests/unit/io_redirect/test_heredoc_alias_route.py — bash collects heredoc bodies at alias expansion, psh cannot; the WHOLE alias-heredoc family; fix = body collection at alias-expansion time, LEDGER 2.5 successor row a), `test_divergence_null_command_named_fd_keeps_the_descriptor` (tests/unit/io_redirect/test_named_fd_heredoc.py — bash performs-then-undoes leaving the var unset; pre-existing semantics newly reachable, successor row b), `test_divergence_plain_and_digit_degenerate_forms` (tests/system/interactive/test_heredoc_detection_interactive_pty.py — plain/digit dangling-heredoc PS2 policy vs bash complete-with-error; asserted in the DIVERGENT direction so a fix is a visible flip, successor row d). Each flips ONLY with a ruling; domains in their docstrings + LEDGER 2.5 successor rows. | successors |

## Must-NOT-flip (sanctioned divergences that stay; guard against accidental "fixes")

| Pin | Status |
|---|---|
| `test_subscript_keying_conformance.py::test_divergence_empty_arith_subscript_fatality` | Re-carried (ledger B#3); 2.3 left it INTACT (verified rounds 1-4). Deliberate flip needs a ruling — never silently. |
| `::test_divergence_dq_ansi_bracket_read` (+ 18-cell parity matrix) | **2.3 KEEP-ruled v0.758.0** (bash cannot read back its own `$'['`-keyed write; psh round-trips). Never "fix" toward bash's broken shape. |
| `::test_divergence_sq_in_dq_readback_outcome` | **2.3 KEEP-ruled v0.758.0** (same bash-cannot-read-own-writes family). |
| `::test_divergence_unlexable_subscript_typed_error` (route × carrier) | **2.3-declared v0.758.0** (e2 family: psh typed rc-1 vs bash rc-2 lexer-reject; base printed 0 on junk keys — never regress to that). |
| 2.3 declared builtin-route faces (printf/read/let/nameref wording + printf-raw rc, in the route-audit pins) | **2.3-declared v0.758.0**; fixing = per-builtin surgery, needs its own grant. |
| `::test_divergence_arith_nested_quote_carriers` | Re-carried (B#23, successor). |
| `::test_divergence_arith_error_wording_not_keying`, `::test_divergence_assoc_enumeration_order`, `::test_divergence_arith_subscript_adjacency_required` | Wording/order/adjacency — both-shells facts, not campaign targets. |
| `test_nested_substitution_timing_conformance.py::test_divergence_alias_local_to_cmdsub_body`, `::test_divergence_heredoc_body_cmdsub_stays_runtime` | Recorded semantics, not #22 targets — 2.3/2.4 must leave them green or re-rule explicitly. |
| `tests/conformance/bash/test_cv_carry_characterization.py` (all classes: TestPosixSpecialBuiltinRedirectFatality, TestAnsiCHighEscapeByteModel, TestTwoTierIntrospectionResidual, TestPermissionDeniedWording, TestStickyNonExecHash, TestExecutableSpecialFileEarlier, TestDoubleBracketArithProvenance) | Characterize re-carried rows (B#18/19/24/27/30/31). Stay. |
| `test_history_p_interactive_conformance.py::TestHistoryEvalOuterSinglePExpansionH35` | B#35, stays. |
| `tests/conformance/differences/` framework + `assert_documented_difference` users (`test_posix_compliance.py` ×2, `test_user_guide_notes_conformance.py` ×1) | Slot 1.2 audits these three during oracle migration: each either maps to a ledger row or gets one. |

## Watch note

Slot 4B.3 (history) closes ledger B#32: the nightly's 6 red
`test_history_outcomes_i4.py` rows on Linux may interact — 1.4 classifies them
first; 4B.3 consumes that classification.
