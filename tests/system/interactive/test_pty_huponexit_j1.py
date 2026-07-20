"""Interactive huponexit / disown -h HUP-on-exit, on a real pseudo-terminal
(campaign J1 / #20 H19).

The end-to-end pin for the interactive HUP behavior the acceptance matrix
names: an interactive shell with ``shopt -s huponexit`` sends SIGHUP to its
running jobs when it exits (via the one ``Shell.shutdown`` path), so a
backgrounded child dies before it can leave a marker; without huponexit the
child survives; ``disown -h`` exempts it even with huponexit set.

Opt-in (marked ``interactive``; not in the run-by-default PTY allowlist),
because it depends on a real HUP race — the DETERMINISTIC wiring is pinned in
tests/unit/executor/test_boundary_j1_job_lifecycle.py
(``test_dispose_jobs_at_exit_*``). Run with ``--run-interactive``. Follows the
test_pty_shutdown_route_f2.py conventions.
"""
import os
import sys
import time
from pathlib import Path

import pexpect
import pytest

PROMPT = 'PSH\\$ '
PSH_ROOT = str(Path(__file__).parent.parent.parent.parent)


def _spawn(timeout=10):
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': '/tmp',
        'TERM': 'xterm',
        'PS1': 'PSH$ ',
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': PSH_ROOT,
    }
    child = pexpect.spawn(
        sys.executable, ['-u', '-m', 'psh', '--norc', '--force-interactive'],
        timeout=timeout, encoding='utf-8', env=env)
    child.send('\r')
    child.expect(PROMPT)
    return child


def _run_and_check_survival(tmp_path, *, huponexit, disown_h=False):
    """Start a bg child that marks a file after a delay, exit the shell, and
    report whether the child outlived the exit."""
    marker = tmp_path / "mark"
    child = _spawn()
    try:
        if huponexit:
            child.send('shopt -s huponexit\r')
            child.expect(PROMPT)
        child.send('{ sleep 0.6; : > %s; } &\r' % marker)
        child.expect(PROMPT)
        if disown_h:
            child.send('disown -h\r')
            child.expect(PROMPT)
        child.send('\x04')                 # Ctrl-D: the REPL EOF shutdown route
        child.expect(pexpect.EOF)
    finally:
        child.close(force=True)
    time.sleep(1.3)                        # past the child's 0.6s delay
    return marker.exists()


def test_no_huponexit_bg_child_survives_exit(tmp_path):
    # Default (huponexit off): the bg child outlives the shell (bash).
    assert _run_and_check_survival(tmp_path, huponexit=False) is True


def test_huponexit_bg_child_is_hupped_on_exit(tmp_path):
    # huponexit on: SIGHUP kills the bg child before it marks the file.
    #
    # This records the PSH login-narrowing MODEL (boundary J1 ruling 1): PSH
    # has no login-shell concept, so every interactive PSH shell is login-like
    # for huponexit and HUPs its jobs on exit. It is NOT a claim of bash parity
    # for the interactive non-login case (bash would not HUP a non-login shell's
    # jobs) — see docs/user_guide/17_differences_from_bash.md.
    assert _run_and_check_survival(tmp_path, huponexit=True) is False


def test_disown_h_exempts_job_from_huponexit(tmp_path):
    # disown -h keeps the job in the table but exempt from the exit HUP, so the
    # child survives even with huponexit set (Job.no_hup honored).
    assert _run_and_check_survival(tmp_path, huponexit=True, disown_h=True) is True


def _child_alive(pid):
    import os
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _received_hup_child_alive(disown_h=False):
    """Start a bg `sleep &`, send SIGHUP to the shell, and report whether the
    child is still alive. False => the shell fanned SIGHUP out to it."""
    import os
    import signal

    child = _spawn()
    try:
        child.send("sleep 5 & echo C=$!\r")
        child.expect(r"C=(\d+)")
        cpid = int(child.match.group(1))
        child.expect(PROMPT)
        if disown_h:
            child.send("disown -h\r")
            child.expect(PROMPT)
        time.sleep(0.2)
        os.kill(child.pid, signal.SIGHUP)      # the shell RECEIVES SIGHUP
        time.sleep(0.8)
        alive = _child_alive(cpid)
        try:
            os.kill(cpid, signal.SIGKILL)
        except OSError:
            pass
        return alive
    finally:
        child.close(force=True)


def test_received_sighup_fans_out_to_jobs():
    """Received-SIGHUP fan-out (boundary J1 ruling 3, FINAL model).

    An interactive shell that RECEIVES an untrapped SIGHUP resends SIGHUP to its
    jobs (bash's hangup_all_jobs), then exits — verified in a tmux-hosted REAL
    terminal (tmp/boundary-ledgers/J1-probes/probe_sighup_tmux.py). PSH's
    fan-out is unconditional, so it is observable in ANY construction; this pins
    it via a plain bg child (killed by the fan-out).

    PROBE-CONSTRUCTION CAVEAT: an earlier "kill -HUP is parity" reading was a
    python-pty artifact — BASH does not fan out under pexpect/pty.fork but DOES
    under tmux. This pin asserts PSH's model, so it is construction-robust; the
    bash comparison lives in the tmux probe (see the J1 ledger's three-state
    ruling-3 history). A HUP-trapping child is NOT used: psh's backgrounded
    brace group does not fire a body-set HUP trap (a separate quirk).
    """
    assert _received_hup_child_alive() is False   # child was HUP'd


def test_received_sighup_honors_disown_h():
    # disown -h exempts a job from the received-SIGHUP fan-out (Job.no_hup).
    assert _received_hup_child_alive(disown_h=True) is True   # child survived


if __name__ == "__main__":  # pragma: no cover - manual smoke
    sys.exit(pytest.main([__file__, "-v", "--run-interactive"]))
