#!/usr/bin/env python3
"""Slot 3.1 Phase A: corpus2 — hardening shapes absent from corpus1.

Two-group chains with pre/post context, nested star-adjacent alternatives,
extra tails. Same ceremony as corpus1 (PATH bash 5.2.26 --norc LC_ALL=C, one
spawn; psh engine via match_shell_pattern; model via bash_model.predict).
Output: corpus2_results.tsv + census.
"""
import os
import subprocess
import sys

WORKTREE = os.environ.get("PSH_WORKTREE", "/Users/pwilson/src/psh-r3-1")
BASH = "/opt/homebrew/bin/bash"
SLOTDIR = os.path.join(WORKTREE, "tmp", "slot31")
NEUTRAL = os.path.join(SLOTDIR, "neutral")
sys.path.insert(0, SLOTDIR)

import psh  # noqa: E402
assert psh.__file__ == os.path.join(WORKTREE, "psh", "__init__.py"), psh.__file__
from psh.expansion.pattern import match_shell_pattern  # noqa: E402

from bash_model import predict  # noqa: E402

import itertools  # noqa: E402

SUBJECTS = [""] + ["".join(t) for L in (1, 2, 3)
                   for t in itertools.product("ab", repeat=L)]

PATTERNS = []
seen = set()


def add(p):
    if p not in seen:
        seen.add(p)
        PATTERNS.append(p)


# 1. two-group chains with context
PAIR = ["!(a)", "?(a)", "@(a|*)", "*(a)", "!(*)", "+(a)", "@(*)", "?(*)"]
for pre in ("", "*", "a", "a*"):
    for g1 in PAIR:
        for g2 in PAIR:
            for post in ("", "a", "*"):
                add(pre + g1 + g2 + post)
# 2. nested star-adjacent alternatives
NEST_ALTS = ["*!(a)", "*?(a)", "*@(a|*)", "*(a)b", "a*!(b)", "*"]
for op in "@?*+!":
    for alt in NEST_ALTS:
        for pre in ("", "*"):
            for post in ("", "a"):
                add(pre + f"{op}({alt})" + post)
# 3. groups separated by literal
for g1 in ("!(a)", "?(a)", "*(a)"):
    for g2 in ("!(b)", "?(b)", "@(b|*)"):
        add(g1 + "a" + g2)
        add("*" + g1 + "a" + g2)
# 4. triple-wildcard runs before groups
for run in ("***", "*?*", "?*", "*??"):
    for g in ("!(a)", "?(a)", "@(a|*)", "*(ab)"):
        add(run + g)

CELLS = [(f"d{i:06d}", s, p)
         for i, (p, s) in enumerate((p, s) for p in PATTERNS for s in SUBJECTS)]
print(f"patterns={len(PATTERNS)} subjects={len(SUBJECTS)} cells={len(CELLS)}")

script_path = os.path.join(SLOTDIR, "corpus2_bash.sh")
with open(script_path, "w") as f:
    f.write("shopt -s extglob\n")
    for _cid, s, p in CELLS:
        f.write(f"[[ '{s}' == {p} ]] && echo 1 || echo 0\n")

r = subprocess.run([BASH, "--norc", script_path], capture_output=True,
                   text=True, env={"PATH": os.environ["PATH"], "LC_ALL": "C"},
                   cwd=NEUTRAL, timeout=600)
bash_lines = r.stdout.split()
assert len(bash_lines) == len(CELLS), (len(bash_lines), len(CELLS),
                                       r.stderr[:500])

model_mm, psh_div = [], []
out_path = os.path.join(SLOTDIR, "corpus2_results.tsv")
with open(out_path, "w") as f:
    f.write("id\tsubject\tpattern\tbash\tpsh\tmodel\n")
    for (cid, s, p), b in zip(CELLS, bash_lines):
        eng = "1" if match_shell_pattern(s, p, extglob_enabled=True) else "0"
        mod = "1" if predict(s, p) else "0"
        f.write(f"{cid}\t{s}\t{p}\t{b}\t{eng}\t{mod}\n")
        if mod != b:
            model_mm.append((cid, s, p, b, mod))
        if eng != b:
            psh_div.append((cid, s, p, b, eng))

print(f"total={len(CELLS)} model-mismatch={len(model_mm)} "
      f"psh-base-divergent={len(psh_div)}")
for m in model_mm[:40]:
    print("  MODEL-MM", m)
