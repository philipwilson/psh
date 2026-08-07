"""The activation/component transaction: fault injection at every boundary.

Slot 4A.1 (HIGH-8). The process-global ownership transaction was incomplete
at four seams, each reproduced by fault injection at base a64eb6e8:

1. A grant's glue can re-entrantly acquire component leases (the locale glue
   does).  When the glue then failed, the activation was popped and the owner
   metadata rolled back, but those components were LEFT — stranded under an
   owner that no longer existed.
2. ``_ensure_owner`` rejected a new owner whenever ANY component lease
   existed, without checking whose, so every later activation blamed a
   quiescent shell that held nothing.  ``find_component`` had the same gap
   and handed the innocent owner the orphan, which its own acquisition then
   folded into.
3. ``release_owner`` returned early for a non-owner caller, so the orphan's
   own shell could not clean up either — nobody could.
4. ``_force_release_components`` swallowed restore failures, so a
   half-restored process reported itself clean.

Every test drives the coordinator directly with dummy owners (no real Shell,
so no real process-global mutation: the "restores" are recording stubs).
The coordinator is a process-wide SINGLETON, so each test runs under
``pristine_coordinator``, which asserts quiescence on entry and restores the
exact prior state on exit INCLUDING the quarantine list — a poisoned
singleton would otherwise bleed into every later test in this xdist worker
and look like unrelated flakiness.

The A5 multi-shell poisoning battery is the first section: shell A fails
activation, and an unrelated shell C must still activate cleanly.
"""

import pytest

from psh.core.process_lease import (
    ComponentKind,
    LeaseError,
    LeaseRestoreError,
    get_coordinator,
)

KINDS = [ComponentKind.LOCALE, ComponentKind.SIGNALS, ComponentKind.STD_FDS,
         ComponentKind.MANAGED_SIGNALS]


class _Owner:
    """A dummy owner token (weakref-able, like ShellState)."""

    locale = None            # _clear_owner consults this defensively

    def __init__(self, name="owner"):
        self.name = name


@pytest.fixture
def coord():
    c = get_coordinator()
    assert c.activation_depth == 0, "leaked activation lease from an earlier test"
    saved = (c._owner_ref, c._baselines, list(c._activations),
             list(c._components), list(c._quarantined), c._relinquish_pending)
    try:
        yield c
    finally:
        (c._owner_ref, c._baselines, activations, components, quarantined,
         c._relinquish_pending) = saved
        c._activations[:] = activations
        c._components[:] = components
        c._quarantined[:] = quarantined


def _failing_glue(coordinator, owner, kind):
    """Grant glue that acquires *kind* and then fails — the real shape.

    ``ShellState._on_activation_grant`` acquires the LOCALE lease before it
    can fail, so a failure always leaves a freshly acquired component behind.
    """
    def glue():
        coordinator.acquire_component(owner, kind, restore=lambda: None,
                                      description=f"glue-{kind.name}")
        raise RuntimeError("injected grant-glue failure")
    return glue


# --- A5: multi-shell poisoning --------------------------------------------

@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
def test_first_owner_failed_activation_leaves_process_usable(coord, kind):
    """A5 verbatim, first-owner shape: A fails activation -> C activates."""
    a, c = _Owner("A"), _Owner("C")
    with pytest.raises(RuntimeError, match="injected"):
        coord.activate(a, on_grant=_failing_glue(coord, a, kind))
    lease = coord.activate(c)
    try:
        assert coord.current_owner() is c
    finally:
        lease.release()
        coord.release_owner(c)
    # Stated without the post-fix introspection API on purpose: this cell is
    # a MUST-HOLD (the dead/absent-owner sweep already self-healed the
    # first-owner shape at a64eb6e8), so it must read GREEN at base too.
    assert [c for c in coord._components if not c.released] == []


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
def test_transfer_rollback_does_not_poison_the_next_shell(coord, kind):
    """A5 transfer-rollback variant (red at a64eb6e8: C got a LeaseError
    naming B, a quiescent shell holding nothing)."""
    b, a2, c2 = _Owner("B"), _Owner("A2"), _Owner("C2")
    coord.activate(b).release()                  # B: owner, quiescent
    with pytest.raises(RuntimeError, match="injected"):
        coord.activate(a2, on_grant=_failing_glue(coord, a2, kind))
    assert coord.current_owner() is b            # ownership rolled back to B
    lease = coord.activate(c2)                   # ... and C2 is not blamed
    try:
        assert coord.current_owner() is c2
    finally:
        lease.release()
        coord.release_owner(c2)


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
def test_failed_grant_strands_no_component(coord, kind):
    """The stranding itself, stated directly: a failed grant leaves the
    component list exactly as it found it."""
    b, a2 = _Owner("B"), _Owner("A2")
    coord.activate(b).release()
    before = list(coord._components)
    with pytest.raises(RuntimeError, match="injected"):
        coord.activate(a2, on_grant=_failing_glue(coord, a2, kind))
    assert list(coord._components) == before


@pytest.mark.parametrize("kind", KINDS, ids=lambda k: k.name)
def test_failed_grant_runs_the_stranded_restore(coord, kind):
    """Unwinding RESTORES the component; it does not merely forget it.
    The globals the glue touched go back before the owner metadata does."""
    b, a2 = _Owner("B"), _Owner("A2")
    coord.activate(b).release()
    restored = []

    def glue():
        coord.acquire_component(a2, kind, restore=lambda: restored.append(kind),
                                description="glue")
        raise RuntimeError("injected grant-glue failure")

    with pytest.raises(RuntimeError):
        coord.activate(a2, on_grant=glue)
    assert restored == [kind]


def test_acquire_component_grant_window_also_unwinds(coord):
    """The SECOND grant window: acquire_component can itself transfer
    ownership and run the same glue (the embedder edge — a reactive locale
    write or a direct trap install on a quiescent shell)."""
    b, a2, c2 = _Owner("B"), _Owner("A2"), _Owner("C2")
    coord.activate(b).release()

    def glue():
        coord.acquire_component(a2, ComponentKind.LOCALE, restore=lambda: None,
                                description="inner")
        raise RuntimeError("injected acquire-grant failure")

    with pytest.raises(RuntimeError, match="injected"):
        coord.acquire_component(a2, ComponentKind.STD_FDS,
                                restore=lambda: None, description="outer",
                                on_grant=glue)
    lease = coord.activate(c2)
    try:
        assert coord.current_owner() is c2
    finally:
        lease.release()
        coord.release_owner(c2)


def test_acquire_component_grant_failure_strands_nothing(coord):
    """The acquire_component window's unwind, observed BEFORE the next
    ownership event.

    Stated at the moment of failure on purpose: the deterministic sweep in
    ``_ensure_owner`` would clean an orphan up at the next activation, which
    masks a missing unwind if the pin only ever looks after that point.
    """
    b, a2 = _Owner("B"), _Owner("A2")
    coord.activate(b).release()
    before = list(coord._components)

    def glue():
        coord.acquire_component(a2, ComponentKind.LOCALE, restore=lambda: None,
                                description="inner")
        raise RuntimeError("injected acquire-grant failure")

    with pytest.raises(RuntimeError, match="injected"):
        coord.acquire_component(a2, ComponentKind.STD_FDS,
                                restore=lambda: None, description="outer",
                                on_grant=glue)
    assert list(coord._components) == before


def test_components_unwind_before_the_owner_rolls_back(coord):
    """Charter order: newly acquired components are restored while the
    FAILING grant is still the recorded owner, and only then does ownership
    revert. A restore that runs after the rollback would see — and could act
    on — an owner that no longer matches the globals it is putting back."""
    b, c = _Owner("B"), _Owner("C")
    coord.activate(b).release()
    owner_during_restore = []

    def glue():
        coord.acquire_component(
            c, ComponentKind.LOCALE,
            restore=lambda: owner_during_restore.append(coord.current_owner()),
            description="glue")
        raise RuntimeError("injected")

    with pytest.raises(RuntimeError):
        coord.activate(c, on_grant=glue)
    assert owner_during_restore == [c], (
        "the component restore must run BEFORE the owner metadata reverts")
    assert coord.current_owner() is b


def _plant_orphan(coord, owner, kind=ComponentKind.LOCALE, restore=None):
    """A live lease whose owner is NOT the current owner.

    Post-fix this state is no longer reachable through the grant path (the
    unwind prevents it), so the recovery arms that exist to handle it are
    exercised by constructing it directly — otherwise they would be
    unfalsifiable code.
    """
    lease = coord.acquire_component(owner, kind,
                                    restore=restore or (lambda: None),
                                    description="planted orphan")
    coord._components.remove(lease)
    lease.released = False
    coord._owner_ref = None
    coord._components.append(lease)
    return lease


def test_release_owner_from_a_non_owner_restores_its_own_lease(coord):
    """Seam 3: the orphan's own shell must be able to clean up, whatever the
    token says. Red at a64eb6e8, where release_owner returned early for any
    non-owner caller and nobody could restore the lease."""
    import weakref

    a, b = _Owner("A"), _Owner("B")
    restored = []
    coord.activate(a).release()
    _plant_orphan(coord, a, restore=lambda: restored.append('a-locale'))
    # Hand the token to B WITHOUT going through _ensure_owner, whose sweep
    # would restore the lease on the way in. That sweep is why the normal
    # paths can no longer produce this state at all — so the safety net in
    # release_owner is exercised by constructing the state it exists to
    # catch, rather than left as code no test can falsify.
    coord._owner_ref = weakref.ref(b)
    assert coord.current_owner() is b
    coord.release_owner(a)                       # A is NOT the owner now
    assert restored == ['a-locale']
    coord.release_owner(b)


def test_nested_activation_never_runs_the_grant_glue(coord):
    """Control: a same-owner nested activation does not re-grant, so there is
    no second glue call and no second checkpoint to unwind."""
    a = _Owner("A")
    outer = coord.activate(a)
    ran = []
    inner = coord.activate(a, on_grant=lambda: ran.append(True))
    inner.release()
    outer.release()
    coord.release_owner(a)
    assert ran == []


# --- orphan discrimination and sweep --------------------------------------

def test_release_owner_sweeps_the_callers_own_orphan(coord):
    """Seam 3 (red at base: release_owner early-returned for a non-owner, so
    the orphan's own shell could not clean up either)."""
    b, a2 = _Owner("B"), _Owner("A2")
    coord.activate(b).release()
    restored = []

    def glue():
        coord.acquire_component(a2, ComponentKind.LOCALE,
                                restore=lambda: restored.append('locale'),
                                description="glue")
        raise RuntimeError("injected")

    with pytest.raises(RuntimeError):
        coord.activate(a2, on_grant=glue)
    # The unwind already restored it; a later release_owner by the same
    # owner is then a no-op rather than a second restore.
    assert restored == ['locale']
    coord.release_owner(a2)
    assert restored == ['locale']
    assert not [c for c in coord._components if not c.released]


def test_find_component_never_returns_another_owners_lease(coord):
    """A-18: find_component gated on who was ASKING, not on whose lease it
    returned, so an innocent owner received a foreign lease and folded its
    own acquisition into it — mutating a global under a restore that reverts
    to someone else's baseline, its own baseline never captured."""
    b, a2 = _Owner("B"), _Owner("A2")
    coord.activate(b).release()
    stranded = []

    def glue():
        stranded.append(coord.acquire_component(
            a2, ComponentKind.LOCALE, restore=lambda: None, description="glue"))
        raise RuntimeError("injected")

    # Strand a lease that survives the unwind by holding it directly: the
    # unwind restores and drops it, so re-create the disagreement the only
    # way it can now exist — a lease whose owner_ref is not the current
    # owner, planted directly.
    with pytest.raises(RuntimeError):
        coord.activate(a2, on_grant=glue)
    orphan = stranded[0]
    orphan.released = False                      # simulate a surviving orphan
    coord._components.append(orphan)
    try:
        assert coord.find_component(b, ComponentKind.LOCALE) is None
        own_restored = []
        mine = coord.acquire_component(b, ComponentKind.LOCALE,
                                       restore=lambda: own_restored.append('B'),
                                       description="B's own")
        assert mine is not orphan
        coord.release_owner(b)
        assert own_restored == ['B'], "B's own restore must run"
    finally:
        orphan.released = True
        if orphan in coord._components:
            coord._components.remove(orphan)


def test_live_owner_holding_its_own_lease_still_rejects(coord):
    """MUST-HOLD, sub-shape (ii): the discrimination must not weaken into
    never-rejecting. An owner at depth 0 legitimately holding its OWN
    component (the between-commands `exec >f` shell) keeps rejecting."""
    a, b = _Owner("A"), _Owner("B")
    coord.activate(a).release()
    coord.acquire_component(a, ComponentKind.STD_FDS, restore=lambda: None,
                            description="legit")
    with pytest.raises(LeaseError, match="competing process owner"):
        coord.activate(b)
    assert coord.current_owner() is a
    coord.release_owner(a)


def test_live_owner_mid_execution_still_rejects(coord):
    """MUST-HOLD, sub-shape (i): a live activation rejects a second shell."""
    a, b = _Owner("A"), _Owner("B")
    lease = coord.activate(a)
    try:
        with pytest.raises(LeaseError, match="competing process owner"):
            coord.activate(b)
        assert coord.activation_depth == 1
    finally:
        lease.release()
        coord.release_owner(a)


def test_rejection_names_only_the_owners_own_components(coord):
    """Blame accuracy: the message lists what the CURRENT owner holds."""
    a, b = _Owner("A"), _Owner("B")
    coord.activate(a).release()
    coord.acquire_component(a, ComponentKind.STD_FDS, restore=lambda: None,
                            description="standard fds")
    with pytest.raises(LeaseError) as excinfo:
        coord.activate(b)
    assert "STD_FDS" in str(excinfo.value)
    assert "LOCALE" not in str(excinfo.value)
    coord.release_owner(a)


# --- restore failures: aggregate + quarantine ------------------------------

def test_every_restore_is_attempted_when_one_fails(coord):
    """Seam 5, half one: a failing restore must not strand its siblings."""
    a = _Owner("A")
    coord.activate(a).release()
    log = []

    def make(name, fail):
        def restore():
            log.append(name)
            if fail:
                raise RuntimeError(f"injected failure in {name}")
        return restore

    for name, kind in (('locale', ComponentKind.LOCALE),
                       ('signals', ComponentKind.SIGNALS),
                       ('fds', ComponentKind.STD_FDS)):
        coord.acquire_component(a, kind, restore=make(name, name == 'signals'),
                                description=name)
    with pytest.raises(LeaseRestoreError):
        coord.release_owner(a)
    assert log == ['fds', 'signals', 'locale']   # all three, LIFO
    coord.clear_quarantine()


def test_restore_failure_is_surfaced_not_swallowed(coord):
    """Seam 5, half two (red at base: swallowed, and the coordinator then
    reported itself clean)."""
    a = _Owner("A")
    coord.activate(a).release()
    coord.acquire_component(a, ComponentKind.LOCALE,
                            restore=_boom, description="libc locale")
    with pytest.raises(LeaseRestoreError) as excinfo:
        coord.release_owner(a)
    assert "LOCALE" in str(excinfo.value)
    assert not coord.is_clean(), "a half-restored process is not clean"
    assert coord.quarantine_report()
    assert "libc locale" in coord.quarantine_report()[0]
    coord.clear_quarantine()


def _boom():
    raise RuntimeError("injected restore failure")


def test_quarantine_blocks_the_next_owner_and_names_the_reason(coord):
    """A quarantined process must not silently hand itself to the next shell,
    and the rejection must name the quarantine — never blame an owner."""
    a, b = _Owner("A"), _Owner("B")
    coord.activate(a).release()
    coord.acquire_component(a, ComponentKind.LOCALE, restore=_boom,
                            description="libc locale")
    with pytest.raises(LeaseRestoreError):
        coord.release_owner(a)
    with pytest.raises(LeaseError) as excinfo:
        coord.activate(b)
    message = str(excinfo.value)
    assert "QUARANTINED" in message
    assert "LOCALE" in message
    assert "competing process owner" not in message
    coord.clear_quarantine()
    lease = coord.activate(b)                    # usable again once cleared
    lease.release()
    coord.release_owner(b)
    assert coord.is_clean()


def test_aggregate_carries_every_failure_as_a_note(coord):
    """One aggregate, not the first failure only."""
    a = _Owner("A")
    coord.activate(a).release()
    for kind in (ComponentKind.LOCALE, ComponentKind.SIGNALS):
        coord.acquire_component(a, kind, restore=_boom, description=kind.name)
    with pytest.raises(LeaseRestoreError) as excinfo:
        coord.release_owner(a)
    assert len(excinfo.value.failures) == 2
    notes = "\n".join(getattr(excinfo.value, '__notes__', []))
    assert "LOCALE" in notes and "SIGNALS" in notes
    coord.clear_quarantine()


def test_single_lease_release_quarantines_like_the_draining_paths(coord):
    """EN-2: one failure meaning, however the release was reached.

    `ComponentLease.release()` used to let a failing restore propagate
    RAW and leave the coordinator reporting itself clean, while the very
    same failing restore reached through `release_owner` quarantined and
    surfaced an aggregate. The asymmetry was invisible: whether the process
    counted as provably-clean depended on which release path a caller
    happened to use.
    """
    a = _Owner("A")
    coord.activate(a).release()
    lease = coord.acquire_component(a, ComponentKind.LOCALE, restore=_boom,
                                    description="libc locale")
    with pytest.raises(LeaseRestoreError):
        lease.release()
    assert not coord.is_clean()
    assert coord.quarantine_report()
    assert "LOCALE" in coord.quarantine_report()[0]
    coord.clear_quarantine()
    coord.release_owner(a)


def test_restore_failure_during_a_failed_grant_keeps_the_original_error(coord):
    """The caller asked why the GRANT failed; the glue's own exception is
    that answer, with the restore trouble attached rather than substituted."""
    b, a2 = _Owner("B"), _Owner("A2")
    coord.activate(b).release()

    def glue():
        coord.acquire_component(a2, ComponentKind.LOCALE, restore=_boom,
                                description="glue")
        raise RuntimeError("injected grant-glue failure")

    with pytest.raises(RuntimeError, match="injected grant-glue failure") as ex:
        coord.activate(a2, on_grant=glue)
    assert any("LOCALE" in note for note in getattr(ex.value, '__notes__', []))
    coord.clear_quarantine()


# --- introspection --------------------------------------------------------

def test_is_clean_distinguishes_no_owner_from_no_state(coord):
    """"No owner" was never the same question as "nothing held": a lease
    stranded by a rolled-back grant leaves the token empty while the globals
    stay mutated."""
    assert coord.is_clean()
    a = _Owner("A")
    lease = coord.activate(a)
    assert not coord.is_clean()
    lease.release()
    coord.release_owner(a)
    assert coord.is_clean()


# --- composition: the fixes must compose with each other ------------------

def test_checkpoint_unwind_while_a_signals_lease_is_held(coord):
    """COMPOSITION (X-1): checkpoint-unwind x SIGNALS lease.

    The owner already holds a lease from an EARLIER grant when a later
    grant's glue fails. The unwind must take back exactly what the failed
    glue acquired — not the lease that was there before it, and not less.
    """
    b, c = _Owner("B"), _Owner("C")
    coord.activate(b).release()                  # quiescent previous owner
    restored = []

    def glue():
        # A real grant glue installs SEVERAL globals before it can fail:
        # ShellState._on_activation_grant registers the process-active
        # locale and lease-applies it, and a shell mid-setup can be holding
        # signal dispositions in the same window.
        for kind in (ComponentKind.SIGNALS, ComponentKind.MANAGED_SIGNALS,
                     ComponentKind.LOCALE):
            coord.acquire_component(
                c, kind, restore=lambda k=kind: restored.append(k.name),
                description=f"glue-{kind.name}")
        raise RuntimeError("injected grant-glue failure")

    with pytest.raises(RuntimeError, match="injected"):
        coord.activate(c, on_grant=glue)
    # Every one of them restored, innermost first, and none stranded.
    assert restored == ['LOCALE', 'MANAGED_SIGNALS', 'SIGNALS']
    assert [lease for lease in coord._components if not lease.released] == []
    assert coord.current_owner() is b            # and B is never blamed
    coord.release_owner(b)


def test_failed_acquisition_while_quarantined_does_not_compound(coord):
    """COMPOSITION (X-2): quarantine x a later acquisition.

    Once quarantined, every ownership event must fail with the QUARANTINE
    reason — not with a competing-owner story, and not by quietly acquiring
    something new on top of a process that cannot be proven clean."""
    a, b = _Owner("A"), _Owner("B")
    coord.activate(a).release()
    coord.acquire_component(a, ComponentKind.STD_FDS, restore=_boom,
                            description="standard fds")
    with pytest.raises(LeaseRestoreError):
        coord.release_owner(a)
    assert coord.quarantine_report()
    with pytest.raises(LeaseError, match="QUARANTINED"):
        coord.acquire_component(b, ComponentKind.STD_FDS,
                                restore=lambda: None, description="B's fds")
    assert not [c for c in coord._components if not c.released], \
        "nothing may be acquired while quarantined"
    coord.clear_quarantine()


def test_fork_reset_clears_quarantine_too(coord):
    """MUST-HOLD: fork discards WITHOUT restoring — the parent's leases
    describe the parent's process. Quarantine is parent state as well."""
    import os
    a = _Owner("A")
    coord.activate(a).release()
    coord.acquire_component(a, ComponentKind.LOCALE, restore=_boom,
                            description="libc locale")
    with pytest.raises(LeaseRestoreError):
        coord.release_owner(a)
    assert coord.quarantine_report()
    real_pid = coord._pid
    try:
        coord._pid = real_pid - 1                # "we are the forked child"
        assert coord.is_clean()                  # child starts clean
        assert coord.quarantine_report() == ()
    finally:
        coord._pid = os.getpid()
        coord._quarantined.clear()
