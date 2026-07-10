"""
Unit tests for disown builtin.

Tests cover:
- Basic disown functionality
- Disowning specific jobs
- Disown with different options
- Error conditions
- Integration with other job control commands

The ``spawned_pids`` fixture (see ``conftest.py``) guarantees every background
job spawned here is SIGKILLed by EXACT PID on teardown — disowned jobs escape
the ``shell`` fixture's ``_cleanup_shell`` net (they're removed from the job
table), so this is what stops a failed test from orphaning a long-lived
``sleep`` that could wedge the runner later.
"""

import time


class TestDisownBuiltin:
    """Test disown builtin functionality."""

    def test_disown_current_job(self, shell, capsys, spawned_pids):
        """Test disowning the current job."""
        # Start a background job
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Verify job is in list
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert 'sleep' in captured.out
        assert '[1]' in captured.out or '1' in captured.out

        # Disown the current job
        exit_code = shell.run_command('disown')
        assert exit_code == 0

        # Job should no longer appear in jobs list
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert 'sleep' not in captured.out or captured.out.strip() == ""

        # Cleanup: `spawned_pids` fixture SIGKILLs the disowned PID by exact id.

    def test_disown_specific_job(self, shell, capsys, spawned_pids):
        """Test disowning a specific job by job ID."""
        # Start multiple background jobs
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)
        shell.run_command('sleep 40 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Verify both jobs are in list
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert '[1]' in captured.out
        assert '[2]' in captured.out

        # Disown job 1 specifically
        exit_code = shell.run_command('disown %1')
        assert exit_code == 0

        # Job 1 should be gone, job 2 should remain
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert '[1]' not in captured.out or 'sleep 30' not in captured.out
        assert '[2]' in captured.out or 'sleep 40' in captured.out

        # Cleanup: both PIDs (disowned %1 and still-tracked %2) SIGKILLed by
        # exact id in the `spawned_pids` fixture teardown.

    def test_disown_by_pid(self, shell, capsys, spawned_pids):
        """Test disowning a job by process ID."""
        # Start a background job
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Get the PID
        shell.run_command('jobs -p')
        captured = capsys.readouterr()
        pid = captured.out.strip()

        if pid and pid.isdigit():
            # Disown by PID
            exit_code = shell.run_command(f'disown {pid}')
            assert exit_code == 0

            # Job should no longer appear in jobs list
            shell.run_command('jobs')
            captured = capsys.readouterr()
            assert 'sleep' not in captured.out or captured.out.strip() == ""

            # Cleanup: disowned PID SIGKILLed by exact id in the fixture.

    def test_disown_all_jobs(self, shell, capsys, spawned_pids):
        """Test disowning all jobs with -a option."""
        # Start multiple background jobs
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)
        shell.run_command('sleep 40 &')
        spawned_pids.append(shell.state.last_bg_pid)
        shell.run_command('sleep 50 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Verify all jobs are in list
        shell.run_command('jobs')
        captured = capsys.readouterr()
        job_count = captured.out.count('[')
        assert job_count >= 3

        # Disown all jobs
        exit_code = shell.run_command('disown -a')
        assert exit_code == 0

        # No jobs should remain in list
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert captured.out.strip() == "" or 'no jobs' in captured.out.lower()

        # Cleanup: all three disowned PIDs SIGKILLed by exact id in the fixture
        # (never `pkill -f sleep`, which would hit sibling workers' sleeps).

    def test_disown_running_jobs_only(self, shell, capsys, spawned_pids):
        """Test disowning only running jobs with -r option."""
        # Start background jobs
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)
        shell.run_command('sleep 40 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Try to stop one job (this might not work in test environment)
        # For testing purposes, we'll assume both are running

        # Disown only running jobs
        exit_code = shell.run_command('disown -r')
        assert exit_code == 0

        # All running jobs should be disowned
        shell.run_command('jobs')
        capsys.readouterr()
        # Should have no running jobs left

        # Cleanup: disowned PIDs SIGKILLed by exact id in the fixture.

    def test_disown_no_jobs(self, shell, capsys):
        """Test disown when no jobs exist."""
        # Make sure no jobs are running
        shell.run_command('jobs')
        captured = capsys.readouterr()

        if captured.out.strip():
            # Clean up any existing jobs first
            shell.run_command('kill $(jobs -p) 2>/dev/null || true')
            time.sleep(0.1)

        # Try to disown when no jobs
        exit_code = shell.run_command('disown')
        assert exit_code != 0

        captured = capsys.readouterr()
        assert 'no' in captured.err.lower() and 'job' in captured.err.lower()

    def test_disown_invalid_job_spec(self, shell, capsys):
        """Test disown with invalid job specification."""
        exit_code = shell.run_command('disown %999')
        assert exit_code != 0

        captured = capsys.readouterr()
        assert 'no such job' in captured.err.lower() or 'not found' in captured.err.lower()

    def test_disown_invalid_pid(self, shell, capsys):
        """Test disown with invalid process ID."""
        exit_code = shell.run_command('disown 99999')
        assert exit_code != 0

        captured = capsys.readouterr()
        assert 'no such' in captured.err.lower() or 'not found' in captured.err.lower()

    def test_disown_help(self, shell, capsys):
        """Test disown help/usage message."""
        exit_code = shell.run_command('disown --help')
        # May or may not be implemented

        captured = capsys.readouterr()
        if exit_code == 0:
            assert 'disown' in captured.out.lower()


class TestDisownOptions:
    """Test disown command options."""

    def test_disown_with_h_option(self, shell, capsys, spawned_pids):
        """Test disown -h to mark job for no SIGHUP."""
        # Start a background job
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Mark job to ignore SIGHUP but keep in job table
        exit_code = shell.run_command('disown -h %1')
        assert exit_code == 0

        # Job should still appear in jobs list (with -h it's not removed)
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert 'sleep' in captured.out

        # Cleanup: PID SIGKILLed by exact id in the fixture (with -h the job
        # stays in the table, but exact-PID cleanup is used uniformly).

    def test_disown_list_jobs(self, shell, capsys, spawned_pids):
        """Test disown with no arguments lists current jobs."""
        # Start some background jobs
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)
        shell.run_command('sleep 40 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # In some shells, disown with no args might list jobs
        # This behavior varies between shells
        shell.run_command('disown')
        capsys.readouterr()

        # Cleanup: both PIDs SIGKILLed by exact id in the fixture.


class TestDisownIntegration:
    """Test disown integration with other job control features."""

    def test_disown_then_fg_fails(self, shell, capsys, spawned_pids):
        """Test that fg fails on disowned job.

        Under `set -m` (job control on) the fg jobspec gate is passed and bash
        reports `%1: no such job` — proving disown actually removed the job.
        (Without monitor, fg reports `no job control` first, before resolution,
        which would not prove the job is gone; bash-verified 5.2.26.)
        """
        # Enable job control so fg resolves the jobspec instead of short-circuiting
        # on the "no job control" gate.
        shell.run_command('set -m')

        # Start background job
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Get job number
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert '[1]' in captured.out

        # Disown the job
        shell.run_command('disown %1')

        # Try to foreground the disowned job
        exit_code = shell.run_command('fg %1')
        assert exit_code != 0

        captured = capsys.readouterr()
        assert 'no such job' in captured.err.lower()

        # Cleanup: disowned PID SIGKILLed by exact id in the fixture.

    def test_disown_then_bg_fails(self, shell, capsys, spawned_pids):
        """Test that bg fails on disowned job (see test_disown_then_fg_fails)."""
        # Enable job control so bg resolves the jobspec (bash-verified: `%1: no
        # such job` under set -m; `no job control` gate fires first otherwise).
        shell.run_command('set -m')

        # Start background job
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Disown the job
        shell.run_command('disown %1')

        # Try to background the disowned job
        exit_code = shell.run_command('bg %1')
        assert exit_code != 0

        captured = capsys.readouterr()
        assert 'no such job' in captured.err.lower()

        # Cleanup: disowned PID SIGKILLed by exact id in the fixture.

    def test_disown_then_kill_fails(self, shell, capsys, spawned_pids):
        """Test that kill %job fails on disowned job."""
        # Start background job
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Disown the job
        shell.run_command('disown %1')

        # Try to kill by job spec (should fail)
        exit_code = shell.run_command('kill %1')
        assert exit_code != 0

        # Cleanup: disowned PID SIGKILLed by exact id in the fixture.

    def test_disown_job_exit_no_notification(self, shell, capsys, spawned_pids):
        """Test disowned job exit doesn't generate notification."""
        # Start a short-lived background job
        shell.run_command('(sleep 0.5; exit 0) &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Disown it immediately
        shell.run_command('disown %1')

        # Clear any output from job start notification
        capsys.readouterr()

        # Wait for job to complete
        time.sleep(1)

        # Run another command to potentially trigger notifications
        shell.run_command('echo "test"')
        captured = capsys.readouterr()

        # Should not see job completion notification
        assert 'Done' not in captured.out
        assert 'Exit' not in captured.out
        assert captured.out.strip() == "test"


class TestDisownErrorCases:
    """Test disown error handling."""

    def test_disown_invalid_option(self, shell, capsys):
        """Test disown with invalid option."""
        exit_code = shell.run_command('disown -z')
        assert exit_code != 0

        captured = capsys.readouterr()
        assert 'invalid option' in captured.err.lower() or 'unknown option' in captured.err.lower()

    def test_disown_mixed_valid_invalid_jobs(self, shell, capsys, spawned_pids):
        """Test disown with mix of valid and invalid job specs."""
        # Start one job
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Try to disown valid and invalid jobs
        shell.run_command('disown %1 %999')

        # Behavior may vary - some shells continue with valid ones
        capsys.readouterr()

        # Cleanup: PID SIGKILLed by exact id in the fixture.

    def test_disown_completed_job(self, shell, capsys, spawned_pids):
        """Test disowning an already completed job."""
        # Start a quick job
        shell.run_command('(sleep 0.1; exit 0) &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Wait for it to complete
        time.sleep(0.2)

        # Try to disown the completed job
        shell.run_command('disown %1')

        # Behavior may vary - some shells allow this, others don't
        capsys.readouterr()


class TestDisownBashCompatibility:
    """Test bash-compatible disown behavior."""

    def test_disown_job_spec_formats(self, shell, capsys, spawned_pids):
        """Test various job specification formats."""
        # Start multiple jobs
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)
        shell.run_command('sleep 40 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Test different job spec formats
        formats = ['%1', '%+', '%-']  # current, most recent, previous

        for fmt in formats:
            # Check if job exists before trying to disown
            shell.run_command('jobs')
            captured = capsys.readouterr()

            if '[1]' in captured.out or '[2]' in captured.out:
                exit_code = shell.run_command(f'disown {fmt}')
                # Should succeed for valid job specs
                if fmt in ['%1', '%+'] and '[1]' in captured.out:
                    assert exit_code == 0

        # Cleanup: both PIDs SIGKILLed by exact id in the fixture.

    def test_disown_preserves_exit_status(self, shell, capsys, spawned_pids):
        """Test disown doesn't change shell exit status inappropriately."""
        # Get current exit status
        shell.run_command('echo $?')
        captured = capsys.readouterr()
        captured.out.strip()

        # Start and disown a job
        shell.run_command('sleep 30 &')
        spawned_pids.append(shell.state.last_bg_pid)
        shell.run_command('disown %1')

        # Clear output from job start notification
        capsys.readouterr()

        # Exit status should still reflect last command success
        shell.run_command('echo $?')
        captured = capsys.readouterr()
        final_status = captured.out.strip()

        # Disown success should give exit status 0
        assert final_status == "0"

        # Cleanup: disowned PID SIGKILLed by exact id in the fixture.


class TestDisownRealWorldUsage:
    """Test real-world disown usage patterns."""

    def test_disown_long_running_process(self, shell, capsys, spawned_pids):
        """Test disowning a long-running process."""
        # Start a long-running background process
        shell.run_command('sleep 300 &')
        spawned_pids.append(shell.state.last_bg_pid)

        # Verify it's in the job list
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert 'sleep 300' in captured.out

        # Disown it (common pattern for detaching processes)
        exit_code = shell.run_command('disown %1')
        assert exit_code == 0

        # Process should continue running but not be in job list
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert 'sleep 300' not in captured.out

        # Process should still be running in the system
        shell.run_command('pgrep -f "sleep 300"')
        captured = capsys.readouterr()
        # Should find the process

        # Cleanup: the disowned `sleep 300` (the exact orphan hazard flagged in
        # the appraisal) is SIGKILLed by exact PID in the fixture teardown,
        # which runs even if an assertion above fails.

    def test_disown_before_shell_exit(self, shell, capsys, spawned_pids):
        """Test disowning jobs before shell exit (common pattern)."""
        # Start several background jobs
        jobs = ['sleep 120', 'sleep 130', 'sleep 140']
        for job in jobs:
            shell.run_command(f'{job} &')
            spawned_pids.append(shell.state.last_bg_pid)

        # Verify all jobs are active
        shell.run_command('jobs')
        captured = capsys.readouterr()
        for job in jobs:
            assert job.split()[1] in captured.out  # sleep duration

        # Disown all jobs (pattern used before exiting shell)
        shell.run_command('disown -a')

        # Job list should be empty
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert captured.out.strip() == "" or 'no jobs' in captured.out.lower()

        # Cleanup: all three disowned PIDs SIGKILLed by exact id in the fixture.
