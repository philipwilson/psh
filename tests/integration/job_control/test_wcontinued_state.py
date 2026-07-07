"""WIFCONTINUED job-state handling (JobManager campaign item 4).

A resumed process must be re-marked Running. On macOS SIGCHLD is not raised on
continue, but a targeted `waitpid(pid, WCONTINUED)` still reports the resume;
this pins Process.update_status / Job.update_state against a REAL stopped-then-
continued child. Uses a targeted waitpid on the child's own pid (never
waitpid(-1)) so it does not disturb sibling children, and SIGKILLs + reaps the
child in a finally. Serial (real signals / process lifecycle).
"""

import os
import signal
import time

import pytest

from psh.executor.job_control import JobManager, JobState


@pytest.mark.serial
def test_wifcontinued_marks_job_running():
    jm = JobManager()

    pid = os.fork()
    if pid == 0:  # child: its own process group, then a long sleep
        try:
            os.setpgid(0, 0)
            os.execvp("sleep", ["sleep", "30"])
        finally:
            os._exit(127)

    try:
        os.setpgid(pid, pid)
    except OSError:
        pass  # child may have won the race

    job = jm.create_job(pgid=pid, command="sleep 30")
    job.add_process(pid, "sleep 30")
    assert job.state is JobState.RUNNING

    time.sleep(0.2)

    # Stop it and observe STOPPED via a targeted waitpid.
    os.killpg(pid, signal.SIGSTOP)
    _, status = os.waitpid(pid, os.WUNTRACED)
    job.update_process_status(pid, status)
    job.update_state()
    assert job.state is JobState.STOPPED
    assert job.processes[0].stopped is True

    # Continue it and observe RUNNING again (WIFCONTINUED).
    os.killpg(pid, signal.SIGCONT)
    _, status = os.waitpid(pid, os.WCONTINUED)
    assert os.WIFCONTINUED(status)
    job.update_process_status(pid, status)
    job.update_state()
    assert job.state is JobState.RUNNING
    assert job.processes[0].stopped is False
    assert job.processes[0].completed is False

    # Cleanup: SIGKILL (the continued child would otherwise run 30s) and reap.
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass
