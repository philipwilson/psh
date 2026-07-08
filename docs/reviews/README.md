# Reviews & Design Notes — Index

This directory is the **development-history record**: point-in-time code
audits, architecture reviews, and design plans. It is **not** a tutorial.

> **Learning PSH?** Start with [`docs/learning_path.md`](../learning_path.md),
> not here. Almost everything in this folder is a snapshot of how the codebase
> looked on a given date — the findings have since been acted on across many
> releases (see [`CHANGELOG.md`](../../CHANGELOG.md)).

Status legend: **Live** = still an authoritative reference · **Completed** =
a plan/roadmap whose work has shipped · **Historical** = a point-in-time audit,
superseded by later work and kept for the record.

> This index is kept complete by a meta-test
> (`tests/unit/tooling/test_reviews_index.py`): every `*.md` in this directory
> must be linked below, so a newly added review can't go unlisted. When you add
> a review file, add a one-line row here in the right section.

## Live references

The few documents worth reading as current truth:

| Document | Why it's live |
|----------|---------------|
| [ground_up_reappraisal_18_2026-07-04](ground_up_reappraisal_18_2026-07-04.md) | The **latest** whole-repo ground-up audit (@ v0.617.0) — the newest of the reappraisal series and the current canonical whole-repo appraisal. |
| [core_state_subsystem_appraisal_2026-07-06](core_state_subsystem_appraisal_2026-07-06.md) | Canonical core-state appraisal; Phases 1–3 shipped (v0.656–0.657, v0.665.0), Phase 4+ is the open roadmap. |
| [interactive_subsystem_appraisal_2026-07-07](interactive_subsystem_appraisal_2026-07-07.md) | Canonical interactive-subsystem appraisal (B+, PTY-verified); drives the open notify/history-UX campaign. |
| [io_redirect_subsystem_appraisal_2026-07-07](io_redirect_subsystem_appraisal_2026-07-07.md) | Canonical I/O-redirect appraisal (A−); supersedes the 2026-06-13 review; drives the open exec-close-reopen campaign. |
| [scripting_subsystem_appraisal_2026-07-07](scripting_subsystem_appraisal_2026-07-07.md) | Canonical scripting/non-interactive appraisal (A−); drives the open stdin-as-script campaign. |
| [test_performance_appraisal_2026-07-07](test_performance_appraisal_2026-07-07.md) | Measured suite-runtime breakdown (gate ≈5 min single-tenant; serial-phase disproportion); drives the open runtime-optimization campaign. |
| [posix_special_builtin_exit_matrix_2026-07-07](posix_special_builtin_exit_matrix_2026-07-07.md) | Reference matrix of POSIX-mode special-builtin exit-on-error behavior pinned to bash 5.2.26. |
| [parallel_test_safety_2026-06-06](parallel_test_safety_2026-06-06.md) | The authoritative rationale for the `serial` marker and xdist test safety — cited by the root `CLAUDE.md`. |
| [code_architecture_teaching_quality_reassessment_2026-06-20](code_architecture_teaching_quality_reassessment_2026-06-20.md) | Re-grades the 2026-06-18 findings after the v0.504–510 work and lists remaining prioritized next steps. |
| [code_architecture_teaching_quality_review_2026-06-18](code_architecture_teaching_quality_review_2026-06-18.md) | The whole-repo review whose Findings #1–#6 drove releases v0.504–v0.510. |

## Completed plans & roadmaps

Design notes whose work has shipped; kept to record the decision.

| Document | Outcome |
|----------|---------|
| [rd_parser_root_shape_compatibility_analysis_2026-07-04](rd_parser_root_shape_compatibility_analysis_2026-07-04.md) | Canonical `Program` AST root; shipped v0.647.0. |
| [tests_documentation_appraisal_2026-07-06](tests_documentation_appraisal_2026-07-06.md) | Tests/docs truth-alignment; shipped v0.664.0 (claims requalified, no-assert probes converted, real `--quick` tier, generated stats); runtime items continue via the 2026-07-07 performance appraisal. |
| [builtins_subsystem_appraisal_2026-07-06](builtins_subsystem_appraisal_2026-07-06.md) | Findings shipped across v0.657–v0.663 (VariableStore, resolver, input service, contracts cluster); POSIX exit-matrix follow-up tracked with its own live matrix doc. |
| [execution_subsystem_improvement_plan_2026-07-05](execution_subsystem_improvement_plan_2026-07-05.md) | P1a shipped v0.652; findings 11–14 shipped v0.661 (JobManager transactions incl. F13 rollback). |
| [expansion_subsystem_improvement_plan_2026-07-05](expansion_subsystem_improvement_plan_2026-07-05.md) | P1a v0.651, shared fd-remap v0.653, pattern engine v0.658, nested-Program v0.659; typed-fragments remainder rescoped by the double-parse discovery. |
| [parser_subsystem_appraisal_2026-07-05](parser_subsystem_appraisal_2026-07-05.md) | Campaign 1 hardening v0.650, honest-config deletion v0.654, nested-Program flagship v0.659. |
| [lexer_subsystem_appraisal_2026-07-05](lexer_subsystem_appraisal_2026-07-05.md) | Phase 1–2 shipped v0.648–0.649 (linear heredocs, keyword-position fixes); Phases 3–6 remain an open roadmap. |
| [lexer_implementation_improvement_plan_2026-07-05](lexer_implementation_improvement_plan_2026-07-05.md) | Companion implementation plan to the lexer appraisal; Phases 1–2 shipped v0.648–0.649. |
| [parser_combinator_subsystem_appraisal_2026-07-06](parser_combinator_subsystem_appraisal_2026-07-06.md) | Combinator parity work landed via T2-H (v0.646) + lockstep in the nested-Program flagship; remaining gaps ledgered. |
| [options_typing_refactor_plan_2026-06-19](options_typing_refactor_plan_2026-06-19.md) | Shipped v0.508.0 (option registry + `ShellOptions`). |
| [parser_top_level_control_structure_refactor_plan_2026-06-19](parser_top_level_control_structure_refactor_plan_2026-06-19.md) | Shipped v0.507.0 (one top-level grammar path). |
| [tier_r8_architecture_roadmap_2026-06-14](tier_r8_architecture_roadmap_2026-06-14.md) | Tier R8 architecture work; shipped. |
| [r9c3_combinator_grammar_brief](r9c3_combinator_grammar_brief.md) | Combinator grammar rewrite; shipped v0.433–434. |
| [reappraisal_4_tier_b](reappraisal_4_tier_b.md) | Reappraisal #4 Tier B residue; shipped. |
| [reappraisal_4_tier_c_lexer_parser](reappraisal_4_tier_c_lexer_parser.md) | Reappraisal #4 Tier C (lexer/parser/AST elegance); shipped. |

## Historical — ground-up reappraisal & appraisal series

Each is a full-repo audit at a point in time; each is superseded by the next.
The latest is [#18](ground_up_reappraisal_18_2026-07-04.md), also listed under
Live above.

| Document | Snapshot |
|----------|----------|
| [ground_up_reappraisal_2026-06-10](ground_up_reappraisal_2026-06-10.md) | #1 @ v0.274 |
| [ground_up_reappraisal_2026-06-11](ground_up_reappraisal_2026-06-11.md) | #2 @ v0.287 |
| [ground_up_reappraisal_2026-06-12](ground_up_reappraisal_2026-06-12.md) | #3 @ v0.311 |
| [reappraisal_4_tier_b](reappraisal_4_tier_b.md) / [reappraisal_4_tier_c_lexer_parser](reappraisal_4_tier_c_lexer_parser.md) | #4 (Tiers B & C; see Completed) |
| [ground_up_reappraisal_5_2026-06-13](ground_up_reappraisal_5_2026-06-13.md) | #5 (textbook-grade scorecard) |
| [ground_up_reappraisal_6_2026-06-14](ground_up_reappraisal_6_2026-06-14.md) | #6 |
| [ground_up_reappraisal_7_2026-06-14](ground_up_reappraisal_7_2026-06-14.md) | #7 |
| [ground_up_reappraisal_2026-06-15](ground_up_reappraisal_2026-06-15.md) | #8 — textbook-grade audit (2026-06-15) |
| [ground_up_reappraisal_9_2026-06-15](ground_up_reappraisal_9_2026-06-15.md) | #9 @ v0.437 |
| [ground_up_reappraisal_10_2026-06-15](ground_up_reappraisal_10_2026-06-15.md) | #10 @ v0.447 |
| [ground_up_reappraisal_11_2026-06-16](ground_up_reappraisal_11_2026-06-16.md) | #11 @ v0.464 |
| [ground_up_reappraisal_12_2026-06-16](ground_up_reappraisal_12_2026-06-16.md) | #12 @ v0.472 |
| [ground_up_reappraisal_13_2026-06-16](ground_up_reappraisal_13_2026-06-16.md) | #13 @ v0.485 |
| [ground_up_appraisal_2026-06-21](ground_up_appraisal_2026-06-21.md) | Appraisal @ v0.514 (2026-06-21) |
| [ground_up_reappraisal_14_2026-06-22](ground_up_reappraisal_14_2026-06-22.md) | #14 @ v0.539 |
| [ground_up_reappraisal_15_2026-07-01](ground_up_reappraisal_15_2026-07-01.md) | #15 @ v0.559 |
| [ground_up_reappraisal_16_2026-07-03](ground_up_reappraisal_16_2026-07-03.md) | #16 @ v0.580 |
| [ground_up_reappraisal_17_2026-07-03](ground_up_reappraisal_17_2026-07-03.md) | #17 @ v0.600 |
| [codebase_appraisal_2026-07-04](codebase_appraisal_2026-07-04.md) | Deep codebase appraisal @ v0.617 (2026-07-04) |
| [ground_up_reappraisal_18_2026-07-04](ground_up_reappraisal_18_2026-07-04.md) | #18 @ v0.617 (**latest** — see Live) |

## Historical — architecture & subsystem reviews

| Document | Topic |
|----------|-------|
| [fresh_architecture_review_2026-06-14](fresh_architecture_review_2026-06-14.md) | Whole-architecture review |
| [architecture_feature_review_2026-06-09](architecture_feature_review_2026-06-09.md) | Architecture & feature review @ v0.237 |
| [executor_command_dispatch_architecture_review_2026-06-13](executor_command_dispatch_architecture_review_2026-06-13.md) | Executor / command dispatch |
| [expansion_architecture_review_2026-06-13](expansion_architecture_review_2026-06-13.md) | Expansion subsystem |
| [redirection_io_architecture_review_2026-06-13](redirection_io_architecture_review_2026-06-13.md) | Redirection / I/O (~90% resolved; superseded by the 2026-07-07 io_redirect appraisal) |
| [interactive_subsystem_appraisal_2026-07-06](interactive_subsystem_appraisal_2026-07-06.md) | Interactive subsystem (superseded next day by the PTY-verified 2026-07-07 appraisal) |
| [lexer_parser_ast_architecture_review_2026-06-13](lexer_parser_ast_architecture_review_2026-06-13.md) | Lexer/parser/AST (superseded same day by the reassessment) |
| [lexer_parser_ast_architecture_reassessment_2026-06-13](lexer_parser_ast_architecture_reassessment_2026-06-13.md) | Lexer/parser/AST reassessment |
| [parser_combinator_architecture_review_2026-06-15](parser_combinator_architecture_review_2026-06-15.md) | Educational combinator parser |
| [combinator_diagnostic_characterization_2026-06-14](combinator_diagnostic_characterization_2026-06-14.md) | Combinator diagnostics |

## Historical — code-quality assessments

A chain where each reassessment supersedes the previous.

| Document | Topic |
|----------|-------|
| [code_quality_assessment_2026-06-13](code_quality_assessment_2026-06-13.md) | Code-quality assessment |
| [code_quality_subsystem_reassessment_2026-06-12](code_quality_subsystem_reassessment_2026-06-12.md) | Subsystem reassessment (2026-06-12) |
| [code_quality_subsystem_reassessment_2026-06-11](code_quality_subsystem_reassessment_2026-06-11.md) | Subsystem reassessment (2026-06-11) |
| [code_quality_subsystem_assessment_2026-06-11](code_quality_subsystem_assessment_2026-06-11.md) | Subsystem assessment (original) |

## Historical — early studies (Feb–Jun 2026)

| Document | Topic |
|----------|-------|
| [codebase_study_2026-06-05](codebase_study_2026-06-05.md) | Codebase study overview |
| [codebase_study_2026-06-05_phase1_correctness](codebase_study_2026-06-05_phase1_correctness.md) | Phase 1: correctness & conformance |
| [codebase_study_2026-06-05_phase2_architecture](codebase_study_2026-06-05_phase2_architecture.md) | Phase 2: architecture & code quality |
| [codebase_study_2026-06-05_phase3_coverage](codebase_study_2026-06-05_phase3_coverage.md) | Phase 3: test coverage |
| [lexer_token_set_appraisal_2026-02-19](lexer_token_set_appraisal_2026-02-19.md) | Early lexer token-set appraisal |
| [codebase_recommendations_2026-02-17](codebase_recommendations_2026-02-17.md) | Early improvement recommendations |
| [arithmetic_review](arithmetic_review.md) | Early review of the original arithmetic module (since decomposed into `psh/expansion/arithmetic/`) |
