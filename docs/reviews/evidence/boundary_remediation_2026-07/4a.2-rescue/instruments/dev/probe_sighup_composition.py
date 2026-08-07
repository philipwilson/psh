#!/usr/bin/env python3
"""4A.2 Phase A -- composition: trap-exit x the RECEIVED-SIGHUP route.

An interactive shell that RECEIVES SIGHUP runs psh's `shutdown('signal-hup')`
(signal_manager.py:328) -- job fan-out AND history save -- then dies 128+HUP.
If the EXIT trap itself runs `exit N`, does that route still fan out and save?

Construction: tmux-hosted REAL terminal (the J1 construction; J1 recorded that
pexpect/pty.fork is NOT faithful for bash's received-SIGHUP fan-out).  psh's
fan-out is unconditional, so it is observable in either construction; the bash
arm needs tmux to be meaningful.

Observables (no instrumentation): a bg child's marker file, and the histfile.

    python tmp/w4a2-probes/probe_sighup_composition.py
"""
import os
import signal
import subprocess
import sys
import tempfile
import time

BASH = "/opt/homebrew/bin/bash"
TMUX = "/opt/homebrew/bin/tmux"
PSH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

CANARY = "echo CANARY_HIST"
TRAPS = [
    ("no-trap", None),
    ("trap-noexit", "echo TRAPRAN"),
    ("trap-exit7", "exit 7"),
]
DELAY = 0.8
SETTLE = 2.0


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


def run_cell(which, trap, home):
    marker = os.path.join(home, 'marker')
    hist = os.path.join(home, 'histfile')
    env = _env(home)
    if which == 'bash':
        argv = [BASH, '--noprofile', '--norc', '--login', '-i']
    else:
        argv = [sys.executable, '-u', '-m', 'psh', '--norc',
                '--force-interactive']
    session = 'w4a2s_%d' % int(time.time() * 1000 % 10**9)
    envargs = []
    for key, val in env.items():
        envargs += ['-e', f'{key}={val}']
    subprocess.run([TMUX, 'new-session', '-d', '-s', session] + envargs
                   + ['--'] + argv, check=True, capture_output=True)
    try:
        time.sleep(1.2)
        pane_pid = int(subprocess.run(
            [TMUX, 'list-panes', '-t', session, '-F', '#{pane_pid}'],
            capture_output=True, text=True, check=True).stdout.strip())
        lines = [CANARY]
        if trap is not None:
            lines.append("trap '%s' EXIT" % trap)
        lines.append('{ sleep %s; : > %s; } &' % (DELAY, marker))
        for line in lines:
            subprocess.run([TMUX, 'send-keys', '-t', session, line, 'Enter'],
                           check=True, capture_output=True)
            time.sleep(0.4)
        os.kill(pane_pid, signal.SIGHUP)      # the shell RECEIVES SIGHUP
        time.sleep(SETTLE)
        survived = os.path.exists(marker)
        body = ''
        if os.path.exists(hist):
            with open(hist, errors='replace') as fh:
                body = fh.read()
    finally:
        subprocess.run([TMUX, 'kill-session', '-t', session],
                       capture_output=True)
    return {'job_survived': survived,
            'hist_written': os.path.exists(hist),
            'hist_canary': CANARY in body}


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
    print(f"# construction: {tmux_ver} REAL terminal (J1 construction)")
    print("# job_survived=True => NO fan-out reached the job")
    print()
    scratch = os.path.join(PSH_ROOT, 'tmp', 'w4a2-probes', 'scratch')
    os.makedirs(scratch, exist_ok=True)
    for label, trap in TRAPS:
        for which in ('bash', 'psh'):
            with tempfile.TemporaryDirectory(dir=scratch) as home:
                try:
                    res = run_cell(which, trap, home)
                except Exception as exc:
                    res = {'error': f"{type(exc).__name__}: {exc}"}
            print(f"{which:<5} {label:<12} {res}")
        print()


if __name__ == '__main__':
    main()
