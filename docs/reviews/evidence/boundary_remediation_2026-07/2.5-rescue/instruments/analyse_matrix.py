#!/usr/bin/env python3
"""Derive the matrix's own counts and the bash-vs-psh agreement table.

Counts are DERIVED from the anchor file, never hand-carried into prose --
round-1 blocker R4-D was exactly a hand-carried count (42/14) contradicting
its own anchor (48/16).
"""
import collections
import re
import sys

rows = collections.defaultdict(dict)
sha = oracle = "?"
for line in open(sys.argv[1]):
    if line.startswith("# SHA:"):
        sha = line.split(":", 1)[1].strip()
    if line.startswith("# bash oracle:"):
        oracle = line.split(":", 1)[1].strip()
    m = re.match(r"RESULT case=(\S+) shell=(\S+) parser=(\S+) outcome=(\S+) "
                 r"prompts=(\S*)", line)
    if m:
        case, shell, parser, outcome, prompts = m.groups()
        rows[case][f"{shell}/{parser}"] = (outcome, prompts)

print(f"SHA:    {sha}")
print(f"ORACLE: {oracle}")
print(f"DERIVED: rows={sum(len(v) for v in rows.values())} cases={len(rows)}")
disagree = []
for case, by_shell in sorted(rows.items()):
    b = by_shell.get("bash/-")
    for key, val in by_shell.items():
        if key == "bash/-":
            continue
        if val != b:
            disagree.append((case, key, b, val))
print(f"DISAGREEMENTS (psh vs bash, outcome AND prompt sequence): {len(disagree)}")
for d in disagree:
    print("   ", d)
