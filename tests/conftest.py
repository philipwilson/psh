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
    # Close signal notifier pipe FDs to prevent FD exhaustion across tests
    if hasattr(shell_instance, 'interactive_manager'):
        sm = shell_instance.interactive_manager.signal_manager
        if hasattr(sm, '_sigchld_notifier'):
            sm._sigchld_notifier.close()
        if hasattr(sm, '_sigwinch_notifier'):
            sm._sigwinch_notifier.close()


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
    """Create a shell instance with completely fresh environment.

    This fixture creates a shell with minimal environment setup,
    useful for testing core functionality without interference.
    """
    shell_instance = Shell()
    # Clear environment variables except essentials
    essential_vars = {'PATH', 'HOME', 'USER', 'SHELL'}
    for var in list(shell_instance.state.variables.keys()):
        if var not in essential_vars:
            del shell_instance.state.variables[var]
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
def shell_with_temp_dir(shell, temp_dir):
    """Shell instance operating in an isolated temporary working directory.

    Changes BOTH the process cwd and the shell's PWD to a per-test temp dir so
    that redirections (``> file``) and relative file reads land there instead of
    the shared working directory. The previous version only set ``PWD`` and left
    ``> file`` writing to the real cwd — which collided across xdist workers
    (fixed-name files like ``output.txt``) and caused flaky parallel failures.
    """
    original_cwd = os.getcwd()
    original_pwd = shell.state.variables.get('PWD', original_cwd)

    os.chdir(temp_dir)
    shell.state.variables['PWD'] = temp_dir

    try:
        yield shell
    finally:
        os.chdir(original_cwd)
        shell.state.variables['PWD'] = original_pwd


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


class MockStdout:
    """Mock stdout that captures output for testing."""

    def __init__(self):
        self.content = StringIO()

    def write(self, text):
        self.content.write(text)

    def flush(self):
        pass

    def getvalue(self):
        return self.content.getvalue()


class MockStderr:
    """Mock stderr that captures error output for testing."""

    def __init__(self):
        self.content = StringIO()

    def write(self, text):
        self.content.write(text)

    def flush(self):
        pass

    def getvalue(self):
        return self.content.getvalue()


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

    def capturing_run_command(command_string, add_to_history=True, base_line=1):
        """Run command with output capture."""
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
            result = original_run_command(command_string, add_to_history, base_line)
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


@pytest.fixture
def isolated_subprocess_env():
    """Provide an isolated environment for subprocess tests.

    This fixture is specifically designed for tests that spawn
    PSH as a subprocess to ensure proper isolation in parallel execution.
    """
    import tempfile

    # Create a unique temp directory for this test
    temp_dir = tempfile.mkdtemp(prefix=f'psh_test_{os.getpid()}_')

    # Create clean environment
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': os.environ.get('HOME', '/tmp'),
        'USER': os.environ.get('USER', 'test'),
        'SHELL': os.environ.get('SHELL', '/bin/sh'),
        'TMPDIR': temp_dir,
        'TEMP': temp_dir,
        'TMP': temp_dir,
        'PYTHONPATH': str(PSH_ROOT),
        'PYTHONUNBUFFERED': '1',
    }

    yield {'env': env, 'cwd': temp_dir}

    # Cleanup
    import shutil
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except:
        pass


# Test markers for categorizing tests
pytest_configure_node_id_parts = ["suite", "category", "component"]


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests that test isolated components"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests that test component interactions"
    )
    config.addinivalue_line(
        "markers", "system: System tests that test end-to-end functionality"
    )
    config.addinivalue_line(
        "markers", "conformance: Tests that verify bash compatibility"
    )
    config.addinivalue_line(
        "markers", "performance: Performance and benchmark tests"
    )
    config.addinivalue_line(
        "markers", "interactive: Tests that require interactive shell features"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take more than 1 second to run"
    )
    config.addinivalue_line(
        "markers", "serial: Tests that must run serially (no parallel execution)"
    )
    config.addinivalue_line(
        "markers", "isolated: Tests that need extra isolation"
    )
    config.addinivalue_line(
        "markers", "flaky: Tests that are known to be flaky in parallel execution"
    )


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
        # The redirection suite forks for heredocs / here-strings / process
        # substitution and manipulates fds; concurrently these clobber the xdist
        # worker channel (each file can pass alone, but the dir flakes). Serial.
        "integration/redirection",
    )

    # Mark tests that need special handling

    for item in items:
        if any(marker in str(item.fspath) for marker in serial_path_markers):
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
            item.add_marker(pytest.mark.isolated)

        # Mark error recovery tests as needing isolation
        if "test_error_recovery" in str(item.fspath):
            item.add_marker(pytest.mark.isolated)


# Skip interactive tests by default unless explicitly requested
def pytest_runtest_setup(item):
    """Skip interactive tests unless explicitly requested."""
    if item.get_closest_marker("interactive"):
        # The PTY smoke suite (test_pty_smoke.py) is deterministic and runs
        # by default — it is the interactive coverage the suite relies on.
        # The remaining legacy interactive tests stay opt-in.
        if "test_pty_smoke" in str(item.fspath):
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
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests (performance benchmarks)"
    )
    parser.addoption(
        "--strict-isolation",
        action="store_true",
        default=False,
        help="Run with strict test isolation (slower but more reliable)"
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
