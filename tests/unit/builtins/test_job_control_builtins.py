"""
Unit tests for job control builtins (jobs, fg, bg).

Tests cover:
- Listing jobs
- Foreground/background job control
- Job state transitions
- Error conditions

Note: Many job control features require interactive terminal,
so some tests may need to be marked as xfail.
"""



class TestJobsBuiltin:
    """Test jobs builtin functionality."""

    def test_jobs_empty_list(self, shell, capsys):
        """Test jobs with no background jobs."""
        shell.run_command('jobs')
        captured = capsys.readouterr()
        # Should have no output or minimal output
        assert captured.out.strip() == "" or "no jobs" in captured.out.lower()

    def test_jobs_with_background_job(self, shell, capsys):
        """Test jobs with a background job."""
        # Start a background job
        shell.run_command('sleep 10 &')

        # List jobs
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert 'sleep' in captured.out
        assert '&' in captured.out or 'Running' in captured.out

        # Clean up
        shell.run_command('kill %1 2>/dev/null || true')

    def test_jobs_multiple_background(self, shell, capsys):
        """Test jobs with multiple background jobs."""
        # Start multiple background jobs
        shell.run_command('sleep 10 &')
        shell.run_command('sleep 20 &')

        # List jobs
        shell.run_command('jobs')
        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')
        assert len(lines) >= 2
        assert '[1]' in captured.out
        assert '[2]' in captured.out

        # Clean up
        shell.run_command('kill %1 %2 2>/dev/null || true')

    def test_jobs_with_options(self, shell, capsys):
        """Test jobs with various options."""
        shell.run_command('sleep 10 &')

        # Test -l (long format with PIDs)
        shell.run_command('jobs -l')
        captured = capsys.readouterr()
        # Should show PID
        assert any(char.isdigit() for char in captured.out)

        # Test -p (PIDs only)
        shell.run_command('jobs -p')
        captured = capsys.readouterr()
        # Should be just numbers
        assert captured.out.strip().isdigit()

        # Clean up
        shell.run_command('kill %1 2>/dev/null || true')

    def test_jobs_l_pid_column(self, shell, capsys):
        """jobs -l adds the PID column (bash: `[1]+ 12345 Running  cmd &`)."""
        import re
        shell.run_command('sleep 10 &')
        shell.run_command('jobs -l')
        captured = capsys.readouterr()
        # bash format: [N]marker space PID space State ... command &
        assert re.search(r'^\[1\]\+ \d+ Running\s+sleep 10 &$', captured.out, re.M)

        # -p wins over -l (bash): only PIDs
        shell.run_command('jobs -lp')
        captured = capsys.readouterr()
        assert captured.out.strip().isdigit()

    def test_jobs_invalid_option_is_usage_error(self, shell, capsys):
        """jobs with invalid option: rc 2 + usage, like bash."""
        rc = shell.run_command('jobs -z')
        captured = capsys.readouterr()
        assert rc == 2
        assert 'invalid option' in captured.err
        assert 'usage:' in captured.err

    def test_disown_job(self, shell, capsys):
        """Test disowning a job."""
        # Start a background job
        shell.run_command('sleep 10 &')

        # Try to disown it
        exit_code = shell.run_command('disown %1')
        assert exit_code == 0

        # Job should not appear in jobs list
        shell.run_command('jobs')
        captured = capsys.readouterr()
        assert 'sleep' not in captured.out

        # Clean up (kill by searching process)
        shell.run_command('pkill -f "sleep 10" 2>/dev/null || true')
