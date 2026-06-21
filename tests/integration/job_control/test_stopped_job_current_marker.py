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


def _stop(job):
    job.processes[0].stopped = True
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
    job.processes[0].completed = True
    job.update_state()
    assert job.state == JobState.DONE

    jm.finish_foreground_job(terminal_transferred=False, job=job)
    # A completed job is not the current job (it will be removed by the caller).
    assert jm.current_job is None
