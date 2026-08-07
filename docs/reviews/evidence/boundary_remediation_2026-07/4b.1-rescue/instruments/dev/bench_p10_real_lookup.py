#!/usr/bin/env python3
"""P10 — certification benchmark: the REAL ScopeManager.lookup(), unpatched.

Deliberately a DIFFERENT method from P3b/P4, which swapped candidate classes
into the module in one process (D-3.5: an instrument that mirrors the claim's
method cannot find the claim's error). This one patches nothing — it measures
whatever `psh` the checkout provides — and is run twice, at a detached checkout
of the declared BASE and of the declared TIP. The comparison is between two
runs, not between two arms of one run.

Run from inside the checkout under test; it prints the SHA it measured so the
two halves cannot be silently mismatched (B71: never measure inside a live
worktree — this is invoked at detached checkouts).

Methodology: ledger §1.3 — R=11, N=100_000, min/median/spread.
"""
from __future__ import annotations

import gc
import os
import statistics
import subprocess
import sys
import timeit

R = 11
N = 100_000


def main() -> int:
    here = os.path.realpath(os.getcwd())
    import psh
    resolved = os.path.realpath(psh.__file__)
    if not resolved.startswith(here + os.sep):
        raise SystemExit(
            f"DISCRIMINATOR FAIL: imported psh from {resolved}, "
            f"expected under the checkout under test {here}")

    from psh.core.scope import ScopeManager
    from psh.core.variable_lookup import VariableLookup

    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                         text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()
    print("P10 real-lookup certification benchmark (no patching)")
    print(f"checkout: {here}")
    print(f"psh from: {resolved}")
    print(f"SHA: {sha}")
    print(f"tracked-file dirt: "
          f"{'YES -> ' + dirty.replace(chr(10), '; ') if dirty else 'none'}")
    print(f"python: {sys.version.split()[0]}   GC {'on' if gc.isenabled() else 'OFF'}")
    print(f"representation: {'binding' in getattr(VariableLookup, '__slots__', ())}"
          f"  slots={getattr(VariableLookup, '__slots__', None)}")
    print(f"methodology: R={R}, N={N}")
    print("=" * 78)

    mgr = ScopeManager()
    mgr.set_variable("SET", "v")
    mgr.push_scope("f")
    mgr.create_local("DECL")

    cells = [
        ("VALUE          lookup('SET')", "m.lookup('SET')"),
        ("PRESENT_UNSET  lookup('DECL')", "m.lookup('DECL')"),
        ("MISSING        lookup('NOPE')", "m.lookup('NOPE')"),
        ("production     lookup('SET').is_set", "m.lookup('SET').is_set"),
        ("control        get_variable('SET')", "m.get_variable('SET')"),
    ]
    print(f"    {'cell':40s} {'min ns/op':>11s} {'median':>10s} {'spread':>9s}")
    for title, stmt in cells:
        t = timeit.Timer(stmt, globals={"m": mgr})
        vals = t.repeat(repeat=R, number=N)
        mn = min(vals) / N * 1e9
        med = statistics.median(vals) / N * 1e9
        spread = (max(vals) - min(vals)) / N * 1e9
        print(f"    {title:40s} {mn:11.2f} {med:10.2f} {spread:9.2f}")
    mgr.pop_scope()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
