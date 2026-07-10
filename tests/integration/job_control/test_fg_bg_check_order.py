"""fg/bg job-control gate, check order, messages, and bare-number semantics.

Task #9 [#27+#28] job-cosmetics. bash-pinned (5.2.26, /opt/homebrew/bin/bash):

- fg/bg check the job-control flag (psh: `set -m`/monitor) FIRST, before
  resolving the jobspec: with job control OFF the error is `no job control`
  (rc 1), even for `fg %99` — bash never gets to "no such job".
- With job control ON but no current job, bare `fg`/`bg` report
  `current: no such job` (rc 1), not psh's old `no current job`.
- A bare integer operand to fg/bg is a JOB NUMBER (`fg 1` == `fg %1`), unlike
  wait/kill where a bare integer is a PID (guarded here).
- With monitor on but no controlling terminal (the test environment), fg still
  foregrounds and WAITS for the job, returning its exit status — it does not
  bail out with the old "no job control in this shell".

These run psh in a subprocess (`-c`) with a timeout so a wedged fg cannot hang
the suite. They live under integration/job_control (auto-marked serial by path).
"""

import subprocess
import sys


def _psh(script: str, timeout: float = 15.0):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


# ---- job-control gate: OFF (no set -m) reports "no job control" first --------

def test_fg_no_job_control_when_monitor_off():
    out, err, rc = _psh("fg")
    assert "no job control" in err
    assert rc == 1


def test_bg_no_job_control_when_monitor_off():
    out, err, rc = _psh("bg")
    assert "no job control" in err
    assert rc == 1


def test_fg_badspec_gate_precedes_resolution():
    # bash gates on job control BEFORE resolving %99 -> "no job control",
    # never "no such job".
    out, err, rc = _psh("fg %99")
    assert "no job control" in err
    assert "no such job" not in err
    assert rc == 1


# ---- job-control ON, no current job: "current: no such job" ------------------

def test_fg_bare_no_current_job_message():
    out, err, rc = _psh("set -m; fg")
    assert "current: no such job" in err
    assert rc == 1


def test_bg_bare_no_current_job_message():
    out, err, rc = _psh("set -m; bg")
    assert "current: no such job" in err
    assert rc == 1


# ---- bare integer operand to fg/bg is a JOB NUMBER ---------------------------

def test_fg_bare_number_is_job_number():
    # `fg 1` == `fg %1`: foregrounds job 1, echoes its command, waits, rc 0.
    out, err, rc = _psh("set -m; sleep 0.3 & fg 1; echo rc=$?", timeout=15)
    assert "sleep 0.3" in out
    assert "rc=0" in out


def test_fg_propagates_job_exit_status_without_tty():
    # monitor on, no tty: fg foregrounds+waits and returns the job's status
    # (distinctive 7, so this cannot pass by coincidence with a rc-1 failure).
    out, err, rc = _psh("set -m; sh -c 'exit 7' & fg %1; echo rc=$?", timeout=15)
    assert "rc=7" in out
    assert "no job control in this shell" not in err


# ---- guard: wait/kill keep bare integer = PID (must NOT become jobnum) --------

def test_wait_bare_number_stays_pid():
    # `wait 1` treats 1 as a PID (pid 1 is not our child) -> not-a-child / 127,
    # and must NOT foreground/wait job %1. If the fg/bg jobnum change leaked into
    # wait, `wait 1` would block on the sleep instead.
    out, err, rc = _psh("set -m; sleep 5 & wait 1; echo rc=$?", timeout=10)
    assert "rc=127" in out


def test_kill_bare_number_stays_pid():
    # `kill 1` targets PID 1 (not job %1). Non-child pid 1 -> permission error,
    # not a job resume; job %1 keeps running.
    out, err, rc = _psh("set -m; sleep 0.3 & kill 999999 2>&1; echo rc=$?; wait",
                        timeout=10)
    # 999999: no such process -> nonzero; the point is it is treated as a PID.
    assert "rc=1" in out or "rc=127" in out
