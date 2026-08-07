#!/usr/bin/env python3
"""4A.2 Phase A -- INSTANCE-3 investigation of the TestExitTrapOnFatalSignal
flake family (standing order, brief S:Slot-specific test hygiene).

Recorded loss (psh-r3-5 gate transcript, tmp/flake-watch-3-5/gate-attest.txt
line 608): `test_matches_bash_for_sigterm` saw psh stdout '' where bash had
'EXIT-TRAP-FIRED\\n'; both died -15.  So the EXIT trap's OUTPUT was lost, not
the trap.

HYPOTHESIS UNDER TEST: the harness's own readiness sentinel opens the race.
`_inject_ready` rewrites the script to `: > "$ready"; sleep 0.5`, and the
parent signals AS SOON AS $ready EXISTS -- but that file is created by the
REDIRECTION SETUP of `: > $ready`, i.e. while stdout is still redirected into
it.  A SIGTERM delivered inside that window runs the EXIT trap with the
command's redirection installed, so `echo EXIT-TRAP-FIRED` lands in the READY
FILE instead of stdout.

DECIDING OBSERVABLE: on a losing run, read the ready file.  If it contains
EXIT-TRAP-FIRED, the mechanism is confirmed and the flake is harness-induced
(a test-construction defect), not a shutdown-phase defect.

    python tmp/w4a2-probes/probe_flake.py [--iters N]
"""
import argparse
import os
import random
import subprocess
import sys
import tempfile
import time

PSH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = 'trap "echo EXIT-TRAP-FIRED" EXIT\nsleep 0.5\n'


def _inject_ready(script, ready, sentinel='redirect'):
    """Two sentinel constructions, A/B.

    'redirect' is the harness's own: `: > "$ready"` -- the file is created by
    the REDIRECTION SETUP, so the parent's "file exists" trigger fires while
    stdout is redirected into it.
    'mkdir' creates the sentinel with NO redirection anywhere, so the trigger
    cannot coincide with a redirect window.
    """
    if sentinel == 'mkdir':
        cmd = f'mkdir "{ready}"'
    else:
        cmd = f': > "{ready}"'
    return script.replace('sleep 0.5', f'{cmd}; sleep 0.5', 1)


def _wait_for_ready(ready, proc, timeout=20, busy=False):
    """busy=True polls with no sleep: it shrinks detection latency to
    microseconds, which AMPLIFIES the chance of signalling inside the
    redirect window (the harness itself sleeps 0.01s)."""
    deadline = time.time() + timeout
    n = 0
    while time.time() < deadline:
        if os.path.exists(ready):
            return True
        n += 1
        if n % 4096 == 0 and proc.poll() is not None:
            return False
        if not busy:
            if proc.poll() is not None:
                return False
            time.sleep(0.001)
    return False


def one_run(workdir, signum=15, sentinel='redirect', busy=False,
            post_delay=0.0):
    ready = os.path.join(workdir, 'psh.ready')
    path = os.path.join(workdir, 'sig.sh')
    with open(path, 'w') as fh:
        fh.write(_inject_ready(SCRIPT, ready, sentinel))
    env = dict(os.environ)
    env['PYTHONPATH'] = PSH_ROOT
    proc = subprocess.Popen([sys.executable, '-m', 'psh', path],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=PSH_ROOT, env=env)
    if not _wait_for_ready(ready, proc, busy=busy):
        out, err = proc.communicate()
        return {'harness': True, 'out': out, 'err': err, 'rc': proc.returncode}
    if post_delay:
        time.sleep(post_delay)
    try:
        os.kill(proc.pid, signum)
    except ProcessLookupError:
        pass
    try:
        out, err = proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    ready_body = ''
    if os.path.isfile(ready):
        with open(ready, errors='replace') as fh:
            ready_body = fh.read()
    return {'harness': False, 'out': out, 'err': err, 'rc': proc.returncode,
            'ready_body': ready_body, 'post_delay': post_delay}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iters', type=int, default=200)
    ap.add_argument('--sentinel', default='redirect',
                    choices=['redirect', 'mkdir'])
    ap.add_argument('--busy', action='store_true')
    ap.add_argument('--sweep-ms', type=float, default=0.0,
                    help='random post-detection delay in [0, N] ms')
    args = ap.parse_args()
    sha = subprocess.run(['git', '-C', PSH_ROOT, 'rev-parse', 'HEAD'],
                         capture_output=True, text=True).stdout.strip()
    print(f"# psh tree: {PSH_ROOT}  tip: {sha}")
    print(f"# iterations: {args.iters} sentinel={args.sentinel} busy={args.busy}")
    scratch = os.path.join(PSH_ROOT, 'tmp', 'w4a2-probes', 'scratch')
    os.makedirs(scratch, exist_ok=True)

    wins = losses = harness = 0
    confirmed = 0
    other = []
    t0 = time.time()
    for i in range(args.iters):
        with tempfile.TemporaryDirectory(dir=scratch) as wd:
            delay = (random.uniform(0, args.sweep_ms / 1000.0)
                     if args.sweep_ms else 0.0)
            res = one_run(wd, sentinel=args.sentinel, busy=args.busy,
                          post_delay=delay)
        if res['harness']:
            harness += 1
            continue
        if res['out'] == 'EXIT-TRAP-FIRED\n' and res['rc'] == -15:
            wins += 1
            continue
        losses += 1
        in_ready = 'EXIT-TRAP-FIRED' in res.get('ready_body', '')
        if in_ready:
            confirmed += 1
        else:
            other.append(res)
        print(f"  LOSS #{losses} at iter {i}: out={res['out']!r} "
              f"rc={res['rc']} delay_ms={res.get('post_delay',0)*1000:.2f} "
              f"ready_body={res.get('ready_body','')!r} "
              f"err={res['err'][:200]!r}")
    dt = time.time() - t0
    print()
    print(f"RESULT iters={args.iters} wins={wins} losses={losses} "
          f"harness_failures={harness} elapsed={dt:.1f}s")
    print(f"       losses whose trap output landed in the READY FILE: "
          f"{confirmed}/{losses}")
    if other:
        print(f"       losses with ANOTHER mechanism: {len(other)}")


if __name__ == '__main__':
    main()
