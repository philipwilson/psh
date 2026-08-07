"""I-A: coordinator-level fault-injection matrix for slot 4A.1 (Phase A).

ONE CELL PER PROCESS.  Invoked as ``python coord_matrix.py <cell-id>``; the
driver (run_matrix.sh) launches one subprocess per cell with cwd and
PYTHONPATH pointing at the tree under test, so the process-wide
ProcessLeaseCoordinator singleton is constructed FRESH for every cell and
cannot inherit residue from a sibling.  This is deliberately NOT the
brief-time probe's topology (all scenarios sharing one process/one
coordinator) — D-3.5 joint lesson: verify with a different method than the
one that produced the claim.

Output contract (machine-checkable; the driver derives counts, nothing is
hand-tallied):

    DISCRIM <abs path of the psh package under test>
    CELL <id> KEY=<name> VALUE=<value>          (zero or more observations)
    CELL <id> RESULT=<disposition>              (exactly one, last)

Dispositions: CLEAN, POISONED:<blamed owner>, ORPHANS:<n>, plus cell-specific
tokens documented at each cell.
"""
import gc  # noqa: F401  (used by cells that force collection)
import os
import sys
import weakref

import psh

print("DISCRIM", os.path.abspath(psh.__file__))

from psh.core.process_lease import (  # noqa: E402
    ComponentKind,
    LeaseError,
    get_coordinator,
)

COORD = get_coordinator()
KINDS = {'LOCALE': ComponentKind.LOCALE,
         'SIGNALS': ComponentKind.SIGNALS,
         'STD_FDS': ComponentKind.STD_FDS}

CELL = None


def emit(key, value):
    print(f"CELL {CELL} KEY={key} VALUE={value}")


def result(disposition):
    print(f"CELL {CELL} RESULT={disposition}")


class Owner:
    """A dummy owner token (weakref-able, like ShellState)."""

    locale = None            # _clear_owner consults this defensively

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"<Owner {self.name}>"


def live_components():
    return [c for c in COORD._components if not c.released]


def census(tag):
    """Emit the PUBLIC and PRIVATE views and whether they AGREE.

    Public view: what an embedder can see (current_owner / activation_depth /
    find_component).  Private view: the coordinator's own lists.  A
    coordinator that looks clean publicly while privately holding live
    component leases is an ORPHAN — the disagreement IS the finding, so it is
    reported as its own observation rather than asserted away.
    """
    owner = COORD.current_owner()
    live = live_components()
    kinds = sorted(c.kind.name for c in live)
    owned_by_current = [c for c in live
                        if c.owner_ref() is not None and c.owner_ref() is owner]
    orphans = [c for c in live if c.owner_ref() is not owner]
    # AGREEMENT, precisely: every live component lease must be REACHABLE
    # through the public surface.  find_component only ever reports leases of
    # the CURRENT owner, so an orphan (owner rolled back, or owner dead) is
    # invisible to any embedder — that invisibility is the observability gap,
    # not merely "an owner exists".  A quiescent owner holding the token with
    # no components is a legitimate state and must NOT read as disagreement.
    visible = [c for c in live
               if COORD.find_component(owner, c.kind) is c] if owner is not None else []
    invisible = [c for c in live if c not in visible]
    emit(f"{tag}.owner", getattr(owner, 'name', owner))
    emit(f"{tag}.depth", COORD.activation_depth)
    emit(f"{tag}.live_components", ",".join(kinds) or "-")
    emit(f"{tag}.owned_by_current", len(owned_by_current))
    emit(f"{tag}.orphans", len(orphans))
    # MISATTRIBUTION: find_component gates on "is the CALLER the current
    # owner", then returns any live lease of that kind — so a lease belonging
    # to a rolled-back owner is handed to whoever now holds the token.  That
    # is strictly worse than invisibility, and it is a third site (beyond
    # _ensure_owner and release_owner) lacking owner-ref discrimination.
    misattributed = [c for c in visible if c.owner_ref() is not owner]
    emit(f"{tag}.publicly_visible", len(visible))
    emit(f"{tag}.publicly_invisible", len(invisible))
    emit(f"{tag}.misattributed", len(misattributed))
    emit(f"{tag}.views_agree", not invisible and not misattributed)
    return orphans


def try_activate(owner, **kw):
    """Activate and classify the outcome as CLEAN or POISONED:<blame>."""
    try:
        lease = COORD.activate(owner, **kw)
    except LeaseError as exc:
        # The blame the error text pins on someone: whoever is registered as
        # the current owner when the rejection fires.
        blamed = COORD.current_owner()
        emit("lease_error", str(exc).split(';')[0].replace(' ', '_'))
        return f"POISONED:{getattr(blamed, 'name', blamed)}"
    lease.release()
    return "CLEAN"


# --------------------------------------------------------------------------
# A-01..A-03 — FIRST-OWNER activation whose grant glue fails after acquiring
# a component of each kind.  Brief S1 (A-01) is a MUST-HOLD green cell.
# --------------------------------------------------------------------------

def first_owner_glue_fail(kind_name):
    a = Owner("A")
    kind = KINDS[kind_name]

    def glue():
        COORD.acquire_component(a, kind, restore=lambda: None,
                                description=f"probe-orphan-{kind_name}")
        raise RuntimeError("injected post-acquire glue failure")

    try:
        COORD.activate(a, on_grant=glue)
        emit("activation", "UNEXPECTEDLY_SUCCEEDED")
    except RuntimeError as exc:
        emit("activation", f"failed_as_injected:{type(exc).__name__}")
    census("after_A_failure")
    c = Owner("C")
    outcome = try_activate(c)
    census("after_C")
    result(outcome)


# --------------------------------------------------------------------------
# A-04..A-06 — TRANSFER variant: quiescent previous owner B, A2's transfer
# grant fails after the glue acquired a component.  Brief S1b.
# --------------------------------------------------------------------------

def transfer_glue_fail(kind_name, then=None):
    b = Owner("B")
    COORD.activate(b).release()            # B: owner, quiescent, no components
    census("B_quiescent")
    a2 = Owner("A2")
    kind = KINDS[kind_name]

    def glue():
        COORD.acquire_component(a2, kind, restore=lambda: None,
                                description=f"probe-orphan-{kind_name}")
        raise RuntimeError("injected transfer-grant failure")

    try:
        COORD.activate(a2, on_grant=glue)
        emit("transfer", "UNEXPECTEDLY_SUCCEEDED")
    except RuntimeError as exc:
        emit("transfer", f"failed_as_injected:{type(exc).__name__}")
    orphans = census("after_A2_failure")
    emit("orphan_owner_is_A2",
         all(o.owner_ref() is a2 for o in orphans) if orphans else "n/a")
    if then is not None:
        return then(b, a2)
    c2 = Owner("C2")
    outcome = try_activate(c2)
    census("after_C2")
    result(outcome)


# --------------------------------------------------------------------------
# A-07 — NESTED (same-owner) re-activation with a failing glue: `changed` is
# False, so the glue must not run at all (control cell).
# --------------------------------------------------------------------------

def nested_glue_not_run():
    a = Owner("A")
    outer = COORD.activate(a)
    ran = []

    def glue():
        ran.append(True)
        raise RuntimeError("glue must not run on a nested activation")

    try:
        inner = COORD.activate(a, on_grant=glue)
        emit("nested_activation", "succeeded")
        inner.release()
    except RuntimeError:
        emit("nested_activation", "raised")
    emit("glue_ran", bool(ran))
    outer.release()
    COORD.release_owner(a)
    census("end")
    result("GLUE_SKIPPED" if not ran else "GLUE_RAN")


# --------------------------------------------------------------------------
# A-08 — acquire_component's OWN transfer-grant window: the glue re-entrantly
# acquires a DIFFERENT kind, then fails.  Second stranding window (seam 1b).
# --------------------------------------------------------------------------

def acquire_component_glue_fail(kind_name, inner_kind_name):
    b = Owner("B")
    COORD.activate(b).release()
    a2 = Owner("A2")
    kind, inner_kind = KINDS[kind_name], KINDS[inner_kind_name]

    def glue():
        COORD.acquire_component(a2, inner_kind, restore=lambda: None,
                                description=f"probe-inner-{inner_kind_name}")
        raise RuntimeError("injected acquire_component grant failure")

    try:
        COORD.acquire_component(a2, kind, restore=lambda: None,
                                description=f"probe-outer-{kind_name}",
                                on_grant=glue)
        emit("acquire", "UNEXPECTEDLY_SUCCEEDED")
    except RuntimeError as exc:
        emit("acquire", f"failed_as_injected:{type(exc).__name__}")
    census("after_failure")
    c2 = Owner("C2")
    outcome = try_activate(c2)
    census("after_C2")
    result(outcome)


# --------------------------------------------------------------------------
# A-10 / A-11 — can anyone SWEEP the orphan?
# --------------------------------------------------------------------------

def release_owner_from_orphan(b, a2):
    """A-10: the orphan's own shell calls release_owner (brief S3)."""
    COORD.release_owner(a2)
    orphans = census("after_release_owner_A2")
    result(f"ORPHANS:{len(orphans)}")


def release_owner_from_current(b, a2):
    """A-11: the INNOCENT current owner (B) closes while an orphan is live."""
    COORD.release_owner(b)
    orphans = census("after_release_owner_B")
    c2 = Owner("C2")
    outcome = try_activate(c2)
    census("after_C2")
    result(f"ORPHANS:{len(orphans)}|C2:{outcome}")


# --------------------------------------------------------------------------
# A-12..A-15 — restore-callable failures.
# --------------------------------------------------------------------------

def restore_failure(which):
    """A-12/A-13: release_owner with failing restore callables.

    `which` selects the failing subset: 'middle' (1 of 3) or 'all'.
    Observes whether the remaining restores are STILL ATTEMPTED and whether
    the failure reaches the caller at all.
    """
    a = Owner("A")
    COORD.activate(a).release()
    log = []

    def make(name, fail):
        def restore():
            log.append(name)
            if fail:
                raise RuntimeError(f"injected restore failure in {name}")
        return restore

    order = ['LOCALE', 'SIGNALS', 'STD_FDS']
    failing = {'middle': {'SIGNALS'}, 'all': set(order)}[which]
    for name in order:
        COORD.acquire_component(a, KINDS[name],
                                restore=make(name, name in failing),
                                description=f"probe-{name}")
    raised = None
    try:
        COORD.release_owner(a)
    except BaseException as exc:            # noqa: BLE001 — probing the shape
        raised = f"{type(exc).__name__}:{exc}"
    emit("restores_attempted", ",".join(log) or "-")
    emit("all_three_attempted", len(log) == 3)
    emit("raised_to_caller", raised or "NOTHING")
    census("after_release")
    result("SWALLOWED" if raised is None else f"RAISED:{raised.split(':')[0]}")


def restore_failure_in_dead_owner_sweep():
    """A-14: the dead/absent-owner sweep in _ensure_owner hits a failing
    restore — does the takeover still complete, and is the failure visible?"""
    a = Owner("A")
    COORD.activate(a).release()
    log = []

    def restore():
        log.append('LOCALE')
        raise RuntimeError("injected restore failure during sweep")

    COORD.acquire_component(a, ComponentKind.LOCALE, restore=restore,
                            description="probe-sweep")
    del a
    gc.collect()
    census("after_owner_dropped")
    c = Owner("C")
    raised = None
    try:
        outcome = try_activate(c)
    except BaseException as exc:            # noqa: BLE001
        outcome = "EXCEPTION"
        raised = f"{type(exc).__name__}:{exc}"
    emit("restore_attempted", bool(log))
    emit("raised_to_caller", raised or "NOTHING")
    census("after_C")
    result(outcome)


def restore_failure_single_lease_release():
    """A-15: ComponentLease.release() (the LIFO single-lease path) with a
    failing restore.

    Post-EN-2 this path is UNIFIED with the draining paths: the failure
    quarantines its lease and surfaces the same aggregate, rather than
    propagating raw while the coordinator reported itself clean."""
    a = Owner("A")
    COORD.activate(a).release()

    def restore():
        raise RuntimeError("injected restore failure on direct release")

    lease = COORD.acquire_component(a, ComponentKind.LOCALE, restore=restore,
                                    description="probe-direct")
    raised = None
    try:
        lease.release()
    except BaseException as exc:            # noqa: BLE001
        raised = f"{type(exc).__name__}"
    emit("raised_to_caller", raised or "NOTHING")
    emit("lease_marked_released", lease.released)
    emit("popped_from_list", lease not in COORD._components)
    census("after_release")
    result("PROPAGATED" if raised else "SWALLOWED")


# --------------------------------------------------------------------------
# A-16 — MUST-HOLD controls (guard rails that must stay green after the fix).
# --------------------------------------------------------------------------

def control_lifo_violation():
    a = Owner("A")
    l1 = COORD.activate(a)
    l2 = COORD.activate(a)
    raised = None
    try:
        l1.release()
    except LeaseError:
        raised = "LeaseError"
    l2.release()
    l1.release()
    COORD.release_owner(a)
    emit("out_of_order_raised", raised or "NOTHING")
    census("end")
    result("RAISES" if raised else "SILENT")


def control_genuine_competing_owner():
    """A LIVE shell mid-execution must still reject a second owner LOUDLY."""
    a, b = Owner("A"), Owner("B")
    lease = COORD.activate(a)
    outcome = try_activate(b)
    emit("owner_unchanged", COORD.current_owner() is a)
    emit("depth_unchanged", COORD.activation_depth == 1)
    lease.release()
    COORD.release_owner(a)
    census("end")
    # A rejection here is the DESIGNED protection, not poisoning — label it
    # for what it is so the summary column cannot be misread.
    result("REJECTED_AS_DESIGNED" if outcome.startswith("POISONED")
           else f"NOT_REJECTED:{outcome}")


def control_legitimate_quiescent_holder():
    """A-16d (R1 point 6, sub-shape ii): an owner at depth 0 that
    LEGITIMATELY holds its OWN components (alive and reachable — the
    between-commands `exec >f` shell) must KEEP rejecting a second owner.

    This is exactly the coordinator state S1b abuses, and the fix's
    discrimination is per-lease ``owner_ref`` vs current owner — so the
    control pins that the legitimate variant (owner_ref IS the current
    owner) still raises."""
    a, b = Owner("A"), Owner("B")
    COORD.activate(a).release()                      # depth 0, still owner
    lease = COORD.acquire_component(a, ComponentKind.STD_FDS,
                                    restore=lambda: None,
                                    description="probe-legit")
    emit("depth", COORD.activation_depth)
    emit("lease_owner_is_current_owner", lease.owner_ref() is COORD.current_owner())
    emit("owner_reachable", a is not None)
    outcome = try_activate(b)
    emit("owner_unchanged", COORD.current_owner() is a)
    COORD.release_owner(a)
    census("end")
    result("REJECTED_AS_DESIGNED" if outcome.startswith("POISONED")
           else f"NOT_REJECTED:{outcome}")


def control_fork_discard():
    """_check_fork discards WITHOUT running restores (semantics unchanged)."""
    a = Owner("A")
    lease = COORD.activate(a)
    restored = []
    COORD.acquire_component(a, ComponentKind.SIGNALS,
                            restore=lambda: restored.append('sig'),
                            description="probe-fork")
    real_pid = COORD._pid
    COORD._pid = real_pid - 1               # pretend we are the forked child
    b = Owner("B")
    child = COORD.activate(b)
    emit("parent_restores_ran", bool(restored))
    emit("child_owner", getattr(COORD.current_owner(), 'name', None))
    child.release()
    lease.release()                          # stale parent lease: no-op
    COORD._pid = os.getpid()
    COORD.release_owner(b)
    census("end")
    result("DISCARDED_WITHOUT_RESTORE" if not restored else "RESTORED")


# --------------------------------------------------------------------------
# A-17 — orphan lease identity: does the orphan still name its rolled-back
# owner, i.e. is owner_ref ENOUGH to discriminate (subtlety 3)?
# --------------------------------------------------------------------------

def orphan_owner_ref_discriminates():
    b = Owner("B")
    COORD.activate(b).release()
    a2 = Owner("A2")
    keep = []

    def glue():
        keep.append(COORD.acquire_component(
            a2, ComponentKind.LOCALE, restore=lambda: None,
            description="probe-discriminate"))
        raise RuntimeError("injected")

    try:
        COORD.activate(a2, on_grant=glue)
    except RuntimeError:
        pass
    lease = keep[0]
    emit("orphan_owner_ref_alive", lease.owner_ref() is not None)
    emit("orphan_owner_is_a2", lease.owner_ref() is a2)
    emit("current_owner_is_b", COORD.current_owner() is b)
    emit("ref_is_weak", isinstance(lease.owner_ref, weakref.ref))
    # And when the rolled-back owner is itself dropped:
    del a2
    gc.collect()
    emit("orphan_owner_ref_after_drop",
         "DEAD" if lease.owner_ref() is None else "ALIVE")
    census("end")
    result("DISCRIMINABLE" if lease.owner_ref is not None else "OPAQUE")


def orphan_is_handed_to_innocent_owner(b, a2):
    """A-18: after the S1b strand, does the INNOCENT owner B receive A2's
    orphan from find_component — and does B's own acquisition then FOLD into
    it, leaving B mutating a global under a lease whose restore belongs to
    A2?  (Downstream amplification of the missing owner-ref filter; the
    LOCALE case is exactly ShellState._acquire_locale_lease's guard.)"""
    found = COORD.find_component(b, ComponentKind.LOCALE)
    emit("find_component_B_returns_a_lease", found is not None)
    emit("returned_lease_belongs_to_A2",
         found is not None and found.owner_ref() is a2)
    b_restored = []
    folded = COORD.acquire_component(b, ComponentKind.LOCALE,
                                     restore=lambda: b_restored.append('B'),
                                     description="probe-B-own")
    emit("B_acquisition_folded_into_orphan", folded is found)
    emit("B_has_own_lease",
         any(c.owner_ref() is b for c in live_components()))
    COORD.release_owner(b)
    emit("B_own_restore_ran", bool(b_restored))
    census("end")
    result("MISATTRIBUTED" if folded is found else "SEPARATE")


CELLS = {
    'A-18': lambda: transfer_glue_fail('LOCALE',
                                       then=orphan_is_handed_to_innocent_owner),
    'A-01': lambda: first_owner_glue_fail('LOCALE'),
    'A-02': lambda: first_owner_glue_fail('SIGNALS'),
    'A-03': lambda: first_owner_glue_fail('STD_FDS'),
    'A-04': lambda: transfer_glue_fail('LOCALE'),
    'A-05': lambda: transfer_glue_fail('SIGNALS'),
    'A-06': lambda: transfer_glue_fail('STD_FDS'),
    'A-07': nested_glue_not_run,
    'A-08a': lambda: acquire_component_glue_fail('STD_FDS', 'LOCALE'),
    'A-08b': lambda: acquire_component_glue_fail('SIGNALS', 'LOCALE'),
    'A-08c': lambda: acquire_component_glue_fail('LOCALE', 'SIGNALS'),
    'A-10': lambda: transfer_glue_fail('LOCALE', then=release_owner_from_orphan),
    'A-11': lambda: transfer_glue_fail('LOCALE', then=release_owner_from_current),
    'A-12': lambda: restore_failure('middle'),
    'A-13': lambda: restore_failure('all'),
    'A-14': restore_failure_in_dead_owner_sweep,
    'A-15': restore_failure_single_lease_release,
    'A-16a': control_lifo_violation,
    'A-16b': control_genuine_competing_owner,
    'A-16d': control_legitimate_quiescent_holder,
    'A-16c': control_fork_discard,
    'A-17': orphan_owner_ref_discriminates,
}


if __name__ == '__main__':
    CELL = sys.argv[1]
    if CELL == '--list':
        for name in CELLS:
            print(name)
        raise SystemExit(0)
    CELLS[CELL]()
