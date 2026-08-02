#!/usr/bin/env python3
"""A4 — REGRESSION RISK probe for the P2 ok-table.

The ok-table is memoized per (group, gi, se). Consumers that hold si fixed and
VARY se (`matching_ends`, `span_at`/`spanner`) would build O(n) tables of
O(n) entries each. Measure whether P2 helps, is neutral, or REGRESSES them —
before proposing it. A design that fixes full_match by pessimising
substitution is not a fix.
"""
import os
import sys
import time

PSH_ROOT = os.environ.get('PSH_ROOT', '/Users/pwilson/src/psh-r3-2')
import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proto_design import (BashMatcherProto, matching_ends_proto)  # noqa: E402

if not os.path.realpath(pe.__file__).startswith(os.path.realpath(PSH_ROOT) + os.sep):
    sys.exit("DISCRIMINATOR FAIL")
print(f"\n# risk probe; version={psh.version.__version__}")


def span_at_shipped(root, s, pos):
    bm = pe._BashMatcher(s, False, False)
    for k in range(len(s), pos - 1, -1):
        if bm.match(root, 0, pos, k):
            return k - pos
    return None


def span_at_proto(root, s, pos):
    bm = BashMatcherProto(s, False, False)
    for k in range(len(s), pos - 1, -1):
        if bm.match(root, 0, pos, k):
            return k - pos
    return None


def growth(label, fn, sizes, budget=20.0):
    print(f"\n## {label}")
    print(f"{'N':>7} {'seconds':>11} {'ratio':>8}")
    prev = None
    for n in sizes:
        subj = 'a' * n
        t0 = time.perf_counter()
        fn(subj)
        dt = time.perf_counter() - t0
        r = (dt / prev) if prev else float('nan')
        print(f"{n:>7} {dt:>11.4f} {r:>8.2f}")
        prev = dt
        if dt > budget:
            print("        (stopped)")
            break


PAT = '**(a)b'          # the `*`-group shape the ok-table targets
root = pe.compile_pattern(PAT)
cp = pe.CompiledPattern(root)

print("=" * 74)
print(f"matching_ends({PAT!r}) — si fixed, se VARIES over n values")
print("=" * 74)
growth("SHIPPED", lambda s: cp.matching_ends(s, 0, pe.STRING), (50, 100, 200, 400))
growth("PROTO  ", lambda s: matching_ends_proto(root, s), (50, 100, 200, 400))

print("\n" + "=" * 74)
print(f"span_at({PAT!r}, pos=0) — se varies downward from n")
print("=" * 74)
growth("SHIPPED", lambda s: span_at_shipped(root, s, 0), (50, 100, 200, 400))
growth("PROTO  ", lambda s: span_at_proto(root, s, 0), (50, 100, 200, 400))

print("\n" + "=" * 74)
print("AGREEMENT re-check on the varying-se consumers (small, exhaustive)")
print("=" * 74)
bad = 0
cells = 0
for p in ('**(a)b', '*+(a)', '**(a)', '*@(a|b)c', '*(a)b', '**(a|b)c',
          '*?(a)!(b)', 'a*+(b)c'):
    r = pe.compile_pattern(p)
    c = pe.CompiledPattern(r)
    for s in ('', 'a', 'b', 'ab', 'aab', 'abb', 'aabb', 'abab', 'aaab', 'ba'):
        cells += 1
        if c.matching_ends(s, 0, pe.STRING) != matching_ends_proto(r, s):
            bad += 1
            print(f"  ENDS MISMATCH {p!r} {s!r}")
        for pos in range(len(s) + 1):
            cells += 1
            if span_at_shipped(r, s, pos) != span_at_proto(r, s, pos):
                bad += 1
                print(f"  SPAN MISMATCH {p!r} {s!r} pos={pos}")
print(f"  cells={cells} disagreements={bad}")
