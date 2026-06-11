"""Global pytest configuration for psh tests."""
import pytest
import sys
import os
from psh.shell import Shell
from psh.executor.job_control import JobState


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
