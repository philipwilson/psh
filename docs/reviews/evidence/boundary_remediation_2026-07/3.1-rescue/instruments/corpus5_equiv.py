#!/usr/bin/env python3
"""Slot 3.1 Phase D (R10 B2-2 Path A): corpus-union equivalence proof.

For EVERY (pattern, subject) cell in the union of corpus1/2/3 whose pattern
is Path-A eligible (pattern_engine.sub_fast_eligible), evaluate all FOUR
substitution operators through BOTH code paths — the real dispatch (fast)
and the bash machinery (forced by patching the eligibility predicate seen
by parameter_expansion) — and require ZERO disagreements.

Run: PSH_WORKTREE=<wt> PYTHONPATH=<wt> python3 corpus5_equiv.py  (neutral cwd)
"""
import os
import sys
import time

WORKTREE = os.environ.get("PSH_WORKTREE", "/Users/pwilson/src/psh-r3-1")
SLOTDIR = os.path.join(WORKTREE, "tmp", "slot31")

import psh  # noqa: E402
assert psh.__file__ == os.path.join(WORKTREE, "psh", "__init__.py"), psh.__file__
import psh.expansion.parameter_expansion as px  # noqa: E402
from psh.shell import Shell  # noqa: E402

# --- collect union cells -----------------------------------------------------
cells = set()
for tsv, cols in (("corpus1_results.tsv", (1, 2)),
                  ("corpus2_results.tsv", (1, 2)),
                  ("corpus3_results.tsv", (0, 1))):
    with open(os.path.join(SLOTDIR, tsv)) as f:
        next(f)
        for line in f:
            parts = line.rstrip("\n").split("\t")
            cells.add((parts[cols[1]], parts[cols[0]]))  # (pattern, subject)
# Round-2 backslash-axis shapes (corpus4 constants, duplicated for
# instrument independence) join the union so the fast_ok gate's remaining
# eligible backslash patterns are equivalence-proven too.
_BS_PATS = [
    r"\*", r"a\*", r"*a\*", r"*\*", r"\*a", r"\**", r"*\*a", r"a\*b",
    r"a\\*", r"a\\\*", r"*a\\*", r"*a\\\*", r"\\*", r"\\\*",
    r"\?", r"*\?", r"a\?", r"\?*", r"*a\?",
    r"\*!(a)", r"!(\*)", r"*!(\*)", r"@(\*|a)", r"*@(a|\*)", r"+(\*)",
    r"?(\*)a", r"*a\*!(b)",
    "(a)", r"\(a\)", "(a|b)", r"*(a)\*",
]
_BS_SUBJECTS = ["", "a", "b", "*", "a*", "*b", "a*b", "ab", "**", "a**b",
                "(a)", "b(a)c", "?", "a?b", "\\", "a\\b", "a*b*", "*a*"]
for _p in _BS_PATS:
    for _s in _BS_SUBJECTS:
        cells.add((_p, _s))
cells = sorted(cells)
print(f"union cells (+backslash axis): {len(cells)}")

eligible_pats = {}
for pat, _s in cells:
    if pat not in eligible_pats:
        # The REAL dispatch condition: machinery fast_ok (AST eligibility
        # x wrapper redundancy) — anchor-independent.
        eligible_pats[pat] = px._sub_machinery_cached(pat, "any", True)[3]
ecells = [(p, s) for p, s in cells if eligible_pats[p]]
print(f"eligible patterns: {sum(1 for v in eligible_pats.values() if v)}"
      f"/{len(eligible_pats)}; eligible cells: {len(ecells)}")

sh = Shell()
sh.run_command("shopt -s extglob")
po = px.ParameterExpansionOps(sh)

OPS = [("first", po.substitute_first), ("all", po.substitute_all),
       ("beg", po.substitute_prefix), ("end", po.substitute_suffix)]

t0 = time.perf_counter()
fast_results = {}
for pat, subj in ecells:
    for name, fn in OPS:
        fast_results[(pat, subj, name)] = fn(subj, pat, "Z")
t1 = time.perf_counter()
print(f"fast pass: {t1 - t0:.1f}s")

real_pred = px.sub_fast_eligible
px.sub_fast_eligible = lambda seq: False  # force the bash machinery
# Clear the machinery memo: its cached tuples carry fast_ok computed with
# the REAL predicate (the first run of this extended proof compared fast
# vs fast because of exactly this — round-2 lesson).
px._sub_machinery_cached.cache_clear()
try:
    disagreements = []
    for pat, subj in ecells:
        for name, fn in OPS:
            got = fn(subj, pat, "Z")
            if got != fast_results[(pat, subj, name)]:
                disagreements.append(
                    (pat, subj, name, fast_results[(pat, subj, name)], got))
finally:
    px.sub_fast_eligible = real_pred
    px._sub_machinery_cached.cache_clear()
t2 = time.perf_counter()
print(f"machinery pass: {t2 - t1:.1f}s")
print(f"EQUIVALENCE: {len(ecells)} eligible cells x 4 ops = "
      f"{len(ecells) * 4} comparisons, disagreements={len(disagreements)}")
for d in disagreements[:30]:
    print("  DISAGREE", d)
sys.exit(0 if not disagreements else 1)
