#!/usr/bin/env python3
"""Per-cell red/green derivation — ONE interpreter per cell.

4B.1 lesson 3: red-on-base is well-defined ONLY per-cell. A batched run lets one
cell's collateral poison later cells in the same interpreter, so the count from a
single `pytest <file>` is not a red-on-base count. This driver collects the
nodes, then runs EACH node in its own pytest process and reports the per-class
measured split.

Usage: python redderive.py <label> <test-path> [<test-path> ...]
Writes the table to stdout; exit 0 always (the SPLIT is the result, not a
verdict).
"""
import collections
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def collect(paths):
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', *paths, '-q', '--collect-only'],
        cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print("COLLECTION FAILED:", file=sys.stderr)
        print(r.stdout[-4000:], file=sys.stderr)
        sys.exit(2)
    return [ln.strip() for ln in r.stdout.splitlines()
            if '::' in ln and not ln.startswith(' ')]


def klass(node):
    """Class-level bucket for the measured split (file::Class)."""
    path, _, rest = node.partition('::')
    cls = rest.split('::')[0] if '::' in rest else '<module>'
    return f"{os.path.basename(path)}::{cls}"


def main() -> int:
    label = sys.argv[1]
    paths = sys.argv[2:]
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT,
                           capture_output=True, text=True).stdout
    dirty_lines = [ln for ln in dirty.splitlines()
                   if 'INTEGRATOR-INBOX' not in ln]
    print("== DISCRIMINATOR ==")
    print(f"label:      {label}")
    print(f"HEAD:       {head}")
    print(f"tree dirty: {len(dirty_lines)} entries (excluding the inbox)")
    for ln in dirty_lines:
        print(f"            {ln}")
    print(f"paths:      {' '.join(paths)}")
    print()

    nodes = collect(paths)
    print(f"collected {len(nodes)} nodes; running ONE INTERPRETER PER CELL\n")
    results = {}
    t0 = time.monotonic()
    for node in nodes:
        r = subprocess.run(
            [sys.executable, '-m', 'pytest', node, '-q', '--no-header', '-p',
             'no:randomly'],
            cwd=ROOT, capture_output=True, text=True)
        results[node] = 'PASS' if r.returncode == 0 else 'FAIL'
    dt = time.monotonic() - t0

    per_class = collections.defaultdict(lambda: {'PASS': 0, 'FAIL': 0})
    for node, verdict in results.items():
        per_class[klass(node)][verdict] += 1

    print(f"{'NODE':<96} VERDICT")
    print("-" * 108)
    for node, verdict in results.items():
        print(f"{node:<96} {verdict}")

    print()
    print("== PER-CLASS MEASURED SPLIT ==")
    tot = {'PASS': 0, 'FAIL': 0}
    for cls in sorted(per_class):
        s = per_class[cls]
        tot['PASS'] += s['PASS']
        tot['FAIL'] += s['FAIL']
        print(f"  {cls:<74} {s['PASS']:>3} pass / {s['FAIL']:>3} fail")
    print(f"  {'TOTAL':<74} {tot['PASS']:>3} pass / {tot['FAIL']:>3} fail")
    print(f"\n  ({len(nodes)} interpreters, {dt:.1f}s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
