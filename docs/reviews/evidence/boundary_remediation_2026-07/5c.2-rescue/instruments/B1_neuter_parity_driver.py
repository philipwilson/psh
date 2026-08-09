#!/usr/bin/env python3
"""B1 — neuter-parity probe for D-5B.2-dead (`state.foreground_pgid`).

CLAIM UNDER TEST: `state.foreground_pgid` is write-only in production, so
neutering every production WRITE must leave shell behaviour unchanged.

Selection (the recorded meaning of "the 392 set"): `tests/integration/job_control`
— 392 collected at base. Path-auto-marked SERIAL, so it runs WITHOUT `-n`.

THREE ARMS (R1 §5 condition iii / R3 §2):

  A  BASE      unmodified tree              -> record outcome
  B  NEUTER    every production write to foreground_pgid disabled
               -> expect IDENTICAL outcome to A (that is the parity claim)
  C  RED       a deliberate behavioural defect seeded in a LIVE part of the
               SAME job-control path (`_promote_to_current` made a no-op)
               -> expect RED, and the failures must name the stopped-job
               CURRENT-marker behaviour, i.e. fail for the SEEDED reason

Arm C exists because a parity claim from a green run is worthless unless the
harness is demonstrably able to go red. It deliberately does NOT target
foreground_pgid: the whole point is that the field is dead, so a change to it
CANNOT fire. Sensitivity therefore has to be shown on a live sibling path.

DISCIPLINE:
  - PYTHONDONTWRITEBYTECODE=1 in every arm (5B.1 lesson 1: same-length edits
    defeat pyc mtime+size invalidation).
  - Every edit is an ANCHORED `str.replace(..., count=1)` (5B.2 lesson 6) and
    the driver ASSERTS the anchor matched exactly once before proceeding.
  - The seeded defect never outlives the instrument: the tree is restored in a
    `finally`, and the driver prints `git status --short` at the end.
  - Arm C asserts its failure REASON, not merely non-zero exit (5B.1 lesson 2).

Usage: B1_neuter_parity_driver.py            (runs all three arms)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/pwilson/src/psh-r5c-2")
TARGET = REPO / "psh/executor/job_control.py"
SELECTION = "tests/integration/job_control"

ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

# --- the three production writes (D2.1 / LEDGER D-5B.2-dead: :358, :989, :1020)
NEUTER_EDITS = [
    # 1. the publish member's only statement
    ("""        if self.shell_state is not None:
            self.shell_state.foreground_pgid = pgid""",
     """        if self.shell_state is not None:
            pass  # NEUTERED (B1 arm B)"""),
    # 2 + 3. the two hasattr-guarded clears — textually identical, so they are
    # replaced one at a time with an occurrence assertion (never replace_all).
]
CLEAR_SRC = """            if self.shell_state is not None and hasattr(self.shell_state, 'foreground_pgid'):
                self.shell_state.foreground_pgid = None"""
CLEAR_DST = """            if self.shell_state is not None:
                pass  # NEUTERED (B1 arm B)"""
CLEAR_SRC_8 = """        if self.shell_state is not None and hasattr(self.shell_state, 'foreground_pgid'):
            self.shell_state.foreground_pgid = None"""
CLEAR_DST_8 = """        if self.shell_state is not None:
            pass  # NEUTERED (B1 arm B)"""

RED_SRC = """        if self.current_job is job:
            return
        self.previous_job = self.current_job
        self.current_job = job"""
RED_DST = """        if self.current_job is job:
            return
        return  # SEEDED DEFECT (B1 arm C): promotion disabled"""


def anchored(text, src, dst, label):
    n = text.count(src)
    assert n == 1, f"anchor {label!r} matched {n} times, expected exactly 1"
    return text.replace(src, dst, 1)


def run_selection(label):
    print(f"\n===== ARM {label}: pytest {SELECTION} (serial, no -n)", flush=True)
    p = subprocess.run(
        [sys.executable, "-m", "pytest", SELECTION, "-q", "--no-header", "-p", "no:randomly"],
        cwd=REPO, env=ENV, capture_output=True, text=True)
    tail = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "(no output)"
    m = re.search(r"(\d+) passed", p.stdout)
    passed = int(m.group(1)) if m else -1
    f = re.search(r"(\d+) failed", p.stdout)
    failed = int(f.group(1)) if f else 0
    print(f"  rc={p.returncode}  passed={passed}  failed={failed}")
    print(f"  tail: {tail}")
    failing_names = re.findall(r"^(FAILED [^\s]+)", p.stdout, re.M)
    return {"rc": p.returncode, "passed": passed, "failed": failed,
            "tail": tail, "failing": failing_names, "stdout": p.stdout}


original = TARGET.read_text()
results = {}
try:
    results["A"] = run_selection("A (BASE, unmodified)")

    # ---- arm B: neuter all three production writes
    text = original
    for src, dst in NEUTER_EDITS:
        text = anchored(text, src, dst, "publish member")
    text = anchored(text, CLEAR_SRC, CLEAR_DST, "clear #2 (12-space indent)")
    text = anchored(text, CLEAR_SRC_8, CLEAR_DST_8, "clear #1 (8-space indent)")
    assert "self.shell_state.foreground_pgid" not in text, \
        "arm B did not remove every production write"
    TARGET.write_text(text)
    print("\n[arm B] all three production writes neutered; "
          "zero `self.shell_state.foreground_pgid` assignments remain")
    results["B"] = run_selection("B (NEUTERED)")

    # ---- arm C: RED sensitivity control on a LIVE sibling path
    TARGET.write_text(anchored(original, RED_SRC, RED_DST,
                               "_promote_to_current"))
    print("\n[arm C] _promote_to_current disabled (live path, NOT foreground_pgid)")
    results["C"] = run_selection("C (RED CONTROL)")
finally:
    TARGET.write_text(original)
    st = subprocess.run(["git", "status", "--short"], cwd=REPO,
                        capture_output=True, text=True).stdout.strip()
    print(f"\n[restore] tree restored; git status --short:\n{st or '  (clean)'}")
    assert TARGET.read_text() == original, "RESTORE FAILED — tree not returned to base"

print("\n================ VERDICT")
a, b, c = results["A"], results["B"], results["C"]
print(f"  A base    : passed={a['passed']} failed={a['failed']} rc={a['rc']}")
print(f"  B neutered: passed={b['passed']} failed={b['failed']} rc={b['rc']}")
print(f"  C red ctl : passed={c['passed']} failed={c['failed']} rc={c['rc']}")

parity = (a["passed"], a["failed"], a["rc"]) == (b["passed"], b["failed"], b["rc"])
print(f"\n  PARITY (A == B): {'YES' if parity else 'NO'}"
      "   <- the deadness claim")
# R4 §1 REQUIRED AMENDMENT: the docstring and D3 §3(iii) claim arm C asserts
# its failure REASON, but `failed > 0 and rc != 0` would accept a
# red-for-the-wrong-reason (an unrelated flake) as sensitivity — a NAME-VS-BODY
# gap in this instrument against its own docstring, and the exact 5B.1 lesson-2
# class. The reason is now part of the verdict, not merely printed.
named = any("stopped_job_current_marker" in n for n in c["failing"])
sensitive = c["failed"] > 0 and c["rc"] != 0 and named
print("  arm C failing names:")
for name in c["failing"][:12]:
    print(f"      {name}")
if sensitive:
    print("  SENSITIVITY (C red, for its SEEDED reason): YES"
          "   <- harness can detect a delta at all")
elif c["failed"] > 0 and c["rc"] != 0:
    print("  SENSITIVITY: RED-BUT-WRONG-REASON — NOT established"
          "   <- arm C went red without naming stopped_job_current_marker")
else:
    print("  SENSITIVITY: NO — arm C did not go red at all")
print("\n  CLAIM HOLDS" if (parity and sensitive) else
      "\n  CLAIM NOT ESTABLISHED — do not proceed to the delete")
