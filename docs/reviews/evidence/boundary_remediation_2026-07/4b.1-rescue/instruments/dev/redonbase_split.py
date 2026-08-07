#!/usr/bin/env python3
"""Derive the RED-ON-BASE split for the 4B.1 pin file, one cell per process.

Why per-process rather than one pytest run: several cells attempt DELETION of
a field on a SHARED singleton. At base those attempts SUCCEED (the fields are
plain writable slots), which damages the singleton for every later cell in the
same process. A single run would therefore report collateral failures and
inflate the red count — the number would be real but would not mean what the
pre-registration says it means. Running each cell in its own interpreter makes
the split immune to ordering and pollution.

At TIP the same cells are non-destructive (the attempts raise), so the
committed suite is safe under xdist either way; this isolation is a property
of the MEASUREMENT, not of the suite.

Counts are DERIVED here and printed; nothing is hand-tallied.
Usage: python tmp/4b1-instruments/redonbase_split.py [test_file]
"""
from __future__ import annotations

import os
import subprocess
import sys
from collections import Counter

WORKTREE = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT = "tests/unit/core/test_variable_lookup_immutability.py"


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WORKTREE,
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=WORKTREE,
                           capture_output=True, text=True).stdout.strip()

    collect = subprocess.run(
        [sys.executable, "-m", "pytest", target, "--collect-only", "-q",
         "--no-header"],
        cwd=WORKTREE, capture_output=True, text=True)
    ids = [ln.strip() for ln in collect.stdout.splitlines()
           if "::" in ln and ln.strip().startswith(target)]
    print(f"redonbase_split — {target}")
    print(f"SHA: {sha}")
    print(f"worktree dirty: {'YES' if dirty else 'no'}")
    if dirty:
        for line in dirty.splitlines():
            print(f"    {line}")
    print(f"python: {sys.version.split()[0]}")
    print(f"collected: {len(ids)} cells; running each in its own process")
    print("=" * 90)

    results: dict[str, str] = {}
    for tid in ids:
        run = subprocess.run(
            [sys.executable, "-m", "pytest", tid, "-q", "--no-header",
             "-p", "no:cacheprovider"],
            cwd=WORKTREE, capture_output=True, text=True)
        # Exit 0 = passed, 1 = failed, others = error/collection problem.
        if run.returncode == 0:
            results[tid] = "GREEN"
        elif run.returncode == 1:
            results[tid] = "RED"
        else:
            results[tid] = f"ERROR(rc={run.returncode})"

    by_class: dict[str, Counter] = {}
    for tid, verdict in results.items():
        cls = tid.split("::")[1] if tid.count("::") >= 2 else "(module)"
        by_class.setdefault(cls, Counter())[verdict] += 1

    print(f"{'class':40s} {'cells':>6s} {'RED':>6s} {'GREEN':>7s} {'other':>7s}")
    total = Counter()
    for cls in sorted(by_class):
        c = by_class[cls]
        other = sum(v for k, v in c.items() if k not in ("RED", "GREEN"))
        n = sum(c.values())
        print(f"{cls:40s} {n:6d} {c['RED']:6d} {c['GREEN']:7d} {other:7d}")
        total.update(c)
    other = sum(v for k, v in total.items() if k not in ("RED", "GREEN"))
    print("-" * 90)
    print(f"{'TOTAL':40s} {sum(total.values()):6d} {total['RED']:6d} "
          f"{total['GREEN']:7d} {other:7d}")

    print("\nRED cells (defect evidence unless labelled otherwise):")
    for tid in ids:
        if results[tid] == "RED":
            print(f"    {tid.split('::', 1)[1]}")
    anomalies = [t for t, v in results.items()
                 if v not in ("RED", "GREEN")]
    if anomalies:
        print("\nANOMALIES (neither clean pass nor clean fail):")
        for tid in anomalies:
            print(f"    {results[tid]}  {tid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
