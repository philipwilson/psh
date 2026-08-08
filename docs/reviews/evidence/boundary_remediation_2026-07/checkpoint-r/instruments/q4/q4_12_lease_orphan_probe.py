#!/usr/bin/env python3
"""Q4 axis-5: FRESH lease-orphan-sweep probe (not the suite's own cells). v2.

v1 errata (kept in the transcript): v1 asserted is_clean() immediately after
release_owner(B) while B's ACTIVATION lease was still held — the coordinator
defers the token release until the activation stack unwinds (documented
mid-activation contract), so that failure was probe misuse, not a defect.

v2 exercises the 4A.1 sweep from outside the suite's own cells, with the
mechanism made VISIBLE (instrument-mirror discipline): A's restore callable
records its invocation, so "orphan gone" is discriminated between SWEPT
(restore ran) and DROPPED (restore never ran — would be a regression of the
'restored, never merely dropped' claim).

  1. Owner A activates + acquires a LOCALE component lease with a recording
     restore; A (and its leases' strong refs) are dropped without release.
  2. Owner B activates: the sweep at the ownership event must RUN A's restore
     (deterministic, not GC-dependent), and find_component(B, LOCALE) must be
     None (A-18: no folding into a foreign lease).
  3. B acquires+releases properly (activation lease released too):
     coordinator ends is_clean().

Run with cwd = Q4 worktree and PYTHONPATH = worktree.
"""
import gc
import os

WT = ("/private/tmp/claude-501/-Users-pwilson-src-psh/"
      "05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q4/wt")
assert os.getcwd() == WT, f"cwd {os.getcwd()} != worktree"
import psh  # noqa: E402
assert os.path.realpath(psh.__file__).startswith(os.path.realpath(WT)), \
    psh.__file__

from psh.core.process_lease import (  # noqa: E402
    ComponentKind, ProcessLeaseCoordinator)


class Owner:
    def __init__(self, name):
        self.name = name


restore_log = []
coord = ProcessLeaseCoordinator()

a = Owner("A")
act_a = coord.activate(a)
coord.acquire_component(
    a, ComponentKind.LOCALE,
    restore=lambda: restore_log.append("A-LOCALE-restored"),
    description="q4 probe A")
print(f"A acquired: live components = {len(coord._live_components())}")

# strand A: drop every strong ref without releasing (rolled-back-owner shape)
del act_a
del a
gc.collect()
print(f"after strand: restore_log = {restore_log} (sweep must be at the "
      "ownership event, not GC)")

b = Owner("B")
act_b = coord.activate(b)
print(f"after B activate: restore_log = {restore_log}")
assert restore_log == ["A-LOCALE-restored"], (
    "orphan was not RESTORED at the ownership event")
found = coord.find_component(b, ComponentKind.LOCALE)
print(f"find_component(B, LOCALE) -> {found!r} (must be None: A-18)")
assert found is None, "A-18 REGRESSION: B handed A's orphan"

lease_b = coord.acquire_component(
    b, ComponentKind.LOCALE,
    restore=lambda: restore_log.append("B-LOCALE-restored"),
    description="q4 probe B")
coord.release_owner(b)
act_b.release()
print(f"end: restore_log = {restore_log}, live = "
      f"{len(coord._live_components())}, is_clean = {coord.is_clean()}")
assert restore_log == ["A-LOCALE-restored", "B-LOCALE-restored"]
assert coord.is_clean(), "coordinator not clean after full release"
print("LEASE-ORPHAN-SWEEP-OK")
