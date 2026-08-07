#!/usr/bin/env python3
"""4A.2 Phase A -- the shutdown-phase BYPASS battery (observable side effects).

Method note (D-3.5 instrument-mirror): the integrator's brief-time evidence
came from an INSTRUMENTED Shell that recorded which shutdown steps ran.  This
probe re-derives the same facts from a DIFFERENT substrate wherever it can --
real OBSERVABLE consequences (was the detached child actually reaped? was the
histfile actually written on disk? was hangup actually delivered?) -- and only
then adds a step-recording cell as a cross-check.

Every cell runs in its OWN subprocess: the process-lease coordinator is a
process-wide singleton and the cells drive a real Shell's shutdown (which may
raise SystemExit).

Usage:
    python tmp/w4a2-probes/probe_bypass.py            # run all cells
    python tmp/w4a2-probes/probe_bypass.py --cell ID  # one cell (internal)
"""
import argparse
import json
import os
import subprocess
import sys
import time

PSH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: (cell id, trap action, description).  The trap-noexit arm of each pair is
#: the CONTROL: it proves the cell's observable is reachable at all, so a
#: "bypassed" reading cannot be a vacuous probe (D-3.4 lesson 8).
TRAPS = [
    ("no-trap", None),
    ("trap-noexit", "echo TRAPRAN >/dev/null"),
    ("trap-exit7", "exit 7"),
]


# --------------------------------------------------------------------------
# cell bodies (run inside the per-cell subprocess)
# --------------------------------------------------------------------------

def _mkshell(tmpdir, *, interactive=False, huponexit=False, trap=None,
             histfile=None):
    sys.path.insert(0, PSH_ROOT)
    from psh.shell import Shell
    shell = Shell(norc=True)
    if histfile is not None:
        shell.run_command(f"export HISTFILE={histfile}")
    if interactive:
        shell.state.options['interactive'] = True
    if huponexit:
        shell.run_command("shopt -s huponexit")
    if trap is not None:
        shell.run_command(f"trap '{trap}' EXIT")
    return shell


def cell_reap(trap, tmpdir):
    """A bare-`disown`ed child that has EXITED: does shutdown reap it?

    Observable WITHOUT instrumentation: this process is the child's parent, so
    after shutdown we ask the kernel.  ECHILD => psh reaped it; a returned pid
    => psh left it a zombie (the reap phase was skipped).
    """
    shell = _mkshell(tmpdir, trap=trap)
    shell.run_command("sleep 0.15 &")
    pid = shell.state.last_bg_pid
    shell.run_command("disown")
    time.sleep(0.6)                       # child is now an unreaped zombie
    raised = None
    try:
        shell.shutdown('exit-builtin')
    except SystemExit as exc:
        raised = f"SystemExit({exc.code})"
    try:
        got, _status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        got = -1                          # ECHILD: psh already reaped it
    reaped = (got == -1)
    if not reaped:                        # tidy up so the harness leaves none
        try:
            os.waitpid(pid, 0)
        except OSError:
            pass
    return {"raised": raised, "reaped": reaped}


def cell_history(trap, tmpdir):
    """Does the histfile get WRITTEN on disk on the exit-builtin route?"""
    histfile = os.path.join(tmpdir, "histfile")
    shell = _mkshell(tmpdir, interactive=True, trap=trap, histfile=histfile)
    shell.run_command("echo CANARY_CMD >/dev/null")
    raised = None
    try:
        shell.shutdown('exit-builtin')
    except SystemExit as exc:
        raised = f"SystemExit({exc.code})"
    written = os.path.exists(histfile)
    body = ""
    if written:
        with open(histfile) as fh:
            body = fh.read()
    return {"raised": raised, "histfile_written": written,
            "has_canary": "CANARY_CMD" in body}


def cell_hangup(trap, tmpdir):
    """interactive + huponexit + running bg job: is SIGHUP delivered?

    Observable: the child writes a marker file AFTER a delay.  A HUP'd child
    never writes it.  This process puts itself in its OWN process group first
    so a killpg aimed at the job cannot take the harness with it.
    """
    os.setpgrp()
    marker = os.path.join(tmpdir, "marker")
    shell = _mkshell(tmpdir, interactive=True, huponexit=True, trap=trap)
    shell.run_command("{ sleep 0.5; : > %s; } &" % marker)
    pid = shell.state.last_bg_pid
    time.sleep(0.15)
    raised = None
    try:
        shell.shutdown('exit-builtin')
    except SystemExit as exc:
        raised = f"SystemExit({exc.code})"
    time.sleep(1.2)                       # past the child's 0.5s delay
    survived = os.path.exists(marker)
    for sig in (9,):
        try:
            os.kill(pid, sig)
        except OSError:
            pass
    try:
        os.waitpid(pid, os.WNOHANG)
    except OSError:
        pass
    return {"raised": raised, "hupped": not survived}


def cell_steps(trap, tmpdir):
    """Cross-check: WHICH shutdown steps ran (step recording).

    This is the mirror of the integrator's method, kept as a cross-check on
    the observable cells above rather than as the primary evidence.
    """
    histfile = os.path.join(tmpdir, "histfile")
    shell = _mkshell(tmpdir, interactive=True, huponexit=True, trap=trap,
                     histfile=histfile)
    steps = []
    hm = shell.interactive_manager.history_manager
    jm = shell.job_manager
    orig = {
        'save_to_file': hm.save_to_file,
        'hangup_jobs': jm.hangup_jobs,
        'reap_detached': jm.reap_detached,
        'close': shell.close,
    }

    def wrap(name, fn):
        def inner(*a, **kw):
            steps.append(name)
            return fn(*a, **kw)
        return inner

    hm.save_to_file = wrap('history', orig['save_to_file'])
    jm.hangup_jobs = wrap('hangup', orig['hangup_jobs'])
    jm.reap_detached = wrap('reap', orig['reap_detached'])
    shell.close = wrap('close', orig['close'])
    raised = None
    try:
        shell.shutdown('exit-builtin')
    except SystemExit as exc:
        raised = f"SystemExit({exc.code})"
    return {"raised": raised, "steps": steps,
            "latched": getattr(shell, '_shutdown_reason', None)}


CELLS = {
    "reap": cell_reap,
    "history": cell_history,
    "hangup": cell_hangup,
    "steps": cell_steps,
}


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def run_one(cell, trap, tmpdir):
    fn = CELLS[cell]
    return fn(trap, tmpdir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell")
    ap.add_argument("--trap", default="")
    ap.add_argument("--tmpdir")
    args = ap.parse_args()

    if args.cell:
        trap = args.trap or None
        try:
            result = run_one(args.cell, trap, args.tmpdir)
        except BaseException as exc:            # report, never hide
            result = {"error": f"{type(exc).__name__}: {exc}"}
        sys.stdout.write("RESULT " + json.dumps(result) + "\n")
        sys.stdout.flush()
        os._exit(0)                             # skip interpreter teardown

    # parent: run every (cell, trap) pair in a fresh subprocess
    import tempfile
    sha = subprocess.run(["git", "-C", PSH_ROOT, "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    print(f"# psh tree: {PSH_ROOT}")
    print(f"# psh tip:  {sha}")
    print(f"# discriminator: psh/shell.py "
          f"{os.path.getsize(os.path.join(PSH_ROOT, 'psh', 'shell.py'))} bytes")
    print()
    scratch = os.path.join(PSH_ROOT, "tmp", "w4a2-probes", "scratch")
    os.makedirs(scratch, exist_ok=True)
    for cell in CELLS:
        for label, trap in TRAPS:
            with tempfile.TemporaryDirectory(dir=scratch) as td:
                argv = [sys.executable, __file__, "--cell", cell,
                        "--tmpdir", td]
                if trap:
                    argv += ["--trap", trap]
                env = dict(os.environ)
                env["PYTHONPATH"] = PSH_ROOT
                env["HOME"] = td
                proc = subprocess.run(argv, capture_output=True, text=True,
                                      timeout=60, cwd=PSH_ROOT, env=env)
                line = [ln for ln in proc.stdout.splitlines()
                        if ln.startswith("RESULT ")]
                payload = line[0][7:] if line else f"NO-RESULT rc={proc.returncode} err={proc.stderr[-400:]!r}"
                print(f"{cell:<9} {label:<12} {payload}")
        print()


if __name__ == "__main__":
    main()
