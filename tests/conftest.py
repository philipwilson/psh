"""
Pytest configuration for the new PSH test suite.

This provides fixtures and configuration specific to the organized test structure,
avoiding conflicts with the main test suite's conftest.py.
"""

import os
import signal
import sys
from io import StringIO
from pathlib import Path

import pytest

# Add PSH to path
PSH_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PSH_ROOT))

# The shared oracle harness (tests/harness/shell_oracle.py) is the ONE bash
# resolver + typed differential runner (campaign E2). tests/ is not a package,
# so put the harness directory on sys.path here — every test module can then
# `from shell_oracle import resolve_bash, run_shell_case` regardless of depth.
sys.path.insert(0, str(PSH_ROOT / "tests" / "harness"))

# On macOS with XQuartz installed, DISPLAY points at a launchd socket that
# AUTO-STARTS XQuartz the moment any X11-capable client the suite spawns
# connects to it (a GUI popping up mid-test-run). Strip it here, at import
# time, so every test process — including xdist workers — and every
# subprocess they spawn inherits an X11-free environment. XAUTHORITY goes
# with it. No psh or bash behavior under test depends on either.
os.environ.pop("DISPLAY", None)
os.environ.pop("XAUTHORITY", None)

from psh.core import ReadonlyVariableError
from psh.executor.job_control import JobState
from psh.shell import Shell


def _reap_children():
    """Reap any zombie child processes to prevent leakage between tests."""
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
        except ChildProcessError:
            break
        except OSError:
            break


def _kill_job(job):
    """SIGKILL a still-running job's process group (and pids); return its pids.

    Tests routinely start long-lived background jobs (``sleep 30 &``) purely to
    exercise job control and never expect them to finish. Teardown must *kill*
    them, not ``wait_for_job`` on them — waiting blocks for the full sleep
    duration and was the dominant cost of the serial test phase
    (see docs/reviews/parallel_test_safety_2026-06-06.md).
    """
    if job.pgid:
        try:
            os.killpg(job.pgid, signal.SIGKILL)
        except OSError:
            pass
    pids = [proc.pid for proc in job.processes]
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    return pids


def _cleanup_shell(shell_instance):
    """Kill leftover background jobs and reap zombies after a test."""
    killed_pids = []
    for job in list(shell_instance.job_manager.jobs.values()):
        if job.state == JobState.RUNNING:
            killed_pids.extend(_kill_job(job))
    shell_instance.job_manager.jobs.clear()
    # Blocking-reap the pids we just killed (returns in ms once SIGKILL lands)
    # so zombies don't accumulate across the suite.
    for pid in killed_pids:
        try:
            os.waitpid(pid, 0)
        except OSError:
            pass
    _reap_children()
    # Release the shell's fd-backed resources (the signal-notifier self-pipes)
    # to prevent FD exhaustion across tests. Shell.close() is idempotent and
    # None-safe for shells that never allocated the notifiers (lazy alloc).
    if hasattr(shell_instance, 'close'):
        shell_instance.close()


@pytest.fixture(autouse=True)
def _restore_os_environ():
    """Roll back os.environ mutations after each test.

    In-process shells sync `export` into the test runner's own os.environ,
    so exported names (FOO, A, B, ...) would otherwise leak into every
    later test's shell and subprocess. This kills that pollution class.
    """
    saved = os.environ.copy()
    yield
    for k in list(os.environ.keys()):
        if k not in saved:
            del os.environ[k]
    for k, v in saved.items():
        if os.environ.get(k) != v:
            os.environ[k] = v


#: Signals whose process-level dispositions in-process shells can mutate
#: (psh's TrapManager installs real handlers for `trap` actions; job control
#: touches TSTP/TTIN/TTOU/CHLD). SIGALRM is deliberately EXCLUDED —
#: pytest-timeout owns it. SIGKILL/SIGSTOP cannot be caught anyway.
_HERMETIC_SIGNALS = tuple(
    getattr(signal, name) for name in (
        'SIGINT', 'SIGTERM', 'SIGHUP', 'SIGQUIT', 'SIGPIPE', 'SIGCHLD',
        'SIGTSTP', 'SIGTTIN', 'SIGTTOU', 'SIGUSR1', 'SIGUSR2', 'SIGWINCH',
        'SIGCONT', 'SIGABRT',
    ) if hasattr(signal, name)
)


@pytest.fixture(autouse=True)
def _restore_signal_dispositions_and_std_fds():
    """Snapshot/restore process signal dispositions, fds 0/1/2, and the
    process-global libc locale per test (boundary campaign E3: hermetic
    process state).

    WHY suite-wide autouse: an in-process shell that runs `trap "..." SIG`
    installs a REAL handler in the test runner's process
    (``TrapManager._set_signal_handler``). ``Shell.close()`` restores it, but
    a test that constructs a raw ``Shell()`` outside the fixture family — or
    calls ``signal.signal`` itself — leaks the disposition into every later
    test and, worse, into every later SUBPROCESS (an inherited SIG_IGN made
    a whole class of fatal-signal tests silently meaningless in the past —
    see the SIGINT-gate memory). Likewise a test that rewires fd 0/1/2
    permanently corrupts the whole worker; and a shell given a non-C locale
    profile calls libc ``setlocale`` PROCESS-GLOBALLY
    (``LocaleService._try_setlocale``) — a later C-profile shell never calls
    ``setlocale`` at all (C mode is the no-setlocale fast path), so a leaked
    non-C worker locale would silently recolor every later collation/ctype
    answer. Restoring is a handful of syscalls per test and acts only on
    drift, so the fixture is safe at suite scope; scope rationale recorded
    in the E23 boundary ledger.

    The teardown runs AFTER the shell-family fixtures' cleanup (autouse
    fixtures are set up first, torn down last), so it observes the
    post-``Shell.close()`` state and only repairs genuine leaks.
    """
    import locale as _locale
    try:
        saved_locale = _locale.setlocale(_locale.LC_ALL)
    except _locale.Error:  # pragma: no cover - unqueryable locale state
        saved_locale = None
    saved_signals = {}
    for sig in _HERMETIC_SIGNALS:
        try:
            handler = signal.getsignal(sig)
        except (OSError, ValueError):
            continue
        if handler is not None:  # None = non-Python handler; not restorable
            saved_signals[sig] = handler
    saved_fds = {}
    for fd in (0, 1, 2):
        try:
            saved_fds[fd] = os.dup(fd)
        except OSError:
            pass
    try:
        yield
    finally:
        if saved_locale is not None:
            try:
                if _locale.setlocale(_locale.LC_ALL) != saved_locale:
                    _locale.setlocale(_locale.LC_ALL, saved_locale)
            except _locale.Error:  # pragma: no cover - unrestorable composite
                pass
        for sig, handler in saved_signals.items():
            try:
                if signal.getsignal(sig) is not handler:
                    signal.signal(sig, handler)
            except (OSError, ValueError, TypeError):
                # ValueError: not in main thread — nothing we can do safely.
                pass
        for fd, dup in saved_fds.items():
            try:
                os.dup2(dup, fd)
            except OSError:
                pass
            finally:
                try:
                    os.close(dup)
                except OSError:
                    pass


@pytest.fixture
def shell():
    """Create a fresh shell instance for testing.

    This fixture creates a new Shell instance with clean state for each test.
    Unlike the main test suite, this doesn't capture output automatically.
    """
    shell_instance = Shell()
    yield shell_instance
    _cleanup_shell(shell_instance)


@pytest.fixture
def clean_shell():
    """Create a shell instance with a minimal set of variables.

    Removes every shell variable except a small essential set so a test can
    exercise core behavior without interference from the ambient environment.

    ``shell.state.variables`` is a *derived* dict — the property rebuilds it
    from the scope manager on every read (see ``ShellState.variables``), so
    ``del shell.state.variables[name]`` mutates a throwaway copy and changes
    nothing. Removal must go through the scope-manager API. Readonly specials
    (UID/EUID/PPID) cannot be unset and are left in place.
    """
    shell_instance = Shell()
    essential_vars = {'PATH', 'HOME', 'USER', 'SHELL'}
    scope = shell_instance.state.scope_manager
    for var in list(shell_instance.state.variables.keys()):
        if var in essential_vars:
            continue
        try:
            scope.unset_variable(var)
        except ReadonlyVariableError:
            pass
    yield shell_instance
    _cleanup_shell(shell_instance)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files.

    This fixture creates a temporary directory that is automatically
    cleaned up after the test completes.
    """
    import shutil
    import tempfile

    temp_dir = tempfile.mkdtemp(prefix='psh_test_')
    original_cwd = os.getcwd()

    yield temp_dir

    # Cleanup
    os.chdir(original_cwd)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def shell_with_temp_dir(isolated_shell_with_temp_dir):
    """Deprecated thin alias of :func:`isolated_shell_with_temp_dir`.

    This fixture once had subtly different semantics: it reused the ``shell``
    fixture's instance (constructed *before* the chdir) and moved ``$PWD`` via
    ``set_variable`` rather than constructing a fresh Shell inside the temp dir,
    and it never set ``os.environ['PWD']``. That divergent twin was exactly the
    "two blessed ways to do the same setup" pattern the reappraisal-#19 T12
    slot converged: every current user was measured under the alias and the
    difference proved inert (see ``tmp/r19-ledgers/T12-probes/
    fixture_alias_verdict.txt``), so the two paths are now one.

    Prefer ``isolated_shell_with_temp_dir`` directly in new tests. The ratchet
    meta-test ``tests/unit/tooling/test_fixture_ratchets.py`` caps the number of
    remaining ``shell_with_temp_dir`` references and only allows it to shrink.
    """
    return isolated_shell_with_temp_dir


@pytest.fixture
def isolated_shell_with_temp_dir(temp_dir):
    """Shell instance with a real os.chdir into a per-test temp directory.

    Use for tests that create files or perform redirections: each test
    gets its own directory, so fixed-name outputs can't collide across
    xdist workers. (The old caveat about needing pytest's `-s` flag was
    fixed in v0.195.0 — forked children now do fd-level I/O, so capture
    no longer interferes.)
    """
    import os
    import sys

    from psh.shell import Shell

    # Store original working directory and change to temp directory FIRST
    original_cwd = os.getcwd()
    original_pwd = os.environ.get('PWD', original_cwd)
    os.chdir(temp_dir)
    os.environ['PWD'] = temp_dir

    # Create a completely fresh shell instance (now in temp directory)
    shell = Shell()

    # Store original file descriptors to ensure proper cleanup
    original_stdin = sys.stdin
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    yield shell

    # Clean up jobs and zombie processes
    _cleanup_shell(shell)

    # Ensure streams are restored (defensive cleanup)
    sys.stdin = original_stdin
    sys.stdout = original_stdout
    sys.stderr = original_stderr

    # Restore original working directory and PWD environment
    os.chdir(original_cwd)
    os.environ['PWD'] = original_pwd


@pytest.fixture
def captured_shell():
    """Shell with output capture for testing.

    This fixture provides a shell instance where stdout and stderr
    are captured properly, working around the executor's tendency
    to reset shell.stdout to sys.stdout.

    The approach: capture at the sys.stdout/stderr level during
    command execution, which is more reliable than trying to
    intercept at the shell level.
    """
    # Create shell with captured I/O
    shell = Shell()

    # Store original sys streams
    original_sys_stdout = sys.stdout
    original_sys_stderr = sys.stderr

    # Create capture buffers
    captured_stdout = StringIO()
    captured_stderr = StringIO()

    # Store original run_command method
    original_run_command = shell.run_command

    def capturing_run_command(command_string, add_to_history=True, base_line=1,
                              line_oriented=False, **kwargs):
        """Run command with output capture.

        ``**kwargs`` forwards any further Shell.run_command keyword
        arguments (e.g. the trap manager's ``posix_syntax_exit=False``)
        so the wrapper stays signature-compatible.
        """
        # Replace sys streams during execution
        sys.stdout = captured_stdout
        sys.stderr = captured_stderr

        # Also replace shell's internal streams to capture all output
        # Some code uses shell.stderr directly instead of sys.stderr
        original_shell_stdout = shell.stdout
        original_shell_stderr = shell.stderr
        shell.stdout = captured_stdout
        shell.stderr = captured_stderr

        try:
            result = original_run_command(command_string, add_to_history,
                                          base_line, line_oriented, **kwargs)
        finally:
            # Always restore
            sys.stdout = original_sys_stdout
            sys.stderr = original_sys_stderr
            shell.stdout = original_shell_stdout
            shell.stderr = original_shell_stderr

        return result

    # Replace run_command
    shell.run_command = capturing_run_command

    # Add helper methods
    shell.get_stdout = lambda: captured_stdout.getvalue()
    shell.get_stderr = lambda: captured_stderr.getvalue()
    shell.clear_output = lambda: (
        captured_stdout.truncate(0),
        captured_stdout.seek(0),
        captured_stderr.truncate(0),
        captured_stderr.seek(0)
    )

    yield shell

    # Cleanup jobs, zombies, and signal notifier FDs
    _cleanup_shell(shell)

    # Restore streams
    sys.stdout = original_sys_stdout
    sys.stderr = original_sys_stderr


@pytest.fixture(autouse=True)
def reset_environment():
    """Restore the working directory after each test.

    Environment-variable rollback is handled wholesale by the
    `_restore_os_environ` autouse fixture above (this fixture used to
    restore a hardcoded list of var names, which that one supersedes).
    """
    original_cwd = os.getcwd()
    yield
    os.chdir(original_cwd)


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on file paths."""


    # Tests that need serial execution to avoid race conditions
    serial_tests = [
        "test_file_not_found_redirection",
        "test_permission_denied_redirection",
    ]

    # Whole files that are unsafe to run *concurrently* under pytest-xdist and
    # must run in a serial pass (see docs/reviews/parallel_test_safety_2026-06-06.md):
    #   - process/signal/job-control tests spawn/kill/wait on processes and send
    #     signals that destabilise sibling workers;
    #   - in-process forked-fd tests (read from a redirected/forked fd, here-string
    #     reads) manipulate the runner's fds, which under xdist are the execnet
    #     worker channel — they intentionally exercise the in-process path so they
    #     cannot simply be run in a subprocess.
    # `run_tests.py --parallel` excludes `-m serial` from the xdist phase and runs
    # them serially afterward; a bare `pytest -n auto` should use `-m "not serial"`.
    serial_path_markers = (
        "job_control",            # integration/job_control/* + test_job_control_builtins
        "test_disown",
        "test_signal_builtins",
        # Traps and DELIVERS signals (kill -N $$) while comparing against live
        # bash; concurrently the signal dispositions race across xdist workers
        # (flaked in the parallel phase, always passes serially / in isolation).
        "test_trap_signal_spec_conformance",
        "test_pty",
    )

    # The redirection suite forks for heredocs / here-strings / process
    # substitution and manipulates fds in-process; concurrently those clobber
    # the xdist worker channel (each file can pass alone, but the dir flakes).
    # It therefore defaults to SERIAL — a NEW redirection file is serial until
    # vetted (safe-by-default preserved).
    #
    # EXCEPTION (campaign #21, item d — test_performance appraisal 2026-07-07):
    # the files below were individually audited as xdist-safe and opt OUT of the
    # serial default into the parallel phase. Two safety classes qualify:
    #   (1) SUBPROCESS-DRIVEN — every test runs psh via subprocess.run/Popen, so
    #       all fd/fork/signal/exec effects happen inside the child, fully
    #       isolated from the pytest worker; and
    #   (2) PER-COMMAND IN-PROCESS — only fd-0/1/2 per-command redirects on the
    #       in-process shell (psh saves/restores fds around each command — the
    #       exact pattern already green across thousands of Phase-1 captured_shell
    #       tests), plus ordinary external-command forks.
    # Files that fork IN-PROCESS for heredoc/here-string/process-sub, do
    # permanent `exec` fd changes in-process, manipulate fd>=3 in-process, or
    # reap bg jobs at the worker level are NOT listed and stay serial (the 4
    # unsafe + 3 mixed files: test_here_string_bareword, test_here_string_word_quoting,
    # test_read_forked_fd, test_high_fd_redirection, test_advanced_redirection,
    # test_heredoc, test_simple_redirection).
    # See docs/reviews/parallel_test_safety_2026-06-06.md.
    REDIRECTION_PARALLEL_SAFE = frozenset({
        "test_builtin_dup_source_reassigned.py",
        "test_builtin_redirect_child_visibility.py",
        "test_builtin_redirect_nesting.py",
        "test_child_fd_inheritance.py",
        "test_compound_redirect_failure.py",
        "test_exec_close_output_leak.py",
        "test_exec_permanent_redirect.py",
        "test_explicit_fd_heredoc_no_self_close.py",
        "test_external_redirect_once.py",
        "test_fd_move_and_csh_redirect.py",
        "test_here_string_tilde.py",
        "test_heredoc_composite_delimiter.py",
        "test_large_heredoc.py",
        "test_named_fd.py",
        "test_noclobber_targets.py",
        "test_process_sub_cleanup.py",
        "test_process_sub_closed_fds.py",
        "test_process_sub_embedded.py",
        "test_redirect_error_messages.py",
        "test_redirect_failure_paths.py",
        "test_redirection_restore.py",
        "test_script_fd_relocation.py",
    })

    # Mark tests that need special handling

    for item in items:
        fspath = str(item.fspath)
        if any(marker in fspath for marker in serial_path_markers):
            item.add_marker(pytest.mark.serial)
        elif "integration/redirection" in fspath and (
                os.path.basename(fspath) not in REDIRECTION_PARALLEL_SAFE):
            # Redirection file not on the vetted allowlist → serial default.
            item.add_marker(pytest.mark.serial)

        # Add markers based on test file location
        if "unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "system/" in str(item.fspath):
            item.add_marker(pytest.mark.system)
        elif "conformance/" in str(item.fspath):
            item.add_marker(pytest.mark.conformance)
        elif "performance/" in str(item.fspath):
            item.add_marker(pytest.mark.performance)

        # Mark interactive (PTY/terminal-driven) tests. tests/unit/interactive/
        # holds pure in-process unit tests of editor/completion logic — no
        # terminal needed — so it runs by default and is exempt here.
        if "interactive/" in str(item.fspath) and "unit/interactive/" not in str(item.fspath):
            item.add_marker(pytest.mark.interactive)

        # Mark tests that need serial execution
        if any(test_name in item.name for test_name in serial_tests):
            item.add_marker(pytest.mark.serial)


# Skip interactive tests by default unless explicitly requested
def pytest_runtest_setup(item):
    """Skip interactive tests unless explicitly requested."""
    if item.get_closest_marker("interactive"):
        # The PTY smoke suite (test_pty_smoke.py) is deterministic and runs
        # by default — it is the interactive coverage the suite relies on —
        # as is the F2 REPL-EOF shutdown-route pin (same conventions).
        # The remaining legacy interactive tests stay opt-in.
        if ("test_pty_smoke" in str(item.fspath)
                or "test_pty_shutdown_route_f2" in str(item.fspath)):
            return
        if not item.config.getoption("--run-interactive", default=False):
            pytest.skip("Interactive tests skipped (use --run-interactive to run)")

    # Note: per-test process cleanup is handled by the `shell` fixture teardown
    # (`_cleanup_shell`). No pre-test global `pkill` here — a pattern broad enough
    # to catch leaked psh processes also matches sibling xdist workers and crashes
    # them. `serial`-marked tests are kept out of the xdist phase by
    # `run_tests.py --parallel` (`-m "not serial"`) and run in a separate serial
    # pass; a bare `pytest -n auto` should pass `-m "not serial"`. (The old
    # gw0-only skip was removed: under xdist each test runs on exactly one worker,
    # so skipping serial tests on non-gw0 workers silently dropped them.)


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--run-interactive",
        action="store_true",
        default=False,
        help="Run interactive tests (requires pexpect and terminal)"
    )
    # Must live in the ROOT conftest: pytest only honours pytest_addoption from
    # the rootdir conftest (a copy in tests/behavioral/conftest.py was silently
    # ignored on full-suite runs, so the golden bash-comparison tests could never
    # be enabled). Run with: pytest tests/behavioral --compare-bash
    parser.addoption(
        "--compare-bash",
        action="store_true",
        default=False,
        help="Also run each golden test against bash and compare output",
    )
