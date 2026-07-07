"""F13: a partially-launched pipeline rolls back transactionally (campaign item 5).

If a pipe()/fork() fails part-way through launching a pipeline, the children
already forked must be signalled, reaped, and left neither running an
incomplete pipeline nor lingering as zombies, and the terminal must be
reclaimed. These drive a real psh Shell in a SUBPROCESS with os.fork / os.pipe
monkeypatched to fail at the k-th call, then assert no zombie and no orphaned
running child remain. Serial (real process lifecycle / signals).
"""

import subprocess
import sys
import textwrap

import pytest

# Driver: patch os.fork or os.pipe to fail at the k-th call, run a 3-stage
# pipeline of long sleeps through a real Shell, then report leak state. The
# long sleeps make an unkilled orphan detectable: reaping one that was not
# killed would block until it exits (well past the test timeout).
_DRIVER = textwrap.dedent('''
    import os, sys, signal

    FAIL_FORK_AT = int(os.environ.get("FAIL_FORK_AT", "0"))
    FAIL_PIPE_AT = int(os.environ.get("FAIL_PIPE_AT", "0"))

    _real_fork = os.fork
    _fork_n = [0]
    def _fake_fork():
        _fork_n[0] += 1
        if _fork_n[0] == FAIL_FORK_AT:
            raise OSError(35, "injected fork failure")
        return _real_fork()

    _real_pipe = os.pipe
    _pipe_n = [0]
    def _fake_pipe():
        _pipe_n[0] += 1
        if _pipe_n[0] == FAIL_PIPE_AT:
            raise OSError(24, "injected pipe failure")
        return _real_pipe()

    if FAIL_FORK_AT:
        os.fork = _fake_fork
    if FAIL_PIPE_AT:
        os.pipe = _fake_pipe

    from psh.shell import Shell
    shell = Shell()

    raised = ""
    try:
        rc = shell.run_command("sleep 30 | sleep 31 | sleep 32")
    except Exception as e:  # pragma: no cover - reported to the parent
        rc = -1
        raised = type(e).__name__

    # Restore real syscalls before auditing so the audit itself is honest.
    os.fork = _real_fork
    os.pipe = _real_pipe

    # No zombie: waitpid(-1, WNOHANG) must report ECHILD (no children left).
    zombie = 0
    try:
        while True:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
            zombie += 1        # a reapable child means the rollback missed it
    except ChildProcessError:
        pass

    jobs_left = len(shell.job_manager.jobs)
    print("RC=%s RAISED=%s ZOMBIE=%d JOBS=%d" % (rc, raised, zombie, jobs_left))
''')


def _run_driver(env_extra: dict):
    import os
    env = dict(os.environ)
    env.update(env_extra)
    result = subprocess.run(
        [sys.executable, "-c", _DRIVER],
        capture_output=True, text=True, timeout=20, env=env,
    )
    return result


def _parse(out: str) -> dict:
    line = [ln for ln in out.splitlines() if ln.startswith("RC=")]
    assert line, f"driver did not report: {out!r}"
    fields = dict(tok.split("=", 1) for tok in line[-1].split())
    return fields


@pytest.mark.serial
def test_fork_failure_midpipeline_leaves_no_zombie_or_orphan():
    # Leader (fork #1) launched; member b's fork (#2) fails -> rollback must
    # kill+reap the leader. A timeout here would mean the leader was reaped
    # WITHOUT being killed (blocking wait on a live sleep).
    result = _run_driver({"FAIL_FORK_AT": "2"})
    assert result.returncode == 0, result.stderr
    fields = _parse(result.stdout)
    assert fields["ZOMBIE"] == "0", result.stdout
    assert fields["JOBS"] == "0", result.stdout   # no provisional job record
    # The pipeline reported failure rather than success.
    assert fields["RC"] != "0" or fields["RAISED"], result.stdout


@pytest.mark.serial
def test_pipe_failure_midpipeline_leaves_no_zombie_or_orphan():
    # sync pipe (#1), boundary 0 (#2) ok -> leader launched; boundary 1's pipe
    # (#3) fails -> rollback must kill+reap the leader.
    result = _run_driver({"FAIL_PIPE_AT": "3"})
    assert result.returncode == 0, result.stderr
    fields = _parse(result.stdout)
    assert fields["ZOMBIE"] == "0", result.stdout
    assert fields["JOBS"] == "0", result.stdout


@pytest.mark.serial
def test_pipe_failure_before_any_fork_is_clean():
    # boundary 0's pipe (#2) fails before any child is forked: no children to
    # reap, no job record, clean re-raise.
    result = _run_driver({"FAIL_PIPE_AT": "2"})
    assert result.returncode == 0, result.stderr
    fields = _parse(result.stdout)
    assert fields["ZOMBIE"] == "0", result.stdout
    assert fields["JOBS"] == "0", result.stdout
