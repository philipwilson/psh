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
      tab-completion (command/variable name)†, and the two git-range
      self-check rows skip loudly (expected on CI checkouts).

      † **CORRECTION (2026-07-25, slot 1.4):** the PTY tab-completion rows
      were NOT failures in this census — run 30065826566's own log records
      both as XFAIL (w0-clean.txt:3133-3134), under `strict=True` markers
      dating to `8dde4fdb` (v0.313.0, 2026-06-12, ~6 weeks before Wave 0).
      They are active pins on the documented path-only CompletionEngine
      limitation, unchanged from Wave 0 through the 1.4 green runs; no
      campaign slot touched them. Provenance in `1.4-rescue/slot-ledger.md`
      Part 10. (Lesson: the census grep pattern matched the module path,
      not the test names — the same instrument error 1.4 later made and
      corrected.)
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

## RECOVERY (2026-07-25, slot 1.4, shipped v0.755.0)

- **GREEN.** Three consecutive green `workflow_dispatch` runs on
  `fix/remediation-1-4`: 30171120171 (`a768f497`), 30172534890 (`d3783922`),
  30175067149 (`cdff0704`, the merged tip). Both jobs SUCCESS each time:
  conformance 2,671 passed; parallel+golden 21,873 passed / 0 failed; real
  ENOSPC 0; runner free-space floor 91.26 GB (was 0 pre-fix).
- **The red record ends at 23+ nights** (2026-07-02 → 2026-07-24 census;
  first green dispatch 2026-07-25). Census: 30 parallel rows + 54
  conformance rows classified (i)/(ii)/(iii)/(iv)/(v) — full per-row table
  in `1.4-rescue/slot-ledger.md` Part 10.
- **Three real defects found and fixed** (the rest was platform honesty +
  env): psh `bg` stale-state SIGCONT gap; psh locale reactive over-warning
  (LC_ALL reset path); harness cap/timeout kill missing escaped process
  groups — the runaway `yes` on unlinked capture files (~480 MB/s) that
  caused the `[Errno 28]` deaths HERE and the "external consumer" disk
  collapses on the macOS gate host. One bug, both platforms.
- **OWED (Wave 1 exit checklist): the first SCHEDULED run after the merge
  must be verified green** — dispatch runs do not prove the schedule.
  Check: `gh run list --workflow=nightly.yml --limit 3`.
- **Instrumentation expiry**: the disk sampler / fd snapshots /
  PSH_DISK_WATCH / core_pattern normalization remain as relapse watch;
  removal criterion recorded in the workflow comment (several consecutive
  green scheduled nightlies, zero ENOSPC, no trips).

## FIRST POST-MERGE SCHEDULED NIGHTLY (2026-07-26, run 30187441750)

The first SCHEDULED nightly after v0.755.0 merged (the Wave 1 exit check) ran
at `a765f1a0` and reported **1 failed / 21,872 passed** — conformance job GREEN,
parallel job failed on a SINGLE golden comparison. CLASSIFIED, not a regression:

- **Failure:** `--compare-bash` case `r18t1_bgtrap_wait_bare_then_explicit_127`
  (`( exit 5 ) & p=$!; wait; wait $p; echo rc=$?`), stdout divergence
  psh=`rc=127` vs live-bash=`rc=5`. psh gave the CORRECT declared value; the
  LIVE BASH ORACLE raced. This command is a double-reap race on which bash
  (no task-#37 reclaim fix) is nondeterministic under runner load; psh is
  deterministic (rc=127). A reap race compared against a racy oracle is not a
  valid gate. **Disposition: marked `psh_only: true`** (comparison leg skipped;
  psh behavior stays pinned by the psh-golden assertion AND the deterministic
  seam in `tests/integration/job_control/test_wait_reap_echild_reclaim.py`).
  Fixed on `fix/nightly-golden-reap-race`.
- **Transient `[Errno 28]`:** the disk instrumentation recorded one
  `[Errno 28] on mkdir under /tmp while df reported 88G and 18.5M` that
  RECOVERED — the suite ran to completion. This is the v0.755.0 instrumentation
  working (a transient event surfaced and self-cleared), NOT the escaped-writer
  disk collapse returning (that was fixed and the release-gate low-water is
  131 GiB). No ENOSPC-driven test death.
- **Watch candidate (not quarantined — no recorded instance yet):**
  `r18t1_bgtrap_wait_bare_clears_explicit_retention` has the same double-`wait`
  reap structure and could race the live bash oracle on a future nightly; if it
  does, mark it `psh_only` with its own recorded run link then.

**Wave 1 exit check: SATISFIED by classification.** The nightly's only red row is
a racy-oracle artifact, dispositioned above with the run link; psh behavior is
correct and deterministically pinned. Nightly instrumentation (sampler + fd
snapshots + PSH_DISK_WATCH) stays per its recorded removal criterion.

## Scheduled-nightly window 2026-07-26 → 2026-07-30 (classified at resume, fixed v0.759.0)

Five scheduled runs since the pause: 07-26 FAILED (30187441750), 07-27 FAILED
(30236690742), 07-28 GREEN (30327629745), 07-29 GREEN (30421244108), 07-30
FAILED (30512764726). All three failures classified; none is a psh behavior
regression:

- **07-26 (`a765f1a0`):** golden `r18t1_bgtrap_wait_bare_then_explicit_127`
  stdout divergence — this run executed BEFORE PR #504's `psh_only`
  quarantine merged; the case is quarantined at every later tip. Pre-existing
  classification stands unchanged; no action.
- **07-27 + 07-30 (both at `1b271d77` = v0.758.0):**
  `test_process_sub_closed_fds.py::test_write_side_procsub_closed_fds_matches_bash`
  — 07-27 the `exec 0<&-` param, 07-30 the bare param — each with
  psh=('', '', 'data\n') vs bash=('', '', ''). Same commit was GREEN 07-28
  and 07-29: an intermittent HARNESS race, not behavior. Mechanism (probed
  2026-07-30, forced-slow child): NEITHER shell waits for a write-side
  `>(...)` child at command end — bash exits in 0.00s with the fd 9 file
  still empty (the child settles it later), and `run_shell_case`'s post-exit
  defensive `_killpg_sigkill` sweep then races the child. Bash's `cat` loses
  under Linux-runner load → empty file; psh's child won every observed race
  only because ~170 ms of interpreter teardown shields it — the psh-side
  delivery assertions were latently flaky too. **Fix (v0.759.0, test-only):**
  `_WRITE_BODY` carries a shell-neutral completion barrier (substitution
  touches a flag file after writing; parent spin-waits, bounded at ~4 s so a
  real delivery regression still fails as a comparison, not a timeout).
  Verified: forced-1s-slow child delivers by exit on bash 5.2.26 + psh RD +
  psh combinator (1.02/1.15/1.16 s); file soaked 20/20 green.
- **Probe by-catch (recorded in LEDGER Part D, successor row):** bash 5.2's
  bare `wait` DOES reach the procsub child (1.02 s, delivered); psh's bare
  `wait` does NOT (0.12 s, empty). Real divergence, deliberately NOT
  exercised by the fixed test (the barrier avoids `wait` precisely so the
  test doesn't depend on divergent semantics).

## v0.760.0 note — new default-run PTY differential (slot 2.4)

`tests/system/interactive/test_substitution_abort_interactive_pty.py` now runs
in the DEFAULT suite (conftest allowlist; ~8 s, serial phase) — an opt-in pin
for a PTY-only fact is an accidentally-green pin. Two things a nightly reader
needs: it resolves the bash oracle AT IMPORT and fails LOUDLY (deliberate —
a missing oracle must not silently skip a differential), and its BASH-side
values ('1', '2') were measured against 5.2.26 on macOS while the Linux
nightly runs a different bash build (plan A12) — a bash-version-dependent PTY
value there fails the default suite and should be read as an ORACLE-VERSION
question first, not a psh regression.

## v0.761.0 note — PTY suite growth (slot 2.5)

Slot 2.5 adds a second default-run PTY module
(`tests/system/interactive/test_heredoc_detection_interactive_pty.py`, ~70
tests) beside 2.4's substitution-abort module, plus the alias-route and
named-fd differential files (subprocess, parallel-safe). The PTY modules run
in the SERIAL phase; local serial-phase cost grew ~4x over the 2.4 precedent
(accounted per round-5 N3 / R11-D). Same reading rule as v0.760.0: these
modules resolve the bash oracle loudly at import and their bash-side
expectations were measured against 5.2.26 — a Linux nightly failure in them is
an ORACLE-VERSION question first. New wrinkle from 2.5: psh answers "need
more" with CONTEXTUAL prompts (`then> `, `for then> `) — the 2.5 module's
detector understands them; 2.4's module does not need to (no case opens a
construct) but shares the limitation LATENTLY (LEDGER 2.5 successor row h).
