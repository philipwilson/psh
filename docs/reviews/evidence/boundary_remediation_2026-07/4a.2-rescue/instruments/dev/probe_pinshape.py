#!/usr/bin/env python3
"""4A.2 Phase A -- RED-ON-BASE verification of the PLANNED pin shapes.

D-3.4 lesson 7: a test that passes before its fix proves nothing, and the
prover must force on the REAL path.  Before writing any pin, this runs each
planned assertion AT BASE and reports RED (fails now, will pass after the
phase split) or GREEN (must-hold).  The counts feed the Phase-B
pre-registration block; they are RE-DERIVED at the declared tip, never carried.

The deterministic cells reuse the J1 pin shape already in the tree
(tests/unit/executor/test_boundary_j1_job_lifecycle.py): a SYNTHETIC job plus
a patched os.killpg, so no real signal is ever delivered and the cells are
xdist-safe.

Each cell runs in its own subprocess (process-wide coordinator singleton).

    python tmp/w4a2-probes/probe_pinshape.py
"""
import argparse
import json
import os
import subprocess
import sys

PSH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRAP_EXIT = "exit 7"


def _shell(trap=None, *, interactive=False, huponexit=False, histfile=None):
    sys.path.insert(0, PSH_ROOT)
    from psh.shell import Shell
    sh = Shell(norc=True)
    if histfile is not None:
        sh.run_command(f"export HISTFILE={histfile}")
    if interactive:
        sh.state.options['interactive'] = True
    if huponexit:
        sh.state.options['huponexit'] = True
    if trap:
        sh.run_command(f"trap '{trap}' EXIT")
    return sh


def _make_job(jm, pid, cmd="sleep 5"):
    job = jm.create_job(pid, cmd)
    job.add_process(pid, cmd)
    return job


def _patch_killpg(sent):
    real = os.killpg
    os.killpg = lambda pgid, sig: sent.append((pgid, sig))
    return real


# --- planned pins ----------------------------------------------------------

def pin_hup_under_trap_exit():
    """P1: interactive+huponexit, EXIT trap runs `exit 7` -> job still HUP'd."""
    import signal
    sh = _shell(TRAP_EXIT, interactive=True, huponexit=True)
    job = _make_job(sh.job_manager, 7007)
    sent = []
    real = _patch_killpg(sent)
    try:
        try:
            sh.shutdown('exit-builtin')
        except SystemExit:
            pass
    finally:
        os.killpg = real
    return (job.pgid, signal.SIGHUP) in sent


def pin_signal_hup_fanout_under_trap_exit():
    """P2: reason 'signal-hup' + trap-exit -> unconditional fan-out survives."""
    import signal
    sh = _shell(TRAP_EXIT, interactive=True)
    job = _make_job(sh.job_manager, 1414)
    sent = []
    real = _patch_killpg(sent)
    try:
        try:
            sh.shutdown('signal-hup')
        except SystemExit:
            pass
    finally:
        os.killpg = real
    return (job.pgid, signal.SIGHUP) in sent


def pin_history_under_trap_exit(tmpdir):
    """P3: history-saving route + trap-exit -> histfile still written."""
    histfile = os.path.join(tmpdir, 'hist')
    sh = _shell(TRAP_EXIT, interactive=True, histfile=histfile)
    sh.run_command('echo CANARY_CMD >/dev/null')
    try:
        sh.shutdown('exit-builtin')
    except SystemExit:
        pass
    return os.path.exists(histfile)


def pin_reap_under_trap_exit():
    """P4: detached-child reap still runs under trap-exit."""
    called = []
    sh = _shell(TRAP_EXIT)
    real = sh.job_manager.reap_detached
    sh.job_manager.reap_detached = lambda: (called.append(1), real())[1]
    try:
        sh.shutdown('exit-builtin')
    except SystemExit:
        pass
    return bool(called)


def pin_close_always_runs():
    """M1 (must-hold): close() runs on the trap-exit route today."""
    called = []
    sh = _shell(TRAP_EXIT)
    real = sh.close
    sh.close = lambda: (called.append(1), real())[1]
    try:
        sh.shutdown('exit-builtin')
    except SystemExit:
        pass
    return bool(called)


def pin_status_preserved():
    """M2 (must-hold): the trap's `exit 7` still escapes as SystemExit(7)."""
    sh = _shell(TRAP_EXIT)
    code = None
    try:
        sh.shutdown('exit-builtin')
    except SystemExit as exc:
        code = exc.code
    return code == 7


def pin_close_error_wins():
    """M3 (must-hold): a close() LeaseRestoreError outranks the held
    SystemExit, which survives as __context__."""
    sys.path.insert(0, PSH_ROOT)
    from psh.core.process_lease import LeaseRestoreError
    sh = _shell(TRAP_EXIT)
    real = sh.close

    def boom():
        real()
        raise LeaseRestoreError("INJECTED", [])

    sh.close = boom
    try:
        sh.shutdown('exit-builtin')
    except LeaseRestoreError as exc:
        return isinstance(exc.__context__, SystemExit) and exc.__context__.code == 7
    except BaseException:
        return False
    return False


def pin_second_shutdown_is_noop():
    """M4 (must-hold): the latch keeps __main__'s later funnel a no-op."""
    sh = _shell(TRAP_EXIT)
    try:
        sh.shutdown('exit-builtin')
    except SystemExit:
        pass
    called = []
    real = sh.close
    sh.close = lambda: (called.append(1), real())[1]
    sh.shutdown('main-exit')
    return not called and sh._shutdown_reason == 'exit-builtin'


def pin_no_trap_control_hups():
    """M5 (must-hold control): without a trap the job is HUP'd (proves the
    P1 observable is reachable -- a red P1 cannot be vacuous)."""
    import signal
    sh = _shell(None, interactive=True, huponexit=True)
    job = _make_job(sh.job_manager, 7008)
    sent = []
    real = _patch_killpg(sent)
    try:
        sh.shutdown('exit-builtin')
    finally:
        os.killpg = real
    return (job.pgid, signal.SIGHUP) in sent


#: name -> (callable, expected-at-base)  RED = must fail now.
PINS = {
    'P1-hup-under-trap-exit':      (pin_hup_under_trap_exit, 'RED'),
    'P2-signal-hup-under-trap':    (pin_signal_hup_fanout_under_trap_exit, 'RED'),
    'P3-history-under-trap-exit':  (pin_history_under_trap_exit, 'RED'),
    'P4-reap-under-trap-exit':     (pin_reap_under_trap_exit, 'RED'),
    'M1-close-always-runs':        (pin_close_always_runs, 'GREEN'),
    'M2-status-preserved':         (pin_status_preserved, 'GREEN'),
    'M3-close-error-wins':         (pin_close_error_wins, 'GREEN'),
    'M4-second-shutdown-noop':     (pin_second_shutdown_is_noop, 'GREEN'),
    'M5-no-trap-control-hups':     (pin_no_trap_control_hups, 'GREEN'),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pin')
    ap.add_argument('--tmpdir')
    args = ap.parse_args()

    if args.pin:
        fn = PINS[args.pin][0]
        try:
            passed = fn(args.tmpdir) if args.pin == 'P3-history-under-trap-exit' else fn()
            out = {'passed': bool(passed)}
        except BaseException as exc:
            out = {'error': f"{type(exc).__name__}: {exc}"}
        sys.stdout.write("RESULT " + json.dumps(out) + "\n")
        sys.stdout.flush()
        os._exit(0)

    import tempfile
    sha = subprocess.run(['git', '-C', PSH_ROOT, 'rev-parse', 'HEAD'],
                         capture_output=True, text=True).stdout.strip()
    print(f"# psh tree: {PSH_ROOT}  tip: {sha}")
    print("# RED = assertion FAILS at base (the pin forces the fix)")
    print()
    scratch = os.path.join(PSH_ROOT, 'tmp', 'w4a2-probes', 'scratch')
    os.makedirs(scratch, exist_ok=True)
    red = green = wrong = 0
    for name, (_fn, expected) in PINS.items():
        with tempfile.TemporaryDirectory(dir=scratch) as td:
            env = dict(os.environ)
            env['PYTHONPATH'] = PSH_ROOT
            env['HOME'] = td
            proc = subprocess.run(
                [sys.executable, __file__, '--pin', name, '--tmpdir', td],
                capture_output=True, text=True, timeout=60, cwd=PSH_ROOT,
                env=env)
        line = [ln for ln in proc.stdout.splitlines() if ln.startswith('RESULT ')]
        res = json.loads(line[0][7:]) if line else {'error': proc.stderr[-300:]}
        if 'error' in res:
            actual = 'ERROR'
        else:
            actual = 'GREEN' if res['passed'] else 'RED'
        ok = (actual == expected)
        if actual == 'RED':
            red += 1
        elif actual == 'GREEN':
            green += 1
        if not ok:
            wrong += 1
        mark = '   ' if ok else '  <-- NOT AS PREDICTED'
        print(f"{name:<30} expected={expected:<5} actual={actual:<5}{mark} {res}")
    print()
    print(f"TOTAL pins={len(PINS)} red={red} green={green} mispredicted={wrong}")


if __name__ == '__main__':
    main()
