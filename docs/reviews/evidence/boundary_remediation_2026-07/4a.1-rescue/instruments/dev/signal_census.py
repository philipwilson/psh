"""I-C: MEDIUM-8 — do managed signal dispositions outlive Shell.close()?

ONE CELL PER PROCESS (``python signal_census.py <cell-id>``).  Signal
dispositions are process-global; a fresh subprocess per cell means no cell's
handler installs can be mistaken for another's, and no @pytest.mark.serial
question arises at probe time.

Method: snapshot ``signal.getsignal`` for the FULL managed set BEFORE any
Shell exists (the pre-psh host disposition — the value MEDIUM-8 says close()
must restore), drive the shell, snapshot again, and report per-signal
equality.  Comparison is by IDENTITY for callables and by value for the
SIG_DFL/SIG_IGN constants, which is what "the EXACT previous handler" means.

Output contract: as in coord_matrix.py.
"""
import os
import signal
import sys

import psh

print("DISCRIM", os.path.abspath(psh.__file__))

from psh.shell import Shell  # noqa: E402

CELL = None

# The full set _setup_script_mode_handlers / _setup_interactive_mode_handlers
# install through _install_handler (signal_manager.py:107-138).
MANAGED = ['SIGINT', 'SIGTERM', 'SIGHUP', 'SIGQUIT', 'SIGTSTP', 'SIGTTOU',
           'SIGTTIN', 'SIGCHLD', 'SIGPIPE', 'SIGWINCH']


def emit(key, value):
    print(f"CELL {CELL} KEY={key} VALUE={value}")


def result(disposition):
    print(f"CELL {CELL} RESULT={disposition}")


def numbers():
    out = []
    for name in MANAGED:
        sig = getattr(signal, name, None)
        if sig is not None:
            out.append((name, sig))
    return out


def snapshot():
    return {name: signal.getsignal(sig) for name, sig in numbers()}


def describe(handler):
    if handler is signal.SIG_DFL:
        return 'SIG_DFL'
    if handler is signal.SIG_IGN:
        return 'SIG_IGN'
    if handler is None:
        return 'NONE(non-python)'
    return getattr(handler, '__qualname__', repr(handler))


def compare(before, after, tag):
    """Emit per-signal restoration facts; return the leaked signal names."""
    leaked = []
    for name in before:
        if before[name] is not after[name]:
            leaked.append(name)
            emit(f"{tag}.{name}",
                 f"{describe(before[name])}->{describe(after[name])}")
    emit(f"{tag}.leaked_count", len(leaked))
    emit(f"{tag}.leaked", ",".join(leaked) or "-")
    return leaked


def make_shell(mode):
    sh = Shell(norc=True)
    sh.state.is_script_mode = (mode == 'script')
    return sh


def setup(sh):
    sh.interactive_manager.signal_manager.setup_signal_handlers()


def basic(mode):
    """C-01/C-02: setup in <mode>, then close() — are the host's dispositions
    back?  This is MEDIUM-8's headline observation."""
    before = snapshot()
    sh = make_shell(mode)
    setup(sh)
    during = snapshot()
    installed = [n for n in before if before[n] is not during[n]]
    emit("installed_by_setup", ",".join(installed) or "-")
    emit("installed_count", len(installed))
    sh.close()
    after = snapshot()
    leaked = compare(before, after, "after_close")
    result("RESTORED" if not leaked else f"LEAKED:{len(leaked)}")


def teardown_then_close(mode):
    """C-03: the interactive-loop teardown runs first, then close()."""
    before = snapshot()
    sh = make_shell(mode)
    setup(sh)
    sh.interactive_manager.signal_manager.restore_default_handlers()
    mid = snapshot()
    compare(before, mid, "after_teardown")
    sh.close()
    after = snapshot()
    leaked = compare(before, after, "after_close")
    result("RESTORED" if not leaked else f"LEAKED:{len(leaked)}")


def close_then_teardown(mode):
    """C-04: the other order — close() first, then the loop teardown.  Both
    orders must end at the host's dispositions and neither may raise."""
    before = snapshot()
    sh = make_shell(mode)
    setup(sh)
    sh.close()
    mid = snapshot()
    compare(before, mid, "after_close")
    raised = None
    try:
        sh.interactive_manager.signal_manager.restore_default_handlers()
    except BaseException as exc:                       # noqa: BLE001
        raised = type(exc).__name__
    emit("teardown_raised", raised or "NOTHING")
    after = snapshot()
    leaked = compare(before, after, "after_teardown")
    result("RESTORED" if not leaked else f"LEAKED:{len(leaked)}")


def double_setup(mode):
    """C-05: setup twice (psh's __main__ installs at startup and the
    interactive loop re-runs setup).  FIRST-setup-wins setdefault must mean
    the restore target is still the PRE-PSH disposition."""
    before = snapshot()
    sh = make_shell(mode)
    setup(sh)
    setup(sh)
    sh.close()
    after = snapshot()
    leaked = compare(before, after, "after_close")
    emit("original_handlers_len",
         len(sh.interactive_manager.signal_manager._original_handlers))
    result("RESTORED" if not leaked else f"LEAKED:{len(leaked)}")


def reuse_after_close(mode):
    """C-06: close() then keep using the shell (close() only frees what the
    shell re-creates on demand).  A lease-based restore must re-acquire."""
    before = snapshot()
    sh = make_shell(mode)
    setup(sh)
    sh.close()
    rc = sh.run_command('echo reuse >/dev/null')
    emit("post_close_run_rc", rc)
    setup(sh)
    after_resetup = snapshot()
    emit("resetup_installed",
         len([n for n in before if before[n] is not after_resetup[n]]))
    sh.close()
    after = snapshot()
    leaked = compare(before, after, "after_second_close")
    result("RESTORED" if not leaked else f"LEAKED:{len(leaked)}")


def two_sequential_shells(mode):
    """C-07: shell 1 sets up and closes, then shell 2 does.  Does shell 2
    restore to the PRE-SHELL-1 host dispositions, or to shell 1's handlers?
    (The out-of-order-restore shape the SIGNALS lease exists to prevent.)"""
    before = snapshot()
    s1 = make_shell(mode)
    setup(s1)
    s1.close()
    mid = snapshot()
    compare(before, mid, "after_shell1_close")
    s2 = make_shell(mode)
    setup(s2)
    s2.close()
    after = snapshot()
    leaked = compare(before, after, "after_shell2_close")
    result("RESTORED" if not leaked else f"LEAKED:{len(leaked)}")


def managed_and_trap_composition(mode):
    """C-08: managed dispositions AND a trap-installed unmanaged one on the
    SAME shell — the composition cell the two SIGNALS families must satisfy
    together.  USR1 is leased today; the managed set is not."""
    usr1_before = signal.getsignal(signal.SIGUSR1)
    before = snapshot()
    sh = make_shell(mode)
    setup(sh)
    rc = sh.run_command("trap ':' USR1")
    emit("trap_rc", rc)
    emit("usr1_installed", signal.getsignal(signal.SIGUSR1) is not usr1_before)
    sh.close()
    after = snapshot()
    leaked = compare(before, after, "after_close")
    usr1_restored = signal.getsignal(signal.SIGUSR1) is usr1_before
    emit("usr1_restored", usr1_restored)
    emit("managed_restored", not leaked)
    result(f"USR1:{'RESTORED' if usr1_restored else 'LEAKED'}"
           f"|MANAGED:{'RESTORED' if not leaked else f'LEAKED:{len(leaked)}'}")


def platform_facts():
    """C-09: the platform facts the Linux-vs-macOS reasoning rests on
    (CLAUDE.md Known Test Issues #5) — asserted, never assumed."""
    emit("platform", sys.platform)
    for name in MANAGED:
        emit(f"has.{name}", hasattr(signal, name))
    emit("SIGCHLD_is_SIGCLD",
         getattr(signal, 'SIGCHLD', None) == getattr(signal, 'SIGCLD', None))
    emit("managed_set_has_realtime",
         any(n.startswith('SIGRT') for n in MANAGED))
    result("RECORDED")


def sibling_after_teardown(mode, teardown):
    """C-10/C-11: after the interactive-loop teardown (or without it), can an
    unrelated second shell take ownership?

    The MANAGED_SIGNALS lease introduces a new way to block siblings: a
    shell holding a lease over an ALREADY-DRAINED map has restored every
    global it took, so it must not keep rejecting other shells.  C-11 (no
    teardown, handlers still installed) SHOULD reject — that is the designed
    protection, not a regression."""
    from psh.core.process_lease import LeaseError, get_coordinator
    before = snapshot()
    s1 = make_shell(mode)
    setup(s1)
    if teardown:
        s1.interactive_manager.signal_manager.restore_default_handlers()
    coord = get_coordinator()
    held = sorted(c.kind.name for c in coord._components if not c.released)
    emit("s1_leases", ",".join(held) or "-")
    emit("map_drained",
         not s1.interactive_manager.signal_manager._original_handlers)
    s2 = make_shell(mode)
    try:
        rc = s2.run_command('echo sibling >/dev/null')
        outcome = "SIBLING_RAN"
        emit("s2_rc", rc)
    except LeaseError as exc:
        outcome = "SIBLING_REJECTED"
        emit("s2_error", str(exc).split(';')[0].replace(' ', '_'))
    finally:
        s2.close()
        s1.close()
    after = snapshot()
    compare(before, after, "after_both_close")
    result(outcome)


CELLS = {
    'C-10s': lambda: sibling_after_teardown('script', True),
    'C-10i': lambda: sibling_after_teardown('interactive', True),
    'C-11s': lambda: sibling_after_teardown('script', False),
    'C-01': lambda: basic('script'),
    'C-02': lambda: basic('interactive'),
    'C-03s': lambda: teardown_then_close('script'),
    'C-03i': lambda: teardown_then_close('interactive'),
    'C-04s': lambda: close_then_teardown('script'),
    'C-04i': lambda: close_then_teardown('interactive'),
    'C-05s': lambda: double_setup('script'),
    'C-05i': lambda: double_setup('interactive'),
    'C-06s': lambda: reuse_after_close('script'),
    'C-06i': lambda: reuse_after_close('interactive'),
    'C-07s': lambda: two_sequential_shells('script'),
    'C-07i': lambda: two_sequential_shells('interactive'),
    'C-08s': lambda: managed_and_trap_composition('script'),
    'C-08i': lambda: managed_and_trap_composition('interactive'),
    'C-09': platform_facts,
}


if __name__ == '__main__':
    CELL = sys.argv[1]
    if CELL == '--list':
        for name in CELLS:
            print(name)
        raise SystemExit(0)
    CELLS[CELL]()
