#!/usr/bin/env python3
"""Fold the r6b/r6b2/r6b3 battery outputs into ONE chain table.

Columns: bash 5.2.26 | base 1b271d77 | r4 f0cc466e | tip (arg, default the
round-6 partial 360090b2). Each cell is (rc, stdout). The verdict names WHERE
the row stands: MATCH (tip == bash), REGRESSION (base == bash != tip),
BASE-IDENTICAL-DIVERGENCE (base == tip != bash), or FIXED (base != bash == tip).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BATTERIES = ("r6b", "r6b2", "r6b3")
TIP = sys.argv[1] if len(sys.argv) > 1 else "tip360090b2"
COMMITS = (("bash", None), ("base", "base1b271d77"), ("r4", "r4f0cc466e"),
           ("tip", TIP))


def parse(path):
    """{(case, channel): {'bash': (rc,out), 'psh': (rc,out), 'cb': (rc,out)}}"""
    rows = {}
    case = None
    key = None
    for line in open(path):
        line = line.rstrip("\n")
        if re.match(r"^[a-z]\d+_", line):
            case = line
            continue
        m = re.match(r"^  \[(\w+)\] (MATCH|DIVERGE)", line)
        if m:
            key = (case, m.group(1))
            rows.setdefault(key, {})
            continue
        m = re.match(r"^    (bash|psh-rd|psh-cb)\s+rc=(\S+) out=(.*)$", line)
        if m and key:
            who, rc, out = m.groups()
            rows[key][{"bash": "bash", "psh-rd": "psh",
                       "psh-cb": "cb"}[who]] = (rc, out)
    return rows


def main():
    per_commit = {}
    for label, suffix in COMMITS:
        if suffix is None:
            continue
        merged = {}
        for bat in BATTERIES:
            path = os.path.join(HERE, f"{bat}-{suffix}.txt")
            merged.update(parse(path))
        per_commit[label] = merged

    keys = sorted(per_commit["tip"])
    print(f"CHAIN TABLE  bash 5.2.26 | base 1b271d77 | r4 f0cc466e | tip {TIP}")
    print(f"rows={len(keys)}")
    counts = {}
    for key in keys:
        bash = per_commit["tip"][key].get("bash")
        base = per_commit["base"].get(key, {}).get("psh")
        r4 = per_commit["r4"].get(key, {}).get("psh")
        tip = per_commit["tip"][key].get("psh")
        cb = per_commit["tip"][key].get("cb")
        if tip == bash:
            verdict = "MATCH"
        elif base == bash and tip != bash:
            verdict = "REGRESSION"
        elif base == tip:
            verdict = "BASE-IDENTICAL-DIVERGENCE"
        elif base != bash and tip != bash:
            verdict = "MOVED-STILL-DIVERGENT"
        else:
            verdict = "OTHER"
        if cb != tip:
            verdict += " <<< PARSER SPLIT"
        counts[verdict] = counts.get(verdict, 0) + 1
        print(f"{verdict:26s} {key[0]:44s} [{key[1]:5s}] "
              f"bash={bash} base={base} r4={r4} tip={tip}")
    print("-" * 72)
    for k in sorted(counts):
        print(f"{k:26s} {counts[k]}")


if __name__ == "__main__":
    main()
