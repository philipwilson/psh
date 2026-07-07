"""`kill %job` signals the process group once (JobManager campaign item 2).

bash signals the job's process group; psh used to expand a jobspec to every
recorded member PID and `os.kill` each one, which raised a spurious
"No such process" for a pipeline member that had already exited even though
the live members were signalled fine. The fix routes `kill %job` through one
`os.killpg(job.pgid, ...)`.
"""

import signal
import subprocess
import sys

import pytest

from psh.executor.job_control import JobManager


def _psh(script: str):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def test_kill_jobspec_calls_killpg_once(monkeypatch):
    """`kill %1` on a two-member pipeline job -> exactly one killpg, no per-PID kill."""
    from psh.builtins.kill_command import KillBuiltin

    jm = JobManager()
    job = jm.create_job(pgid=4242, command="a | b")
    job.add_process(101, "a")
    job.add_process(102, "b")

    killpg_calls = []
    kill_calls = []
    monkeypatch.setattr("os.killpg", lambda pgid, sig: killpg_calls.append((pgid, sig)))
    monkeypatch.setattr("os.kill", lambda pid, sig: kill_calls.append((pid, sig)))

    class Shell:
        pass
    shell = Shell()
    shell.job_manager = jm
    # KillBuiltin only needs shell.job_manager and self.error's stream; route
    # errors somewhere harmless.
    shell.state = type("S", (), {"stderr": sys.stderr})()

    builtin = KillBuiltin()
    rc = builtin.execute(["kill", "-TERM", "%1"], shell)

    assert rc == 0
    assert killpg_calls == [(4242, signal.SIGTERM)]
    assert kill_calls == []  # never per-member


def test_kill_jobspec_no_spurious_error_when_member_reaped(monkeypatch):
    """A killpg on the pgid still succeeds when one member PID is already gone."""
    from psh.builtins.kill_command import KillBuiltin

    jm = JobManager()
    job = jm.create_job(pgid=4242, command="a | b")
    job.add_process(101, "a")
    job.add_process(102, "b")

    # killpg succeeds (the group still has a live member); a per-PID kill on the
    # exited member would have raised ProcessLookupError.
    monkeypatch.setattr("os.killpg", lambda pgid, sig: None)

    errors = []

    class Shell:
        pass
    shell = Shell()
    shell.job_manager = jm

    builtin = KillBuiltin()
    monkeypatch.setattr(builtin, "error", lambda msg, sh: errors.append(msg))
    rc = builtin.execute(["kill", "%1"], shell)

    assert rc == 0
    assert errors == []


@pytest.mark.serial
def test_kill_jobspec_terminates_pipeline_end_to_end():
    """`sleep 5 | sleep 6 & kill %1` terminates the whole group; wait sees SIGTERM."""
    out, err, rc = _psh(
        "sleep 5 | sleep 6 & kill %1 && wait %1 2>/dev/null; echo rc=$?")
    # kill succeeded (&&), no spurious "No such process" line.
    assert "No such process" not in err
    assert "rc=0" not in out  # wait reports the signal death, not success
    assert "rc=" in out


@pytest.mark.serial
def test_kill_no_such_job():
    out, err, rc = _psh("sleep 0.2 & kill %9; echo rc=$?; wait")
    assert "%9: no such job" in err
    assert "rc=1" in out
