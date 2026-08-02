#!/usr/bin/env python3
"""Slot 3.1 anchor probes, part 2: case + pathname glob cells with extglob
enabled on its OWN LINE (incremental parse), which part 1 showed is required.
Oracle: PATH bash /opt/homebrew/bin/bash 5.2.26. psh at base 29456fdc.
"""
import os
import subprocess
import sys

WORKTREE = "/Users/pwilson/src/psh-r3-1"
BASH = "/opt/homebrew/bin/bash"
NEUTRAL = os.path.join(WORKTREE, "tmp", "slot31", "neutral")
GLOBDIR = os.path.join(WORKTREE, "tmp", "slot31", "globdir")
ENV = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"),
       "LC_ALL": "C", "PYTHONPATH": WORKTREE}


def run(argv, cwd=NEUTRAL):
    r = subprocess.run(argv, capture_output=True, text=True, env=ENV,
                       cwd=cwd, timeout=30)
    return r.returncode, r.stdout, r.stderr


def fmt(r):
    return f"rc={r[0]} out={r[1]!r} err={r[2]!r}"


CELLS = [
    ("case_H7b", NEUTRAL, 'case a in\n*!(a)) echo M;;\n*) echo N;;\nesac'),
    ("case_H7a", NEUTRAL, 'case "" in\n*@(a|*)) echo M;;\n*) echo N;;\nesac'),
    ("case_H7c", NEUTRAL, 'case "" in\n*!(*)) echo M;;\n*) echo N;;\nesac'),
    ("glob_negA", GLOBDIR, 'printf "[%s]\\n" *!(a)'),
    ("glob_negStar", GLOBDIR, 'printf "[%s]\\n" *!(*)'),
    ("glob_atStar", GLOBDIR, 'printf "[%s]\\n" *@(a|*)'),
]
for rid, cwd, body in CELLS:
    script = "shopt -s extglob\n" + body + "\necho rc=$?\n"
    b = run([BASH, "--norc", "-c", script], cwd=cwd)
    p = run([sys.executable, "-m", "psh", "--parser", "rd", "-c", script],
            cwd=cwd)
    pc = run([sys.executable, "-m", "psh", "--parser", "combinator", "-c",
              script], cwd=cwd)
    mark = "SAME" if (b[0], b[1]) == (p[0], p[1]) else "DIFF"
    cmark = "SAME" if (b[0], b[1]) == (pc[0], pc[1]) else "DIFF"
    print(f"{rid} [rd:{mark} comb:{cmark}] (cwd={os.path.basename(cwd)})")
    print(f"    bash    :[{fmt(b)}]")
    print(f"    psh-rd  :[{fmt(p)}]")
    print(f"    psh-comb:[{fmt(pc)}]")
