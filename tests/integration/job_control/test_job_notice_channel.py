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

import signal
from io import StringIO

from psh.executor.job_control import (
    JobManager,
    JobState,
    background_completion_label,
)


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


def _exited_status(code):
    """Raw waitpid status for a normal exit with the given code."""
    return (code & 0xFF) << 8


def _signaled_status(sig, core=False):
    """Raw waitpid status for death by signal `sig` (optionally with core)."""
    return (sig & 0x7F) | (0x80 if core else 0)


class TestBackgroundCompletionLabel:
    """The bash state label for a completed bg job (R18 M-i3).

    Unlike the FOREGROUND diagnostic (abnormal_termination_message), the
    background notice announces SIGINT but stays silent for SIGPIPE, and it
    splits a normal exit into Done (0) / Exit N. Signal text is libc's
    strsignal (platform-specific — 'Terminated: 15' on macOS, 'Terminated'
    on Linux), so assert against signal.strsignal, not a hard-coded string.
    Pinned to bash 5.2 (tmp/probes-r18t2-interactive/probe_mi3_*).
    """

    def test_exit_zero_is_done(self):
        assert background_completion_label(_exited_status(0)) == "Done"

    def test_none_status_is_done(self):
        # A never-reaped process is treated as a clean Done.
        assert background_completion_label(None) == "Done"

    def test_nonzero_exit_is_exit_n(self):
        assert background_completion_label(_exited_status(3)) == "Exit 3"
        assert background_completion_label(_exited_status(130)) == "Exit 130"

    def test_sigterm_uses_strsignal(self):
        assert (background_completion_label(_signaled_status(signal.SIGTERM))
                == signal.strsignal(signal.SIGTERM))

    def test_sigkill_uses_strsignal(self):
        assert (background_completion_label(_signaled_status(signal.SIGKILL))
                == signal.strsignal(signal.SIGKILL))

    def test_sigint_is_announced_for_background(self):
        # The foreground diagnostic suppresses SIGINT; the bg notice does NOT.
        assert (background_completion_label(_signaled_status(signal.SIGINT))
                == signal.strsignal(signal.SIGINT))

    def test_sigpipe_is_silent(self):
        # bash prints no notice for a SIGPIPE'd bg job.
        assert background_completion_label(_signaled_status(signal.SIGPIPE)) is None

    def test_core_dumped_suffix(self):
        label = background_completion_label(
            _signaled_status(signal.SIGQUIT, core=True))
        assert label == signal.strsignal(signal.SIGQUIT) + " (core dumped)"


class TestCompletionNoticeStates:
    """notify_completed_jobs renders the bash-accurate state word, not
    always 'Done' (R18 M-i3)."""

    def _finished_job(self, jm, status, command="sleep 30"):
        job = _add_background_job(jm, command=command)
        job.processes[0].status = status
        job.processes[0].completed = True
        job.update_state()
        assert job.state == JobState.DONE
        return job

    def test_terminated_notice(self):
        jm, state = _make_manager()
        self._finished_job(jm, _signaled_status(signal.SIGTERM))
        jm.notify_completed_jobs()
        out = state.stderr.getvalue()
        assert f"[1]+  {signal.strsignal(signal.SIGTERM)}" in out
        assert "Done" not in out

    def test_exit_n_notice(self):
        jm, state = _make_manager()
        self._finished_job(jm, _exited_status(3), command="false")
        jm.notify_completed_jobs()
        assert "[1]+  Exit 3" in state.stderr.getvalue()

    def test_sigpipe_notice_is_silent_but_reaped(self):
        jm, state = _make_manager()
        self._finished_job(jm, _signaled_status(signal.SIGPIPE))
        jm.notify_completed_jobs()
        # No line printed, and the job is still removed from the table.
        assert state.stderr.getvalue() == ""
        assert jm.get_job(1) is None

    def test_done_notice_unchanged_for_clean_exit(self):
        jm, state = _make_manager()
        self._finished_job(jm, _exited_status(0))
        jm.notify_completed_jobs()
        assert "[1]+  Done" in state.stderr.getvalue()


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
