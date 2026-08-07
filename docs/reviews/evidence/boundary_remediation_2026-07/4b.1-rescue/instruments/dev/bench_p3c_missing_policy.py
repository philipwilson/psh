#!/usr/bin/env python3
"""P3c — ruling (c)'s _MISSING question, priced both ways.

The brief asks for the `_MISSING` reading "frozen-singleton-kept vs
fresh-per-miss, with the perf figure for each". P3b priced the singleton arm;
this prices the fresh-per-miss arm on the SAME harness so the two figures are
comparable rather than inferred.

Arms (all with the proposed immutable shape — properties over private slots,
binding omitted; they differ ONLY in the nullary-status policy):

  S  shared frozen singletons for MISSING and PRESENT_UNSET
  F  fresh instance allocated on every MISSING and PRESENT_UNSET read

Methodology: ledger §1.3 — R=11, N=100_000, interleaved, min/median/spread.
"""
from __future__ import annotations

import os
import statistics
import subprocess
import sys
import timeit

WORKTREE = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = 11
N = 100_000


def build(LookupStatus):
    class Base:
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
        def of_value(cls, value, binding=None):
            return cls(LookupStatus.VALUE, value)

    class S(Base):
        __slots__ = ()

        @classmethod
        def missing(cls):
            return _S_MISSING

        @classmethod
        def present_unset(cls, binding=None):
            return _S_PU

    _S_MISSING = S(LookupStatus.MISSING, None)
    _S_PU = S(LookupStatus.PRESENT_UNSET, None)

    class F(Base):
        __slots__ = ()

        @classmethod
        def missing(cls):
            return cls(LookupStatus.MISSING, None)

        @classmethod
        def present_unset(cls, binding=None):
            return cls(LookupStatus.PRESENT_UNSET, None)

    return S, F


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
    print("P3c _MISSING policy — shared frozen singleton vs fresh-per-miss")
    print(f"psh from: {p}")
    print(f"SHA: {sha}   python: {sys.version.split()[0]}")
    print(f"methodology: R={R}, N={N}, interleaved round-robin")
    print("=" * 84)

    S, F = build(LookupStatus)
    arms = [("BASE (today: mutable shared _MISSING)", VariableLookup),
            ("S  frozen shared singletons", S),
            ("F  fresh instance per miss", F)]
    original = scope_mod.VariableLookup

    mgr = ScopeManager()
    mgr.set_variable("SET", "v")
    mgr.push_scope("f")
    mgr.create_local("DECL")
    cells = [("MISSING        m.lookup('NOPE')", "m.lookup('NOPE')"),
             ("PRESENT_UNSET  m.lookup('DECL')", "m.lookup('DECL')")]
    try:
        for title, stmt in cells:
            acc: dict[str, list[float]] = {n: [] for n, _ in arms}
            for _ in range(R):
                for name, cls in arms:
                    scope_mod.VariableLookup = cls
                    t = timeit.Timer(stmt, globals={"m": mgr})
                    acc[name].append(t.timeit(number=N))
            print(f"\n--- {title} ---")
            print(f"    {'arm':40s} {'min ns/op':>11s} {'median':>10s} "
                  f"{'spread':>9s} {'vs BASE':>9s} {'delta ns':>10s}")
            base_min = min(acc[arms[0][0]]) / N * 1e9
            for name, _cls in arms:
                vals = acc[name]
                mn = min(vals) / N * 1e9
                med = statistics.median(vals) / N * 1e9
                spread = (max(vals) - min(vals)) / N * 1e9
                print(f"    {name:40s} {mn:11.2f} {med:10.2f} {spread:9.2f} "
                      f"{mn / base_min:8.3f}x {mn - base_min:+10.2f}")
    finally:
        scope_mod.VariableLookup = original
        mgr.pop_scope()

    print("\n--- safety control: is a shared singleton safe once frozen? ---")
    for name, cls in arms:
        a = cls.missing()
        b = cls.missing()
        try:
            a.status = LookupStatus.VALUE
            a.value = 'POISON'
            poisoned = (b.status is LookupStatus.VALUE and b.value == 'POISON')
            note = f"mutation ACCEPTED; second miss poisoned={poisoned}"
        except Exception as exc:                               # noqa: BLE001
            note = (f"mutation rejected ({type(exc).__name__}); "
                    f"shared={a is b}; second miss clean="
                    f"{b.status is LookupStatus.MISSING}")
        print(f"    {name:40s} {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
