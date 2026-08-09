#!/usr/bin/env python3
"""A6 — how many (file, qualname) keys are NOT unique in the census?

Bears directly on the hub-ledger KEY SHAPE (Phase A item 4): a ledger keyed on
(file, qualname) silently merges rows wherever a qualname repeats in a file
(@property/@x.setter pairs, TYPE_CHECKING branches, same-named nested defs).
Reports the duplicate keys in the FULL set and in the >=100 set separately,
since only the latter is what the ledger must key.

Usage: A6_dupkey_census.py <census.json>
"""
import json
import sys
from collections import Counter
from pathlib import Path

doc = json.loads(Path(sys.argv[1]).read_text())
for key, title in (("all", "FULL SET"), ("ge100", ">=100 SET")):
    rows = doc[key]
    c = Counter((r["file"], r["fn"]) for r in rows)
    dups = {k: v for k, v in c.items() if v > 1}
    extra = sum(v - 1 for v in dups.values())
    print(f"=== {title}: rows={len(rows)} unique-keys={len(c)} "
          f"duplicate-keys={len(dups)} extra-rows-hidden={extra}")
    for (f, q), v in sorted(dups.items(), key=lambda t: (-t[1], t[0])):
        lens = sorted(r["len"] for r in rows if (r["file"], r["fn"]) == (f, q))
        print(f"    x{v}  {f}::{q}  lens={lens}")
    print()
