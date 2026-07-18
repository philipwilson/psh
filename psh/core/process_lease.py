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


class ComponentKind(Enum):
    """The process-global resources a shell may lease under its owner token."""

    LOCALE = auto()    # libc locale (LC_CTYPE / LC_COLLATE via setlocale)
    SIGNALS = auto()   # unmanaged-signal dispositions (trap USR1/ALRM/...)
    STD_FDS = auto()   # fds 0/1/2 + sys.std* streams (permanent exec redirects)


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
        self._relinquish_pending = False

    # -- introspection -------------------------------------------------

    def current_owner(self) -> Optional[Any]:
        """The live owning ShellState, or None (no owner / owner collected)."""
        self._check_fork()
        return self._owner_ref() if self._owner_ref is not None else None

    @property
    def activation_depth(self) -> int:
        return len(self._activations)

    def find_component(self, owner: Any,
                       kind: ComponentKind) -> Optional[ComponentLease]:
        """The owner's live lease for *kind*, or None."""
        self._check_fork()
        if self._owner_ref is None or self._owner_ref() is not owner:
            return None
        for lease in self._components:
            if lease.kind is kind and not lease.released:
                return lease
        return None

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
            try:
                _ensure_recursion_headroom()
                if on_grant is not None:
                    on_grant()
            except BaseException:
                self._activations.pop()
                lease.released = True
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
            try:
                _ensure_recursion_headroom()
                if on_grant is not None:
                    on_grant()
            except BaseException:
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

        The ``Shell.close()``/``shutdown()`` path.  A no-op when *owner* is
        not the current owner.  When called mid-activation (the exit builtin
        runs inside its own execution), components are restored immediately
        and the owner token is released when the activation stack unwinds to
        zero.
        """
        self._check_fork()
        if self._owner_ref is None or self._owner_ref() is not owner:
            return
        self._force_release_components()
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
        self._activations.clear()
        self._components.clear()
        self._owner_ref = None
        self._baselines = None
        self._relinquish_pending = False
        self._pid = os.getpid()

    def _ensure_owner(self, owner: Any) -> Tuple[bool, Tuple]:
        """Make *owner* the current owner; reject a competing live holder.

        Returns ``(changed, rollback_token)``.  Rejection happens BEFORE any
        mutation.  A previous owner that is quiescent (no activations, no
        components) — or already garbage-collected — hands ownership over;
        a collected owner's leftover component leases are force-restored
        first (GC-safety: drop-without-close still releases the globals).
        """
        current = self._owner_ref() if self._owner_ref is not None else None
        if current is owner:
            return False, ()
        if current is not None and (self._activations or self._components):
            kinds = [c.kind.name for c in self._components]
            raise LeaseError(
                "competing process owner: another live shell holds the "
                f"process activation (depth={len(self._activations)}, "
                f"components={kinds}); simultaneous active shells are "
                "unsupported — close()/shutdown() the other shell first "
                "(campaign F2)")
        if current is None:
            # Dead or absent owner: its activations are stale bookkeeping;
            # its component leases still describe live process mutations —
            # restore them so the globals return to their baselines.
            for act in self._activations:
                act.released = True
            self._activations.clear()
            self._force_release_components()
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
        """Restore and drop every component lease, innermost (LIFO) first."""
        while self._components:
            lease = self._components.pop()
            if lease.released:
                continue
            lease.released = True
            try:
                lease._restore()
            except Exception:
                pass  # best-effort: one failed restore must not block the rest

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
