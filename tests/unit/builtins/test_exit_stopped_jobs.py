"""The stopped-jobs exit guard (reappraisal #17 M3).

bash exit.def semantics, PTY-probed (tmp/probes-r17t2-interactive/
probe_stopped_jobs2.py): an interactive `exit` (or Ctrl-D) with stopped
jobs prints "There are stopped jobs." and is blocked with $?=1; a second
consecutive attempt proceeds; any command in between re-arms the guard —
EXCEPT `jobs`, which instead exempts the next attempt outright (bash's
`last_shell_builtin == jobs_builtin`: the user just looked at the job
table, so `jobs` then `exit` exits with no warning at all). Blank lines
and pure assignments neither re-arm nor clear the exemption. `exit` in
a SOURCED file bypasses the guard entirely (bash skips the check while
sourcing), and running (non-stopped) background jobs never warn.

The REPL-side plumbing (Ctrl-D path, re-arming after a command) is
exercised by the PTY tier (tests/system/interactive/test_pty_smoke.py
TestPtyExitPolicy); these tests pin the chokepoint itself.
"""

import pytest

from psh.executor.job_control import JobState


def stop_a_fake_job(shell, pgid=999_999, command='sleep 40'):
    """Plant a STOPPED job in the job table (no real process needed)."""
    job = shell.job_manager.create_job(pgid, command)
    job.state = JobState.STOPPED
    job.notified = True  # keep notify_stopped_jobs quiet
    return job


@pytest.fixture
def interactive_shell(captured_shell):
    captured_shell.state.options['interactive'] = True
    yield captured_shell
    # Fake jobs have no processes; drop them so teardown has nothing to kill.
    captured_shell.job_manager.jobs.clear()


class TestExitBuiltinGuard:
    def test_first_exit_blocked_with_warning(self, interactive_shell):
        shell = interactive_shell
        stop_a_fake_job(shell)
        rc = shell.run_command("exit")
        assert rc == 1
        assert "There are stopped jobs." in shell.get_stderr()
        assert shell.state.last_exit_code == 1  # bash: EXECUTION_FAILURE

    def test_second_consecutive_exit_proceeds(self, interactive_shell):
        shell = interactive_shell
        stop_a_fake_job(shell)
        assert shell.run_command("exit") == 1
        with pytest.raises(SystemExit):
            shell.run_command("exit")

    def test_warning_printed_once_per_arm(self, interactive_shell):
        shell = interactive_shell
        stop_a_fake_job(shell)
        shell.run_command("exit")
        assert shell.get_stderr().count("There are stopped jobs.") == 1

    def test_rearmed_guard_warns_again(self, interactive_shell):
        shell = interactive_shell
        stop_a_fake_job(shell)
        assert shell.run_command("exit") == 1
        # The REPL re-arms after an intervening command; simulate it.
        shell.job_manager.clear_exit_warning()
        assert shell.run_command("exit") == 1
        assert shell.get_stderr().count("There are stopped jobs.") == 2

    def test_no_stopped_jobs_exits_directly(self, interactive_shell):
        with pytest.raises(SystemExit):
            interactive_shell.run_command("exit")

    def test_running_job_does_not_warn(self, interactive_shell):
        shell = interactive_shell
        job = shell.job_manager.create_job(999_998, 'sleep 40')
        job.state = JobState.RUNNING
        job.notified = True
        with pytest.raises(SystemExit):
            shell.run_command("exit")
        assert "There are stopped jobs." not in shell.get_stderr()

    def test_non_interactive_never_warns(self, captured_shell):
        # Script-mode shells exit straight through (bash checks
        # `interactive` before the jobs scan).
        shell = captured_shell
        stop_a_fake_job(shell)
        try:
            with pytest.raises(SystemExit):
                shell.run_command("exit")
            assert "There are stopped jobs." not in shell.get_stderr()
        finally:
            shell.job_manager.jobs.clear()

    def test_blocked_exit_skips_exit_trap(self, interactive_shell):
        # The EXIT trap must only fire when the shell really exits.
        shell = interactive_shell
        stop_a_fake_job(shell)
        shell.run_command("trap 'echo TRAPPED' EXIT")
        assert shell.run_command("exit") == 1
        assert "TRAPPED" not in shell.get_stdout()


class TestJobsBuiltinExemption:
    """`jobs` as the immediately preceding command disarms the guard
    (bash: `jobs` then `exit`/Ctrl-D exits with no warning at all)."""

    def test_jobs_then_exit_exits_without_warning(self, interactive_shell):
        shell = interactive_shell
        stop_a_fake_job(shell)
        shell.run_command("jobs")
        with pytest.raises(SystemExit):
            shell.run_command("exit")
        assert "There are stopped jobs." not in shell.get_stderr()

    def test_warned_then_jobs_then_exit_exits(self, interactive_shell):
        shell = interactive_shell
        stop_a_fake_job(shell)
        assert shell.run_command("exit") == 1
        shell.run_command("jobs")
        with pytest.raises(SystemExit):
            shell.run_command("exit")

    def test_jobs_then_other_command_warns_again(self, interactive_shell):
        shell = interactive_shell
        stop_a_fake_job(shell)
        shell.run_command("jobs")
        shell.run_command("true")   # clears the exemption (bash)
        assert shell.run_command("exit") == 1
        assert "There are stopped jobs." in shell.get_stderr()

    def test_pure_assignment_keeps_exemption(self, interactive_shell):
        # bash: assignments run no command word — no shift, `jobs` stays
        # the last command.
        shell = interactive_shell
        stop_a_fake_job(shell)
        shell.run_command("jobs")
        shell.run_command("x=1")
        with pytest.raises(SystemExit):
            shell.run_command("exit")


class TestSourcedExitBypass:
    """bash skips the stopped-jobs check for `exit` while sourcing."""

    def test_sourced_exit_bypasses_guard(self, interactive_shell, tmp_path):
        shell = interactive_shell
        stop_a_fake_job(shell)
        script = tmp_path / "leave.sh"
        script.write_text("exit\n")
        with pytest.raises(SystemExit):
            shell.run_command(f"source {script}")
        assert "There are stopped jobs." not in shell.get_stderr()

    def test_source_depth_passes_chokepoint(self, interactive_shell):
        jm = interactive_shell.job_manager
        stop_a_fake_job(interactive_shell)
        interactive_shell.state.source_depth = 1
        try:
            assert jm.confirm_exit_with_stopped_jobs() is True
        finally:
            interactive_shell.state.source_depth = 0
        assert jm.confirm_exit_with_stopped_jobs() is False  # warns normally


class TestChokepointDirect:
    """The shared chokepoint used by both exit and the REPL EOF path."""

    def test_confirm_blocks_then_allows(self, interactive_shell):
        jm = interactive_shell.job_manager
        stop_a_fake_job(interactive_shell)
        assert jm.confirm_exit_with_stopped_jobs() is False
        assert jm.exit_warning_pending is True
        # Second consecutive attempt (exit OR Ctrl-D) proceeds.
        assert jm.confirm_exit_with_stopped_jobs() is True

    def test_clear_exit_warning_rearms(self, interactive_shell):
        jm = interactive_shell.job_manager
        stop_a_fake_job(interactive_shell)
        assert jm.confirm_exit_with_stopped_jobs() is False
        jm.clear_exit_warning()
        assert jm.exit_warning_pending is False
        assert jm.confirm_exit_with_stopped_jobs() is False  # warns again

    def test_has_stopped_jobs(self, interactive_shell):
        jm = interactive_shell.job_manager
        assert jm.has_stopped_jobs() is False
        job = stop_a_fake_job(interactive_shell)
        assert jm.has_stopped_jobs() is True
        job.state = JobState.RUNNING
        assert jm.has_stopped_jobs() is False

    def test_note_simple_command_shift_register(self, interactive_shell):
        # bash last/this_shell_builtin: the guard reads the LAST slot —
        # `jobs` exempts while it is the previous command, and is
        # cleared by the next shift (function/external = None).
        jm = interactive_shell.job_manager
        stop_a_fake_job(interactive_shell)
        jm.note_simple_command('jobs')
        jm.note_simple_command('exit')   # the exit builtin's own shift
        assert jm.confirm_exit_with_stopped_jobs() is True
        jm.note_simple_command(None)     # an external/function ran
        jm.note_simple_command('exit')
        assert jm.confirm_exit_with_stopped_jobs() is False  # warns
