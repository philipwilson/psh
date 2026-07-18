"""REPL EOF shutdown route (campaign F2), on a real pseudo-terminal.

The Ctrl-D exit of the interactive loop routes through the one top-level
cleanup path, ``Shell.shutdown('repl-eof')``: the EXIT trap fires exactly
once, bash's ``exit`` echo appears, and the process ends cleanly.  Follows
the test_pty_smoke.py conventions (CR line endings, sentinel outputs,
prompt-sync before every send).
"""

import os
import sys
from pathlib import Path

import pexpect

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


def test_ctrl_d_fires_exit_trap_once_and_exits():
    child = _spawn()
    try:
        child.send("trap 'echo BYE_$((40+2))' EXIT\r")
        child.expect(PROMPT)
        child.send('\x04')                       # Ctrl-D: the REPL EOF route
        child.expect('exit')                     # bash-style echo on the EOF
        child.expect('BYE_42')                   # EXIT trap fired
        child.expect(pexpect.EOF)
        output = child.before or ''
        assert 'BYE_42' not in output            # ...and did not fire again
    finally:
        child.close(force=True)
    assert child.exitstatus == 0


def test_ctrl_d_exit_status_is_last_command_status():
    child = _spawn()
    try:
        child.send('false\r')
        child.expect(PROMPT)
        child.send('\x04')
        child.expect(pexpect.EOF)
    finally:
        child.close(force=True)
    # bash: EOF exits with the last command's status.
    assert child.exitstatus == 1
