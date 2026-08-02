#!/usr/bin/env python3
"""Slot 3.1 Phase A: generated finite-alphabet corpus, bash-measured.

Deterministic enumeration (no randomness). One bash spawn for the whole
corpus (batched script). psh side evaluated through the exact [[ engine path
(match_shell_pattern, STRING profile, extglob on), with an end-to-end [[
sample cross-check of 40 cells.

Ceremony: oracle = PATH bash /opt/homebrew/bin/bash 5.2.26, --norc, LC_ALL=C.
psh = worktree tree (discriminator asserted below). Run from neutral cwd with
PYTHONPATH=/Users/pwilson/src/psh-r3-1.

Output: corpus1_results.tsv (id, subject, pattern, bash, psh) + census to stdout.
"""
import os
import subprocess
import sys

WORKTREE = os.environ.get("PSH_WORKTREE", "/Users/pwilson/src/psh-r3-1")
BASH = "/opt/homebrew/bin/bash"
SLOTDIR = os.path.join(WORKTREE, "tmp", "slot31")
NEUTRAL = os.path.join(SLOTDIR, "neutral")

import psh  # noqa: E402
assert psh.__file__ == os.path.join(WORKTREE, "psh", "__init__.py"), psh.__file__
from psh.expansion.pattern import match_shell_pattern  # noqa: E402

# --- deterministic corpus ----------------------------------------------------

OPS = ["@", "?", "*", "+", "!"]
ALTS = ["a", "b", "ab", "a|b", "*", "a|*", "a*", "", "a|",
        "?(a)", "!(a)", "@(a|*)"]
PRE = ["", "*", "?", "a", "*a", "a*", "**", "*?"]
POST = ["", "a", "*", "?", "a*", "*a", "b"]
SUBJECTS = [""]
for L in (1, 2, 3):
    def _gen(prefixes):
        return [p + c for p in prefixes for c in "ab"]
    SUBJECTS += [s for s in
                 (lambda: [  # all strings over {a,b} of length L
                     "".join(t) for t in __import__("itertools").product("ab", repeat=L)
                 ])()]

PATTERNS = []
seen = set()


def add(p):
    if p not in seen:
        seen.add(p)
        PATTERNS.append(p)


# plain controls (no group)
for pre in PRE:
    for post in POST:
        if pre or post:
            add(pre + post)
# one group with context
for pre in PRE:
    for op in OPS:
        for alt in ALTS:
            g = f"{op}({alt})"
            for post in POST:
                add(pre + g + post)
# two adjacent groups (small set)
PAIR = ["!(a)", "?(a)", "@(a|*)", "*(a)", "!(*)"]
for pre in ("", "*"):
    for g1 in PAIR:
        for g2 in PAIR:
            add(pre + g1 + g2)

CELLS = [(f"c{i:06d}", s, p)
         for i, (p, s) in enumerate((p, s) for p in PATTERNS for s in SUBJECTS)]

print(f"patterns={len(PATTERNS)} subjects={len(SUBJECTS)} cells={len(CELLS)}")

# --- bash, one spawn ---------------------------------------------------------

script_path = os.path.join(SLOTDIR, "corpus1_bash.sh")
with open(script_path, "w") as f:
    f.write("shopt -s extglob\n")
    for _cid, s, p in CELLS:
        f.write(f"[[ '{s}' == {p} ]] && echo 1 || echo 0\n")

r = subprocess.run([BASH, "--norc", script_path], capture_output=True,
                   text=True, env={"PATH": os.environ["PATH"],
                                   "LC_ALL": "C"},
                   cwd=NEUTRAL, timeout=600)
bash_lines = r.stdout.split()
assert r.returncode in (0, 1), (r.returncode, r.stderr[:500])
assert len(bash_lines) == len(CELLS), (len(bash_lines), len(CELLS),
                                       r.stderr[:500])

# --- psh engine ([[ path) ----------------------------------------------------

rows = []
for (cid, s, p), b in zip(CELLS, bash_lines):
    mine = "1" if match_shell_pattern(s, p, extglob_enabled=True) else "0"
    rows.append((cid, s, p, b, mine))

out_path = os.path.join(SLOTDIR, "corpus1_results.tsv")
with open(out_path, "w") as f:
    f.write("id\tsubject\tpattern\tbash\tpsh\n")
    for row in rows:
        f.write("\t".join(row) + "\n")

div = [row for row in rows if row[3] != row[4]]
print(f"total={len(rows)} divergent={len(div)}")

# --- end-to-end [[ sample cross-check (every 1300th cell + all divergent
#     anchor-class shapes capped at 15) --------------------------------------
sample = rows[::1300] + div[:15]
bad = 0
for cid, s, p, b, mine in sample:
    sc = f"[[ '{s}' == {p} ]] && echo 1 || echo 0"
    rr = subprocess.run([sys.executable, "-m", "psh", "-c", sc],
                        capture_output=True, text=True,
                        env={"PATH": os.environ["PATH"], "LC_ALL": "C",
                             "PYTHONPATH": WORKTREE,
                             "HOME": os.environ.get("HOME", "/tmp")},
                        cwd=NEUTRAL, timeout=30)
    got = rr.stdout.strip()
    if got != mine:
        bad += 1
        print(f"E2E-MISMATCH {cid} subj={s!r} pat={p!r} engine={mine} psh-e2e={got}")
print(f"e2e sample: {len(sample)} cells, mismatches={bad}")

# --- census: divergences by coarse shape ------------------------------------


def shape(p):
    import re as _re
    star_group = _re.search(r"\*[?*+@!]\(", p)
    qmark_group = _re.search(r"\?[?*+@!]\(", p)
    if "!(" in p:
        fam = "neg"
    elif any(op + "(" in p for op in "@?*+"):
        fam = "posgroup"
    else:
        fam = "plain"
    return (fam, bool(star_group), bool(qmark_group))


from collections import Counter  # noqa: E402
cnt = Counter()
cnt_div = Counter()
for row in rows:
    sh = shape(row[2])
    cnt[sh] += 1
    if row[3] != row[4]:
        cnt_div[sh] += 1
print("\ncensus (family, star-adj-group, qm-adj-group): divergent/total")
for sh in sorted(cnt):
    print(f"  {sh}: {cnt_div.get(sh, 0)}/{cnt[sh]}")
print("\nfirst 40 divergent rows:")
for row in div[:40]:
    print("  ", row)
