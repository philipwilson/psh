"""A foreground job stopped by Ctrl-Z becomes the current job (%+).

When a foreground job is stopped (SIGTSTP), bash keeps it as the CURRENT job
(``%+``) so a bare ``fg``/``bg`` resumes it. psh's foreground teardown called
``set_foreground_job(None)``, which demoted the still-current stopped job to
``%-`` and cleared ``%+`` — so ``[1]+`` printed as ``[1]-`` and bare ``fg``/
``bg`` failed with ``%+: no such job`` (appraisal 2026-06-21, finding H9).

``finish_foreground_job`` now re-promotes a stopped job to ``%+`` (keeping the
job that was current before it as ``%-``). These tests drive the bookkeeping
directly — deterministic, no real SIGTSTP needed.
"""

from io import StringIO

from psh.executor.job_control import JobManager, JobState


class _FakeState:
    def __init__(self):
        self.options = {'interactive': False, 'notify': False}
        self.stdout = StringIO()
        self.stderr = StringIO()
        self.last_bg_pid = None
        self.foreground_pgid = None


def _manager():
    jm = JobManager()
    jm.set_shell_state(_FakeState())
    return jm


def _foreground_job(jm, pid, command):
    """Create a job and run it as the foreground job (current_job)."""
    job = jm.create_job(pid, command)
    job.add_process(pid, command)
    job.foreground = True
    jm.set_foreground_job(job)
    return job


def _background_job(jm, pid, command):
    """Create a job and register it as a running background job (becomes %+)."""
    job = jm.create_job(pid, command)
    job.add_process(pid, command)
    jm.register_background_job(job, shell_state=jm.shell_state, last_pid=pid)
    return job


def _run_foreground_command(jm, pid, command):
    """Drive the external/pipeline foreground path for a command that COMPLETES.

    Mirrors ExternalCommandStrategy: create_job + set_foreground_job +
    finish_foreground_job + remove_job, with the terminal never transferred
    (as under a non-tty / pytest). A completing foreground command must leave
    the %+/%- rotation untouched.
    """
    job = _foreground_job(jm, pid, command)
    job.update_process_status(pid, 0)  # WIFEXITED, code 0
    job.update_state()
    assert job.state == JobState.DONE
    jm.finish_foreground_job(terminal_transferred=False, job=job)
    jm.remove_job(job.job_id)


def _stop(job):
    # 0x7f is a WIFSTOPPED waitpid status; route it through the counter-aware
    # update_process_status rather than poking the (now read-only) flag.
    job.update_process_status(job.processes[0].pid, 0x7f)
    job.update_state()
    assert job.state == JobState.STOPPED


def test_stopped_foreground_job_is_current():
    jm = _manager()
    job = _foreground_job(jm, 111, "sleep 30")
    _stop(job)

    jm.finish_foreground_job(terminal_transferred=False, job=job)

    assert jm.current_job is job          # %+ is the stopped job
    assert jm.previous_job is None
    # Bare `fg`/`bg` (and %+) resolve to it.
    assert jm.parse_job_spec('') is job
    assert jm.parse_job_spec('%+') is job


def test_stopped_job_notice_shows_plus_marker():
    jm = _manager()
    job = _foreground_job(jm, 222, "cat")
    _stop(job)
    jm.finish_foreground_job(terminal_transferred=False, job=job)

    jm.notify_stopped_jobs()
    notice = jm.shell_state.stderr.getvalue()
    assert "[1]+" in notice and "Stopped" in notice


def test_second_stopped_job_demotes_first_to_previous():
    jm = _manager()
    first = _foreground_job(jm, 333, "sleep 30")
    _stop(first)
    jm.finish_foreground_job(terminal_transferred=False, job=first)
    assert jm.current_job is first

    second = _foreground_job(jm, 444, "sleep 40")
    _stop(second)
    jm.finish_foreground_job(terminal_transferred=False, job=second)

    assert jm.current_job is second       # newest stopped → %+
    assert jm.previous_job is first       # prior current → %-
    assert jm.parse_job_spec('%+') is second
    assert jm.parse_job_spec('%-') is first


def test_completed_foreground_job_does_not_become_current():
    jm = _manager()
    job = _foreground_job(jm, 555, "true")
    job.update_process_status(job.processes[0].pid, 0)  # WIFEXITED, code 0
    job.update_state()
    assert job.state == JobState.DONE

    jm.finish_foreground_job(terminal_transferred=False, job=job)
    # A completed job is not the current job (it will be removed by the caller).
    assert jm.current_job is None


# ---------------------------------------------------------------------------
# A foreground command must NOT clobber a running BACKGROUND job's %+.
#
# bash keeps a background job as %+ across intervening foreground commands
# (probe: `sleep 30 & /usr/bin/true; jobs` -> `[1]+`, and `kill %+` targets
# it). psh's finish_foreground_job -> set_foreground_job(None) used to steal
# %+ from the bg job and leave it as None/%-, so `jobs` showed a blank marker
# and `kill %+`/`wait %+`/bare `fg`/`bg` failed with "%+: no such job"
# (task #24). set_foreground_job no longer touches the rotation.
# ---------------------------------------------------------------------------

def test_foreground_command_preserves_background_current_job():
    jm = _manager()
    bg = _background_job(jm, 1000, "sleep 30")
    assert jm.current_job is bg                       # bg job is %+

    _run_foreground_command(jm, 2000, "true")

    assert jm.current_job is bg                       # still %+ after fg cmd
    assert jm.previous_job is None
    assert jm.parse_job_spec('%+') is bg              # kill/wait/fg %+ target it
    assert jm.parse_job_spec('%%') is bg
    assert jm.parse_job_spec('') is bg                # bare fg/bg


def test_foreground_command_preserves_both_background_markers():
    jm = _manager()
    first = _background_job(jm, 1000, "sleep 30")     # job 1
    second = _background_job(jm, 1001, "sleep 31")    # job 2 -> %+, job 1 -> %-
    assert jm.current_job is second and jm.previous_job is first

    _run_foreground_command(jm, 2000, "true")

    assert jm.current_job is second                   # %+ unchanged
    assert jm.previous_job is first                   # %- unchanged
    assert jm.parse_job_spec('%+') is second
    assert jm.parse_job_spec('%-') is first


def test_many_foreground_commands_preserve_background_current_job():
    jm = _manager()
    bg = _background_job(jm, 1000, "sleep 30")
    for pid in (2000, 2001, 2002):
        _run_foreground_command(jm, pid, "true")
    assert jm.current_job is bg
    assert jm.parse_job_spec('%+') is bg


def test_stopped_foreground_job_demotes_background_to_previous():
    # bash's stopped-job priority even with a running bg job: a newly stopped
    # foreground job becomes %+, demoting the running bg job to %-.
    jm = _manager()
    bg = _background_job(jm, 1000, "sleep 30")
    fg = _foreground_job(jm, 2000, "cat")
    _stop(fg)
    jm.finish_foreground_job(terminal_transferred=False, job=fg)

    assert jm.current_job is fg                        # newly stopped -> %+
    assert jm.previous_job is bg                       # running bg -> %-


def test_notice_marker_plus_for_current_bg_job():
    # A single (current) background job's Done notice shows '+'.
    jm = _manager()
    bg = _background_job(jm, 1000, "sleep 0.1")
    bg.update_process_status(1000, 0)
    bg.update_state()
    jm.notify_completed_jobs()
    assert "[1]+  Done" in jm.shell_state.stderr.getvalue()


def test_notice_marker_space_for_noncurrent_bg_job():
    # A non-current bg job completing while another is %+ shows a SPACE marker
    # (never '-') — PTY-pinned vs bash 5.2.26.
    jm = _manager()
    first = _background_job(jm, 1000, "sleep 0.1")    # job 1
    _background_job(jm, 1001, "sleep 30")             # job 2 -> %+, job 1 -> %-
    first.update_process_status(1000, 0)
    first.update_state()
    jm.notify_completed_jobs()
    out = jm.shell_state.stderr.getvalue()
    assert "[1]   Done" in out                        # three spaces, not '-'
    assert "[1]-" not in out
