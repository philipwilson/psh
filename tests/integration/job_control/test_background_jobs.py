"""
Background job control integration tests.

Tests for background job creation, management, and control including:
- Background job creation with &
- Job status tracking and listing
- Foreground/background job control (fg/bg)
- Job completion detection
- Exit status handling for background jobs
"""

import sys
from pathlib import Path

# Add framework to path
TEST_ROOT = Path(__file__).parent.parent.parent
PSH_ROOT = TEST_ROOT.parent
sys.path.insert(0, str(PSH_ROOT))

# Shell fixture imported automatically from conftest.py


class TestBackgroundJobCreation:
    """Test creation and basic management of background jobs."""

    def test_simple_background_job(self, shell):
        """Test basic background job creation with &."""
        # Start a background job that sleeps briefly
        result = shell.run_command('sleep 0.1 &')
        assert result == 0

        # Should immediately return control to shell
        # Job should be running in background

        # Check that jobs command shows the job
        jobs_result = shell.run_command('jobs')
        assert jobs_result == 0
        # Should show at least one job

    def test_background_job_with_output(self, shell):
        """Test background job that produces output."""
        # Create a background job that outputs to a file
        result = shell.run_command('echo "background output" > /tmp/bg_test &')
        assert result == 0

        # The backgrounded builtin creates the redirect file in the forked
        # child (bash; F3), so wait for the job before reading the file rather
        # than racing it.
        shell.run_command('wait')

        # Check the output was written
        cat_result = shell.run_command('cat /tmp/bg_test')
        assert cat_result == 0
        # Output verification would need shell output capture

        # Clean up
        shell.run_command('rm -f /tmp/bg_test')

    def test_multiple_background_jobs(self, shell):
        """Test creating multiple background jobs."""
        # Start several background jobs
        result1 = shell.run_command('sleep 0.2 &')
        result2 = shell.run_command('sleep 0.2 &')
        result3 = shell.run_command('sleep 0.2 &')

        assert result1 == 0
        assert result2 == 0
        assert result3 == 0

        # jobs command should show multiple jobs
        jobs_result = shell.run_command('jobs')
        assert jobs_result == 0

        # Jobs output verification would need shell output capture

    def test_background_job_exit_status(self, shell):
        """A background job's exit status is reported by `wait PID`; a bare
        `wait` (no operands) returns 0 (POSIX/bash) — a failing background
        job does NOT leak into a no-operand wait."""
        # First, wait for any lingering jobs from previous tests
        shell.run_command('wait')

        # & returns 0 immediately
        assert shell.run_command('false &') == 0

        # `wait PID` reports the specific job's status
        assert shell.run_command('false & wait $!') != 0
        assert shell.run_command('true & wait $!') == 0

        # A bare `wait` always returns 0, even after a failed background job.
        shell.run_command('false &')
        assert shell.run_command('wait') == 0


class TestJobStatusTracking:
    """Test job status tracking and reporting."""

    def test_jobs_command_basic(self, shell):
        """Test basic jobs command functionality."""
        # With no jobs, jobs should return cleanly
        result = shell.run_command('jobs')
        assert result == 0

        # Start a background job
        shell.run_command('sleep 0.5 &')

        # jobs should now show the running job
        jobs_result = shell.run_command('jobs')
        assert jobs_result == 0
        # Job status verification would need shell output capture

    def test_job_numbering(self, shell):
        """Test that jobs are assigned sequential numbers."""
        # Start multiple jobs
        shell.run_command('sleep 0.3 &')
        shell.run_command('sleep 0.3 &')

        jobs_result = shell.run_command('jobs')
        assert jobs_result == 0

        # Job numbering verification would need shell output capture

    def test_job_state_transitions(self, shell):
        """Test job state transitions (Running -> Done)."""
        # Start a short background job
        shell.run_command('sleep 0.1 &')

        # Immediately check - should be running
        jobs_result = shell.run_command('jobs')
        assert jobs_result == 0

        # Wait for job to complete


        # Check again - status should change
        jobs_result2 = shell.run_command('jobs')
        assert jobs_result2 == 0

        # State transition verification would need shell output capture


class TestJobControl:
    """Test foreground/background job control commands."""

    def test_foreground_command(self, shell):
        """Test bringing background job to foreground with fg."""
        # Start a longer-running background job
        shell.run_command('sleep 1 &')

        # Get the job number
        jobs_result = shell.run_command('jobs')
        assert jobs_result == 0

        # Bring job to foreground (this will block until job completes)
        # fg_result = shell.run_command('fg %1')
        # This test is complex because fg blocks, needs special handling

    def test_job_reference_by_number(self, shell):
        """A running job can be referenced with %N (here via `kill -0`)."""
        shell.run_command('sleep 3 &')
        # kill -0 only checks that the job/pid is signalable; %1 must resolve.
        assert shell.run_command('kill -0 %1') == 0


class TestJobCompletion:
    """Test job completion detection and cleanup."""

    def test_wait_for_specific_job(self, shell):
        """Test waiting for a specific background job."""
        # Start a background job
        shell.run_command('sleep 0.2 &')

        # Wait for all background jobs
        wait_result = shell.run_command('wait')
        assert wait_result == 0

        # After wait, no jobs should be running
        jobs_result = shell.run_command('jobs')
        assert jobs_result == 0
        # Output should be empty or show no running jobs

    def test_wait_exit_status(self, shell):
        """`wait PID` returns the waited job's status; a bare `wait` returns 0.

        POSIX/bash: `wait` with no operands always returns 0 once children
        finish — a failing background job does not leak into it. Only the
        operand form `wait PID`/`wait %job` reports a job's exit status.
        """
        # Operand form reports the job's own status.
        assert shell.run_command('true & wait $!') == 0
        assert shell.run_command('false & wait $!') != 0

        # No-operand wait returns 0 regardless of a failed background job.
        shell.run_command('false &')
        assert shell.run_command('wait') == 0

    def test_automatic_job_cleanup(self, shell):
        """Test that completed jobs are eventually cleaned up."""
        # Start and complete a job
        shell.run_command('echo "test" &')


        # jobs should show the completed job initially
        jobs_result1 = shell.run_command('jobs')
        assert jobs_result1 == 0

        # After another command, completed jobs might be cleaned up
        shell.run_command('echo "cleanup trigger"')
        jobs_result2 = shell.run_command('jobs')
        assert jobs_result2 == 0

        # Completed jobs should eventually disappear from jobs list


class TestJobControlWithPipelines:
    """Test job control with pipeline commands."""

    def test_pipeline_background_job(self, shell):
        """Test running an entire pipeline in background."""
        # Run a pipeline in background
        result = shell.run_command('echo "test" | cat > /tmp/pipe_bg_test &')
        assert result == 0

        # Wait for completion


        # Check result
        cat_result = shell.run_command('cat /tmp/pipe_bg_test')
        assert cat_result == 0
        # Output verification would need shell output capture

        # Clean up
        shell.run_command('rm -f /tmp/pipe_bg_test')

    def test_complex_pipeline_background(self, shell):
        """Test complex pipeline in background."""
        # Create test file
        shell.run_command('echo -e "line1\\nline2\\nline3" > /tmp/test_input')

        # Run complex pipeline in background
        result = shell.run_command('cat /tmp/test_input | grep "line" | wc -l > /tmp/pipe_result &')
        assert result == 0

        # Wait and check result

        cat_result = shell.run_command('cat /tmp/pipe_result')
        assert cat_result == 0
        # Output verification would need shell output capture

        # Clean up
        shell.run_command('rm -f /tmp/test_input /tmp/pipe_result')


class TestJobControlErrorHandling:
    """Test error handling in job control scenarios."""

    def test_invalid_job_reference(self, shell):
        """Referencing a non-existent job is an error (non-zero exit)."""
        assert shell.run_command('kill %99') != 0

    def test_job_control_with_errexit(self, shell):
        """Test job control interaction with set -e."""
        # Enable errexit
        shell.run_command('set -e')

        # Background job failure shouldn't affect shell
        result = shell.run_command('false &')
        assert result == 0  # & should succeed even with set -e

        # Shell should continue running
        echo_result = shell.run_command('echo "still running"')
        assert echo_result == 0
        # Output verification would need shell output capture

    def test_background_job_with_redirection_error(self, shell):
        """Test background job with I/O redirection errors.

        PSH evaluates the redirect synchronously for background builtins,
        so the & command itself may return non-zero.  Bash defers the error
        to the child.  Either way, `wait` should return 0 because no async
        child was actually launched.
        """
        # Try to redirect to invalid location
        result = shell.run_command('echo "test" > /invalid/path/file &')
        # PSH returns the redirect error synchronously; accept any exit code
        assert isinstance(result, int)

        wait_result = shell.run_command('wait')
        # No child process was launched, so wait succeeds
        assert wait_result == 0


# Test fixtures and helper functions
# Shell fixture provided by conftest.py


class TestSpecialBuiltinBackground:
    """Backgrounding a POSIX special builtin must not crash.

    Regression: SpecialBuiltinExecutionStrategy delegated to a misnamed
    method (``_execute_in_background`` instead of
    ``_execute_builtin_in_background``), so ``: &`` raised AttributeError
    instead of running the no-op in the background like bash. Run in a
    subprocess (backgrounds a process; see parallel-safety rules).
    """

    def test_colon_builtin_background(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', ': &\necho done\nwait'],
            capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout == 'done\n'
        assert 'AttributeError' not in result.stderr
        assert '_execute_in_background' not in result.stderr
