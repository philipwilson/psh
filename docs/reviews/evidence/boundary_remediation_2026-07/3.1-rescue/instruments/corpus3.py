#!/usr/bin/env python3
"""Slot 3.1 Phase C: corpus3 — the R7 blind-spot grammar, widened.

Star-literal-star contexts (the glibc star-jump surface), post-negation
continuations, group-in-segment shapes (no jump through groups), multi-run
chains, and a disjoint-alphabet {a,c} mirror. Deterministic (these constant
lists are corpus3 v1). Subjects to length 4 (multi-segment room).

Ceremony: PATH bash /opt/homebrew/bin/bash 5.2.26 --norc LC_ALL=C, ONE
spawn per alphabet bucket via a script file; model = bash_model.predict
(v5, star-jump); psh column = worktree engine via match_shell_pattern.
Output: corpus3_results.tsv + census.
"""
import itertools
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


def build(second: str) -> list:
    """Corpus3 patterns over alphabet {'a', second}."""
    b = second
    ops = ["@", "?", "*", "+", "!"]
    alts = ["a", b, "*", f"a|{b}", "a|*", "", "a*"]
    # star-segment-star contexts (the jump surface) + group-in-segment
    pre = ["*a*", f"*{b}*", f"*a{b}*", f"*a*{b}*", "a*a*", "*a?*", "*?a*",
           "**a*", "*a**", "*@(a)*", f"*!({b})a*", f"*a@({b})*",
           f"*a*{b}", f"a*{b}*a*"]
    # continuations incl. after-negation shapes
    post = ["", "a", "?a", "a?", "*a", "a*", b, "@(a)", "?(a)" + b, "*",
            "?", "??"]
    pats = []
    seen = set()

    def add(p):
        if p not in seen:
            seen.add(p)
            pats.append(p)

    for pr in pre:
        for op in ops:
            for alt in alts:
                for po in post:
                    add(pr + f"{op}({alt})" + po)
    # no-group star-segment controls
    for pr in pre:
        for po in post:
            if "(" not in pr + po:
                add(pr + po)
    # multi-run chains with groups mid-pattern
    for chain in (f"*a*{b}*", "*a*a*"):
        for op in ("!", "?", "@"):
            for alt in ("a", "*"):
                for po in ("", "a", "?a"):
                    add(chain + f"{op}({alt})" + po)
    return pats


CELLS = []
for second in ("b", "c"):
    subjects = [""] + ["".join(t) for length in (1, 2, 3, 4)
                       for t in itertools.product("a" + second,
                                                  repeat=length)]
    for p in build(second):
        for s in subjects:
            CELLS.append((s, p))
print(f"corpus3: {len(CELLS)} cells "
      f"({len(set(p for _s, p in CELLS))} distinct patterns)")

script_path = os.path.join(SLOTDIR, "corpus3_bash.sh")
with open(script_path, "w") as f:
    f.write("shopt -s extglob\n")
    for s, p in CELLS:
        f.write(f"[[ '{s}' == {p} ]] && echo 1 || echo 0\n")
r = subprocess.run([BASH, "--norc", script_path], capture_output=True,
                   text=True, env={"PATH": os.environ["PATH"],
                                   "LC_ALL": "C"},
                   cwd=NEUTRAL, timeout=900)
answers = r.stdout.split()
assert len(answers) == len(CELLS), (len(answers), len(CELLS), r.stderr[:400])

model_mm, psh_mm = [], []
with open(os.path.join(SLOTDIR, "corpus3_results.tsv"), "w") as f:
    f.write("subject\tpattern\tbash\tpsh\tmodel\n")
    for (s, p), b in zip(CELLS, answers):
        eng = "1" if match_shell_pattern(s, p, extglob_enabled=True) else "0"
        mod = "1" if predict(s, p) else "0"
        f.write(f"{s}\t{p}\t{b}\t{eng}\t{mod}\n")
        if mod != b:
            model_mm.append((s, p, b, mod))
        if eng != b:
            psh_mm.append((s, p, b, eng))
print(f"model-v5 mismatches={len(model_mm)}  "
      f"engine(tip)-vs-bash={len(psh_mm)}")
for m in model_mm[:30]:
    print("  MODEL-MM", m)
