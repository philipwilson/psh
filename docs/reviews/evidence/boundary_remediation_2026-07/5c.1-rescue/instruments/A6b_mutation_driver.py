#!/usr/bin/env python3
"""A6b — mutation arms for the A6 feasibility probe.

Each arm applies ONE anchored, count=1 replacement (5B.2 lesson 6: an
unanchored str.replace in an instrument is a seeding bug waiting to happen) to
a COPY of A6, runs mypy, and asserts the run fails FOR ITS OWN REASON (5B.1
lesson 2: a RED arm that only checks "something failed" is satisfied by any
failure at all).
"""
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(sys.argv[1])
SRC = os.path.join(ROOT, "tmp/w5c1-instruments/A6_protocol_feasibility.py")
WORK = os.path.join(ROOT, "tmp/w5c1-instruments/_A6_mutant.py")
base = open(SRC, encoding="utf-8").read()

ARMS = [
    ("M1 unknown manager member",
     "    # _ = host.expansion_manager.no_such_member       # MUST error",
     "    _ = host.expansion_manager.no_such_member",
     r'has no attribute "no_such_member"'),
    ("M2 member absent from host",
     "    # _ = host.job_manager                            # MUST error (not on host)",
     "    _ = host.job_manager",
     r'has no attribute "job_manager"'),
    ("M3 producer loses a protocol member (drop .subscript from the surface)",
     "    def subscript(self) -> object: ...",
     "    def subscript_RENAMED(self) -> object: ...",
     r'no_such|subscript|incompatible|Returning Any|error'),
    ("M4 host member typed wrong (state -> int)",
     "    def state(self) -> ShellState: ...",
     "    def state(self) -> int: ...",
     r'error'),
]

fails = []
for name, anchor, repl, reason in ARMS:
    assert base.count(anchor) == 1, f"{name}: anchor not unique ({base.count(anchor)})"
    mutant = base.replace(anchor, repl, 1)
    with open(WORK, "w", encoding="utf-8") as f:
        f.write(mutant)
    env = dict(os.environ, PYTHONPATH=ROOT, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-m", "mypy", "--follow-imports=silent",
                        "--no-error-summary", WORK],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    bit = r.returncode != 0
    right_reason = bool(re.search(reason, r.stdout + r.stderr))
    verdict = "BITES (own reason)" if (bit and right_reason) else (
        "BITES (WRONG REASON)" if bit else "DID NOT BITE")
    print(f"{name:58s} {verdict}")
    for ln in (r.stdout or "").strip().splitlines()[:2]:
        print(f"     {ln}")
    if not (bit and right_reason):
        fails.append(name)

os.path.exists(WORK) and os.remove(WORK)
print()
print(f"arms: {len(ARMS)}, bit for their own reason: {len(ARMS) - len(fails)}")
if fails:
    print("ARMS THAT FAILED TO BITE:", fails)
    sys.exit(1)
print("CONTROL: the unmutated probe must still be CLEAN")
env = dict(os.environ, PYTHONPATH=ROOT, PYTHONDONTWRITEBYTECODE="1")
r = subprocess.run([sys.executable, "-m", "mypy", "--follow-imports=silent",
                    "--no-error-summary", SRC],
                   capture_output=True, text=True, env=env, cwd=ROOT)
print(f"  unmutated exit={r.returncode} (0 expected) {r.stdout.strip()[:120]}")
sys.exit(0 if r.returncode == 0 else 1)
