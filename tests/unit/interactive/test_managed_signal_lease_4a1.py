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

from psh.core.process_lease import (
    ComponentKind,
    LeaseRestoreError,
    get_coordinator,
)
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
    """Install mode handlers WITHOUT owning the process (embedder shape)."""
    sh.interactive_manager.signal_manager.setup_signal_handlers()


def _setup_owned(sh):
    """Install mode handlers the way the REAL entry points do.

    `psh/__main__.py` and `InteractiveManager.run_interactive_loop` both
    activate BEFORE calling setup, so a real psh process always installs
    under the active owner and gets the MANAGED_SIGNALS lease. Executing a
    command is how a test shell reaches that same state.
    """
    assert sh.run_command('true') == 0
    sh.interactive_manager.signal_manager.setup_signal_handlers()


@pytest.fixture(autouse=True)
def pristine_coordinator():
    """EN-5: the coordinator is a process-wide SINGLETON.

    These tests drive real shells through ownership and fault-injection
    paths, and a test that fails PART WAY through leaves the singleton
    holding a lease or a quarantine — which then bleeds into every later
    test in this xdist worker and presents as unrelated flakiness. Restoring
    the exact prior state on exit (quarantine included, since it blocks all
    later grants) is the same hygiene the coordinator's own suites use.
    """
    coord = get_coordinator()
    saved = (coord._owner_ref, coord._baselines, list(coord._activations),
             list(coord._components), list(coord._quarantined),
             coord._relinquish_pending)
    try:
        yield coord
    finally:
        (coord._owner_ref, coord._baselines, activations, components,
         quarantined, coord._relinquish_pending) = saved
        coord._activations[:] = activations
        coord._components[:] = components
        coord._quarantined[:] = quarantined


@pytest.fixture
def host_dispositions():
    """The pre-shell dispositions — the values close() must restore to."""
    before = _snapshot()
    usr2 = signal.getsignal(signal.SIGUSR2)
    try:
        yield before
    finally:
        _restore(before)
        signal.signal(signal.SIGUSR2, usr2)


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
        _setup_owned(sh)
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
        _setup_owned(sh)
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
    _setup_owned(sh)
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
        _setup_owned(sh)                                   # MANAGED_SIGNALS first
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


def test_setup_on_a_second_shell_does_not_take_ownership(host_dispositions):
    """INVERTED PIN (R9 point 4 — this assertion was the opposite in R3).

    Slot 4A.1 first made mode setup acquire the MANAGED_SIGNALS lease
    unconditionally, which TOOK the process owner token (and pulled in
    LOCALE through the grant glue). R3 accepted that widening as a declared
    delta; R8 BL-2 then showed what it cost — a shell that ran setup and was
    dropped without close() held both leases forever, because the signal
    registry keeps its owner reachable so no sweep ever classified it an
    orphan, and every later shell was rejected. R9 retracted the delta.

    Installing mode handlers must therefore NOT take ownership: a second
    shell calling setup while another shell owns the process is no longer
    rejected, and takes no lease.
    """
    owner = Shell(norc=True)
    other = _shell('script')
    try:
        # A trap, NOT `exec 3>/dev/null`: a permanent fd redirect run
        # in-process rewrites the runner's own fd 3 (parallel-safety rule 1).
        # An unmanaged-signal trap takes the SIGNALS lease and holds the
        # process just as firmly, touching no descriptors.
        assert owner.run_command("trap ':' USR2") == 0      # owner holds SIGNALS
        _setup(other)                                        # must NOT raise
        coord = get_coordinator()
        assert coord.current_owner() is owner.state, (
            "mode setup took the owner token")
        assert coord.find_component(other.state,
                                    ComponentKind.MANAGED_SIGNALS) is None
    finally:
        other.close()
        owner.close()
    assert _snapshot() == host_dispositions


def test_leaseless_setup_still_restores_at_close(host_dispositions):
    """MEDIUM-8's guarantee must NOT depend on owning the process.

    A shell that installs mode handlers without owning takes no lease, so
    close()'s unconditional drain is the only thing that restores them —
    and it must.
    """
    owner = Shell(norc=True)
    other = _shell('script')
    try:
        assert owner.run_command("trap ':' USR2") == 0
        _setup(other)
        assert get_coordinator().find_component(
            other.state, ComponentKind.MANAGED_SIGNALS) is None
        assert _snapshot() != host_dispositions, "setup installed nothing"
        other.close()
        assert _snapshot() == host_dispositions
    finally:
        try:
            other.close()
        except Exception:                                    # noqa: BLE001
            pass
        owner.close()


def test_late_activation_after_leaseless_setup_restores_exactly_once(
        host_dispositions):
    """EDGE (R9 point 2): setup while unowned, activate LATER, then close.

    The install is leaseless, so the map is the only record; a later
    activation must not double-restore or leave a second copy behind, and
    the coordinator must end clean. Both teardown orders are exercised.
    """
    for teardown_first in (False, True):
        sh = _shell('script')
        _setup(sh)                                   # leaseless: never owned
        assert get_coordinator().find_component(
            sh.state, ComponentKind.MANAGED_SIGNALS) is None
        assert sh.run_command('true') == 0           # activates HERE
        if teardown_first:
            sh.interactive_manager.signal_manager.restore_default_handlers()
            assert _snapshot() == host_dispositions
        sh.close()
        assert _snapshot() == host_dispositions, teardown_first
        assert get_coordinator().current_owner() is None, teardown_first


def test_aggregate_raise_still_restores_managed_dispositions(
        host_dispositions):
    """COMPOSITION (R9 point 1): aggregate-raise x managed-drain.

    close() surfaces a LeaseRestoreError when a component could not be
    proven restored — but the REST of teardown must complete first. A
    quarantined locale is no reason to leave psh's signal handlers installed
    in the host process.
    """
    sh = _shell('script')
    _setup(sh)
    assert sh.run_command('true') == 0               # own the process
    coord = get_coordinator()

    def boom():
        raise RuntimeError("injected restore failure")

    coord.acquire_component(sh.state, ComponentKind.STD_FDS, restore=boom,
                            description="injected")
    try:
        with pytest.raises(LeaseRestoreError):
            sh.close()
        assert _snapshot() == host_dispositions, (
            "the aggregate cost the shell its signal teardown")
        assert coord.quarantine_report()
    finally:
        coord.clear_quarantine()


def test_dropped_without_close_leaves_next_shell_runnable(host_dispositions):
    """R9 point 5 — the documented limitation, pinned.

    A shell that ran mode setup and was dropped WITHOUT close() leaks its
    handlers: the signal registry retains every registration, so the owner
    stays reachable and no sweep can reach it. That is exactly as base left
    it, and close() is the contract. What must NOT happen — and what R8
    BL-2 caught — is the next shell being REJECTED.
    """
    import gc

    sh = _shell('script')
    _setup(sh)
    del sh
    gc.collect()
    nxt = Shell(norc=True)
    try:
        assert nxt.run_command('echo next >/dev/null') == 0
    finally:
        nxt.close()


def test_two_leaseless_shells_chain_as_at_base(host_dispositions):
    """RECORD-ONLY (R9 point 3): two leaseless shells in sequence.

    Neither owns the process, so neither takes a lease, and shell B's
    "originals" are shell A's handlers. Restoration therefore CHAINS: B
    restores to A's handlers, then A restores to the host's. This is the
    base behaviour, recorded rather than claimed as a guarantee — the
    ordering protection only exists for shells that own the process.
    """
    owner = Shell(norc=True)
    try:
        assert owner.run_command("trap ':' USR2") == 0      # blocks ownership
        a = _shell('script')
        _setup(a)
        after_a = _snapshot()
        b = _shell('script')
        _setup(b)
        assert get_coordinator().find_component(
            b.state, ComponentKind.MANAGED_SIGNALS) is None
        b.close()
        chained = _snapshot()
        a.close()
        final = _snapshot()
        # RECORDED: B restores to A's handlers, then A to the host's.
        assert chained == after_a
        assert final == host_dispositions
    finally:
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
    _setup_owned(sh)
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


def test_dropped_shell_holding_a_trap_lease_still_rejects_the_next(
        host_dispositions):
    """B-03, the DOCUMENTED LIMITATION — ruled R2(c)(ii), pinned here.

    A shell that installed an UNMANAGED-signal trap and was dropped without
    close() keeps its handler installed in the process: the signal registry
    retains every registration, so the owner stays reachable and no sweep
    can classify it an orphan. The next shell is REJECTED, and that is
    CORRECT rather than a defect — the process really is still mutated, and
    `close()` is the contract.

    This is the deliberate counterpart to
    `test_dropped_without_close_leaves_next_shell_runnable`: mode-setup
    handlers are psh's own state and must never block a later shell, while
    a user's trap is user state whose loss would be silent.

    Previously this requirement was discharged against a gitignored probe
    rather than a committed test (R8 BL-3).
    """
    import gc

    from psh.core.process_lease import LeaseError

    usr1_before = signal.getsignal(signal.SIGUSR1)
    try:
        sh = Shell(norc=True)
        assert sh.run_command("trap ':' USR1") == 0
        assert signal.getsignal(signal.SIGUSR1) is not usr1_before
        del sh
        gc.collect()
        nxt = Shell(norc=True)
        try:
            with pytest.raises(LeaseError, match="competing process owner"):
                nxt.run_command('echo next >/dev/null')
        finally:
            nxt.close()
    finally:
        signal.signal(signal.SIGUSR1, usr1_before)
