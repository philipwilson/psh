#!/usr/bin/env python3
"""A2 — per-row reconciliation of two q4_09 function-length censuses.

Usage: A2_census_reconcile.py <old.json> <new.json>

Reports, against the >=100 sets and the FULL function sets:
  - rows present in both, length CHANGED (the growth/shrink drift)
  - rows only in old (left the >=100 set, or deleted/renamed)
  - rows only in new (entered the >=100 set, or added)
  - full-set totals and the added/removed function names behind the delta
Identity is POSITIONAL-FREE: the key is (file, qualname), which is what the
census itself emits; text never identifies an entry by ordinal (4B.3 rule 9).
"""
import json
import sys
from pathlib import Path

old = json.loads(Path(sys.argv[1]).read_text())
new = json.loads(Path(sys.argv[2]).read_text())


def index(doc, key):
    return {(r["file"], r["fn"]): r["len"] for r in doc[key]}


for key, title in (("ge100", ">=100 SET"), ("all", "FULL SET")):
    o, n = index(old, key), index(new, key)
    print(f"=== {title}: old={old['label']} n={len(o)}  new={new['label']} n={len(n)}")
    changed = sorted(
        [(k, o[k], n[k]) for k in o.keys() & n.keys() if o[k] != n[k]],
        key=lambda t: -(t[2] - t[1]),
    )
    only_old = sorted(o.keys() - n.keys())
    only_new = sorted(n.keys() - o.keys())
    print(f"  changed-length: {len(changed)}")
    for (f, q), a, b in changed:
        print(f"    {a:4d} -> {b:4d}  ({b - a:+d})  {f}::{q}")
    print(f"  only-in-old: {len(only_old)}")
    for f, q in only_old:
        print(f"    {o[(f, q)]:4d}  {f}::{q}")
    print(f"  only-in-new: {len(only_new)}")
    for f, q in only_new:
        print(f"    {n[(f, q)]:4d}  {f}::{q}")
    print()

print(f"totals: old total_functions={old['total_functions']} ge100={old['ge100_count']}")
print(f"        new total_functions={new['total_functions']} ge100={new['ge100_count']}")
print(f"        delta total_functions={new['total_functions'] - old['total_functions']:+d} "
      f"ge100={new['ge100_count'] - old['ge100_count']:+d}")
