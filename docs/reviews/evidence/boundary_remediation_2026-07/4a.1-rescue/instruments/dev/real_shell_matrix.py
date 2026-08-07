"""I-B: real-``Shell()`` embedding cells for seams 4 (GC handover) and 7
(STD_FDS retained on failed exec).  ONE CELL PER PROCESS.

Observation channel: these cells make the shell under test perform PERMANENT
``exec`` redirections, which rebind fd 1 process-wide — a probe that printed
to stdout would post its own rows into the redirect target and report
nothing.  So the cell dups the original stdout to a HIGH fd (>= 40: above
the per-command save area at 10, below the STD_FDS parking base at 63) and
writes every row there with ``os.write``.  Same pipe the driver captures,
immune to anything the shell does to 0/1/2.

Output contract as in coord_matrix.py.
"""
import fcntl
import gc
import os
import sys
import tempfile

import psh

# The probe's own channel, taken BEFORE any shell exists.
_CHAN = fcntl.fcntl(1, fcntl.F_DUPFD_CLOEXEC, 40)

CELL = None


def say(line):
    os.write(_CHAN, (line + "\n").encode())


say("DISCRIM " + os.path.abspath(psh.__file__))

from psh.core.process_lease import (  # noqa: E402
    ComponentKind,
    LeaseError,
    get_coordinator,
)
from psh.shell import Shell  # noqa: E402

COORD = get_coordinator()


def emit(key, value):
    say(f"CELL {CELL} KEY={key} VALUE={value}")


def result(disposition):
    say(f"CELL {CELL} RESULT={disposition}")


def leases():
    return sorted(c.kind.name for c in COORD._components if not c.released)


def open_high_fds():
    """Currently-open fds in the STD_FDS parking range (>= 63)."""
    out = []
    for fd in range(63, 96):
        try:
            os.fstat(fd)
            out.append(fd)
        except OSError:
            pass
    return out


def baseline_registered(sh):
    fr = sh.io_manager.file_redirector if hasattr(sh, 'io_manager') else None
    return getattr(fr, '_std_baseline', None) is not None if fr else None


def next_shell_runs():
    """Can a fresh, unrelated shell execute?  CLEAN or POISONED:<blame>."""
    sh = Shell(norc=True)
    try:
        rc = sh.run_command('true')
        emit("next_shell_rc", rc)
        return "CLEAN"
    except LeaseError as exc:
        emit("next_shell_error", str(exc).split(';')[0].replace(' ', '_'))
        return "POISONED"
    finally:
        try:
            sh.close()
        except Exception:                            # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# B-01..B-04 — drop-without-close, quantified over COMPONENT KIND.
# --------------------------------------------------------------------------

def dropped_without_close(kind, close_properly=False):
    d = tempfile.mkdtemp()
    sh = Shell(norc=True)
    if kind == 'STD_FDS':
        sh.run_command('exec 3> %s' % os.path.join(d, 'keep3.txt'))
        sh.run_command('exec > %s' % os.path.join(d, 'out.txt'))
    elif kind == 'SIGNALS':
        sh.run_command("trap ':' USR1")
    else:                                            # LOCALE / none
        sh.run_command('true')
    emit("leases_held", ",".join(leases()) or "-")
    if close_properly:
        sh.close()
        emit("closed", True)
    del sh
    gc.collect()
    emit("owner_after_drop",
         "ALIVE" if COORD.current_owner() is not None else "COLLECTED")
    emit("leases_after_drop", ",".join(leases()) or "-")
    result(next_shell_runs())


# --------------------------------------------------------------------------
# B-05..B-07, B-10 — the LOW: STD_FDS lease retained on a FAILED exec.
# --------------------------------------------------------------------------

def failed_exec_retention(pre_success=False, then_close=False):
    d = tempfile.mkdtemp()
    good = os.path.join(d, 'good.txt')
    sh = Shell(norc=True)
    fds_before_any = open_high_fds()
    if pre_success:
        rc0 = sh.run_command('exec > %s' % good)
        emit("first_exec_rc", rc0)
        emit("leases_after_first_exec", ",".join(leases()) or "-")
    fds_before = open_high_fds()
    emit("parked_fds_before", ",".join(map(str, fds_before)) or "-")
    emit("leases_before", ",".join(leases()) or "-")
    rc = sh.run_command('exec > /nonexistent-dir-4a1/out.txt')
    emit("failing_exec_rc", rc)
    fds_after = open_high_fds()
    emit("parked_fds_after", ",".join(map(str, fds_after)) or "-")
    emit("leases_after", ",".join(leases()) or "-")
    emit("baseline_registered", baseline_registered(sh))
    emit("newly_parked",
         len([f for f in fds_after if f not in fds_before]))
    emit("lease_newly_taken",
         'STD_FDS' in leases() and 'STD_FDS' not in (
             ['STD_FDS'] if pre_success else []))
    emit("fds_leaked_vs_pristine",
         len([f for f in fds_after if f not in fds_before_any]))
    if then_close:
        sh.close()
        emit("closed", True)
        emit("leases_after_close", ",".join(leases()) or "-")
        emit("parked_fds_after_close",
             ",".join(map(str, open_high_fds())) or "-")
        result(next_shell_runs())
        return
    held = 'STD_FDS' in leases()
    # Discrimination: with a PRIOR successful exec the lease must SURVIVE
    # (must-hold); without one it must not have been retained (the LOW).
    if pre_success:
        result("FIRST_LEASE_INTACT" if held else "FIRST_LEASE_LOST")
    else:
        result("RETAINED" if held else "RELEASED")
    sh.close()


def failed_exec_after_relocation():
    """B-10: the failing plan's list already displaced a parked backup
    (relocation protocol) before the failure — ordering check (subtlety 7)."""
    d = tempfile.mkdtemp()
    sh = Shell(norc=True)
    rc0 = sh.run_command('exec 3> %s' % os.path.join(d, 'first.txt'))
    emit("first_exec_rc", rc0)
    parked = open_high_fds()
    emit("parked_after_first", ",".join(map(str, parked)) or "-")
    # One command: claim a parked slot AND then fail.
    target = parked[0] if parked else 63
    rc = sh.run_command('exec %d> %s 4>/nonexistent-dir-4a1/x'
                        % (target, os.path.join(d, 'second.txt')))
    emit("relocating_failing_exec_rc", rc)
    emit("parked_after", ",".join(map(str, open_high_fds())) or "-")
    emit("leases_after", ",".join(leases()) or "-")
    emit("baseline_registered", baseline_registered(sh))
    sh.close()
    emit("leases_after_close", ",".join(leases()) or "-")
    result(next_shell_runs())


# --------------------------------------------------------------------------
# B-08/B-09 — which permanent-redirect SHAPES take the lease (must-hold).
# --------------------------------------------------------------------------

def lease_acquisition_shape(script, label):
    d = tempfile.mkdtemp()
    sh = Shell(norc=True)
    rc = sh.run_command(script % {'d': d})
    emit("rc", rc)
    held = leases()
    emit("leases_held", ",".join(held) or "-")
    emit("baseline_registered", baseline_registered(sh))
    sh.close()
    emit("leases_after_close", ",".join(leases()) or "-")
    result(f"{label}:{'STD_FDS' if 'STD_FDS' in held else 'NO_STD_FDS'}")


def failed_exec_blocks_innocent_shell(pre_success):
    """B-11/B-12: the LOW's BEHAVIOURAL consequence, not an internals reading.

    Shell A performs a FAILING permanent redirect and nothing else (B-11):
    fds 0/1/2 are untouched, so A owns no process-global std state — yet the
    retained lease makes the coordinator reject an unrelated live shell B.
    B-12 is the must-hold control: after a SUCCESSFUL exec, A genuinely does
    own fd 1 and the rejection is the designed protection."""
    # Isolate the STD_FDS lease: under a C locale the activation glue takes
    # no LOCALE lease, so A's ONLY lease is the one this cell is about.  With
    # a LOCALE lease also held, B's rejection would be legitimate and the
    # cell could never discriminate the fix (it would read red-on-base and
    # then fail to flip for a reason that has nothing to do with the LOW).
    os.environ['LC_ALL'] = 'C'
    os.environ['LANG'] = 'C'
    d = tempfile.mkdtemp()
    a = Shell(norc=True)
    if pre_success:
        a.run_command('exec 3> %s' % os.path.join(d, 'ok.txt'))
    rc = a.run_command('exec 3> /nonexistent-dir-4a1/out.txt')
    emit("failing_exec_rc", rc)
    held = leases()
    emit("leases_held_by_A", ",".join(held) or "-")
    # Isolation means: nothing OTHER than STD_FDS may be in play, so B's
    # outcome is attributable to the STD_FDS lease alone.  Holding NOTHING is
    # the post-fix target for B-11 (A's failed exec released it), not an
    # inconclusive reading — only a foreign kind makes the cell unable to
    # discriminate.
    emit("isolated_to_STD_FDS", set(held) <= {'STD_FDS'})
    if not set(held) <= {'STD_FDS'}:
        emit("inconclusive_reason", "A holds leases beyond STD_FDS")
        result(f"INCONCLUSIVE:{','.join(held) or '-'}")
        a.close()
        return
    b = Shell(norc=True)
    try:
        rc_b = b.run_command('true')
        outcome = "B_RAN"
        emit("b_rc", rc_b)
    except LeaseError as exc:
        outcome = "B_REJECTED"
        emit("b_error", str(exc).split(';')[0].replace(' ', '_'))
    finally:
        try:
            b.close()
        except Exception:                            # noqa: BLE001
            pass
        a.close()
    result(outcome)


def baseline_dup_failure_rlimit():
    """B-13a (R1 point 3): make the F_DUPFD_CLOEXEC baseline step FAIL.

    Lowering RLIMIT_NOFILE below the parking base (63) makes
    ``fcntl(fd, F_DUPFD_CLOEXEC, 63)`` fail for every std fd.  Note which
    arm of _acquire_permanent_stream_lease catches it and what state the
    shell is left in — recorded as cell OUTPUT, not inferred."""
    import resource
    d = tempfile.mkdtemp()
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    emit("rlimit_before", f"{soft}/{hard}")
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, hard))
    emit("rlimit_set", resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    sh = Shell(norc=True)
    target = os.path.join(d, 'out.txt')
    raised = None
    try:
        rc = sh.run_command('exec 3> %s' % target)
        emit("exec_rc", rc)
    except BaseException as exc:                     # noqa: BLE001
        raised = f"{type(exc).__name__}:{exc}"
        emit("exec_raised", raised)
    emit("leases_after", ",".join(leases()) or "-")
    emit("baseline_registered", baseline_registered(sh))
    fr = sh.io_manager.file_redirector
    baseline = getattr(fr, '_std_baseline', None)
    if baseline is not None:
        # A dup failure caught by the INNER arm records None, which the
        # restore reads as "this fd was CLOSED at baseline" and re-closes.
        emit("baseline_fds", str(baseline.fds))
        emit("fds_recorded_as_closed",
             sum(1 for v in baseline.fds.values() if v is None))
    resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
    def alive(fd):
        try:
            os.fstat(fd)
            return True
        except OSError:
            return False
    before_close = {fd: alive(fd) for fd in (0, 1, 2)}
    sh.close()
    after_close = {fd: alive(fd) for fd in (0, 1, 2)}
    emit("std_fds_open_before_close", str(before_close))
    emit("std_fds_open_after_close", str(after_close))
    closed_by_restore = [fd for fd in (0, 1, 2)
                         if before_close[fd] and not after_close[fd]]
    emit("std_fds_closed_by_restore", ",".join(map(str, closed_by_restore)) or "-")
    result(f"DUP_FAIL_CLOSES_STD_FDS:{len(closed_by_restore)}")


def baseline_dup_failure_outer_arm():
    """B-13b (R1 point 3): drive the OUTER `except BaseException` arm of
    _acquire_permanent_stream_lease — acquire_component itself rejects
    (competing live owner) AFTER the dups were parked.  Nothing may be
    half-acquired: no lease, no parked fds, no _std_baseline."""
    os.environ['LC_ALL'] = 'C'
    os.environ['LANG'] = 'C'
    d = tempfile.mkdtemp()
    a = Shell(norc=True)
    a.run_command('exec 3> %s' % os.path.join(d, 'a.txt'))   # A holds STD_FDS
    emit("A_leases", ",".join(leases()) or "-")
    parked_before = open_high_fds()
    emit("parked_before", ",".join(map(str, parked_before)) or "-")
    b = Shell(norc=True)
    target = os.path.join(d, 'b.txt')
    raised = None
    try:
        rc = b.run_command('exec > %s' % target)
        emit("b_exec_rc", rc)
    except LeaseError as exc:
        raised = "LeaseError"
        emit("b_error", str(exc).split(';')[0].replace(' ', '_'))
    emit("b_raised", raised or "NOTHING")
    parked_after = open_high_fds()
    emit("parked_after", ",".join(map(str, parked_after)) or "-")
    emit("parked_leaked_by_B",
         len([f for f in parked_after if f not in parked_before]))
    emit("b_baseline_registered", baseline_registered(b))
    emit("b_target_created", os.path.exists(target))
    emit("leases_after", ",".join(leases()) or "-")
    b.close()
    a.close()
    result(f"LEAKED_FDS:{len([f for f in parked_after if f not in parked_before])}")


def acquisition_vs_open_order():
    """B-14 (R1 point 4): RECORD which step of apply_permanent_redirections
    runs first — lease acquisition or the target open — as cell output.

    Two discriminating observations on the SAME command shape:
      * failing target (`/nonexistent-dir/...`): if the lease is taken, the
        acquisition preceded the open;
      * rejected acquisition (competing owner): if the target file was never
        created, the acquisition preceded the open.
    """
    os.environ['LC_ALL'] = 'C'
    os.environ['LANG'] = 'C'
    d = tempfile.mkdtemp()
    # (1) failing target
    sh = Shell(norc=True)
    rc = sh.run_command('exec > /nonexistent-dir-4a1/out.txt')
    emit("failing_target_rc", rc)
    emit("failing_target_lease_taken", 'STD_FDS' in leases())
    emit("failing_target_parked", ",".join(map(str, open_high_fds())) or "-")
    sh.close()
    # (2) rejected acquisition
    a = Shell(norc=True)
    a.run_command('exec 3> %s' % os.path.join(d, 'a.txt'))
    b = Shell(norc=True)
    target = os.path.join(d, 'never.txt')
    try:
        b.run_command('exec > %s' % target)
        emit("rejected_acquisition", "NOT_REJECTED")
    except LeaseError:
        emit("rejected_acquisition", "REJECTED")
    emit("rejected_target_created", os.path.exists(target))
    b.close()
    a.close()
    result("ACQUIRE_BEFORE_OPEN" if not os.path.exists(target)
           else "OPEN_BEFORE_ACQUIRE")


CELLS = {
    'B-13a': baseline_dup_failure_rlimit,
    'B-13b': baseline_dup_failure_outer_arm,
    'B-14': acquisition_vs_open_order,
    'B-11': lambda: failed_exec_blocks_innocent_shell(False),
    'B-12': lambda: failed_exec_blocks_innocent_shell(True),
    'B-01': lambda: dropped_without_close('STD_FDS'),
    'B-02': lambda: dropped_without_close('LOCALE'),
    'B-03': lambda: dropped_without_close('SIGNALS'),
    'B-04': lambda: dropped_without_close('STD_FDS', close_properly=True),
    'B-05': lambda: failed_exec_retention(),
    'B-06': lambda: failed_exec_retention(pre_success=True),
    'B-07': lambda: failed_exec_retention(then_close=True),
    'B-08': lambda: lease_acquisition_shape(
        'exec {v}> %(d)s/named.txt', 'named_fd_only'),
    'B-09': lambda: lease_acquisition_shape(
        'exec 3> %(d)s/three.txt', 'explicit_fd_3'),
    'B-10': failed_exec_after_relocation,
}


if __name__ == '__main__':
    CELL = sys.argv[1]
    if CELL == '--list':
        for name in CELLS:
            say(name)
        raise SystemExit(0)
    CELLS[CELL]()
