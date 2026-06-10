# Targeted Coverage Sprint Plan

PSH has grown into a feature-rich shell with a large test suite, but current coverage is uneven in several runtime-critical areas (signals, process launch, job control, redirection, subshells, line editing, and completion). The main problem is not total test count; it is confidence in high-risk execution paths and the quality of signals from default test gates. The goal of this sprint is to close high-impact blind spots, improve assertion quality, and establish module-level coverage gates that reflect shell behavior risk rather than raw aggregate percentages.

## Scope And Goals

- Increase confidence in process/signal/job-control behavior under real shell conditions.
- Raise coverage in low-coverage, high-risk modules using targeted tests.
- Ensure interactive/subprocess execution contributes reliably to coverage metrics.
- Improve test signal quality by replacing success-only checks with semantic assertions.
- Add module-level thresholds to prevent regressions after the sprint.

## Baseline Risk Modules

- `psh/interactive/signal_manager.py` (~24%)
- `psh/executor/process_launcher.py` (~32%)
- `psh/tab_completion.py` (~31%)
- `psh/builtins/job_control.py` (~42%)
- `psh/io_redirect/manager.py` (~46%)
- `psh/executor/subshell.py` (~47%)
- `psh/line_editor.py` (~49%)
- `psh/history_expansion.py` (~57%)
- `psh/interactive/completion_manager.py` (~35%)

## Key Constraints To Address First

- Interactive tests are skipped by default in standard collection unless explicitly enabled.
- Signal setup is intentionally suppressed under pytest unless test env is configured to allow it.
- A significant portion of integration/PTY execution currently has weak coverage attribution in routine reporting.
- Some interactive tests assert only process success rather than behavior correctness.
- `psh/tab_completion.py` contains a legacy `LineEditor` implementation that may inflate coverage denominator without contributing runtime value.

## Sprint Principles

- Prioritize behavioral risk over raw line count.
- Favor deterministic unit/integration tests for branch completeness; keep PTY tests as focused smoke/contract tests.
- Define explicit acceptance criteria per phase.
- Avoid adding broad/flaky tests that slow feedback loops without increasing signal quality.

## Phase 0: Coverage Measurement Hardening (2-3 days)

### Recommendations

- Configure coverage collection so subprocess/forked execution contributes to module attribution.
- Introduce a dedicated signal-test mode that enables real signal setup only for signal-focused tests.
- Establish a canonical command set for sprint coverage reporting, including branch coverage output.
- Decide and document policy for legacy/duplicate editor logic in `psh/tab_completion.py`:
- Option A: remove/deprecate if dead path.
- Option B: explicitly exclude with rationale before setting strict thresholds.

### Acceptance Criteria

- Coverage runs consistently include interactive/subprocess test execution where intended.
- Signal-focused tests can run with real handler setup in a controlled mode.
- A reproducible module coverage report exists for sprint tracking.

## Phase 1: Process, Signal, And Job-Control Core (3-4 days)

### 1) `psh/interactive/signal_manager.py`

- Add focused tests for script vs interactive handler registration.
- Cover trap-check dispatch behavior for trapped, ignored, and default cases.
- Cover SIGCHLD self-pipe notification flow:
- Reentrancy guard behavior.
- waitpid draining loop semantics.
- stopped-foreground job terminal handoff path.
- Cover SIGWINCH notify/drain behavior.
- Cover `ensure_foreground()` and platform-error handling branches.
- Cover `reset_child_signals()` signal iteration and exception-safe behavior.

### 2) `psh/executor/process_launcher.py`

- Add deterministic tests with patched `os` APIs to validate:
- Role-specific child setup (`SINGLE`, `PIPELINE_LEADER`, `PIPELINE_MEMBER`).
- Sync-pipe handling for pipeline member synchronization.
- Child exception mapping (`SystemExit`, `KeyboardInterrupt`, generic exception).
- Non-int return coercion behavior.
- Parent-side pgid race/error handling.
- `launch_job()` job creation and terminal transfer behavior.

### 3) `psh/builtins/job_control.py`

- Add complete branch matrix for `jobs`, `fg`, `bg`, `wait`:
- Empty/no-current-job paths.
- Invalid job spec paths.
- stopped/running/done states.
- pid-not-child and parse errors.
- wait-for-all cleanup and exit status extraction.
- Add targeted tests for terminal transfer failure handling and expected error messaging.

### Acceptance Criteria

- Critical control-flow branches in these modules are covered and behavior-asserted.
- No reliance on PTY-only tests for core branch coverage in these modules.

## Phase 2: Redirection And Subshell Execution Paths (3-4 days)

### 1) `psh/io_redirect/manager.py`

- Add unit matrix for redirection operator handling:
- `<`, `>`, `>>`, `<<`, `<<-`, `<<<`, `>&`, `<&`, `>&-`, `<&-`.
- Cover noclobber branch behavior.
- Cover bad-file-descriptor validation and error paths.
- Cover process substitution targets in redirection setup.
- Cover restore path semantics for builtins and FD backups.
- Cover temp file cleanup and heredoc tab-strip behavior.

### 2) `psh/executor/subshell.py`

- Cover foreground subshell interactive/non-interactive terminal-control branches.
- Cover background subshell registration and reporting behavior.
- Cover brace group foreground/background path differences.
- Cover redirection apply/restore behavior in subshell/brace contexts.
- Cover job lifecycle cleanup paths after completion.

### Acceptance Criteria

- Redirection and subshell branches are asserted directly with deterministic tests.
- High-risk FD and job-lifecycle behaviors are covered without brittle timing dependencies.

## Phase 3: Interactive Editing, Completion, And History Expansion (3-4 days)

### 1) `psh/line_editor.py`

- Strengthen existing tests beyond “does not crash”:
- Search state machine transitions.
- undo/redo stack behavior.
- multiline history conversion behavior.
- completion insertion/update behavior.
- redraw/resize path behavior.
- vi/emacs mode action dispatch behavior.

### 2) `psh/tab_completion.py` and `psh/interactive/completion_manager.py`

- Cover word-boundary parsing with quotes/escapes.
- Cover path completion behavior including hidden files, directories, and errors.
- Cover escaping rules for completion insertion.
- Cover readline completion state behavior (`state == 0` initialization and match iteration).
- Replace success-only integration assertions with concrete completion output/state assertions.

### 3) `psh/history_expansion.py`

- Add direct matrix for:
- `!!`, `!n`, `!-n`, `!prefix`, `!?substr?`.
- quote suppression rules.
- bracket expression exclusion (`[!... ]`) cases.
- `${...}` and `$((...))` exclusion cases.
- error reporting toggles (`report_errors`) and print controls (`print_expansion`).
- `histexpand` option on/off behavior.

### Acceptance Criteria

- Completion/history tests verify semantic behavior, not only successful process exit.
- Module branch coverage and assertion quality are materially improved.

## Phase 4: Gating And Regression Prevention (1-2 days)

### Recommendations

- Add module-level coverage thresholds for sprint-target modules.
- Keep PTY coverage as a small smoke/contract subset; avoid making PTY tests the sole signal for core semantics.
- Add policy checks for stale `xfail` markers (surface XPASS clearly in CI reports).
- Update testing docs so default gate vs extended gate behavior is explicit and reproducible.

### Acceptance Criteria

- CI enforces module-level thresholds for targeted areas.
- Extended gate captures interactive/subprocess-sensitive behavior.
- Test failures provide clear behavioral signal (not mostly noise/skips).

## Suggested Coverage Targets After Sprint

- `psh/interactive/signal_manager.py` >= 70%
- `psh/executor/process_launcher.py` >= 65%
- `psh/builtins/job_control.py` >= 75%
- `psh/io_redirect/manager.py` >= 70%
- `psh/executor/subshell.py` >= 70%
- `psh/line_editor.py` >= 75%
- `psh/history_expansion.py` >= 85%
- `psh/tab_completion.py` >= 65% (after legacy path policy decision)
- `psh/interactive/completion_manager.py` >= 75%

## Execution Order

1. Complete Phase 0 instrumentation and denominator policy decisions.
2. Execute Phase 1 (signal/process/job-control core).
3. Execute Phase 2 (redirection and subshell correctness paths).
4. Execute Phase 3 (editor/completion/history semantics).
5. Land Phase 4 gates and documentation updates.

## Deliverables Checklist

- Sprint tracking report with before/after module coverage.
- Test inventory by target module with branch map closure status.
- Updated CI/test gate documentation.
- Module threshold configuration and enforcement.
- `xfail` cleanup report (XPASS converted or justified).
