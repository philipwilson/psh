#!/usr/bin/env python3
"""4A.2 Phase A -- composition cells around the TERMINAL signal of shutdown().

Cells:
  A. close() raises LeaseRestoreError while a trap-exit SystemExit is pending
     -- WHICH one escapes shutdown() today?  (4A.1's EN-1 hold-then-raise is
     INSIDE close(); this is the level ABOVE it.)  Must be specified, and the
     current answer is the must-not-flip baseline.
  B. same, with no EXIT trap (control).
  C. re-entry: the exit-builtin-inside-the-trap route is the NORMAL route --
     what does the latch see, and does a SECOND shutdown() do anything?
  D. the non-interactive fatal-signal path (ruling slot (c)) x trap-exit,
     compared against bash: status and trap output.

Each in-process cell runs in its own subprocess (process-wide coordinator).

    python tmp/w4a2-probes/probe_terminal.py
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

BASH = "/opt/homebrew/bin/bash"
PSH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _shell(trap=None):
    sys.path.insert(0, PSH_ROOT)
    from psh.shell import Shell
    sh = Shell(norc=True)
    if trap:
        sh.run_command(f"trap '{trap}' EXIT")
    return sh


def cell_close_raises(trap):
    """close() raises LeaseRestoreError; is a pending trap-exit SystemExit
    preserved, replaced, or chained?"""
    sys.path.insert(0, PSH_ROOT)
    from psh.core.process_lease import LeaseRestoreError
    sh = _shell(trap)
    real_close = sh.close

    def boom():
        real_close()
        raise LeaseRestoreError("INJECTED restore failure", [])

    sh.close = boom
    escaped, ctx = None, None
    try:
        sh.shutdown('exit-builtin')
    except BaseException as exc:
        escaped = f"{type(exc).__name__}({getattr(exc, 'code', exc)})"
        c = exc.__context__
        if c is not None:
            ctx = f"{type(c).__name__}({getattr(c, 'code', c)})"
    return {"escaped": escaped, "context": ctx}


def cell_reentry(trap):
    """The exit-builtin-inside-the-trap route: latch + at-most-once."""
    sh = _shell(trap)
    steps = []
    jm = sh.job_manager
    real_reap = jm.reap_detached
    jm.reap_detached = lambda: (steps.append('reap'), real_reap())[1]
    first = None
    try:
        sh.shutdown('exit-builtin')
    except SystemExit as exc:
        first = f"SystemExit({exc.code})"
    latch1 = getattr(sh, '_shutdown_reason', None)
    trap_fired_once = getattr(sh.trap_manager, '_exit_trap_executed', False)
    second = None
    try:
        sh.shutdown('main-exit')          # __main__'s finally, after the fact
    except SystemExit as exc:
        second = f"SystemExit({exc.code})"
    return {"first": first, "latch": latch1, "second": second,
            "exit_trap_flag": trap_fired_once, "steps": steps}


CELLS = {"close_raises": cell_close_raises, "reentry": cell_reentry}


def run_signal_cell(which, script, sig, workdir):
    """D: non-interactive fatal signal x trap disposition, psh vs bash."""
    ready = os.path.join(workdir, f'{which}.ready')
    body = script.replace('sleep 0.5', f': > "{ready}"; sleep 0.5', 1)
    path = os.path.join(workdir, f'{which}.sh')
    with open(path, 'w') as fh:
        fh.write(body)
    argv = ([BASH, path] if which == 'bash'
            else [sys.executable, '-m', 'psh', path])
    env = dict(os.environ)
    env['PYTHONPATH'] = PSH_ROOT
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=workdir, env=env)
    deadline = time.time() + 20
    while time.time() < deadline and not os.path.exists(ready):
        if proc.poll() is not None:
            break
        time.sleep(0.01)
    try:
        os.kill(proc.pid, sig)
    except ProcessLookupError:
        pass
    out, err = proc.communicate(timeout=20)
    return {'out': out, 'rc': proc.returncode}


SIGNAL_SCRIPTS = [
    ("no-trap",     'sleep 0.5\n'),
    ("trap-noexit", 'trap "echo T" EXIT\nsleep 0.5\n'),
    ("trap-exit7",  'trap "echo T; exit 7" EXIT\nsleep 0.5\n'),
    ("trap-bg-job", 'trap "echo T; exit 7" EXIT\nsleep 9 &\nsleep 0.5\n'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cell')
    ap.add_argument('--trap', default='')
    args = ap.parse_args()
    if args.cell:
        try:
            res = CELLS[args.cell](args.trap or None)
        except BaseException as exc:
            res = {'error': f"{type(exc).__name__}: {exc}"}
        sys.stdout.write("RESULT " + json.dumps(res) + "\n")
        sys.stdout.flush()
        os._exit(0)

    sha = subprocess.run(['git', '-C', PSH_ROOT, 'rev-parse', 'HEAD'],
                         capture_output=True, text=True).stdout.strip()
    ver = subprocess.run([BASH, '--version'], capture_output=True,
                         text=True).stdout.splitlines()[0]
    print(f"# psh tree: {PSH_ROOT}  tip: {sha}")
    print(f"# oracle bash: {BASH} | {ver}")
    print()
    scratch = os.path.join(PSH_ROOT, 'tmp', 'w4a2-probes', 'scratch')
    os.makedirs(scratch, exist_ok=True)

    print("== A/B/C in-process cells ==")
    for cell in CELLS:
        for label, trap in (("no-trap", None), ("trap-noexit", "echo T >/dev/null"),
                            ("trap-exit7", "exit 7")):
            argv = [sys.executable, __file__, '--cell', cell]
            if trap:
                argv += ['--trap', trap]
            env = dict(os.environ)
            env['PYTHONPATH'] = PSH_ROOT
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=60, cwd=PSH_ROOT, env=env)
            line = [ln for ln in proc.stdout.splitlines()
                    if ln.startswith('RESULT ')]
            payload = line[0][7:] if line else f"NO-RESULT {proc.stderr[-300:]!r}"
            print(f"{cell:<13} {label:<12} {payload}")
        print()

    print("== D: non-interactive fatal signal (SIGTERM), psh vs bash ==")
    import signal as _sig
    for label, script in SIGNAL_SCRIPTS:
        row = {}
        for which in ('bash', 'psh'):
            with tempfile.TemporaryDirectory(dir=scratch) as wd:
                try:
                    row[which] = run_signal_cell(which, script, _sig.SIGTERM, wd)
                except Exception as exc:
                    row[which] = {'error': f"{type(exc).__name__}: {exc}"}
        agree = row['bash'] == row['psh']
        print(f"{'OK  ' if agree else 'DIFF'} {label:<12} "
              f"bash={row['bash']} psh={row['psh']}")


if __name__ == '__main__':
    main()
