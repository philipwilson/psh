#!/usr/bin/env python3
"""P4 — END-TO-END ScopeManager.lookup() cost with each candidate patched in.

P3 timed construction in isolation; that overstates the impact because the
real call also pays _resolve_read + get_variable_object + as_string(). This
instrument patches psh.core.scope.VariableLookup with each candidate and
times the REAL lookup() on a real ScopeManager, plus get_variable() as the
contrast arm (it builds no lookup at all, so it must be flat across arms —
that flatness is this instrument's own control).

Cells vary the outcome axis, because the three statuses take different paths:
  VALUE          — builds a fresh instance (of_value)
  PRESENT_UNSET  — builds a fresh instance (present_unset)
  MISSING        — returns the shared singleton (builds NOTHING at base)

Methodology: ledger §1.3 — R=11, N=100_000, interleaved round-robin, one
process, min/median/spread reported.
"""
from __future__ import annotations

import gc
import os
import statistics
import subprocess
import sys
import timeit
from dataclasses import dataclass
from typing import Any, NamedTuple, Optional

WORKTREE = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = 11
N = 100_000


def build_candidates(LookupStatus):
    """Candidate representations, each API-compatible with the real one."""

    class C0_Slots:
        __slots__ = ("status", "value", "binding")

        def __init__(self, status, value=None, binding=None):
            self.status = status
            self.value = value
            self.binding = binding

        @property
        def is_set(self):
            return self.status is LookupStatus.VALUE

        @property
        def is_present(self):
            return self.status is not LookupStatus.MISSING

        @classmethod
        def missing(cls):
            return cls._MISSING

        @classmethod
        def present_unset(cls, binding=None):
            return cls(LookupStatus.PRESENT_UNSET, None, binding)

        @classmethod
        def of_value(cls, value, binding=None):
            return cls(LookupStatus.VALUE, value, binding)

    C0_Slots._MISSING = C0_Slots(LookupStatus.MISSING, None, None)

    @dataclass(frozen=True, eq=False, slots=True)
    class C1_FrozenDC:
        status: Any
        value: Optional[str] = None
        binding: Any = None

        @property
        def is_set(self):
            return self.status is LookupStatus.VALUE

        @property
        def is_present(self):
            return self.status is not LookupStatus.MISSING

        @classmethod
        def missing(cls):
            return _C1_MISSING

        @classmethod
        def present_unset(cls, binding=None):
            return cls(LookupStatus.PRESENT_UNSET, None, binding)

        @classmethod
        def of_value(cls, value, binding=None):
            return cls(LookupStatus.VALUE, value, binding)

    _C1_MISSING = C1_FrozenDC(LookupStatus.MISSING, None, None)

    class C2_NamedTuple(NamedTuple):
        status: Any
        value: Optional[str] = None
        binding: Any = None

        @property
        def is_set(self):
            return self.status is LookupStatus.VALUE

        @property
        def is_present(self):
            return self.status is not LookupStatus.MISSING

        @classmethod
        def missing(cls):
            return _C2_MISSING

        @classmethod
        def present_unset(cls, binding=None):
            return cls(LookupStatus.PRESENT_UNSET, None, binding)

        @classmethod
        def of_value(cls, value, binding=None):
            return cls(LookupStatus.VALUE, value, binding)

    _C2_MISSING = C2_NamedTuple(LookupStatus.MISSING, None, None)

    class C3_RaisingSetattr:
        __slots__ = ("status", "value", "binding")

        def __init__(self, status, value=None, binding=None):
            osa = object.__setattr__
            osa(self, "status", status)
            osa(self, "value", value)
            osa(self, "binding", binding)

        def __setattr__(self, name, value):
            raise AttributeError(f"immutable: cannot set {name!r}")

        @property
        def is_set(self):
            return self.status is LookupStatus.VALUE

        @property
        def is_present(self):
            return self.status is not LookupStatus.MISSING

        @classmethod
        def missing(cls):
            return _C3_MISSING

        @classmethod
        def present_unset(cls, binding=None):
            return cls(LookupStatus.PRESENT_UNSET, None, binding)

        @classmethod
        def of_value(cls, value, binding=None):
            return cls(LookupStatus.VALUE, value, binding)

    _C3_MISSING = C3_RaisingSetattr(LookupStatus.MISSING, None, None)

    class C4_Properties:
        __slots__ = ("_status", "_value", "_binding")

        def __init__(self, status, value=None, binding=None):
            self._status = status
            self._value = value
            self._binding = binding

        @property
        def status(self):
            return self._status

        @property
        def value(self):
            return self._value

        @property
        def binding(self):
            return self._binding

        @property
        def is_set(self):
            return self._status is LookupStatus.VALUE

        @property
        def is_present(self):
            return self._status is not LookupStatus.MISSING

        @classmethod
        def missing(cls):
            return _C4_MISSING

        @classmethod
        def present_unset(cls, binding=None):
            return cls(LookupStatus.PRESENT_UNSET, None, binding)

        @classmethod
        def of_value(cls, value, binding=None):
            return cls(LookupStatus.VALUE, value, binding)

    _C4_MISSING = C4_Properties(LookupStatus.MISSING, None, None)

    return [
        ("C0 plain __slots__ (CURRENT)", C0_Slots),
        ("C1 frozen dataclass slots", C1_FrozenDC),
        ("C2 NamedTuple", C2_NamedTuple),
        ("C3 slots + raising __setattr__", C3_RaisingSetattr),
        ("C4 properties over slots", C4_Properties),
    ]


def main() -> int:
    import psh
    p = os.path.realpath(psh.__file__)
    if not p.startswith(WORKTREE + os.sep):
        raise SystemExit(f"DISCRIMINATOR FAIL: psh from {p}")

    from psh.core import scope as scope_mod
    from psh.core.scope import ScopeManager
    from psh.core.variable_lookup import LookupStatus

    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WORKTREE,
                         capture_output=True, text=True).stdout.strip()
    print("P4 end-to-end ScopeManager.lookup() benchmark")
    print(f"psh from: {p}")
    print(f"SHA: {sha}")
    print(f"python: {sys.version.split()[0]}   GC {'on' if gc.isenabled() else 'OFF'}")
    print(f"methodology: R={R}, N={N}, interleaved round-robin")
    print("=" * 84)

    candidates = build_candidates(LookupStatus)
    original = scope_mod.VariableLookup

    # A manager with one VALUE name, one PRESENT_UNSET name, one MISSING name.
    mgr = ScopeManager()
    mgr.set_variable("SET", "v")
    mgr.push_scope("f")
    mgr.create_local("DECL")          # bare `local DECL` -> PRESENT_UNSET

    cells = [
        ("VALUE          (builds fresh)", "m.lookup('SET')"),
        ("PRESENT_UNSET  (builds fresh)", "m.lookup('DECL')"),
        ("MISSING        (singleton at base)", "m.lookup('NOPE')"),
        ("get_variable   (builds NOTHING - control)", "m.get_variable('SET')"),
    ]

    try:
        for title, stmt in cells:
            acc: dict[str, list[float]] = {n: [] for n, _ in candidates}
            for _ in range(R):
                for name, cls in candidates:
                    scope_mod.VariableLookup = cls
                    t = timeit.Timer(stmt, globals={"m": mgr})
                    acc[name].append(t.timeit(number=N))
            print(f"\n--- {title} ---")
            print(f"    stmt: {stmt}")
            print(f"    {'candidate':34s} {'min ns/op':>11s} {'median':>10s} "
                  f"{'spread':>10s} {'vs C0':>8s} {'delta ns':>10s}")
            base_min = min(acc[candidates[0][0]]) / N * 1e9
            for name, _cls in candidates:
                vals = acc[name]
                mn = min(vals) / N * 1e9
                med = statistics.median(vals) / N * 1e9
                spread = (max(vals) - min(vals)) / N * 1e9
                print(f"    {name:34s} {mn:11.2f} {med:10.2f} {spread:10.2f} "
                      f"{mn / base_min:7.2f}x {mn - base_min:+10.2f}")
    finally:
        scope_mod.VariableLookup = original
        mgr.pop_scope()

    # Correctness control: every candidate must produce the SAME tri-state
    # answers through the real lookup(). A benchmark of a wrong arm is noise.
    print("\n--- correctness control: identical tri-state answers per arm ---")
    mgr2 = ScopeManager()
    mgr2.set_variable("SET", "v")
    mgr2.push_scope("f")
    mgr2.create_local("DECL")
    try:
        for name, cls in candidates:
            scope_mod.VariableLookup = cls
            got = tuple(
                (mgr2.lookup(n).status.name, mgr2.lookup(n).value,
                 mgr2.lookup(n).is_set, mgr2.lookup(n).is_present)
                for n in ("SET", "DECL", "NOPE"))
            print(f"    {name:34s} {got}")
    finally:
        scope_mod.VariableLookup = original
        mgr2.pop_scope()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
