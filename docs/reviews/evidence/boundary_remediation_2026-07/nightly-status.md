# Linux nightly status at campaign launch (Wave 0 baseline fact)

- **Recorded:** 2026-07-24, by the campaign integrator at Wave 0 launch.
- **Finding:** `nightly.yml` (the Linux full-suite + live-bash + coverage
  backstop) has FAILED every night since **2026-07-02** — 23 consecutive red
  runs at launch. Last green: 2026-07-01 (main @ `b314064c`). First red:
  2026-07-02 (main @ `a0e99959`). Nobody checked run results in that window —
  the local gate is THE release gate and the backstop went dark unnoticed,
  through the entire boundary campaign (v0.725.0–v0.750.0), reappraisal #22,
  and the #22 verification. (#22 explicitly assumed "the nightly … stays on as
  a safety net"; the safety net was down. The repo's own CI-green lesson —
  verify with run RESULTS, not config — was violated by everyone, this
  integrator included.)
- **Latest run census (2026-07-24, run 30065826566, head `0215279c` = launch base):**
  - Job "Full Parallel Suite + Bash Golden Comparison": **24 failed / 21,746
    passed** (phase 1 parallel: 16 failed / 19,380 passed; phase 1b serial:
    8 failed / 885 passed; golden phase: 1,481 passed clean). Failing families
    (names from FAILURES headers; full log = run artifact):
    - **J1/signal/process family** (carry #17's watch targets):
      TestAbnormalTerminationDiagnostic, TestExitTrapOnFatalSignal
      (stdin-mode fires exit trap), TestInheritedTrapNotFired
      (subshell+brace), TestPipelineLastMemberSignalDeath,
      TestProcessSubReaping (zombie accumulation), plus child-fd inheritance
      rows (exec image script-fd, self-dup-closed, D2 closed-stdout upstream,
      named-fd child-inherits, child-sees-closed-fd).
    - **History-outcome family** (6 params of
      test_history_outcome_matches_bash: bang_string, identical_expand,
      normal_expand, print_only_recorded_not_executed, set_minus_H_reenables,
      word_star).
    - **Misc:** TestInheritedCtypeProvenance.test_terminal_app_utf8_row
      (locale), test_protocol_member_sets_are_frozen (Q1),
      TestCompositeQuoting.test_tilde_expands_in_key,
      TestCwdReadConvergence.test_pushd_swap_after_plain_cd_uses_real_cwd,
      test_golden[redirect_eval_external_stderr_suppressed], PTY
      tab-completion (command/variable name), and the two git-range
      self-check rows skip loudly (expected on CI checkouts).
  - Job "Full Conformance Suite": **54 failed / 2,600 passed / 1 skipped /
    8 xfailed**. Visible failure census (log tail; complete list requires the
    run artifact): `test_syntax_template_timing_conformance.py` — 15+
    `test_accept_matches_bash[*-file]` rows, all arith-flavored, `-file`
    channel; `test_history_outcomes_i4.py` (6); nested-substitution timing
    (2); subscript keying (1); locale (1).
- **Environment deltas vs the local gate host:** Linux (ubuntu runner),
  Python **3.12.13** (local: 3.14), PATH bash **5.2.21** (local: 5.2.26
  homebrew), no mypy module installed (mypy scope test skips).
- **Layering:** the red set ACCRETED — several failing tests postdate
  2026-07-02 (history-outcome = I4/v0.745 era; protocol-freeze = Q1/v0.747+),
  so they have NEVER passed on Linux; the original 2026-07-02 breakage
  (window `b314064c..a0e99959`) is a distinct, older layer.
- **Disposition (ledger ruling R3):** owned by NEW Wave 1 slot **1.4 — Linux
  nightly recovery**. Exit: nightly green, or every red row classified
  (Linux-genuine defect → fixed or wave-assigned; oracle-version sensitivity
  → handled by the Wave 1 oracle policy, e.g. version-pinned expectations;
  infra/env → fixed) with run links recorded here. Predecessor carry #17
  (J1 watch, a MUST) is discharged inside 1.4, not before.
- **Standing rule going forward:** the integrator checks the latest nightly
  result at every wave close (added to the wave-close checklist in RESUME).
