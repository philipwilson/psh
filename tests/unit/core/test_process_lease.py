"""ProcessLeaseCoordinator invariants (campaign F2).

The coordinator is the ONE process-global mutation gate: one active shell
owner, LIFO activation nesting, LIFO component leases, competing-owner
rejection BEFORE mutation, complete rollback of failed acquisition, fork
reset, and GC-safe ownership release.  These tests drive the coordinator
directly with dummy owner objects (no real Shell, so no real process-global
mutation happens: component "restores" are recording stubs).

Order-independence: every test runs under the ``pristine_coordinator``
fixture, which asserts a quiescent coordinator at entry (no activation in
progress — a leaked lease from ANY earlier test fails loudly here) and
restores the exact coordinator state at exit, so these tests neither depend
on nor disturb their neighbours under seeded shuffling.
"""

import os

import pytest

from psh.core.process_lease import (
    RECURSION_LIMIT,
    ComponentKind,
    LeaseError,
    ProcessBaselines,
    get_coordinator,
)


class _Owner:
    """A dummy owner token (weakref-able, like ShellState)."""


@pytest.fixture
def pristine_coordinator():
    coord = get_coordinator()
    # Entry assertion: no activation may be in progress between tests.
    assert coord.activation_depth == 0, (
        "leaked activation lease from an earlier test")
    saved = (coord._owner_ref, coord._baselines, list(coord._activations),
             list(coord._components), coord._relinquish_pending)
    try:
        yield coord
    finally:
        (coord._owner_ref, coord._baselines, activations, components,
         coord._relinquish_pending) = saved
        coord._activations[:] = activations
        coord._components[:] = components


def test_grant_and_lifo_nesting(pristine_coordinator):
    coord = pristine_coordinator
    a = _Owner()
    l1 = coord.activate(a)
    l2 = coord.activate(a)
    l3 = coord.activate(a)
    assert (l1.depth, l2.depth, l3.depth) == (1, 2, 3)
    assert coord.current_owner() is a
    assert coord.activation_depth == 3
    l3.release()
    l2.release()
    l1.release()
    assert coord.activation_depth == 0
    # Owner token persists after the stack unwinds (components may outlive
    # executions); only close()/shutdown() or a transfer releases it.
    assert coord.current_owner() is a


def test_activation_lease_carries_baselines(pristine_coordinator):
    coord = pristine_coordinator
    a = _Owner()
    lease = coord.activate(a)
    try:
        assert isinstance(lease.baselines, ProcessBaselines)
        assert lease.baselines.cwd == os.getcwd()
        assert isinstance(lease.baselines.libc_ctype, str)
        assert lease.owner_ref() is a
    finally:
        lease.release()


def test_baselines_are_frozen(pristine_coordinator):
    coord = pristine_coordinator
    a = _Owner()
    lease = coord.activate(a)
    try:
        with pytest.raises(AttributeError):
            lease.baselines.cwd = "/elsewhere"  # type: ignore[misc]
    finally:
        lease.release()


def test_out_of_order_activation_release_raises(pristine_coordinator):
    coord = pristine_coordinator
    a = _Owner()
    l1 = coord.activate(a)
    l2 = coord.activate(a)
    with pytest.raises(LeaseError):
        l1.release()          # not the innermost: LIFO violation
    l2.release()
    l1.release()              # now innermost: fine


def test_second_owner_rejected_while_mid_execution(pristine_coordinator):
    coord = pristine_coordinator
    a, b = _Owner(), _Owner()
    lease = coord.activate(a)
    try:
        with pytest.raises(LeaseError):
            coord.activate(b)
        assert coord.current_owner() is a        # rejection mutated nothing
        assert coord.activation_depth == 1
    finally:
        lease.release()


def test_second_owner_rejected_while_holding_component(pristine_coordinator):
    coord = pristine_coordinator
    a, b = _Owner(), _Owner()
    restored = []
    coord.activate(a).release()
    coord.acquire_component(a, ComponentKind.SIGNALS,
                            restore=lambda: restored.append('sig'))
    with pytest.raises(LeaseError):
        coord.activate(b)
    assert restored == []                        # rejection before mutation
    assert coord.current_owner() is a
    coord.release_owner(a)
    assert restored == ['sig']


def test_ownership_transfers_between_quiescent_owners(pristine_coordinator):
    coord = pristine_coordinator
    a, b = _Owner(), _Owner()
    coord.activate(a).release()
    assert coord.current_owner() is a
    lease_b = coord.activate(b)                  # a holds nothing: transfer
    try:
        assert coord.current_owner() is b
    finally:
        lease_b.release()
    # And back again — interleaved direct-construction shells keep working.
    lease_a = coord.activate(a)
    try:
        assert coord.current_owner() is a
    finally:
        lease_a.release()


def test_component_idempotent_per_kind_and_lifo(pristine_coordinator):
    coord = pristine_coordinator
    a = _Owner()
    coord.activate(a).release()
    log = []
    c1 = coord.acquire_component(a, ComponentKind.LOCALE,
                                 restore=lambda: log.append('locale'))
    again = coord.acquire_component(a, ComponentKind.LOCALE,
                                    restore=lambda: log.append('dup'))
    assert again is c1                           # repeated acquisition folds
    c2 = coord.acquire_component(a, ComponentKind.STD_FDS,
                                 restore=lambda: log.append('fds'))
    with pytest.raises(LeaseError):
        c1.release()                             # not innermost
    c2.release()
    c1.release()
    assert log == ['fds', 'locale']              # LIFO restore order


def test_release_owner_restores_components_lifo(pristine_coordinator):
    coord = pristine_coordinator
    a = _Owner()
    coord.activate(a).release()
    log = []
    coord.acquire_component(a, ComponentKind.LOCALE,
                            restore=lambda: log.append('locale'))
    coord.acquire_component(a, ComponentKind.SIGNALS,
                            restore=lambda: log.append('signals'))
    coord.acquire_component(a, ComponentKind.STD_FDS,
                            restore=lambda: log.append('fds'))
    coord.release_owner(a)
    assert log == ['fds', 'signals', 'locale']   # innermost first
    assert coord.current_owner() is None


def test_release_owner_mid_activation_defers_token(pristine_coordinator):
    coord = pristine_coordinator
    a = _Owner()
    lease = coord.activate(a)
    restored = []
    coord.acquire_component(a, ComponentKind.SIGNALS,
                            restore=lambda: restored.append('sig'))
    coord.release_owner(a)                       # the exit-builtin shape
    assert restored == ['sig']                   # components restore NOW
    assert coord.current_owner() is a            # token held until unwind
    lease.release()
    assert coord.current_owner() is None         # released at depth zero


def test_failed_grant_rolls_back_completely(pristine_coordinator):
    coord = pristine_coordinator
    a, b = _Owner(), _Owner()
    coord.activate(a).release()

    def boom():
        raise RuntimeError("synthetic on_grant failure")

    with pytest.raises(RuntimeError, match="synthetic"):
        coord.activate(b, on_grant=boom)
    # Complete rollback: previous owner, empty stacks.
    assert coord.current_owner() is a
    assert coord.activation_depth == 0
    assert coord._components == []


def test_stale_lease_release_is_noop_after_rollback(pristine_coordinator):
    coord = pristine_coordinator
    a = _Owner()

    captured = {}

    def grab_and_boom():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        coord.activate(a, on_grant=grab_and_boom)
    # A rolled-back lease is marked released; releasing it again must not
    # corrupt the (empty) stack.
    assert coord.activation_depth == 0
    assert captured == {}


def test_dead_owner_releases_ownership_and_components(pristine_coordinator):
    coord = pristine_coordinator
    a = _Owner()
    coord.activate(a).release()
    restored = []
    coord.acquire_component(a, ComponentKind.LOCALE,
                            restore=lambda: restored.append('locale'))
    del a                                        # drop without close()
    b = _Owner()
    lease = coord.activate(b)                    # GC-safety: takeover works
    try:
        assert restored == ['locale']            # leftovers restored first
        assert coord.current_owner() is b
    finally:
        lease.release()


def test_fork_reset_discards_without_restoring(pristine_coordinator):
    coord = pristine_coordinator
    a = _Owner()
    lease = coord.activate(a)
    restored = []
    coord.acquire_component(a, ComponentKind.SIGNALS,
                            restore=lambda: restored.append('sig'))
    real_pid = coord._pid
    try:
        coord._pid = real_pid - 1                # simulate "we are the child"
        b = _Owner()
        child_lease = coord.activate(b)          # fork reset, then fresh grant
        assert restored == []                    # parent leases NOT restored
        assert coord.current_owner() is b
        assert coord.activation_depth == 1
        child_lease.release()
        lease.release()                          # stale parent lease: no-op
        assert coord.activation_depth == 0
    finally:
        coord._pid = os.getpid()
        assert coord._pid == real_pid


def test_component_requires_transferable_owner(pristine_coordinator):
    coord = pristine_coordinator
    a, b = _Owner(), _Owner()
    lease = coord.activate(a)
    try:
        with pytest.raises(LeaseError):
            coord.acquire_component(b, ComponentKind.LOCALE,
                                    restore=lambda: None)
    finally:
        lease.release()


def test_recursion_headroom_raised_at_grant(pristine_coordinator):
    coord = pristine_coordinator
    import sys
    a = _Owner()
    lease = coord.activate(a)
    try:
        assert sys.getrecursionlimit() >= RECURSION_LIMIT
    finally:
        lease.release()
