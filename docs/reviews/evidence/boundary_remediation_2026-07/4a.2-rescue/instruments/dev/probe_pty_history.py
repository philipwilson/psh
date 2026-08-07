#!/usr/bin/env python3
"""4A.2 Phase A -- ruling slot (b): is the histfile written when the EXIT trap
itself runs `exit N`?  Interactive shell at a REAL pty, bash oracle vs psh.

The interactive gate makes `-c` probes vacuous for this question, so every
cell here is a pty cell.  Oracle bash = /opt/homebrew/bin/bash by explicit
argv (never /bin/bash).

    python tmp/w4a2-probes/probe_pty_history.py
"""
import os
import subprocess
import sys
import tempfile

import pexpect

BASH = "/opt/homebrew/bin/bash"
PSH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

CANARY = "echo CANARY_HIST"

TRAPS = [
    ("no-trap", None),
    ("trap-noexit", "echo TRAPRAN"),
    ("trap-exit7", "exit 7"),
]
ROUTES = ["ctrl-d", "exit-3"]


def _env(home):
    return {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': home,
        'TERM': 'xterm',
        'PS1': 'SH$ ',
        'HISTFILE': os.path.join(home, 'histfile'),
        'HISTFILESIZE': '500',
        'HISTSIZE': '500',
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': PSH_ROOT,
    }


def _spawn(which, home):
    env = _env(home)
    if which == 'bash':
        return pexpect.spawn(BASH, ['--norc', '--noprofile', '-i'],
                             timeout=15, encoding='utf-8', env=env)
    return pexpect.spawn(sys.executable,
                         ['-u', '-m', 'psh', '--norc', '--force-interactive'],
                         timeout=15, encoding='utf-8', env=env)


def run_cell(which, trap, route, home):
    prompt = r'SH\$ ' if which == 'bash' else r'PSH\$ |SH\$ '
    child = _spawn(which, home)
    try:
        child.send('\r')
        child.expect(prompt)
        if trap is not None:
            child.send("trap '%s' EXIT\r" % trap)
            child.expect(prompt)
        child.send(CANARY + '\r')
        child.expect(prompt)
        if route == 'ctrl-d':
            child.send('\x04')
        else:
            child.send('exit 3\r')
        child.expect(pexpect.EOF)
    finally:
        child.close(force=True)
    status = child.exitstatus if child.exitstatus is not None else -child.signalstatus
    hist = os.path.join(home, 'histfile')
    body = ''
    if os.path.exists(hist):
        with open(hist, errors='replace') as fh:
            body = fh.read()
    return {
        'status': status,
        'histfile_exists': os.path.exists(hist),
        'has_canary': CANARY in body,
    }


def main():
    ver = subprocess.run([BASH, '--version'], capture_output=True,
                         text=True).stdout.splitlines()[0]
    sha = subprocess.run(['git', '-C', PSH_ROOT, 'rev-parse', 'HEAD'],
                         capture_output=True, text=True).stdout.strip()
    print(f"# oracle bash: {BASH}")
    print(f"# {ver}")
    print(f"# psh tree: {PSH_ROOT}  tip: {sha}")
    print(f"# construction: pexpect {pexpect.__version__} pty")
    print()
    scratch = os.path.join(PSH_ROOT, 'tmp', 'w4a2-probes', 'scratch')
    os.makedirs(scratch, exist_ok=True)
    for route in ROUTES:
        for label, trap in TRAPS:
            row = {}
            for which in ('bash', 'psh'):
                with tempfile.TemporaryDirectory(dir=scratch) as home:
                    try:
                        row[which] = run_cell(which, trap, route, home)
                    except Exception as exc:
                        row[which] = {'error': f"{type(exc).__name__}: {exc}"}
            agree = (row['bash'].get('has_canary') == row['psh'].get('has_canary')
                     and row['bash'].get('status') == row['psh'].get('status'))
            mark = 'OK  ' if agree else 'DIFF'
            print(f"{mark} {route:<7} {label:<12} bash={row['bash']}")
            print(f"                          psh ={row['psh']}")
        print()


if __name__ == '__main__':
    main()
