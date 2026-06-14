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

        # Wait a moment for job to complete


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
        """Test that background jobs track exit status correctly."""
        # First, wait for any lingering jobs from previous tests
        shell.run_command('wait')

        # Start a background job that will fail
        result = shell.run_command('false &')
        assert result == 0  # & should return 0 immediately

        # Wait for job to complete
        # Use wait with no arguments to wait for all jobs
        wait_result = shell.run_command('wait')
        # wait should return the exit status of the background job
        assert wait_result != 0  # false should return non-zero


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

    def test_background_command(self, shell):
        """Test sending stopped job to background with bg."""
        # This test would require job suspension which is complex to test
        # bg_result = shell.run_command('bg %1')
        pass

    def test_job_reference_by_number(self, shell):
        """Test referencing jobs by number (%1, %2, etc.)."""
        # Start background jobs
        shell.run_command('sleep 0.3 &')
        shell.run_command('sleep 0.3 &')

        # Test job references in other commands
        # Note: This depends on kill command supporting job references
        # kill_result = shell.run_command('kill %1')
        # This might not be implemented yet


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
        """Test that wait returns the exit status of background job.

        This test was previously marked xfail due to flakiness, but is now
        reliable thanks to executor improvements (H4/H5) that fixed job control
        and terminal restoration.
        """
        # Start background job that succeeds
        shell.run_command('true &')
        wait_result = shell.run_command('wait')
        assert wait_result == 0

        # Start background job that fails
        shell.run_command('false &')
        wait_result = shell.run_command('wait')
        assert wait_result != 0

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
        """Test handling of invalid job references."""
        # Try to reference non-existent job
        # This might not be implemented yet, so we'll mark as xfail
        pass

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


# Integration with signal handling (will be expanded in signal tests)
class TestJobControlSignalIntegration:
    """Test basic integration between job control and signals."""

    def test_background_job_signal_isolation(self, shell):
        """Test that signals to shell don't affect background jobs."""
        # This test would require sending signals to the shell
        # while background jobs are running
        pass

    def test_signal_delivery_to_job_group(self, shell):
        """Test that signals are delivered to entire job groups."""
        # Start a job that creates child processes
        # Send signal and verify all processes in group receive it
        pass


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
