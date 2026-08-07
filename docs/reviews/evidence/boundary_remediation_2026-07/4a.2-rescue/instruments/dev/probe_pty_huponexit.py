#!/usr/bin/env python3
"""4A.2 Phase A -- the charter's named PTY cell: huponexit x trap-exit.

Does the exit-time SIGHUP fan-out still happen when the EXIT trap itself runs
`exit N`?  bash gates the exit-time HUP on an interactive LOGIN shell
(shell.c: `interactive_shell && login_shell && hup_on_exit`), so the bash arm
spawns `--login -i`; psh has no login concept (J1 ruling 1 login-narrowing),
so its gate is interactive + huponexit.

Observable: a backgrounded child writes a marker file AFTER a delay.  Marker
present => the child outlived the shell (no HUP).  Marker absent => HUP'd.

Two constructions are run for the BASH arm because J1 recorded that
pexpect/pty.fork is not always faithful for job-control signal behavior: a
pexpect pty and a tmux-hosted REAL terminal.  Disagreement between them is
itself reported.

    python tmp/w4a2-probes/probe_pty_huponexit.py
"""
import os
import subprocess
import sys
import tempfile
import time

import pexpect

BASH = "/opt/homebrew/bin/bash"
TMUX = "/opt/homebrew/bin/tmux"
PSH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

TRAPS = [
    ("no-trap", None),
    ("trap-noexit", "echo TRAPRAN"),
    ("trap-exit7", "exit 7"),
]
DELAY = 0.8          # child's delay before it writes the marker
SETTLE = 2.0         # wait past the delay before reading the marker


def _env(home):
    return {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': home,
        'TERM': 'xterm',
        'PS1': 'SH$ ',
        'HISTFILE': os.path.join(home, 'histfile'),
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': PSH_ROOT,
    }


def _lines(marker, trap):
    """The shell commands each construction sends, in order."""
    out = ['shopt -s huponexit']
    if trap is not None:
        out.append("trap '%s' EXIT" % trap)
    out.append('{ sleep %s; : > %s; } &' % (DELAY, marker))
    return out


# ---------------------------------------------------------------- pexpect ---

def run_pexpect(which, trap, home):
    marker = os.path.join(home, 'marker')
    env = _env(home)
    prompt = r'SH\$ ' if which == 'bash' else r'PSH\$ |SH\$ '
    if which == 'bash':
        child = pexpect.spawn(BASH, ['--noprofile', '--norc', '--login', '-i'],
                              timeout=15, encoding='utf-8', env=env)
    else:
        child = pexpect.spawn(
            sys.executable, ['-u', '-m', 'psh', '--norc', '--force-interactive'],
            timeout=15, encoding='utf-8', env=env)
    try:
        child.send('\r')
        child.expect(prompt)
        for line in _lines(marker, trap):
            child.send(line + '\r')
            child.expect(prompt)
        child.send('\x04')                       # Ctrl-D: the EOF exit route
        child.expect(pexpect.EOF)
        status = child.exitstatus
    finally:
        child.close(force=True)
    time.sleep(SETTLE)
    return {'status': status, 'survived': os.path.exists(marker)}


# ------------------------------------------------------------------- tmux ---

def run_tmux(which, trap, home):
    """Same cell inside a tmux-hosted REAL terminal (the J1 construction)."""
    marker = os.path.join(home, 'marker')
    session = 'w4a2_%d' % int(time.time() * 1000 % 10**9)
    env = _env(home)
    if which == 'bash':
        argv = [BASH, '--noprofile', '--norc', '--login', '-i']
    else:
        argv = [sys.executable, '-u', '-m', 'psh', '--norc', '--force-interactive']
    envargs = []
    for key, val in env.items():
        envargs += ['-e', f'{key}={val}']
    subprocess.run([TMUX, 'new-session', '-d', '-s', session] + envargs
                   + ['--'] + argv, check=True, capture_output=True)
    try:
        time.sleep(1.2)
        for line in _lines(marker, trap):
            subprocess.run([TMUX, 'send-keys', '-t', session, line, 'Enter'],
                           check=True, capture_output=True)
            time.sleep(0.4)
        subprocess.run([TMUX, 'send-keys', '-t', session, 'C-d'],
                       check=True, capture_output=True)
        time.sleep(SETTLE)
        survived = os.path.exists(marker)
    finally:
        subprocess.run([TMUX, 'kill-session', '-t', session],
                       capture_output=True)
    return {'status': None, 'survived': survived}


def main():
    ver = subprocess.run([BASH, '--version'], capture_output=True,
                         text=True).stdout.splitlines()[0]
    sha = subprocess.run(['git', '-C', PSH_ROOT, 'rev-parse', 'HEAD'],
                         capture_output=True, text=True).stdout.strip()
    tmux_ver = subprocess.run([TMUX, '-V'], capture_output=True,
                              text=True).stdout.strip()
    print(f"# oracle bash: {BASH}")
    print(f"# {ver}")
    print(f"# psh tree: {PSH_ROOT}  tip: {sha}")
    print(f"# constructions: pexpect {pexpect.__version__} | {tmux_ver}")
    print("# survived=True  => child outlived the shell (NO exit-time HUP)")
    print()
    scratch = os.path.join(PSH_ROOT, 'tmp', 'w4a2-probes', 'scratch')
    os.makedirs(scratch, exist_ok=True)
    for label, trap in TRAPS:
        for which in ('bash', 'psh'):
            row = {}
            for ctor, fn in (('pexpect', run_pexpect), ('tmux', run_tmux)):
                with tempfile.TemporaryDirectory(dir=scratch) as home:
                    try:
                        row[ctor] = fn(which, trap, home)
                    except Exception as exc:
                        row[ctor] = {'error': f"{type(exc).__name__}: {exc}"}
            note = ''
            if (row['pexpect'].get('survived')
                    != row['tmux'].get('survived')):
                note = '   <-- CONSTRUCTION DISAGREEMENT'
            print(f"{which:<5} {label:<12} pexpect={row['pexpect']} "
                  f"tmux={row['tmux']}{note}")
        print()


if __name__ == '__main__':
    main()
