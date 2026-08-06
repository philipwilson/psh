"""close() restores the managed signal dispositions exactly (MEDIUM-8).

Slot 4A.1. ``SignalManager`` installs process-global dispositions at mode
setup — INT/TERM/HUP/QUIT/TSTP/TTOU/TTIN/CHLD/PIPE/WINCH — recording each
prior disposition in ``_original_handlers``. Nothing OWNED them: only
trap-installed UNMANAGED signals took a component lease, and
``Shell.close()`` called ``signal_manager.close()``, which frees the
notifier fds and nothing else. So an embedded or transient shell left every
managed handler installed in the hosting process. Measured at base
a64eb6e8 with a ``getsignal`` census taken BEFORE the shell existed: 7
leaked in script mode, 10 in interactive, in every shape below.

They are now under a MANAGED_SIGNALS component lease — a kind of its own,
never ``ComponentKind.SIGNALS``, because ``acquire_component`` is idempotent
per (owner, kind) and one shared kind would keep only whichever family
acquired first and silently drop the other's restore.

Serial: these mutate process-global signal dispositions, following the
precedent of the sibling lease suites. Every test snapshots BEFORE the shell
under test exists and force-restores in a finally, so a failure cannot
pollute the runner.
"""

import signal

import pytest

from psh.core.process_lease import ComponentKind, get_coordinator
from psh.shell import Shell

pytestmark = pytest.mark.serial

#: Everything _setup_script_mode_handlers / _setup_interactive_mode_handlers
#: install through _install_handler.
MANAGED = [signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT,
           signal.SIGTSTP, signal.SIGTTOU, signal.SIGTTIN,
           signal.SIGCHLD, signal.SIGPIPE, signal.SIGWINCH]


def _snapshot():
    return {sig: signal.getsignal(sig) for sig in MANAGED}


def _restore(snapshot):
    for sig, handler in snapshot.items():
        try:
            signal.signal(sig, handler)
        except (OSError, ValueError, TypeError):
            pass


def _shell(mode):
    sh = Shell(norc=True)
    sh.state.is_script_mode = (mode == 'script')
    return sh


def _setup(sh):
    sh.interactive_manager.signal_manager.setup_signal_handlers()


@pytest.fixture
def host_dispositions():
    """The pre-shell dispositions — the values close() must restore to."""
    before = _snapshot()
    try:
        yield before
    finally:
        _restore(before)


@pytest.mark.parametrize("mode", ['script', 'interactive'])
def test_close_restores_every_managed_disposition(host_dispositions, mode):
    """MEDIUM-8's headline: 7 (script) / 10 (interactive) leaked at base."""
    sh = _shell(mode)
    _setup(sh)
    assert _snapshot() != host_dispositions, "setup installed nothing"
    sh.close()
    assert _snapshot() == host_dispositions


@pytest.mark.parametrize("mode", ['script', 'interactive'])
def test_double_setup_restores_the_pre_psh_dispositions(host_dispositions, mode):
    """psh's __main__ installs handlers and the interactive loop re-runs
    setup. FIRST-setup-wins (setdefault) must survive the lease: restoration
    returns to the PRE-PSH state, never to one of psh's own handlers."""
    sh = _shell(mode)
    _setup(sh)
    _setup(sh)
    sh.close()
    assert _snapshot() == host_dispositions


@pytest.mark.parametrize("mode", ['script', 'interactive'])
def test_teardown_then_close_is_idempotent(host_dispositions, mode):
    """The interactive loop's teardown runs, then close(). One draining
    restore serves both triggers, so the second finds nothing to do."""
    sh = _shell(mode)
    _setup(sh)
    sh.interactive_manager.signal_manager.restore_default_handlers()
    assert _snapshot() == host_dispositions
    sh.close()
    assert _snapshot() == host_dispositions


@pytest.mark.parametrize("mode", ['script', 'interactive'])
def test_close_then_teardown_is_idempotent(host_dispositions, mode):
    """The other order, which an embedder can genuinely produce."""
    sh = _shell(mode)
    _setup(sh)
    sh.close()
    assert _snapshot() == host_dispositions
    sh.interactive_manager.signal_manager.restore_default_handlers()
    assert _snapshot() == host_dispositions


@pytest.mark.parametrize("mode", ['script', 'interactive'])
def test_shell_reused_after_close_reacquires_and_restores(host_dispositions,
                                                          mode):
    """close() only frees what the shell re-creates on demand, so a closed
    shell stays usable. A re-setup must RE-ACQUIRE the lease — otherwise the
    second round of handlers would have no owner and leak."""
    sh = _shell(mode)
    _setup(sh)
    sh.close()
    assert sh.run_command('echo reuse >/dev/null') == 0
    _setup(sh)
    assert _snapshot() != host_dispositions
    sh.close()
    assert _snapshot() == host_dispositions


@pytest.mark.parametrize("mode", ['script', 'interactive'])
def test_sequential_shells_never_leak_a_dead_handler(host_dispositions, mode):
    """Two shells in a row net out to the host's dispositions, not to the
    first shell's handlers."""
    for _ in range(3):
        sh = _shell(mode)
        _setup(sh)
        sh.close()
    assert _snapshot() == host_dispositions


@pytest.mark.parametrize("mode", ['script', 'interactive'])
def test_managed_and_trap_families_both_restore(host_dispositions, mode):
    """COMPOSITION (X-3): both signal families on ONE shell.

    The managed dispositions and a trap-installed unmanaged one hold
    SEPARATE leases; close() must restore both exactly. Were they folded
    into a single ComponentKind.SIGNALS, acquisition being idempotent per
    (owner, kind) would keep only the first acquirer's restore and one
    family would silently leak."""
    usr1_before = signal.getsignal(signal.SIGUSR1)
    try:
        sh = _shell(mode)
        _setup(sh)
        assert sh.run_command("trap ':' USR1") == 0
        assert signal.getsignal(signal.SIGUSR1) is not usr1_before
        coord = get_coordinator()
        kinds = {c.kind for c in coord._components if not c.released}
        assert ComponentKind.MANAGED_SIGNALS in kinds
        assert ComponentKind.SIGNALS in kinds, "the two families must not fold"
        sh.close()
        assert signal.getsignal(signal.SIGUSR1) == usr1_before
        assert _snapshot() == host_dispositions
    finally:
        signal.signal(signal.SIGUSR1, usr1_before)


@pytest.mark.parametrize("mode", ['script', 'interactive'])
def test_trap_first_then_managed_also_restores_both(host_dispositions, mode):
    """The same composition in the OTHER acquisition order — the order is
    what a folded single kind is sensitive to, so both are pinned."""
    usr1_before = signal.getsignal(signal.SIGUSR1)
    try:
        sh = _shell(mode)
        assert sh.run_command("trap ':' USR1") == 0
        _setup(sh)
        sh.close()
        assert signal.getsignal(signal.SIGUSR1) == usr1_before
        assert _snapshot() == host_dispositions
    finally:
        signal.signal(signal.SIGUSR1, usr1_before)


def test_teardown_drops_the_inert_lease_so_siblings_are_not_blocked(
        host_dispositions):
    """Inert-lease arm 1: after the teardown has put every managed
    disposition back, the shell must stop counting as a holder.

    A lease left over an already-drained map would reject an unrelated
    shell for a reason that no longer exists — a hazard this slot's own
    MEDIUM-8 design introduced and had to remove."""
    sh = _shell('script')
    _setup(sh)
    coord = get_coordinator()
    assert coord.find_component(sh.state, ComponentKind.MANAGED_SIGNALS)
    sh.interactive_manager.signal_manager.restore_default_handlers()
    assert coord.find_component(sh.state, ComponentKind.MANAGED_SIGNALS) is None
    sh.close()


def test_teardown_keeps_the_lease_when_a_later_one_covers_it(host_dispositions):
    """Inert-lease arm 2: LIFO forbids dropping it when a later lease sits
    above — and leaving it is CORRECT there, because the shell still holds
    that later global and would rightly reject siblings anyway. close()
    releases both, in order."""
    usr1_before = signal.getsignal(signal.SIGUSR1)
    try:
        sh = _shell('script')
        _setup(sh)                                   # MANAGED_SIGNALS first
        assert sh.run_command("trap ':' USR1") == 0   # ... SIGNALS above it
        coord = get_coordinator()
        sh.interactive_manager.signal_manager.restore_default_handlers()
        assert coord.find_component(sh.state,
                                    ComponentKind.MANAGED_SIGNALS) is not None
        assert signal.getsignal(signal.SIGUSR1) is not usr1_before
        sh.close()                                    # both released, in order
        assert coord.find_component(sh.state,
                                    ComponentKind.MANAGED_SIGNALS) is None
        assert signal.getsignal(signal.SIGUSR1) == usr1_before
        assert _snapshot() == host_dispositions
    finally:
        signal.signal(signal.SIGUSR1, usr1_before)


def test_setup_on_a_second_shell_is_rejected_while_another_owns(
        host_dispositions):
    """DECLARED BEHAVIOR DELTA (slot 4A.1): mode setup now takes the process
    owner token, because acquiring any component lease requires one.

    So an embedder calling ``setup_signal_handlers()`` on a never-activated
    shell while ANOTHER shell owns the process is now rejected loudly
    instead of silently installing handlers over it. The real interactive
    path is unaffected — ``run_interactive_loop`` activates BEFORE calling
    setup — and ``python -m psh`` is a sole shell. This pins the rejection
    so the widening cannot regress unnoticed in either direction."""
    from psh.core.process_lease import LeaseError

    owner = Shell(norc=True)
    other = _shell('script')
    try:
        assert owner.run_command('exec 3>/dev/null') == 0   # owner holds STD_FDS
        with pytest.raises(LeaseError, match="competing process owner"):
            _setup(other)
        assert _snapshot() == host_dispositions, (
            "a rejected setup must not have installed anything")
    finally:
        other.close()
        owner.close()


def test_managed_lease_restore_references_no_shell(host_dispositions):
    """The ComponentLease contract: a restore callable must not reference its
    owning shell, so lease bookkeeping alone can never keep a dropped shell
    alive.

    Asserted structurally rather than by garbage collection, because GC
    cannot isolate THIS lease: the process-global SignalRegistry retains an
    unbounded history of every registration, each holding the handler — and
    the managed handlers are bound methods of SignalManager, so any shell
    that ever called setup_signal_handlers() stays reachable through the
    registry no matter what the leases do. (Verified by clearing the history
    and watching the state collect; reported separately as a retention issue
    in psh/utils/signal_utils.py, which slot 4A.1 does not own.)
    """
    sh = _shell('script')
    _setup(sh)
    coord = get_coordinator()
    lease = coord.find_component(sh.state, ComponentKind.MANAGED_SIGNALS)
    assert lease is not None
    restore = lease._restore
    reachable = list(getattr(restore, '__closure__', None) or ())
    captured = [cell.cell_contents for cell in reachable]
    captured += list(getattr(restore, '__defaults__', None) or ())
    assert sh.state not in captured
    assert sh not in captured
    assert not any(getattr(obj, '__self__', None) is sh.state
                   or getattr(obj, '__self__', None) is sh
                   for obj in captured)
    sh.close()
    restore()                                    # still callable, now inert
    assert _snapshot() == host_dispositions
