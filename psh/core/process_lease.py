"""One process activation owner: the ``ProcessLeaseCoordinator`` (campaign F2).

The public object model permits many ``Shell`` instances in one Python
process (the test tree constructs thousands), but several resources a shell
mutates are irreducibly PROCESS-GLOBAL: the libc locale (``setlocale``),
signal dispositions (``signal.signal``), the interpreter recursion limit,
the working directory, and the standard file descriptors / ``sys.std*``
streams.  Before this module each instance leased those independently, so
two live shells could interleave mutations and restore them out of order
(reappraisal #20 continuation, finding B) — e.g. overlapping trap leases
resurrecting a closed shell's handler, or a second shell writing into the
file a first shell's ``exec >file`` opened.

This module is the ONE gate for process-global ownership:

* ``ProcessLeaseCoordinator`` (a process-wide singleton) tracks the single
  ACTIVE shell owner.  ``ShellState.activate()`` obtains the owner token and
  a LIFO :class:`ActivationLease`; nested activation by the same owner is
  counted; a COMPETING owner — a *different* live shell currently holding
  leases — fails loudly (:class:`LeaseError`) BEFORE any mutation; a partial
  acquisition rolls back completely.
* Process-global mutations are recorded as LIFO :class:`ComponentLease`
  objects under the active token (``ComponentKind``: libc locale, unmanaged
  signal dispositions, permanent std-fd/stream rebinds).  Releasing a lease
  that is not the top of its stack raises; ``release_owner`` (the
  ``Shell.close()``/``shutdown()`` path) drains them in LIFO order, so an
  EMBEDDED shell restores every global it took on deactivation.
* Ownership TRANSFERS freely to another shell only while the previous owner
  is quiescent (activation depth zero) and holds no component leases — the
  compatible reading of "one active shell" that keeps sequential and
  interleaved direct-construction shells (the entire test tree) working,
  while the genuinely unsafe overlap states are now impossible instead of
  undefined (campaign doc section 16).
* Activation is IMPLICIT on first execution: the execution entry points
  (``SourceProcessor.execute_from_source``, ``Shell.execute_program`` /
  ``execute_command_list``, the REPL) acquire the lease lazily, so direct
  ``Shell()`` construction stays pure and unchanged for embedders.
* The interpreter recursion-limit raise — process-wide by nature — happens
  at ownership grant, never at construction (F1 handoff).  It only ever
  raises, so it is deliberately not restored (like the cwd baseline, it is
  documented process-owned; the baseline is recorded for introspection).

Fork safety: the coordinator state is per-process.  Every entry point
compares ``os.getpid()`` with the pid the state was built under and, on a
mismatch (we are a forked child holding the parent's copied state), discards
everything WITHOUT running restores — the parent's leases describe the
parent's process, and the child's dispositions were already reset by the
child signal policy.  Stale lease objects release as no-ops.

Threading: psh is a single-threaded shell; the coordinator is deliberately
not thread-safe (same stance as ``setlocale`` itself — see
``locale_service.py``).
"""
from __future__ import annotations

import os
import sys
import weakref
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, List, Optional, Tuple

from .locale_service import (
    active_locale,
    libc_locale_names,
    set_process_active_locale,
)

# Python-frame headroom for psh's recursive engines (parser, expansion,
# executor visitor). One shell function call burns ~18 Python frames and one
# nested compound ~12 (measured empirically, 2026-07-04), so CPython's default
# limit of 1000 capped shell recursion at ~50 calls — bash handles 5000+.
# 40,000 frames gives ~2,200 shell-call / ~3,300 nested-compound depth.
# Safe on the supported interpreters (>= 3.12): Python frames live on the
# heap and C-stack recursion is guarded separately, so a runaway raises
# RecursionError (converted to a clean shell error at the function-call
# boundary / last-resort guards) rather than overflowing the OS stack —
# verified to survive limits up to 60,000 even under `ulimit -s 512`.
RECURSION_LIMIT = 40_000


def _ensure_recursion_headroom() -> None:
    """Raise the interpreter recursion limit to RECURSION_LIMIT.

    Only ever raises, never lowers — an embedding process (e.g. the test
    runner) that already set a higher limit keeps it.  Process-wide by
    nature; idempotent.  Runs at activation-ownership grant (campaign F2:
    construction is process-pure; the raise is a process-global mutation and
    therefore belongs to the activation owner), which every execution entry
    reaches before parsing or executing anything.
    """
    if sys.getrecursionlimit() < RECURSION_LIMIT:
        sys.setrecursionlimit(RECURSION_LIMIT)


class LeaseError(RuntimeError):
    """Loud misuse of process-global ownership.

    Raised for a competing second active shell, an out-of-order (non-LIFO)
    lease release, or a release through a stale/foreign lease.  Deriving
    from ``RuntimeError`` makes it classify as an INTERNAL DEFECT under
    ``strict-errors`` (an embedding/test surfaces it immediately); a real
    ``python -m psh`` process has exactly one shell and can never trigger
    it.
    """


class LeaseRestoreError(LeaseError):
    """One or more component restores failed; the process is not proven clean.

    Raised by the deactivation paths after EVERY restore has been attempted
    (a failing restore must not block its siblings).  Carries the leases it
    could not restore, which are QUARANTINED on the coordinator: ownership
    does not silently return to "clean" when the globals may still be
    mutated.  Deriving from :class:`LeaseError` keeps it in the loud
    internal-defect family AND keeps existing ``pytest.raises(LeaseError)``
    call sites matching; per-failure detail rides on ``__notes__``.
    """

    def __init__(self, message: str,
                 failures: 'List[Tuple[ComponentLease, BaseException]]') -> None:
        super().__init__(message)
        self.failures = failures
        for lease, exc in failures:
            self.add_note(f"{lease.kind.name} ({lease.description or 'no description'}): "
                          f"{type(exc).__name__}: {exc}")


class ComponentKind(Enum):
    """The process-global resources a shell may lease under its owner token."""

    LOCALE = auto()    # libc locale (LC_CTYPE / LC_COLLATE via setlocale)
    SIGNALS = auto()   # unmanaged-signal dispositions (trap USR1/ALRM/...)
    STD_FDS = auto()   # fds 0/1/2 + sys.std* streams (permanent exec redirects)
    # Managed-signal dispositions: the INT/TERM/HUP/QUIT/TSTP/TTOU/TTIN/
    # CHLD/PIPE/WINCH handlers SignalManager installs at mode setup.  A kind
    # of its OWN, never folded into SIGNALS: `acquire_component` is
    # idempotent per (owner, kind), so two families sharing one kind would
    # keep only the FIRST acquirer's restore callable and silently drop the
    # other family's — measured in both acquisition orders (slot 4A.1
    # probe D-04).
    MANAGED_SIGNALS = auto()


@dataclass(frozen=True)
class ProcessBaselines:
    """Process-global state at ownership grant (introspection record).

    ``cwd`` and ``recursion_limit`` are DOCUMENTED process-owned facts
    (campaign doc section 16): they are recorded here but deliberately not
    restored on deactivation — ``cd`` persistence and the only-raises
    recursion policy are shell semantics, not leaks.  The libc names and
    stream identities are the pre-activation values the LOCALE / STD_FDS
    component leases restore to (each lease captures its own restorable
    copy at acquisition; these fields are the activation-time record).
    """

    cwd: Optional[str]
    libc_ctype: str
    libc_collate: str
    std_streams: Tuple[Any, Any, Any]
    recursion_limit: int


def _capture_baselines() -> ProcessBaselines:
    try:
        cwd: Optional[str] = os.getcwd()
    except OSError:
        cwd = None  # cwd deleted under us; bash tolerates this, so do we
    libc_ctype, libc_collate = libc_locale_names()
    return ProcessBaselines(
        cwd=cwd,
        libc_ctype=libc_ctype,
        libc_collate=libc_collate,
        std_streams=(getattr(sys, 'stdin', None), getattr(sys, 'stdout', None),
                     getattr(sys, 'stderr', None)),
        recursion_limit=sys.getrecursionlimit(),
    )


class ActivationLease:
    """One LIFO activation of the owning shell (nesting is counted).

    Carries the owner token (a weak reference to the owning ``ShellState``),
    this activation's 1-based nesting depth, and the process baselines
    captured at ownership grant.  ``release()`` must observe LIFO order —
    releasing a lease that is not the innermost unreleased activation
    raises :class:`LeaseError`.
    """

    __slots__ = ('_coordinator', 'owner_ref', 'baselines', 'depth', 'released')

    def __init__(self, coordinator: 'ProcessLeaseCoordinator',
                 owner_ref: 'weakref.ref[Any]', baselines: ProcessBaselines,
                 depth: int) -> None:
        self._coordinator = coordinator
        self.owner_ref = owner_ref
        self.baselines = baselines
        self.depth = depth
        self.released = False

    def release(self) -> None:
        self._coordinator._release_activation(self)


class ComponentLease:
    """An acquired process-global component under the active owner token.

    Holds the restore callable the acquirer supplied (which must NOT hold a
    strong reference to the owning shell where avoidable, so GC-based
    ownership release stays possible).  ``release()`` enforces LIFO order;
    ``ProcessLeaseCoordinator.release_owner`` drains all of an owner's
    components in LIFO order.
    """

    __slots__ = ('_coordinator', 'owner_ref', 'kind', 'description',
                 '_restore', 'released')

    def __init__(self, coordinator: 'ProcessLeaseCoordinator',
                 owner_ref: 'weakref.ref[Any]', kind: ComponentKind,
                 restore: Callable[[], None], description: str) -> None:
        self._coordinator = coordinator
        self.owner_ref = owner_ref
        self.kind = kind
        self.description = description
        self._restore = restore
        self.released = False

    def release(self) -> None:
        self._coordinator._release_component(self)


class ProcessLeaseCoordinator:
    """Minimal process-wide singleton enforcing ONE active shell owner."""

    def __init__(self) -> None:
        self._pid = os.getpid()
        self._owner_ref: Optional['weakref.ref[Any]'] = None
        self._baselines: Optional[ProcessBaselines] = None
        self._activations: List[ActivationLease] = []
        self._components: List[ComponentLease] = []
        self._quarantined: List[ComponentLease] = []
        self._relinquish_pending = False

    # -- introspection -------------------------------------------------

    def current_owner(self) -> Optional[Any]:
        """The live owning ShellState, or None (no owner / owner collected)."""
        self._check_fork()
        return self._owner_ref() if self._owner_ref is not None else None

    @property
    def activation_depth(self) -> int:
        return len(self._activations)

    def is_clean(self) -> bool:
        """True when this process holds NO un-restored global state.

        The question an embedder could not ask before (slot 4A.1): no owner
        token, no activation in progress, no live component lease, and
        nothing quarantined.  "No owner" alone was never the same question —
        a lease stranded by a rolled-back grant leaves the token empty while
        the globals stay mutated.
        """
        self._check_fork()
        return (self._owner_ref is None and not self._activations
                and not self._live_components() and not self._quarantined)

    def quarantine_report(self) -> Tuple[str, ...]:
        """One line per component that could not be proven restored.

        Empty when the process is not quarantined.  Quarantine happens when
        a restore callable raised: the lease is retained (not silently
        dropped) so the failure stays visible to the next ownership event
        instead of a half-restored process claiming to be clean.
        """
        self._check_fork()
        return tuple(f"{lease.kind.name}: {lease.description or 'no description'}"
                     for lease in self._quarantined)

    def clear_quarantine(self) -> Tuple[str, ...]:
        """Acknowledge the quarantine and drop it; returns what was cleared.

        Quarantine deliberately BLOCKS every later ownership grant — a
        process whose globals may still be mutated must not quietly hand
        itself to the next shell.  Clearing it is therefore an explicit act
        by whoever decided the process is usable after all: an embedder that
        repaired the globals itself, or a fault-injection test tearing down
        its own damage.  Nothing in psh calls this on the normal paths.
        """
        self._check_fork()
        report = self.quarantine_report()
        self._quarantined.clear()
        return report

    def find_component(self, owner: Any,
                       kind: ComponentKind) -> Optional[ComponentLease]:
        """The owner's OWN live lease for *kind*, or None.

        Filters by the lease's own ``owner_ref``, not merely by whether the
        CALLER is the current owner: a lease stranded by a rolled-back grant
        belongs to the rolled-back owner, and handing it to whoever now holds
        the token made that owner fold its own acquisition into a foreign
        lease — mutating a global under a restore callable that reverts to
        someone else's baseline, with its own baseline never captured
        (slot 4A.1 probe A-18).
        """
        self._check_fork()
        if self._owner_ref is None or self._owner_ref() is not owner:
            return None
        for lease in self._components:
            if (lease.kind is kind and not lease.released
                    and lease.owner_ref() is owner):
                return lease
        return None

    # -- lease discrimination ------------------------------------------

    def _live_components(self) -> List[ComponentLease]:
        return [lease for lease in self._components if not lease.released]

    def _components_of(self, owner: Optional[Any]) -> List[ComponentLease]:
        """The live leases *owner* actually holds (empty for None)."""
        if owner is None:
            return []
        return [lease for lease in self._components
                if not lease.released and lease.owner_ref() is owner]

    def _orphan_components(self, current: Optional[Any]) -> List[ComponentLease]:
        """Live leases that are NOT the current owner's.

        Covers both shapes: a lease whose owner was rolled back (its
        ``owner_ref`` names a different, possibly live, shell) and a lease
        whose owner has been collected (``owner_ref()`` is None).  Written as
        the complement of :meth:`_components_of` so a dead owner cannot slip
        through an ``is not current`` comparison when *current* is itself
        None.
        """
        own = self._components_of(current)
        return [lease for lease in self._live_components() if lease not in own]

    # -- the activation transaction ------------------------------------

    def activate(self, owner: Any, *,
                 on_grant: Optional[Callable[[], None]] = None) -> ActivationLease:
        """Obtain the owner token and a LIFO activation lease for *owner*.

        Same-owner nesting is counted (a fresh lease at depth+1).  A grant
        or transfer additionally raises the recursion headroom and runs
        *on_grant* (the owner's process-global installation glue, e.g. the
        active-locale registration); any failure there rolls the whole
        acquisition back — ownership, lease, and stack are exactly as
        before, and the error propagates.
        """
        self._check_fork()
        changed, rollback = self._ensure_owner(owner)
        assert self._baselines is not None
        lease = ActivationLease(self, self._owner_ref,  # type: ignore[arg-type]
                                self._baselines, len(self._activations) + 1)
        self._activations.append(lease)
        if changed:
            checkpoint = len(self._components)
            try:
                _ensure_recursion_headroom()
                if on_grant is not None:
                    on_grant()
            except BaseException as exc:
                self._activations.pop()
                lease.released = True
                self._unwind_components_to(checkpoint, exc)
                self._rollback_owner(rollback)
                raise
        return lease

    def acquire_component(self, owner: Any, kind: ComponentKind, *,
                          restore: Callable[[], None],
                          description: str = "",
                          on_grant: Optional[Callable[[], None]] = None
                          ) -> ComponentLease:
        """Acquire (or return the existing) *kind* lease for *owner*.

        Idempotent per ``(owner, kind)`` — a repeated permanent redirect or a
        second unmanaged trap folds into the one existing lease.  The caller
        captures its restorable baseline BEFORE calling (so a competing-owner
        rejection here happens before any mutation and leaves nothing
        acquired).

        A component acquisition can itself TRANSFER ownership (the embedder
        edge: a reactive locale write or direct trap install on a shell that
        is not mid-execution).  *on_grant* is the owner's grant glue — the
        same callback ``activate`` runs — executed exactly when ownership
        changed here, with the same complete-rollback contract, so a
        transfer through this path also installs the new owner's
        process-active locale instead of leaving the previous shell's
        registered.
        """
        self._check_fork()
        existing = self.find_component(owner, kind)
        if existing is not None:
            return existing
        changed, rollback = self._ensure_owner(owner)
        if changed:
            checkpoint = len(self._components)
            try:
                _ensure_recursion_headroom()
                if on_grant is not None:
                    on_grant()
            except BaseException as exc:
                self._unwind_components_to(checkpoint, exc)
                self._rollback_owner(rollback)
                raise
            # The grant glue may itself have acquired THIS kind (the locale
            # glue lease-applies a non-C profile): stay idempotent per
            # (owner, kind) rather than stacking a duplicate.
            existing = self.find_component(owner, kind)
            if existing is not None:
                return existing
        lease = ComponentLease(self, self._owner_ref,  # type: ignore[arg-type]
                               kind, restore, description)
        self._components.append(lease)
        return lease

    def release_owner(self, owner: Any) -> None:
        """Deactivate *owner*: restore its components (LIFO), drop ownership.

        The ``Shell.close()``/``shutdown()`` path.  When called mid-activation
        (the exit builtin runs inside its own execution), components are
        restored immediately and the owner token is released when the
        activation stack unwinds to zero.

        A caller that is NOT the current owner still restores its OWN leases
        (it may hold leases stranded by a rolled-back grant) — it simply does
        not touch the token or anyone else's leases.  Returning early there
        was what left an orphan nobody could clean up: the coordinator
        refused because the caller was not the owner, and the owner refused
        because the leases were not its own (slot 4A.1 probe A-10 / A5 seam
        3).
        """
        self._check_fork()
        if self._owner_ref is None or self._owner_ref() is not owner:
            self._release_components(self._components_of(owner))
            return
        self._release_components(self._components_of(owner))
        if self._activations:
            self._relinquish_pending = True
        else:
            self._clear_owner()

    # -- internals -----------------------------------------------------

    def _check_fork(self) -> None:
        if os.getpid() == self._pid:
            return
        # Forked child: the copied leases describe the PARENT's process.
        # Discard without restoring; mark them stale so release() no-ops.
        for act in self._activations:
            act.released = True
        for comp in self._components:
            comp.released = True
        for comp in self._quarantined:
            comp.released = True
        self._activations.clear()
        self._components.clear()
        self._quarantined.clear()
        self._owner_ref = None
        self._baselines = None
        self._relinquish_pending = False
        self._pid = os.getpid()

    def _ensure_owner(self, owner: Any) -> Tuple[bool, Tuple]:
        """Make *owner* the current owner; reject a competing live holder.

        Returns ``(changed, rollback_token)``.  Rejection happens BEFORE any
        mutation.  A previous owner that is quiescent (no activations, no
        components OF ITS OWN) — or already garbage-collected — hands
        ownership over; leases that are nobody's (a collected owner's, or a
        rolled-back grant's) are swept DETERMINISTICALLY first, at this
        ownership event, without depending on garbage collection.
        """
        current = self._owner_ref() if self._owner_ref is not None else None
        if current is owner:
            return False, ()
        if self._quarantined:
            raise LeaseError(
                "process ownership is QUARANTINED: "
                f"{len(self._quarantined)} component(s) could not be restored "
                f"and may still be mutated — {'; '.join(self.quarantine_report())}. "
                "No shell can take ownership until the process is proven "
                "clean (slot 4A.1)")
        # Sweep leases belonging to nobody (rolled-back grant) or to a
        # collected owner: they describe live process mutations, so they are
        # restored — never merely dropped — and never counted as a competing
        # owner's holdings.
        orphans = self._orphan_components(current)
        if orphans:
            self._release_components(orphans)
        own = self._components_of(current)
        if current is not None and (self._activations or own):
            held = "; ".join(f"{c.kind.name} ({c.description})" if c.description
                             else c.kind.name for c in own) or "none"
            raise LeaseError(
                "competing process owner: another live shell holds the "
                f"process activation (depth={len(self._activations)}, "
                f"components=[{held}]); simultaneous active shells are "
                "unsupported — close()/shutdown() the other shell first "
                "(campaign F2). A shell dropped WITHOUT close() that still "
                "holds a lease keeps its globals installed and is reported "
                "here: close() is the contract")
        if current is None:
            # Dead or absent owner: its activations are stale bookkeeping.
            for act in self._activations:
                act.released = True
            self._activations.clear()
        rollback = (self._owner_ref, self._baselines, self._relinquish_pending)
        self._owner_ref = weakref.ref(owner)
        self._baselines = _capture_baselines()
        self._relinquish_pending = False
        return True, rollback

    def _rollback_owner(self, rollback: Tuple) -> None:
        if rollback:
            self._owner_ref, self._baselines, self._relinquish_pending = rollback

    def _clear_owner(self) -> None:
        # A relinquished owner must not stay registered as the process-active
        # locale (bounce nit 3: after close() the slot pointed at the closed
        # shell's service; pattern helpers would keep consulting it). The
        # defensive getattr keeps the coordinator generic — a dummy owner in
        # a unit test simply has no `.locale`. Timing matters: this runs at
        # ACTUAL relinquish (immediately, or at depth-0 unwind for a
        # mid-execution close), never earlier — the shell's own EXIT trap
        # still pattern-matches under its own locale during shutdown.
        owner = self._owner_ref() if self._owner_ref is not None else None
        service = getattr(owner, 'locale', None)
        if service is not None and active_locale() is service:
            set_process_active_locale(None)
        self._owner_ref = None
        self._baselines = None
        self._relinquish_pending = False

    def _force_release_components(self) -> None:
        """Restore and drop EVERY component lease, innermost (LIFO) first."""
        self._release_components(self._live_components())

    def _release_components(self, leases: List[ComponentLease]) -> None:
        """Restore and drop *leases*, innermost (LIFO) first.

        Every restore is attempted even when an earlier one raises — a
        failing restore must not strand its siblings.  Failures are
        COLLECTED, the leases that could not be restored are QUARANTINED
        (retained and observable via :meth:`quarantine_report`, so the
        process is not reported clean when it may still be mutated), and one
        aggregate :class:`LeaseRestoreError` is raised naming all of them.
        Before slot 4A.1 the failures were swallowed and a half-restored
        process claimed to be clean.
        """
        if not leases:
            return
        targets = set(map(id, leases))
        failures: List[Tuple[ComponentLease, BaseException]] = []
        # LIFO: walk the live stack from the top, taking only the requested
        # leases (a non-owner caller releases just its own).
        for lease in [c for c in reversed(self._components)
                      if id(c) in targets and not c.released]:
            lease.released = True
            self._components.remove(lease)
            try:
                lease._restore()
            except Exception as exc:                     # noqa: BLE001
                failures.append((lease, exc))
                self._quarantined.append(lease)
        if failures:
            kinds = ", ".join(sorted(lease.kind.name for lease, _ in failures))
            raise LeaseRestoreError(
                f"process-global restore failed for {len(failures)} component"
                f"{'s' if len(failures) > 1 else ''} ({kinds}); the process "
                "cannot be proven clean and those components are QUARANTINED "
                "(see quarantine_report()). Every other restore was still "
                "attempted (campaign F2 / slot 4A.1)", failures)

    def _unwind_components_to(self, checkpoint: int,
                              cause: BaseException) -> None:
        """Restore components acquired ABOVE *checkpoint* (a failed grant).

        The grant glue can re-entrantly acquire component leases (the locale
        glue does).  When the glue then fails, those leases describe
        mutations of a grant that is about to be rolled back: restore them
        LIFO BEFORE the owner metadata reverts, so the rolled-back owner and
        the lease list cannot disagree about who owns what.  Without this the
        lease outlived its owner and every later activation was rejected —
        blaming a shell that held nothing (slot 4A.1 probes A-04/A-08).

        Restore failures here are attached to the propagating *cause* rather
        than replacing it: the caller asked why the grant failed, and the
        glue's own exception is that answer.
        """
        if len(self._components) <= checkpoint:
            return
        try:
            self._release_components(self._components[checkpoint:])
        except LeaseRestoreError as restore_error:
            cause.add_note(f"additionally, rolling back the failed grant: "
                           f"{restore_error}")
            for note in getattr(restore_error, '__notes__', ()):
                cause.add_note(f"  {note}")

    def _release_activation(self, lease: ActivationLease) -> None:
        self._check_fork()
        if lease.released:
            return  # stale (fork reset / rolled-back grant): releasing is a no-op
        if not self._activations or self._activations[-1] is not lease:
            raise LeaseError(
                "activation lease released out of order (LIFO): release the "
                "innermost activation first")
        lease.released = True
        self._activations.pop()
        if not self._activations and self._relinquish_pending:
            self._clear_owner()

    def _release_component(self, lease: ComponentLease) -> None:
        self._check_fork()
        if lease.released:
            return
        if not self._components or self._components[-1] is not lease:
            raise LeaseError(
                f"component lease ({lease.kind.name}) released out of order "
                "(LIFO): release the innermost component first")
        lease.released = True
        self._components.pop()
        lease._restore()


_coordinator: Optional[ProcessLeaseCoordinator] = None


def get_coordinator() -> ProcessLeaseCoordinator:
    """The process-wide coordinator singleton (created on first use)."""
    global _coordinator
    if _coordinator is None:
        _coordinator = ProcessLeaseCoordinator()
    return _coordinator
