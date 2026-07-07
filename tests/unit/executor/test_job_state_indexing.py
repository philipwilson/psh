"""JobManager pid-index + per-state counters are O(1) (campaign item 6).

The old status-processing path scanned every process of a job on each event
(get_job_by_pid, update_process_status, update_state), so handling N events for
an N-stage pipeline was O(N^2). This pins that the hot paths no longer scan the
process list: a job's processes are wrapped in a list that counts iterations,
and processing a status event for each of 200 members must perform ZERO full
scans. Pure in-process, no child processes.
"""

from psh.executor.job_control import JobManager, JobState, ProcessState


class _CountingList(list):
    """A list that counts how many times it is fully iterated."""

    def __init__(self, *args):
        super().__init__(*args)
        self.iter_count = 0

    def __iter__(self):
        self.iter_count += 1
        return super().__iter__()


def _build_job(jm: JobManager, n: int):
    job = jm.create_job(pgid=100000, command=" | ".join("c" for _ in range(n)))
    for k in range(n):
        job.add_process(100000 + k, "c")
    return job


def test_status_processing_does_not_scan_the_process_list():
    n = 200
    jm = JobManager()
    job = _build_job(jm, n)
    # Instrument AFTER building; _pid_index already maps pid -> index.
    job.processes = _CountingList(job.processes)

    for k in range(n):
        # status 0 == WIFEXITED with code 0.
        job.update_process_status(100000 + k, 0)
        job.update_state()
        assert jm.get_job_by_pid(100000 + k) is job  # O(1) dict lookup

    # None of get_job_by_pid / update_process_status / update_state iterated
    # the full process list — the whole point of the pid index + counters.
    assert job.processes.iter_count == 0
    assert job.state is JobState.DONE
    assert job._counts[ProcessState.COMPLETED] == n
    assert job._counts[ProcessState.RUNNING] == 0


def test_counters_track_mixed_transitions():
    jm = JobManager()
    job = _build_job(jm, 3)
    # p0 completes, p1 stops, p2 stays running -> job RUNNING (a live member).
    job.update_process_status(100000, 0)          # exited
    job.update_process_status(100001, 0x7f)       # 0x7f == WIFSTOPPED
    job.update_state()
    assert job._counts[ProcessState.COMPLETED] == 1
    assert job._counts[ProcessState.STOPPED] == 1
    assert job._counts[ProcessState.RUNNING] == 1
    assert job.state is JobState.RUNNING

    # p2 also stops -> every non-completed member stopped -> STOPPED (F10).
    job.update_process_status(100002, 0x7f)
    job.update_state()
    assert job._counts[ProcessState.RUNNING] == 0
    assert job.state is JobState.STOPPED


def test_get_job_by_pid_none_after_removal():
    jm = JobManager()
    job = _build_job(jm, 2)
    assert jm.get_job_by_pid(100000) is job
    jm.remove_job(job.job_id)
    # The pid index is cleared on removal (no stale entries).
    assert jm.get_job_by_pid(100000) is None
    assert jm.get_job_by_pid(100001) is None
    assert jm.pid_index == {}
