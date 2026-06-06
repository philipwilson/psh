# Parallel Test Safety — Root Cause & Remediation (2026-06-06)

/ Status: root cause fixed; `run_tests.py --parallel` is reliable. /

**Update.** Workstreams 1 (fd isolation) and 2 (serial phase) are implemented:
- `test_exec_builtin`'s permanent-redirection tests now run in a subprocess.
- Process/signal/job-control and in-process forked-fd tests (incl. the
  `integration/redirection` dir) are marked `serial`; `run_tests.py --parallel`
  runs `-m "not serial"` under xdist, then `-m serial` without xdist.

Result: the parallel phase is crash-free and repeatable (3263 passed, 0
INTERNALERROR over 4/4 runs); `run_tests.py --parallel` is green end-to-end
(~75s vs ~210s serial); serial mode unchanged (3435 passed). No file-collision
failures were observed once the redirection dir was serialized. A bare
`pytest -n auto` should pass `-m "not serial"`.

## TL;DR

`python -m pytest -n auto` (pytest-xdist) aborts with
`INTERNALERROR> OSError: cannot send (already closed?)`. The root cause is **not**
a worker process crashing — it is the **execnet controller↔worker channel file
descriptor being clobbered** by tests that exercise psh's *permanent,
process-level* fd redirection (`exec >file`, `exec 2>&1`, `exec 3>&1`, fd
`close`/`dup2`) **in-process** via the `shell` / `captured_shell` fixtures.

Because those fixtures run psh inside the test-runner (worker) process, a
permanent redirection rewrites the worker's own file descriptors. Under xdist
those fds carry the execnet channel, so the controller can no longer talk to the
worker and the whole session aborts.

## How it was diagnosed (the spike)

1. **Instrumented `os._exit`** (wrapped, keyed on the worker pid to distinguish
   the worker from a legitimate forked child) and **`faulthandler`** for fatal
   signals (SIGSEGV/SIGABRT/SIGTERM/…). After a crashing run the diagnostic logs
   were **empty** → the worker is **not** exiting via `os._exit` and **not**
   being killed by a catchable signal.
2. **Direct experiment**: ran `exec > file` through an in-process `Shell()`, then
   `os.write(1, b"...")` afterwards — the bytes landed in the file. So in-process
   `exec` **permanently clobbers fd 1** of the running process.
3. **fd-guard probe**: saving/restoring fds 0/1/2 around each test moved the
   deterministic `-n 2` crash from 840 → 1728 passed (partial fix), confirming
   fd-clobbering is the mechanism.
4. **Why 0/1/2 guarding is insufficient**: pytest-xdist replaces the worker's
   fd 1/2 with its own capture and keeps the real channel on a **higher fd
   (≥3)**. psh's **fd≥3 redirection** tests (`exec 3>&1`, high-fd) clobber that
   channel fd, which a 0/1/2 guard cannot protect.
5. **Why serial runs pass**: there is no execnet channel, and pytest's `capfd`
   already saves/restores fds between tests.

Ruled out along the way: `os._exit` in the worker; catchable fatal signals; the
conftest `pkill` (a separate, lesser issue); a specific "killer test" (the
crash-item is random — it is whatever was in flight when the channel broke).

## Remediation (three converging workstreams)

1. **fd isolation (root cause of the crashes).** Tests that exercise permanent /
   process-level fd redirection must run psh in a **subprocess**, not via the
   in-process `shell`/`captured_shell` fixtures. Testing `exec`'s permanent
   redirection in-process is fundamentally wrong — it redirects the test runner
   itself. *This is the workstream that removes the worker crashes.*
2. **Process/signal class → serial phase.** Background-job / disown / signal /
   kill tests can't run *concurrently* with siblings (they send signals / pkill);
   run them in a dedicated serial pass (mark `serial`, exclude from the xdist
   phase). A prototype of this works.
3. **File-collision flakiness.** `shell`-fixture tests write fixed-name files to
   the shared cwd; `shell_with_temp_dir` only sets `PWD` and does **not** isolate
   real fd-level writes. Fix it to `os.chdir` (or migrate to
   `isolated_shell_with_temp_dir`).

## Guidance for writing fd/redirection tests

- A test that changes the shell's fds *permanently* (`exec` redirections, fd
  open/close/dup that outlives a single command) MUST run psh in a subprocess
  (`subprocess.run([sys.executable, '-m', 'psh', '-c', script], ...)`), so the
  redirection affects that subprocess and not the test runner.
- Per-command redirections (`echo x > f`, `cmd 2>&1 | …`) are fine in-process —
  psh saves/restores fds around the command.
- Prefer `isolated_shell_with_temp_dir` (real `os.chdir`) for any test that
  creates files, so file writes land in a per-test temp dir.
