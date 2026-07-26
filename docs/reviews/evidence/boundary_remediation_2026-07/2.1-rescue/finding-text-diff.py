"""Condition-2 differ: base-vs-tip finding-text multiset comparison.

Usage: python finding-text-diff.py base.json tip.json
Reports, per case+mode: LOSS lines (in base multiset, missing from tip —
including count decreases) and gain counts. Exit 1 if any loss exists.
"""
import json
import sys
from collections import Counter

base = json.load(open(sys.argv[1]))
tip = json.load(open(sys.argv[2]))
print(f"# base tree: {base.pop('__tree__')}")
print(f"# tip tree : {tip.pop('__tree__')}")

losses = 0
gains = 0
for case in sorted(base):
    for mode in base[case]:
        b = Counter(base[case][mode])
        t = Counter(tip.get(case, {}).get(mode, []))
        lost = b - t
        gained = t - b
        for line, n in sorted(lost.items()):
            losses += n
            print(f"LOSS  {case} {mode} x{n}: {line}")
        for line, n in sorted(gained.items()):
            gains += n
print(f"# totals: losses={losses} gains={gains}")
sys.exit(1 if losses else 0)
