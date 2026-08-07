# Flip-pin inventory (integrator plan amendment A3)

Tests that PIN a psh↔bash divergence this campaign intends to CLOSE. Each goes
RED when its fix lands; the owning slot must flip it to an equality pin IN THE
SAME SLOT and close the ledger row. Enumerated at `0215279c` via
`grep -rn "def test_divergence_\|KNOWN_DIVERGENCES\|assert_documented_difference" tests/`.

## Must-flip (a wave owns the fix)

| Pin | Owning slot |
|---|---|
| ~~`tests/conformance/bash/test_subscript_keying_conformance.py::test_divergence_operand_at_flattens` (4 params)~~ | **3.3 — FLIPPED v0.765.0** (renamed `test_operand_at_preserves_fields`, 4→21 equality rows vs bash — subject shape, zero/empty positionals, IFS, non-colon operators, `[*]` views — plus `test_operand_at_preserves_fields_combinator` 7 rows; the LAST must-flip row: this table's flip obligations are now ALL discharged) |
| ~~`test_nested_substitution_timing_conformance.py::test_divergence_c_mode_exit_code_is_127_in_bash` (6 params)~~ | **2.4 — FLIPPED v0.760.0** (renamed `test_c_mode_exit_code_is_127_like_bash`, same 6 params, equality vs bash; complete-but-invalid twin `test_c_mode_127_for_complete_but_invalid_bodies` + other-kinds sweep added beside it) |
| ~~**CO-FLIP:** golden `heredoc_nested_error_reports_absolute_line` exit_code 2~~ | **2.4 — FLIPPED v0.760.0** (exit_code 2→127, ONLY that data field — verified in-diff; the row is psh_only so compare-bash composition unchanged) |
| ~~`test_syntax_template_timing_conformance.py::test_divergence_eval_source_fatality_is_i3`~~ | **2.4 — FLIPPED v0.760.0** (renamed `test_eval_source_frame_fatality_matches_bash`; frame table equality vs bash) |
| ~~**CO-FLIP:** `test_divergence_eval_source_procsub_joined_i3`~~ | **2.4 — FLIPPED v0.760.0** (renamed `test_eval_source_procsub_joined_family_matches_bash`; LOCATION CORRECTED: this pin always lived in `test_syntax_template_timing_conformance.py`, not `test_subscript_keying_conformance.py` as this row previously said — integrator transcription error at the v0.758.0 ceremony, caught by dev-2-4 Phase A) |
| ~~`test_subscript_keying_conformance.py::test_divergence_procsub_in_subscript_read_time` (+ adjacent family)~~ | **2.3 — FLIPPED v0.758.0** (equality/parity pins: literal keying + read-time rejection = bash; family superseded by the per-route matrix + render-tier pins) |
| ~~`test_subscript_keying_conformance.py::test_divergence_quote_blind_extent_in_assignment_word` (K1 extent)~~ | **2.3 — FLIPPED v0.758.0** (`test_quote_aware_extent_in_assignment_word` + read-side + whole-string arg validation; = bash) |
| ~~`test_subscript_keying_conformance.py::test_divergence_sq_inside_dq_subscript`~~ | **2.3 — CLOSED v0.758.0 as NEVER-A-LIVE-DIVERGENCE** (basis stale at 0215279c — both shells defer to runtime; replaced by `test_sq_inside_dq_subscript_runtime_stage_parity`, a full parity row; findings-integrity note in LEDGER) |
| 2.4-declared divergence pins (successor-owned if ever flipped): `test_redirect_procsub_suppression_is_a_declared_divergence`, `test_function_member_channel_rule_is_a_declared_divergence`, `test_exit_trap_teardown_under_errexit_is_a_declared_divergence`, `test_interactive_dash_c_channel_disposition`, the O3/O4 declared rows and `--validate` half of `test_static_check_spellings_dash_n_and_validate` — each flips ONLY with a ruling; domains in their docstrings + LEDGER Part D. | successors |
| ~~`tests/unit/expansion/test_pattern_engine_differential.py` `KNOWN_DIVERGENCES` = {q4_sub1, q4_sub2, q4_sub3, neg7_sub3} + `test_known_divergences_are_still_divergent`~~ | **3.1 — CLOSED v0.763.0** (all four keys mechanically derived from bash's substitution consumer layer and CLOSED — the set is deleted and the keys joined the equality lock; the flip instrument was RENAMED `test_former_known_divergences_now_match_bash`, and the old empty-subject rationale ("not derivable from the match extent") is superseded by the measured consumer mechanics; ruling R2, evidence `3.1-rescue/`) |

Plus (unit-level, same slots): any `tests/unit/**` twins of the above that
assert the psh-divergent result — the owning slot sweeps its own files.

## Successor-owned (carry pins added v0.757.0+; no chartered wave slot yet)

| Pin | Owner |
|---|---|
| 2.3 lexer word-extent family: `test_divergence_lexer_splits_quoted_space_subscript`, `test_divergence_procsub_compound_dollar_body_lexer_blocked`, `test_divergence_doubled_open_unclosed_family`, `test_divergence_A1_doubled_open_unclosed_family` | successor lexer slot (LEDGER "2.3 carry: LEXER word-extent family"); the r18 NO-PROGRESS CRASH in the same area is UNPINNED by design — priority row |
| 2.3 residual pins: `test_divergence_unset_nonbracket_arg_silent`, `test_divergence_assignment_prefix_element_split`, `test_divergence_procsub_separated_subshell_residual`, `test_divergence_procsub_compound_render_residual` (4 params), `test_divergence_pipe_amp_body_render`, `test_divergence_comment_in_body` | successor queue (LEDGER 2.3 carry rows; render residuals flip only with a faithful compound/`|&` re-render) |
| 4B.2 declared divergences (NOT named `test_divergence_*` — registered here per R13-E(4) so the grep inventory stays honest): D-4B.2-s1 timeout-partial assignment = `test_input_decoder_seam_4b2.py::TestResumeAcrossReads` (`test_next_read_record_resumes_the_split_character` + `test_next_read_limited_resumes_the_split_character`, 12 params, I1-style assert-psh-AND-assert-bash-differs) + `test_read_exact_timeout_4b2.py::TestRiderRcParityWithDeclaredNew1Residue` (3 cells) | 4B.4 (deferred by 4B.2 ruling (c); doc + code move together) |
| 4B.2 s2/s3: D-4B.2-s2 `-N` count model (rc-reaching) = `test_read_exact_timeout_4b2.py::test_backslash_under_deadline_diverges_in_rc_and_value` (pinned to DEMAND reclassification if fixed); D-4B.2-s3 `read -s -N` tty echo = UNPINNED by design (report row, verifier probe in `4b.2-rescue/`). Carry-#21 characterization cells live in `test_cv_carry_characterization.py` (a must-NOT-flip file; +6 cells at v0.771.0) | successor queue |
| `tests/parser_differential/test_input_contract_parity.py::test_CARRY_array_init_nested_substitution_still_diverges_on_combinator` + its redirect-target twin (combinator arrays.py word-builder seam — array init, element assignment, redirect targets) | successor (LEDGER "2.2 carry: arrays.py word-builder seam"); both co-flip ONLY when the whole seam is threaded at once |

| 2.5-declared divergence pins (v0.761.0; successor-owned if ever flipped): `test_divergence_alias_heredoc_body_is_not_collected` (tests/unit/io_redirect/test_heredoc_alias_route.py — bash collects heredoc bodies at alias expansion, psh cannot; the WHOLE alias-heredoc family; fix = body collection at alias-expansion time, LEDGER 2.5 successor row a), `test_divergence_null_command_named_fd_keeps_the_descriptor` (tests/unit/io_redirect/test_named_fd_heredoc.py — bash performs-then-undoes leaving the var unset; pre-existing semantics newly reachable, successor row b), `test_divergence_plain_and_digit_degenerate_forms` (tests/system/interactive/test_heredoc_detection_interactive_pty.py — plain/digit dangling-heredoc PS2 policy vs bash complete-with-error; asserted in the DIVERGENT direction so a fix is a visible flip, successor row d). Each flips ONLY with a ruling; domains in their docstrings + LEDGER 2.5 successor rows. | successors |
| 3.1-declared divergence pins (v0.763.0; successor-owned if ever flipped): the `RESIDUAL_DIVERGENCES` structure in `tests/unit/expansion/test_pattern_bash_composition_differential.py` — (a) LEXER-SEAM quoted-chars-in-extglob-group family: `lex_q1`/`lex_q3` (`[[ a == !("a") ]]` bash 1 / psh 0 — the lexer embeds the quote characters in the group's raw text; engine-level truth rows prove `compile_protected` is CORRECT, localizing the defect to the lexer seam) + `lex_case_q1` (same defect on the `case` consumer, round-1 N13); the `${}` operand path is NOT affected (q7 closed by the engine fix) so the successor scope is the `[[`/word seam; (b) OPERAND-EXTENT family: `opx_slash` (`v=''; "${v/*!(/)/Z}"` → bash `)/Z` / psh `` — bash terminates the substitution pattern at the first unquoted `/` regardless of the open paren, psh balances parens; PRE-EXISTING, found by round-3 verification). Each pinned in the DIVERGENT direction so a fix is a visible flip; each flips ONLY with a ruling. LEDGER 3.1 successor rows. | successors (lexer-seam rows join the r18/2.3 lexer neighborhood) |
| 3.3-declared divergence pins (v0.765.0; successor-owned if ever flipped; NOTE none is named `test_divergence_*` — recorded here per the R13-E(4) precedent so future FLIP-PINS greps do not miss them): `test_operand_bare_at_ifs_divergence` (3 params, tests/conformance/bash/test_subscript_keying_conformance.py — bare `$@` INSIDE a value operand under non-default IFS: parameter CONTENT resists the very IFS character the joining space splits on; bash `IFS=X; ${x:-$@}` w/ `set -- aXq b` → ONE field `aXq b`, psh splits; mechanism UN-MODELED, do not guess — LEDGER 3.3 successor row a), `test_case_pattern_multifield_operand_divergence` (2 params, same file — bash matches the FIRST FIELD of a multi-field case-pattern operand, psh space-joins = declared policy preserving base; LEDGER 3.3 successor row b), `test_positional_slice_empty_operand_divergence` (tests/conformance/bash/test_operand_field_ir_conformance.py — `${@:}`: bash `bad substitution` rc=1, psh accepts the slice INCLUDING `$0`; psh-side shape changed in 3.3 from joined to fields, declared; LEDGER 3.3 successor row c). Each pinned BOTH-SIDES in the divergent direction; each flips ONLY with a ruling. | successors |

## Must-NOT-flip (sanctioned divergences that stay; guard against accidental "fixes")

| Pin | Status |
|---|---|
| `test_pattern_bash_composition_differential.py::test_bash_matcher_states_stay_polynomial` — bound TIGHTENED (n+2)²→4·(n+2) + n=256 by slot 3.2 | **3.2 declared pin change v0.764.0** (ruled R1(4), tighten-only, red-on-base verified by round-2 diffAudit: base states 154 at n=16 vs bound 72; tip 18). The original bound was accidentally green — `count_states` counts memo misses (quadratic) while the guarded evaluation was cubic; complexity pins now live on `count_transitions`/`operation_transitions` (`test_pattern_engine_transitions.py`). Loosening either bound needs a ruling. |
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

| `tests/system/test_analysis_state_aware.py::TestTwoStaticSurfaces::test_two_static_surfaces_split` | 2.6 DELIBERATE divergence: `--validate` is state-aware, `psh -n`/`bash -n` stay state-blind (analysis-totality charter). RED-ON-BASE. NOT discoverable via the `def test_divergence_` enumeration above — recorded here per R13-E(4); the `bash -n` AGREEMENT half is `tests/conformance/bash/test_noexec_state_blindness_conformance.py` (claim-proving CONTROL ROW, green-on-base by design). |
| `tests/system/test_analysis_state_aware.py::TestExpandAliasesIsOrderedNotMonotone::test_unreached_conditional_disable_is_the_declared_cost` (+ the four R13-B shapes) | 2.6 declared COST pin, divergent direction: an unreached conditional `shopt -u expand_aliases` narrows analysis (exec 0 / validate 2). Closing it = successor's alias-overlay work; flip only with a re-ruling. |
| `tests/system/test_analysis_state_aware.py::TestAliasAxisNormalizationAsymmetry` (5 spelling classes) + `TestAliasIsolationAsymmetry` | 2.6 declared limitations, divergent direction (base-faithful): prefixed/quoted alias heads invisible to analysis; alias-table absorption isolation-blind. Successor row (b) owns them. |

## Watch note

Slot 4B.3 (history) closes ledger B#32: the nightly's 6 red
`test_history_outcomes_i4.py` rows on Linux may interact — 1.4 classifies them
first; 4B.3 consumes that classification.

### 3.4-declared divergence pins (v0.766.0; none named `test_divergence_*` are must-flip — recorded per R13-E(4))

| pin | divergence |
|---|---|
| `test_divergence_readonly_prefix_rc_under_a_value_side_flip` (+ diagnostic leg) | posix special-builtin readonly abort: bash rc 127 / psh rc 1 (pre-existing shape, newly reachable) |
| `test_divergence_nameref_spelled_posix_store_dispatch` (+ bounding control) | `A=$((npc=1))` via nameref: bash FN+posix-off / psh BP+posix-on (hook over-coupling, D-3.4-s2) |
| `test_divergence_masked_special_own_read_layer_route` family | `RANDOM=1 eval 'echo $RANDOM'`: bash literal / psh generates (carry-#7 residue, D-3.4-s4) |
| readonly-refusal WORDING leg (both routes) | psh names the TARGET, bash names the NAMEREF (D-3.4-s1) |
| persistence cell `A=1 B=$((A=9)) cmd; echo $A` | bash 9 / psh UNSET (D-3.4-s6) |
| `${!PREFIX*}` staging-window enumeration | sees staged bindings (D-3.4-s7) |
| function-target nameref-to-element body read | bash NEW / psh stale (D-3.4-s8) |
| X1 / R4 confounders | posix fn-name validation; posix special-builtin redirection fatality |

All both-sides pinned: each flips VISIBLY when a successor takes its row.

### 3.5-declared divergence pins (v0.767.0; none named `test_divergence_*` — recorded per R13-E(4))

| pin | file | divergence | owner |
|---|---|---|---|
| `TestDeclaredDivergences::test_ps4_bad_subscript_aborts_in_psh_but_not_bash` | tests/conformance/bash/test_typed_expansion_errors_conformance.py | PS4 containing a bad-subscript expansion: bash falls back to raw PS4 and CONTINUES rc 0; psh aborts rc 1 (`TopLevelAbort` is a BaseException and escapes the narrowed `except PshError` net — pre-existing, byte-identical base/tip) | D-3.5-s4 |
| `TestDeclaredDivergences::test_invalid_regex_diagnostic_is_psh_only` | tests/conformance/bash/test_typed_expansion_errors_conformance.py | `[[ x =~ '(' ]]`: both shells rc 2, but psh prints `psh: [[: invalid regex: …` where bash is SILENT (wording/stream class) | D-3.5-s5 |

Both pinned BOTH-SIDES in the divergent direction; each flips ONLY with a ruling.

### 4A.1-declared divergence pin (v0.768.0)

| pin | file | divergence | owner |
|---|---|---|---|
| `test_sub_16_rlimit_envelope_is_recorded_not_claimed` | tests/integration/redirection/test_failed_exec_lease_4a1.py | Permanent redirect under RLIMIT_NOFILE ≤ 12: bash succeeds; psh DECLINES CLEANLY (diagnostic, rc≠0, nothing half-acquired — the alternative was the pre-4A.1 silent `None` baseline that closed the HOST's fds 0/1/2 at close()). Parity measured and pinned at every threshold ≥ 13 (adaptive parking base) | D-4A.1-s4 |

Pinned in the divergent direction; flips ONLY with a ruling (a sub-13
parking strategy would need its own design round).

### 4B.3-declared divergence pins (v0.772.0; registered per R13-E(4) — none named `test_divergence_*`)

| Pin | Owner |
|---|---|
| 4B.3 deviation family (bash's positional-tail `-a` loses/leaks; psh keeps/doesn't): `test_history_state_machine_conformance.py::TestDeclaredDeviations` (b1(i) no-dup-on-read, b2 `-w`-then-`-n`, b3 `-d`-while-pending, b5 default-file `-w`→`-a` + its no-`-w` control) and `::TestNamedReadCursorDeviation` (b4 FORWARD `test_named_read_then_default_read_new`; b4 MIRROR `test_named_read_new_resumes_at_the_global_offset_in_bash` + `test_an_unadvanced_counter_reads_the_whole_named_file_in_both` control). Every cell asserts BOTH shells with named failure messages; each flips ONLY with a ruling | 4B.3; flip = ruling |

The bash-side cells are characterization of bash 5.2.26's measured tail-count
mechanism — a "failure" there means the ORACLE's behavior moved (bash version),
not psh; read per the nightly rules before touching.
