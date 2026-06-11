"""Job-state notification channel tests (error-channel unification).

Bash writes ALL asynchronous job notices to the shell's stderr, never
stdout — probed with bash 5.2 under a pty with the shell's own fd 1/2
redirected to a file:

    fd 1 -> file:  file empty, pty shows "[1] PID" and "[1]+  Done ..."
    fd 2 -> file:  file holds both notices, pty empty

psh used bare print() (stdout) for the Done/Stopped notices until this
was unified onto the state stderr stream (the "[N] PID" launch notice
moved in v0.276). The `jobs` BUILTIN's listing is command output and
stays on stdout — these tests cover only asynchronous notifications.
"""

from io import StringIO

from psh.executor.job_control import JobManager, JobState


class _FakeState:
    """Minimal shell-state stand-in: options + stdio streams."""

    def __init__(self, interactive=False, notify=False):
        self.options = {'interactive': interactive, 'notify': notify}
        self.stdout = StringIO()
        self.stderr = StringIO()
        self.last_bg_pid = None


def _make_manager(**state_kwargs):
    jm = JobManager()
    state = _FakeState(**state_kwargs)
    jm.set_shell_state(state)
    return jm, state


def _add_background_job(jm, pid=12345, command="sleep 0.1"):
    job = jm.create_job(pid, command)
    job.add_process(pid, command)
    job.foreground = False
    return job


class TestNotificationStream:
    """JobManager notices must go to the state's stderr, not stdout."""

    def test_done_notice_on_stderr(self, capsys):
        jm, state = _make_manager()
        job = _add_background_job(jm)
        job.processes[0].completed = True
        job.update_state()
        assert job.state == JobState.DONE

        jm.notify_completed_jobs()

        assert "[1]+  Done" in state.stderr.getvalue()
        assert "sleep 0.1" in state.stderr.getvalue()
        assert state.stdout.getvalue() == ""
        # Nothing leaked to the process-level streams either
        captured = capsys.readouterr()
        assert "Done" not in captured.out

    def test_stopped_notice_on_stderr(self, capsys):
        jm, state = _make_manager()
        job = _add_background_job(jm, command="cat")
        job.processes[0].stopped = True
        job.update_state()
        assert job.state == JobState.STOPPED

        jm.notify_stopped_jobs()

        assert "Stopped" in state.stderr.getvalue()
        assert state.stdout.getvalue() == ""
        captured = capsys.readouterr()
        assert "Stopped" not in captured.out

    def test_launch_notice_on_stderr_when_interactive(self):
        jm, state = _make_manager(interactive=True)
        jm.launch_background(4242, "sleep 5", [(4242, "sleep 5")])

        assert "[1] 4242" in state.stderr.getvalue()
        assert state.stdout.getvalue() == ""

    def test_no_launch_notice_when_not_interactive(self):
        jm, state = _make_manager(interactive=False)
        jm.launch_background(4242, "sleep 5", [(4242, "sleep 5")])

        assert state.stderr.getvalue() == ""
        assert state.stdout.getvalue() == ""


class TestNotifyOptionChannel:
    """set -b (notify) immediate Done notices use stderr end to end."""

    def test_set_b_done_notice_on_stderr(self, captured_shell):
        rc = captured_shell.run_command("set -b; sleep 0.05 & wait")
        assert rc == 0
        assert "Done" in captured_shell.get_stderr()
        assert "sleep 0.05" in captured_shell.get_stderr()
        assert "Done" not in captured_shell.get_stdout()

    def test_jobs_builtin_listing_stays_on_stdout(self, captured_shell):
        """The jobs BUILTIN is command output, not a notification."""
        captured_shell.run_command("sleep 0.3 &")
        captured_shell.clear_output()
        rc = captured_shell.run_command("jobs")
        assert rc == 0
        assert "sleep 0.3" in captured_shell.get_stdout()
        assert "sleep 0.3" not in captured_shell.get_stderr()
        captured_shell.run_command("wait")
