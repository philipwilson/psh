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


def test_kill_hup_to_interactive_shell_does_not_fan_out(tmp_path):
    """Received-SIGHUP parity (boundary J1 ruling 3, corrected finding).

    A programmatic ``kill -HUP`` to an interactive shell does NOT fan SIGHUP out
    to its jobs — in EITHER shell. Probe-derived vs bash 5.2 (trap-based;
    tmp/boundary-ledgers/J1-probes/sighup_definitive.txt): bash fans out only on
    a genuine terminal DISCONNECT, which it distinguishes from an explicit
    ``kill -HUP``. PSH matches the kill -HUP case (parity); the disconnect
    fan-out is a documented residual (docs/missing_features.md). This pins the
    parity so the corrected model can't silently regress into a spurious
    kill -HUP fan-out.
    """
    import os
    import signal

    marker = tmp_path / "hupmark"
    child = _spawn()
    try:
        # child traps HUP and marks a file; only the shell's fan-out could send
        # HUP to a running bg child (a running orphaned pgroup gets no kernel HUP).
        child.send("{ trap ': > %s' HUP; sleep 3; } &\r" % marker)
        child.expect(PROMPT)
        time.sleep(0.2)
        os.kill(child.pid, signal.SIGHUP)      # explicit kill -HUP to the shell
        time.sleep(0.8)
        # The shell did not fan out, so the child never caught HUP.
        assert not marker.exists()
    finally:
        child.close(force=True)


if __name__ == "__main__":  # pragma: no cover - manual smoke
    sys.exit(pytest.main([__file__, "-v", "--run-interactive"]))
