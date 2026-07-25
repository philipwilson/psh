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

    def test_background_job_with_output(self, isolated_shell_with_temp_dir):
        """Test background job that produces output.

        Runs in the per-test temp dir rather than a fixed system /tmp path
        shared with every other process on the host, and verifies the file's
        CONTENT — the old body asserted only that `cat` succeeded.
        """
        shell = isolated_shell_with_temp_dir

        # Create a background job that outputs to a file
        result = shell.run_command('echo "background output" > bg_test &')
        assert result == 0

        # The backgrounded builtin creates the redirect file in the forked
        # child (bash; F3), so wait for the job before reading the file rather
        # than racing it.
        assert shell.run_command('wait') == 0

        # Check the output was written
        with open('bg_test') as f:
            assert f.read() == "background output\n"

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

    def test_pipeline_background_job(self, isolated_shell_with_temp_dir):
        """Test running an entire pipeline in background.

        Same two fixes as test_complex_pipeline_background: the "Wait for
        completion" section was EMPTY, so the read raced the background
        pipeline, and the fixed system /tmp path is now the per-test temp
        dir. The content is verified rather than just `cat`'s exit status.
        """
        shell = isolated_shell_with_temp_dir

        # Run a pipeline in background
        result = shell.run_command('echo "test" | cat > pipe_bg_test &')
        assert result == 0

        # Deterministic hand-off through the job API — no sleeps.
        assert shell.run_command('wait') == 0

        # Check result
        with open('pipe_bg_test') as f:
            assert f.read() == "test\n"

    def test_complex_pipeline_background(self, isolated_shell_with_temp_dir):
        """Test complex pipeline in background.

        Two fixes to a test that flaked under load (1.2's final gate):

        * It read ``pipe_result`` with nothing between the launch and the
          read but an empty "Wait and check result" comment, so it passed
          only when the background pipeline won the race. Proven by slowing
          the pipeline: the read then fails because the file is not there
          yet. ``wait`` — the shell's own job API — is the hand-off now.
        * It used FIXED paths in the system /tmp, shared with every other
          process on the host and against this project's use-the-temp-dir
          rule. It now runs in the per-test temp dir.

        The result is also actually verified: the old body asserted only
        that ``cat`` succeeded, with a comment saying output verification
        would need capture. The file's content is the point, so it is read
        directly and pinned to bash 5.2's output for this pipeline.
        """
        shell = isolated_shell_with_temp_dir

        # Create test file
        shell.run_command('echo -e "line1\\nline2\\nline3" > test_input')

        # Run complex pipeline in background
        result = shell.run_command('cat test_input | grep "line" | wc -l > pipe_result &')
        assert result == 0

        # Deterministic hand-off through the job API — no sleeps.
        assert shell.run_command('wait') == 0
        assert shell.job_manager.count_active_jobs() == 0

        # Unconditional, and about the RESULT: `wc -l` counted all 3 lines.
        with open('pipe_result') as f:
            assert f.read().strip() == '3'


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

        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', ': &\necho done\nwait'],
            capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout == 'done\n'
        assert 'AttributeError' not in result.stderr
        assert '_execute_in_background' not in result.stderr
