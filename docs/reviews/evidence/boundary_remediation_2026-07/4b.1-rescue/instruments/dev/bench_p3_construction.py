#!/usr/bin/env python3
"""P3 — MEASURED construction cost per candidate representation.

The module docstring of variable_lookup.py justifies the current non-frozen
design: "freezing roughly triples construction cost (object.__setattr__ per
field)". That claim is RE-MEASURED here, not quoted.

Candidates (all carrying the same three fields status/value/binding and the
same is_set/is_present projections):

  C0  plain __slots__ class                      (CURRENT / base)
  C1  @dataclass(frozen=True, eq=False, slots=True)   (3.2 pattern-node precedent)
  C2  NamedTuple                                  (tuple-fast, immutable)
  C3  __slots__ + raising __setattr__, object.__setattr__ in __init__
  C4  read-only properties over private __slots__

Measured per candidate:
  (i)   bare construction                 — cls(status, value, binding)
  (ii)  FACTORY construction              — cls.of_value(value, binding)
        (what production actually pays: scope.py:391 calls of_value)
  (iii) attribute read                    — r.is_set  (the ONE production read)

Methodology (pinned in ledger §1.3 BEFORE measuring):
  CPython as reported below, no -O, GC on.
  timeit.Timer.repeat(repeat=R, number=N) with R=11, N=200_000.
  Candidates measured in ONE process, INTERLEAVED round-robin across repeats,
  so drift/thermal effects hit every arm alike.
  Reported: min (the standard timeit statistic), median, and spread
  (max-min over repeats) so variance is visible.
"""
from __future__ import annotations

import gc
import statistics
import subprocess
import sys
import timeit
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, NamedTuple, Optional

R = 11
N = 200_000


class LookupStatus(Enum):
    MISSING = auto()
    PRESENT_UNSET = auto()
    VALUE = auto()


# --- C0: current -----------------------------------------------------------
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
    def of_value(cls, value, binding=None):
        return cls(LookupStatus.VALUE, value, binding)


# --- C1: frozen dataclass with slots (3.2 precedent) -----------------------
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
    def of_value(cls, value, binding=None):
        return cls(LookupStatus.VALUE, value, binding)


# --- C2: NamedTuple --------------------------------------------------------
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
    def of_value(cls, value, binding=None):
        return cls(LookupStatus.VALUE, value, binding)


# --- C3: __slots__ + raising __setattr__ -----------------------------------
class C3_RaisingSetattr:
    __slots__ = ("status", "value", "binding")

    def __init__(self, status, value=None, binding=None):
        osa = object.__setattr__
        osa(self, "status", status)
        osa(self, "value", value)
        osa(self, "binding", binding)

    def __setattr__(self, name, value):
        raise AttributeError(f"VariableLookup is immutable: cannot set {name!r}")

    def __delattr__(self, name):
        raise AttributeError(f"VariableLookup is immutable: cannot delete {name!r}")

    @property
    def is_set(self):
        return self.status is LookupStatus.VALUE

    @property
    def is_present(self):
        return self.status is not LookupStatus.MISSING

    @classmethod
    def of_value(cls, value, binding=None):
        return cls(LookupStatus.VALUE, value, binding)


# --- C4: read-only properties over private slots ---------------------------
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
    def of_value(cls, value, binding=None):
        return cls(LookupStatus.VALUE, value, binding)


CANDIDATES = [
    ("C0 plain __slots__ (CURRENT)", C0_Slots),
    ("C1 frozen dataclass slots", C1_FrozenDC),
    ("C2 NamedTuple", C2_NamedTuple),
    ("C3 slots + raising __setattr__", C3_RaisingSetattr),
    ("C4 properties over slots", C4_Properties),
]

BINDING = object()  # stand-in for a Variable cell; identical cost for all arms


def measure(stmt: str, cls) -> list[float]:
    """One repeat-set for one candidate. Returns per-repeat seconds."""
    t = timeit.Timer(stmt, globals={"C": cls, "S": LookupStatus,
                                    "B": BINDING, "LookupStatus": LookupStatus})
    return t.repeat(repeat=R, number=N)


def interleaved(stmt: str) -> dict[str, list[float]]:
    """Round-robin across candidates within each repeat, so drift is shared."""
    acc: dict[str, list[float]] = {name: [] for name, _ in CANDIDATES}
    for _ in range(R):
        for name, cls in CANDIDATES:
            t = timeit.Timer(stmt, globals={"C": cls, "S": LookupStatus,
                                            "B": BINDING,
                                            "LookupStatus": LookupStatus})
            acc[name].append(t.timeit(number=N))
    return acc


def report(title: str, stmt: str, acc: dict[str, list[float]]) -> None:
    print(f"\n--- {title} ---")
    print(f"    stmt: {stmt}")
    print(f"    {'candidate':34s} {'min ns/op':>11s} {'median':>10s} "
          f"{'spread':>10s} {'vs C0':>8s}")
    base_min = min(acc[CANDIDATES[0][0]]) / N * 1e9
    for name, _cls in CANDIDATES:
        vals = acc[name]
        mn = min(vals) / N * 1e9
        med = statistics.median(vals) / N * 1e9
        spread = (max(vals) - min(vals)) / N * 1e9
        ratio = mn / base_min
        print(f"    {name:34s} {mn:11.2f} {med:10.2f} {spread:10.2f} "
              f"{ratio:7.2f}x")


def main() -> int:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                         text=True).stdout.strip()
    print("P3 construction-cost benchmark — candidate representations")
    print(f"SHA: {sha}")
    print(f"python: {sys.version}")
    print(f"methodology: timeit repeat R={R}, number N={N}, interleaved "
          f"round-robin, GC {'on' if gc.isenabled() else 'OFF'}")
    print("=" * 78)

    report("(i) bare construction  C(S.VALUE, 'v', B)",
           "C(S.VALUE, 'v', B)",
           interleaved("C(S.VALUE, 'v', B)"))

    report("(ii) FACTORY construction  C.of_value('v', B)  [production shape]",
           "C.of_value('v', B)",
           interleaved("C.of_value('v', B)"))

    # (iii) attribute read: construct once outside the timed statement.
    print("\n--- (iii) attribute read  r.is_set  [the ONE production read] ---")
    print(f"    {'candidate':34s} {'min ns/op':>11s} {'median':>10s} "
          f"{'spread':>10s} {'vs C0':>8s}")
    racc: dict[str, list[float]] = {name: [] for name, _ in CANDIDATES}
    for _ in range(R):
        for name, cls in CANDIDATES:
            t = timeit.Timer("r.is_set",
                             setup="r = C.of_value('v', B)",
                             globals={"C": cls, "B": BINDING,
                                      "LookupStatus": LookupStatus,
                                      "S": LookupStatus})
            racc[name].append(t.timeit(number=N))
    base_min = min(racc[CANDIDATES[0][0]]) / N * 1e9
    for name, _cls in CANDIDATES:
        vals = racc[name]
        mn = min(vals) / N * 1e9
        med = statistics.median(vals) / N * 1e9
        spread = (max(vals) - min(vals)) / N * 1e9
        print(f"    {name:34s} {mn:11.2f} {med:10.2f} {spread:10.2f} "
              f"{mn / base_min:7.2f}x")

    # Mutability check: prove each arm actually rejects (or accepts) writes.
    print("\n--- mutation-rejection check (what each candidate actually does) ---")
    for name, cls in CANDIDATES:
        r = cls.of_value('v', BINDING)
        try:
            r.value = 'MUTATED'
            verdict = f"ACCEPTED the write -> value={r.value!r}"
        except Exception as exc:                               # noqa: BLE001
            verdict = f"rejected: {type(exc).__name__}: {exc}"
        print(f"    {name:34s} {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
