"""Job.update_state classifies mixed completed/stopped pipelines (executor F10).

`Job.update_state` used to mark a job STOPPED only when EVERY process was
stopped. A completed process has stopped=False, so a pipeline with one
completed member and one stopped member was classified RUNNING even though
none of its live processes was running. The rule is now:

    all completed              -> DONE
    every non-completed stopped -> STOPPED
    else                        -> RUNNING
"""

from psh.executor.job_control import Job, JobState


def _job(*states):
    """Build a Job whose processes have the given (completed, stopped) flags.

    States are applied through update_process_status with real waitpid statuses
    (0 == WIFEXITED code 0; 0x7f == WIFSTOPPED) so the per-state counters stay
    exact — `completed`/`stopped` are read-only properties of ProcessState now.
    """
    job = Job(1, 1000, "pipeline")
    for i, (completed, stopped) in enumerate(states):
        job.add_process(100 + i, f"p{i}")
        if completed:
            job.update_process_status(100 + i, 0)
        elif stopped:
            job.update_process_status(100 + i, 0x7f)
        # else: leave RUNNING (the state after add_process)
    return job


def test_completed_plus_stopped_is_stopped():
    # The headline F10 fix: one member finished, one stopped -> STOPPED.
    job = _job((True, False), (False, True))
    job.update_state()
    assert job.state == JobState.STOPPED


def test_all_completed_is_done():
    job = _job((True, False), (True, False))
    job.update_state()
    assert job.state == JobState.DONE


def test_all_stopped_is_stopped():
    job = _job((False, True), (False, True))
    job.update_state()
    assert job.state == JobState.STOPPED


def test_running_plus_stopped_is_running():
    job = _job((False, False), (False, True))
    job.update_state()
    assert job.state == JobState.RUNNING


def test_running_plus_completed_is_running():
    job = _job((False, False), (True, False))
    job.update_state()
    assert job.state == JobState.RUNNING


def test_single_completed_is_done():
    job = _job((True, False))
    job.update_state()
    assert job.state == JobState.DONE


def test_single_stopped_is_stopped():
    job = _job((False, True))
    job.update_state()
    assert job.state == JobState.STOPPED
