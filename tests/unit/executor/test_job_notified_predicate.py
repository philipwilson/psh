"""The F4 `notified` predicate: cleared on any real state transition.

`Job.notified` is the single source of truth for bash's J_NOTIFIED flag — "the
user has seen the job's current status". It is SET when a job is displayed by
`jobs` / reported by an async notice, and CLEARED by `Job.update_state` the
moment the state actually changes, so a stop / continue / completion is
announced (or shown by `jobs -n`) exactly once. These unit tests pin the
clear-on-transition contract directly (no processes needed).
"""

import os
import signal

from psh.executor.job_control import JobManager, JobState


def _exited(code: int) -> int:
    """A raw waitpid status for a normal exit with the given code."""
    return code << 8


def _stopped(sig: int = signal.SIGSTOP) -> int:
    """A raw waitpid status for a stop by the given signal."""
    return (sig << 8) | 0x7f


def _running_job(pid: int = 4321):
    jm = JobManager()
    job = jm.create_job(pid, "sleep 5")
    job.add_process(pid, "sleep 5")
    return jm, job


def test_running_to_stopped_clears_notified():
    _jm, job = _running_job()
    job.notified = True
    job.update_process_status(job.processes[0].pid, _stopped())
    job.update_state()
    assert job.state == JobState.STOPPED
    assert job.notified is False


def test_running_to_done_clears_notified():
    _jm, job = _running_job()
    job.notified = True
    job.update_process_status(job.processes[0].pid, _exited(0))
    job.update_state()
    assert job.state == JobState.DONE
    assert job.notified is False


def test_stopped_to_running_clears_notified():
    _jm, job = _running_job()
    # Stop it, mark the user notified of the stop.
    job.update_process_status(job.processes[0].pid, _stopped())
    job.update_state()
    assert job.state == JobState.STOPPED
    job.notified = True
    # Continue it (WIFCONTINUED leaves status untouched, state -> RUNNING).
    if not hasattr(os, "WIFCONTINUED"):
        return
    job.mark_running()          # STOPPED procs -> RUNNING (the fg/bg resume path)
    job.update_state()
    assert job.state == JobState.RUNNING
    assert job.notified is False


def test_no_transition_keeps_notified():
    """An update_state that does NOT change the state leaves notified set —
    a job already reported at its current status is not re-reported."""
    _jm, job = _running_job()
    job.notified = True
    job.update_state()          # still RUNNING: no transition
    assert job.state == JobState.RUNNING
    assert job.notified is True
