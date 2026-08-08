#!/usr/bin/env python3
"""Q4 axis-4: which >=100-line functions are NEW at tip vs v0.750.0, which
left the list, and which grew while already on it.

Usage: q4_10_cliff_delta.py <base.json> <tip.json>
"""
import json
import sys
from pathlib import Path

base = json.loads(Path(sys.argv[1]).read_text())
tip = json.loads(Path(sys.argv[2]).read_text())

b_all = {(r["file"], r["fn"]): r["len"] for r in base["all"]}
t_all = {(r["file"], r["fn"]): r["len"] for r in tip["all"]}
b_big = {(r["file"], r["fn"]): r["len"] for r in base["ge100"]}
t_big = {(r["file"], r["fn"]): r["len"] for r in tip["ge100"]}

entered = {k: v for k, v in t_big.items() if k not in b_big}
left = {k: v for k, v in b_big.items() if k not in t_big}
stayed_grew = {k: (b_big[k], v) for k, v in t_big.items()
               if k in b_big and v > b_big[k]}

print(f"base ge100: {len(b_big)}  tip ge100: {len(t_big)}")
print(f"\nENTERED the >=100 list at tip ({len(entered)}):")
for (f, fn), n in sorted(entered.items(), key=lambda kv: -kv[1]):
    prev = b_all.get((f, fn))
    status = "BRAND-NEW fn" if prev is None else f"GREW {prev} -> {n}"
    print(f"  {n:4d}  {f}::{fn}   [{status}]")
print(f"\nLEFT the list ({len(left)}):")
for (f, fn), n in sorted(left.items(), key=lambda kv: -kv[1]):
    now = t_all.get((f, fn))
    status = "fn REMOVED" if now is None else f"shrank {n} -> {now}"
    print(f"  {n:4d}  {f}::{fn}   [{status}]")
print(f"\nAlready >=100 and GREW further ({len(stayed_grew)}):")
for (f, fn), (a, b) in sorted(stayed_grew.items(), key=lambda kv: -(kv[1][1]-kv[1][0])):
    print(f"  {a} -> {b}  (+{b-a})  {f}::{fn}")
print("\nTop 10 at tip:")
for r in tip["ge100"][:10]:
    prev = b_all.get((r["file"], r["fn"]))
    delta = "" if prev is None else f" (base {prev})"
    print(f"  {r['len']:4d}  {r['file']}::{r['fn']}{delta}")
