"""Mandatory shutdown phases at a REAL pseudo-terminal (slot 4A.2, MEDIUM-1).

The charter's exit criterion is a PTY one: an EXIT-trap exit must still apply
the HUP / reap / history policy.  Both facts pinned here exist ONLY at a
terminal -- `huponexit` and the history save are interactive-gated, so a `-c`
pin for them is green on base and therefore proves nothing.  That is why this
file is admitted to the run-by-default PTY allowlist in tests/conftest.py, on
the same terms as its neighbours.

Red at base tip d1e4f1ae: with `trap 'exit 7' EXIT` installed, the trap's
`SystemExit` escaped `Shell.shutdown`'s try, so the backgrounded job was never
HUP'd and the histfile was never written.  bash does both (probed in both a
pexpect pty and a tmux-hosted real terminal, and on both the `exit N` and the
Ctrl-D route).  The exit STATUS was correct at base and must stay correct.

Follows the test_pty_shutdown_route_f2.py / test_pty_huponexit_j1.py
conventions: hermetic env, prompt-sync before every send, CR line endings.
Auto-marked `serial` by the `test_pty` path marker in tests/conftest.py.
"""
import os
import sys
import time
from pathlib import Path

import pexpect

PROMPT = 'PSH\\$ '
PSH_ROOT = str(Path(__file__).parent.parent.parent.parent)
CANARY = 'echo CANARY_HIST'


def _spawn(histfile, timeout=15):
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': str(Path(histfile).parent),
        'TERM': 'xterm',
        'PS1': 'PSH$ ',
        'HISTFILE': str(histfile),
        'HISTFILESIZE': '500',
        'HISTSIZE': '500',
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': PSH_ROOT,
    }
    child = pexpect.spawn(
        sys.executable, ['-u', '-m', 'psh', '--norc', '--force-interactive'],
        timeout=timeout, encoding='utf-8', env=env)
    child.send('\r')
    child.expect(PROMPT)
    return child


def test_huponexit_hups_the_job_even_when_the_exit_trap_exits(tmp_path):
    """huponexit x trap-exit -- the charter's named cell.

    The child marks a file after a delay; a HUP'd child never gets there.
    bash (interactive login shell) HUPs here in both constructions, so this is
    parity for the trap composition, on top of psh's login-narrowed gate
    (boundary J1 ruling 1, documented in 17_differences_from_bash.md).
    """
    marker = tmp_path / "mark"
    child = _spawn(tmp_path / "histfile")
    try:
        child.send('shopt -s huponexit\r')
        child.expect(PROMPT)
        child.send("trap 'exit 7' EXIT\r")
        child.expect(PROMPT)
        child.send('{ sleep 0.6; : > %s; } &\r' % marker)
        child.expect(PROMPT)
        child.send('\x04')                     # Ctrl-D: the REPL EOF route
        child.expect(pexpect.EOF)
    finally:
        child.close(force=True)
    time.sleep(1.3)                            # past the child's 0.6s delay
    assert not marker.exists(), "bg child survived: the exit-time HUP was skipped"


def test_without_huponexit_the_job_survives_a_trap_that_exits(tmp_path):
    """ANTI-VACUITY CONTROL for the cell above, carried in THIS file.

    The huponexit cell asserts the marker is ABSENT — which a construction
    that simply never created the marker would satisfy silently.  This is the
    same construction with `huponexit` OFF: the marker MUST appear.  The pair
    together show the observable moves in both directions, so the absence
    above is the SIGHUP rather than a broken harness.  (The sibling file's
    survival control runs WITHOUT a trap, so it does not cover this shape.)
    """
    marker = tmp_path / "mark"
    child = _spawn(tmp_path / "histfile")
    try:
        child.send("trap 'exit 7' EXIT\r")        # no `shopt -s huponexit`
        child.expect(PROMPT)
        child.send('{ sleep 0.6; : > %s; } &\r' % marker)
        child.expect(PROMPT)
        child.send('\x04')
        child.expect(pexpect.EOF)
    finally:
        child.close(force=True)
    time.sleep(1.3)
    assert marker.exists(), (
        "control failed: the bg child never marked even WITHOUT huponexit, so "
        "the huponexit cell's absent-marker assertion would prove nothing")


def test_history_is_saved_even_when_the_exit_trap_exits(tmp_path):
    """Ruling (b): bash writes the histfile under a trap that runs `exit N`;
    the documented psh skip was a divergence, not a policy."""
    histfile = tmp_path / "histfile"
    child = _spawn(histfile)
    try:
        child.send("trap 'exit 7' EXIT\r")
        child.expect(PROMPT)
        child.send(CANARY + '\r')
        child.expect(PROMPT)
        child.send('exit 3\r')
        child.expect(pexpect.EOF)
    finally:
        child.close(force=True)
    assert histfile.exists(), "histfile never written under a trap that exits"
    assert CANARY in histfile.read_text()


def test_trap_exit_status_still_overrides_on_the_interactive_routes(tmp_path):
    """Must-hold: the trap's `exit 7` still sets the status on BOTH interactive
    routes (it did at base; the phase split holds the signal and re-raises it,
    so it must still arrive)."""
    for route in ('\x04', 'exit 3\r'):
        child = _spawn(tmp_path / "histfile")
        try:
            child.send("trap 'exit 7' EXIT\r")
            child.expect(PROMPT)
            child.send(route)
            child.expect(pexpect.EOF)
        finally:
            child.close(force=True)
        assert child.exitstatus == 7, f"route {route!r} exited {child.exitstatus}"
