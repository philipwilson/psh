# Executor Signal & Process-Group Improvements

This note captures follow-up recommendations after reviewing the current
executor architecture (signals, job control, process groups).

## 1. Centralize Child Signal Reset Policy

- **Current state:** `ProcessLauncher` locally ignores `SIGTTOU` before it calls
  `SignalManager.reset_child_signals()`, and later code (e.g., the final stage
  of a foreground pipeline) manually restores `SIGTTOU`/`SIGTTIN`.
- **Concern:** The policy for which signals are ignored vs. restored is
  fragmented across multiple files, making it easy to leave a child in the
  wrong state when adding new fork sites.
- **Recommendation:** Extend `SignalManager.reset_child_signals()` with an
  optional parameter that keeps specific signals ignored during process-group
  setup, and re-enable them before the child executes user code. All fork sites
  would call this helper, keeping the contract in one place.

## 2. Clarify Pipeline Context Management

- **Current state:** Each pipeline command builds an execution closure that
  mutates `visitor.context` directly after calling
  `context.pipeline_context_enter()`. The control flow is correct but
  non-obvious.
- **Concern:** Future refactors may use the visitor concurrently or add new
  nested contexts; the manual assignment can easily drift or leak state.
- **Recommendation:** Introduce a small helper (e.g.,
  `visitor.with_child_context(pipeline_ctx)`) or a context manager that ensures
  the visitor’s context is restored automatically. This documents the intent
  and prevents context leaks.

## 3. Provide a Terminal-Transfer Guard

- **Current state:** `ProcessLauncher`, `PipelineExecutor`, and
  `SubshellExecutor` all duplicate the pattern of saving the shell’s PGID,
  calling `transfer_terminal_control`, waiting, and restoring.
- **Concern:** The duplication increases the likelihood of forgetting to
  restore the terminal in new pathways.
- **Recommendation:** Add a helper/context manager on `JobManager` (or a small
  utility module) that captures the original PGID, performs the transfer, and
  guarantees restoration in a `finally` block. This would be used as
  `with terminal_control(job_pgid, "Pipeline"):` around waits.

## 4. Strengthen SIGCHLD Reaping Loop

- **Current state:** `SignalManager.process_sigchld_notifications()` drains the
  notifier and then calls `waitpid(-1, WNOHANG | WUNTRACED)` in a loop until no
  children remain, but it only enters this loop when the notifier produced an
  event.
- **Concern:** If multiple SIGCHLDs collapse into one notification, some
  children might not be reaped promptly.
- **Recommendation:** After draining the notifier, keep calling `waitpid` until
  it raises `ECHILD`, regardless of how many signals were queued. This
  guarantees every pending child is handled promptly under heavy signal load.

## 5. Add Regression Tests for PGID Synchronization

- **Current state:** The sync-pipe logic in `PipelineExecutor` ensures
  non-leader children wait for PGID assignment, but there are no targeted tests
  covering the race it prevents.
- **Concern:** Future changes might remove the synchronization for perceived
  simplicity or performance.
- **Recommendation:** Add an integration test that constructs a pipeline,
  introduces artificial delays in `os.setpgid`, and asserts each child observes
  the intended PGID before running user code. This keeps the synchronization
  contract guarded by CI.

Implementing these focused improvements keeps signal handling, terminal
control, and job-control decisions in obvious locations, reducing the risk of
regressions as the executor evolves.
