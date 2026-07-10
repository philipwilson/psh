"""Regression pins for the task #37 wait/reap ECHILD-reclaim race.

The flaky golden `r18t1_bgtrap_wait_bare_then_explicit_127`
(`( exit 5 ) & p=$!; wait; wait $p`) once raced to rc=5 instead of bash's
rc=127 under full xdist load. Root cause: `JobManager.wait_for_job`'s ECHILD
branch assumed a group wait (`waitpid(-pgid)`) that finds no member of the
job's process group means the child was reaped elsewhere, and marked the job
done WITHOUT reaping it. A child still alive (or a zombie) in an *unexpected*
process group is invisible to the group wait yet reapable by `waitpid(pid)`;
leaving it unreaped let a later `wait $p` reap its status (rc=5).

The fix reclaims each still-running process by its specific pid in the ECHILD
branch. Because the real race is essentially unreproducible standalone (the
child's own setpgid plus the parent's synchronous setpgid close the window on
this platform — see the dev ledger), these pins use the inert, env-gated
fault-injection seam `PSH_TEST_FORCE_GROUPWAIT_ECHILD` to force the group wait
to return ECHILD once, making the window deterministic.

RED-ON-BASE (seam present, reclaim absent): rc=5. GREEN (with reclaim): rc=127.

These tests fork / signal, so they are serial (the job_control/ path is
auto-marked serial by tests/conftest.py).
"""
import os
import signal
import subprocess
import sys

import pytest

TREE = os.path.dirname(  # .../psh-flake
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _run(cmd: str, *, seam: bool, timeout: int = 15):
    env = dict(os.environ)
    if seam:
        env["PSH_TEST_FORCE_GROUPWAIT_ECHILD"] = "1"
    else:
        env.pop("PSH_TEST_FORCE_GROUPWAIT_ECHILD", None)
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", cmd],
        cwd=TREE, capture_output=True, text=True, timeout=timeout, env=env,
    )


FLAKE_CMD = "( exit 5 ) & p=$!; wait; wait $p; echo rc=$?"
SLOW_FLAKE_CMD = "( sleep 0.2; exit 5 ) & p=$!; wait; wait $p; echo rc=$?"


def test_bare_wait_reclaims_child_missed_by_group_wait():
    """Seam forces a group-wait ECHILD; the bare wait must still reap the
    child by pid so the later `wait $p` returns 127, not the child's status."""
    r = _run(FLAKE_CMD, seam=True)
    assert r.stdout == "rc=127\n", (r.stdout, r.stderr)
    assert r.returncode == 0


def test_bare_wait_reclaims_slow_child_missed_by_group_wait():
    """Same, with a child that is still running when the bare wait starts —
    the reclaim must block on it (not a WNOHANG peek) to reap it."""
    r = _run(SLOW_FLAKE_CMD, seam=True)
    assert r.stdout == "rc=127\n", (r.stdout, r.stderr)
    assert r.returncode == 0


MULTI_PID_PIPELINE_CMD = (
    'sleep 0.05 | bash -c "sleep 0.35; exit 7" & p=$!; wait; wait $p; echo rc=$?'
)


def test_bare_wait_reclaims_all_pipeline_procs():
    """A multi-pid pipeline job: the reclaim must reap EVERY still-running
    process by pid, not just the first. `$!` is the last process (exit 7); if
    the reclaim stopped after the first proc, that second proc would leak past
    the bare wait and be reaped by `wait $p` (rc=7). It must be reaped in the
    reclaim so `wait $p` returns 127. (Guards the loop against a
    first-proc-only regression, which the single-subshell pins cannot catch —
    their lone leftover is mopped up by the orphan `waitpid(-1)` loop.)"""
    r = _run(MULTI_PID_PIPELINE_CMD, seam=True)
    assert r.stdout == "rc=127\n", (r.stdout, r.stderr)
    assert r.returncode == 0


def test_seam_inert_when_unset():
    """With the seam unset (production default), behavior is unchanged: the
    group wait reaps the child directly and `wait $p` returns 127."""
    r = _run(FLAKE_CMD, seam=False)
    assert r.stdout == "rc=127\n", (r.stdout, r.stderr)
    assert r.returncode == 0


def test_reclaim_stopped_child_recorded_stopped_not_completed():
    """The ECHILD reclaim, when its per-pid wait sees a STOPPED child, records
    it STOPPED (alive) — NOT completed-with-stop-status — and does not hang.

    Exercises `_reclaim_orphaned_by_pid` directly against a real forked child
    that stops itself, so the process is cleaned up deterministically (no
    lingering stopped orphan). WUNTRACED lets the blocking per-pid wait return
    on the stop instead of blocking forever.
    """
    from psh.executor.job_control import (
        JobManager,
        ProcessState,
    )

    pid = os.fork()
    if pid == 0:  # child: stop, then exit 5 once continued
        try:
            os.kill(os.getpid(), signal.SIGSTOP)
            os._exit(5)
        except BaseException:
            os._exit(127)

    jm = JobManager()
    job = jm.create_job(pid, "stopper")
    job.add_process(pid, "stopper")
    try:
        # The child stops itself; the reclaim's blocking WUNTRACED wait
        # observes the stop and records STOPPED (not COMPLETED).
        jm._reclaim_orphaned_by_pid(job)
        proc = job.processes[0]
        assert proc.state is ProcessState.STOPPED, proc.state
        assert proc.state is not ProcessState.COMPLETED
        job.update_state()
        from psh.executor.job_control import JobState
        assert job.state is JobState.STOPPED
    finally:
        # Continue and reap so no stopped orphan leaks.
        try:
            os.kill(pid, signal.SIGCONT)
            os.waitpid(pid, 0)
        except OSError:
            pass


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
