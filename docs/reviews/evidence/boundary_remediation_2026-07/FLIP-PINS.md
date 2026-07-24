# Flip-pin inventory (integrator plan amendment A3)

Tests that PIN a psh↔bash divergence this campaign intends to CLOSE. Each goes
RED when its fix lands; the owning slot must flip it to an equality pin IN THE
SAME SLOT and close the ledger row. Enumerated at `0215279c` via
`grep -rn "def test_divergence_\|KNOWN_DIVERGENCES\|assert_documented_difference" tests/`.

## Must-flip (a wave owns the fix)

| Pin | Owning slot |
|---|---|
| `tests/conformance/bash/test_subscript_keying_conformance.py::test_divergence_operand_at_flattens` (4 params) | 3.3 |
| `tests/conformance/bash/test_nested_substitution_timing_conformance.py::test_divergence_c_mode_exit_code_is_127_in_bash` (6 params: `$(if)`, `<(if)`, `${x:-$(if)}`, `$(($(if)+1))`, `${a[$(if)]}`, `a[$(if)]=v`) | 2.4 |
| `tests/conformance/bash/test_syntax_template_timing_conformance.py::test_divergence_eval_source_fatality_is_i3` | 2.4 |
| `test_subscript_keying_conformance.py::test_divergence_procsub_in_subscript_read_time` (+ the adjacent procsub timing/dead-branch divergence tests around it) | 2.3 |
| `test_subscript_keying_conformance.py::test_divergence_quote_blind_extent_in_assignment_word` (K1 extent) | 2.3 |
| `test_subscript_keying_conformance.py::test_divergence_sq_inside_dq_subscript` (parse-time vs runtime rejection half) | 2.3 |
| `tests/unit/expansion/test_pattern_engine_differential.py` `KNOWN_DIVERGENCES` = {q4_sub1, q4_sub2, q4_sub3, neg7_sub3} + `test_known_divergences_are_still_divergent` | 3.1 |

Plus (unit-level, same slots): any `tests/unit/**` twins of the above that
assert the psh-divergent result — the owning slot sweeps its own files.

## Must-NOT-flip (sanctioned divergences that stay; guard against accidental "fixes")

| Pin | Status |
|---|---|
| `test_subscript_keying_conformance.py::test_divergence_empty_arith_subscript_fatality` | Re-carried (ledger B#3); 2.3 may deliberately flip WITH a ruling — never silently. |
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
