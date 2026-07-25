"""Slot 1.4 probe: `bg %1` -> `jobs` state, for psh AND bash, same harness.

Usage: pty-bg-probe2.py psh|bash
"""
import os
import sys
import time

import pexpect

ROOT = os.environ.get("PSH_ROOT", "/repo")


def spawn(which):
    env = dict(os.environ, PYTHONPATH=ROOT, PS1="PSH$ ", TERM="dumb")
    if which == 'psh':
        return pexpect.spawn(sys.executable,
                             ['-u', '-m', 'psh', '--norc', '--force-interactive'],
                             env=env, cwd=ROOT, encoding='utf-8', timeout=15)
    return pexpect.spawn('/bin/bash', ['--norc', '-i'],
                         env=env, cwd=ROOT, encoding='utf-8', timeout=15)


def one_round(which, settle):
    sh = spawn(which)
    prompt = r'PSH\$ '
    try:
        sh.expect(prompt)
        sh.send('sleep 42 &\r')
        sh.expect(r'\[1\]')
        sh.expect(prompt)
        sh.send('kill -STOP %1\r')
        sh.expect(prompt)
        time.sleep(0.3)
        sh.send('bg %1\r')
        sh.expect('sleep 42', timeout=8)
        sh.expect(prompt)
        if settle:
            time.sleep(settle)
        sh.send('jobs\r')
        sh.expect(prompt, timeout=10)
        out = sh.before
        return ('Running' if 'Running' in out
                else 'Stopped' if 'Stopped' in out else f'?({out!r})')
    except Exception as exc:
        return f'ERR({type(exc).__name__})'
    finally:
        try:
            sh.terminate(force=True)
        except Exception:
            pass


if __name__ == '__main__':
    which = sys.argv[1]
    for settle in (0.0, 1.0):
        results = [one_round(which, settle) for _ in range(5)]
        print(f"{which} settle={settle:<4} Running "
              f"{results.count('Running')}/5   {results}")
