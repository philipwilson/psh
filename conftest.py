"""Global pytest configuration for psh tests."""
import os

import pytest

from psh.executor.job_control import JobState
from psh.shell import Shell


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "visitor_xfail(reason): mark test as expected to fail when using visitor executor"
    )

    # Ensure subprocesses can import the local psh package when invoked via
    # ``python -m psh`` by propagating the repository root through PYTHONPATH.
    repo_root = os.path.dirname(os.path.abspath(__file__))
    existing = os.environ.get('PYTHONPATH')
    path_entries = [repo_root]
    if existing:
        path_entries.append(existing)
    os.environ['PYTHONPATH'] = os.pathsep.join(path_entries)

    # Run the entire suite with strict-errors enabled so a genuine INTERNAL
    # DEFECT (a Python bug surfacing as an unexpected exception) fails loudly
    # instead of being masked as an ordinary exit-1. This env var seeds the
    # strict-errors option at Shell construction, so it covers BOTH in-process
    # shells AND subprocess ``python -m psh`` instances.
    #
    # Expected shell errors are NOT affected: per the taxonomy in
    # psh/core/internal_errors.py, PshError / OSError / SyntaxError reaching a
    # last-resort guard pass through to normal handling (print + exit 1) even
    # under strict mode. Only true defects (RuntimeError, AttributeError,
    # TypeError, ...) are re-raised.
    os.environ['PSH_STRICT_ERRORS'] = '1'


def pytest_collection_modifyitems(config, items):
    """Apply xfail marking to tests marked with visitor_xfail."""
    # Visitor executor is now the only executor
    # All tests marked with visitor_xfail should be expected to fail
    for item in items:
        # Check if test has visitor_xfail marker
        visitor_xfail_marker = item.get_closest_marker("visitor_xfail")
        if visitor_xfail_marker:
            reason = visitor_xfail_marker.kwargs.get("reason", "Test fails due to pytest output capture limitations with forked processes")
            item.add_marker(pytest.mark.xfail(reason=reason))


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


@pytest.fixture
def shell():
    """Create a clean shell instance for testing."""
    # Save original file descriptors
    original_stdin = os.dup(0)
    original_stdout = os.dup(1)
    original_stderr = os.dup(2)

    # Create shell instance - visitor executor is now the only executor
    shell_instance = Shell()

    try:
        yield shell_instance
    finally:
        # Wait for any background jobs managed by this shell
        for job in list(shell_instance.job_manager.jobs.values()):
            if job.state == JobState.RUNNING:
                try:
                    shell_instance.job_manager.wait_for_job(job)
                except (OSError, Exception):
                    pass
        shell_instance.job_manager.jobs.clear()

        # Reap any remaining zombie child processes
        _reap_children()

        # Ensure file descriptors are restored
        try:
            os.dup2(original_stdin, 0)
            os.dup2(original_stdout, 1)
            os.dup2(original_stderr, 2)
        except OSError:
            pass
        finally:
            try:
                os.close(original_stdin)
                os.close(original_stdout)
                os.close(original_stderr)
            except OSError:
                pass
