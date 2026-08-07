#!/usr/bin/env python3
"""P3b — the PROPOSED design measured end-to-end, on its own terms.

P3/P4 measured a candidate space where every arm kept all three fields. The
design I actually propose for ruling (a)+(b)+(c) is narrower, so it gets its
own number rather than an inference from the candidate table:

  D  = read-only properties over private __slots__   (P3's C4 shape: the only
       arm with ZERO measured construction cost that still rejects writes)
     + `binding` OMITTED                             (census: 0 production
       consumers; removes the live-cell leak STRUCTURALLY rather than
       guarding it)
     + BOTH nullary statuses as shared FROZEN singletons — MISSING *and*
       PRESENT_UNSET. Once `binding` is gone, a PRESENT_UNSET result carries
       no per-instance data, so it can be a constant exactly like MISSING.

That third point is the interesting one: at BASE, PRESENT_UNSET allocates a
fresh instance on every declared-unset read. Under D it allocates nothing.
So D should be FASTER than base on the PRESENT_UNSET path while being
immutable everywhere — this instrument's job is to confirm or refute that,
not to assume it.

Arms:
  BASE  the real psh.core.variable_lookup.VariableLookup at this SHA
  D     the proposed design
  D3    same as D but with a raising __setattr__ instead of properties
        (the stricter-threat-model variant, priced for ruling (c))

Methodology: ledger §1.3 — R=11, N=100_000, interleaved, min/median/spread.
"""
from __future__ import annotations

import gc
import os
import statistics
import subprocess
import sys
import timeit

WORKTREE = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = 11
N = 100_000


def build(LookupStatus):
    # ---- D: properties over private slots, binding omitted, 2 singletons ----
    class D:
        __slots__ = ("_status", "_value")

        def __init__(self, status, value=None):
            self._status = status
            self._value = value

        @property
        def status(self):
            return self._status

        @property
        def value(self):
            return self._value

        @property
        def is_set(self):
            return self._status is LookupStatus.VALUE

        @property
        def is_present(self):
            return self._status is not LookupStatus.MISSING

        @classmethod
        def missing(cls):
            return _D_MISSING

        @classmethod
        def present_unset(cls, binding=None):
            return _D_PRESENT_UNSET

        @classmethod
        def of_value(cls, value, binding=None):
            return cls(LookupStatus.VALUE, value)

    _D_MISSING = D(LookupStatus.MISSING, None)
    _D_PRESENT_UNSET = D(LookupStatus.PRESENT_UNSET, None)

    # ---- D3: raising __setattr__ variant (stricter, priced) ----
    class D3:
        __slots__ = ("status", "value")

        def __init__(self, status, value=None):
            osa = object.__setattr__
            osa(self, "status", status)
            osa(self, "value", value)

        def __setattr__(self, name, value):
            raise AttributeError(f"immutable: cannot set {name!r}")

        def __delattr__(self, name):
            raise AttributeError(f"immutable: cannot delete {name!r}")

        @property
        def is_set(self):
            return self.status is LookupStatus.VALUE

        @property
        def is_present(self):
            return self.status is not LookupStatus.MISSING

        @classmethod
        def missing(cls):
            return _D3_MISSING

        @classmethod
        def present_unset(cls, binding=None):
            return _D3_PRESENT_UNSET

        @classmethod
        def of_value(cls, value, binding=None):
            return cls(LookupStatus.VALUE, value)

    _D3_MISSING = D3(LookupStatus.MISSING, None)
    _D3_PRESENT_UNSET = D3(LookupStatus.PRESENT_UNSET, None)

    return D, D3


def main() -> int:
    import psh
    p = os.path.realpath(psh.__file__)
    if not p.startswith(WORKTREE + os.sep):
        raise SystemExit(f"DISCRIMINATOR FAIL: psh from {p}")

    from psh.core import scope as scope_mod
    from psh.core.scope import ScopeManager
    from psh.core.variable_lookup import LookupStatus, VariableLookup

    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WORKTREE,
                         capture_output=True, text=True).stdout.strip()
    print("P3b PROPOSED design, end-to-end through the real ScopeManager.lookup()")
    print(f"psh from: {p}")
    print(f"SHA: {sha}   python: {sys.version.split()[0]}   "
          f"GC {'on' if gc.isenabled() else 'OFF'}")
    print(f"methodology: R={R}, N={N}, interleaved round-robin")
    print("=" * 84)

    D, D3 = build(LookupStatus)
    arms = [("BASE (plain __slots__, 3 fields)", VariableLookup),
            ("D    (properties, binding omitted, 2 singletons)", D),
            ("D3   (raising __setattr__, same shape)", D3)]
    original = scope_mod.VariableLookup

    mgr = ScopeManager()
    mgr.set_variable("SET", "v")
    mgr.push_scope("f")
    mgr.create_local("DECL")

    cells = [
        ("VALUE          m.lookup('SET')", "m.lookup('SET')"),
        ("PRESENT_UNSET  m.lookup('DECL')", "m.lookup('DECL')"),
        ("MISSING        m.lookup('NOPE')", "m.lookup('NOPE')"),
        ("is_set read    m.lookup('SET').is_set  [production shape]",
         "m.lookup('SET').is_set"),
    ]
    try:
        for title, stmt in cells:
            acc: dict[str, list[float]] = {n: [] for n, _ in arms}
            for _ in range(R):
                for name, cls in arms:
                    scope_mod.VariableLookup = cls
                    t = timeit.Timer(stmt, globals={"m": mgr})
                    acc[name].append(t.timeit(number=N))
            print(f"\n--- {title} ---")
            print(f"    {'arm':50s} {'min ns/op':>11s} {'median':>10s} "
                  f"{'spread':>9s} {'vs BASE':>9s}")
            base_min = min(acc[arms[0][0]]) / N * 1e9
            for name, _cls in arms:
                vals = acc[name]
                mn = min(vals) / N * 1e9
                med = statistics.median(vals) / N * 1e9
                spread = (max(vals) - min(vals)) / N * 1e9
                print(f"    {name:50s} {mn:11.2f} {med:10.2f} {spread:9.2f} "
                      f"{mn / base_min:8.3f}x")
    finally:
        scope_mod.VariableLookup = original
        mgr.pop_scope()

    # Correctness + immutability controls.
    print("\n--- correctness control (identical tri-state answers) ---")
    mgr2 = ScopeManager()
    mgr2.set_variable("SET", "v")
    mgr2.push_scope("f")
    mgr2.create_local("DECL")
    try:
        for name, cls in arms:
            scope_mod.VariableLookup = cls
            got = tuple((mgr2.lookup(n).status.name, mgr2.lookup(n).value,
                         mgr2.lookup(n).is_set, mgr2.lookup(n).is_present)
                        for n in ("SET", "DECL", "NOPE"))
            print(f"    {name:50s} {got}")
    finally:
        scope_mod.VariableLookup = original
        mgr2.pop_scope()

    print("\n--- immutability control (per field, per surface) ---")
    for name, cls in arms:
        results = []
        for kind, obj in (("fresh VALUE", cls.of_value('v')),
                          ("MISSING singleton", cls.missing()),
                          ("PRESENT_UNSET singleton", cls.present_unset())):
            for field in ("status", "value"):
                try:
                    setattr(obj, field, 'X')
                    results.append(f"{kind}.{field}=ACCEPTED")
                except Exception as exc:                       # noqa: BLE001
                    results.append(f"{kind}.{field}={type(exc).__name__}")
        print(f"    {name}")
        for rline in results:
            print(f"        {rline}")

    print("\n--- singleton-identity control (allocation behaviour) ---")
    for name, cls in arms:
        print(f"    {name:50s} MISSING shared={cls.missing() is cls.missing()}  "
              f"PRESENT_UNSET shared="
              f"{cls.present_unset() is cls.present_unset()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
