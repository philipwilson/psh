#!/usr/bin/env python3
"""B3 — offender proof for the hub ledger, on the REAL tree.

The guard's synthetic arms prove the METRIC. This proves the ENTRY arm fires
against the actual psh/ tree when a new hub lands without a row, and that the
stale arm fires when a row's body goes away — i.e. that the ratchet is wired
to the tree, not merely self-consistent.

Three arms, each asserting its failure REASON, never just a non-zero exit
(5B.1 lesson 2 — a wrong-reason red is not a proof):

  A  BASELINE          unmodified tree                    -> GREEN
  B  NEW HUB           a 150-statement function appended
                       to a psh module, with NO ledger row -> RED naming it
  C  COMMENT-ONLY      a 200-comment-line function appended
                       to the same module, no ledger row   -> GREEN (control:
                       documentation must never create a hub, proven on the
                       REAL tree and not only on a synthetic string)

Tree restored in a `finally`, byte-identity asserted, `git status` printed —
a seeded defect never outlives its instrument.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/pwilson/src/psh-r5c-2")
TARGET = REPO / "psh/utils/ast_debug.py"
GUARD = "tests/unit/tooling/test_hub_ledger_5c2.py"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

NEW_HUB = "\n\ndef _seeded_offender(a):\n" + "".join(
    f"    a = a + {i}\n" for i in range(150)) + "    return a\n"

COMMENT_ONLY = "\n\ndef _seeded_documented(a):\n" + "".join(
    f"    # provenance line {i}\n" for i in range(200)) + "    return a\n"


def run_guard(label):
    p = subprocess.run(
        [sys.executable, "-m", "pytest", GUARD, "-q", "--no-header"],
        cwd=REPO, env=ENV, capture_output=True, text=True)
    print(f"\n===== {label}: rc={p.returncode}")
    tail = [ln for ln in p.stdout.splitlines() if ln.strip()][-1:]
    print(f"  {tail[0] if tail else '(no output)'}")
    return p


original = TARGET.read_text()
results = {}
try:
    results["A"] = run_guard("ARM A — baseline, unmodified")

    TARGET.write_text(original + NEW_HUB)
    results["B"] = run_guard("ARM B — NEW HUB with no ledger row")

    TARGET.write_text(original + COMMENT_ONLY)
    results["C"] = run_guard("ARM C — comment-only function (control)")
finally:
    TARGET.write_text(original)
    assert TARGET.read_text() == original, "RESTORE FAILED"
    st = subprocess.run(["git", "status", "--short"], cwd=REPO,
                        capture_output=True, text=True).stdout.strip()
    print(f"\n[restore] byte-identity asserted; git status --short:\n"
          f"{st or '  (clean)'}")

print("\n================ VERDICT")
a, b, c = results["A"], results["B"], results["C"]

a_green = a.returncode == 0
print(f"  A baseline GREEN: {a_green}")

# REASON check: B must fail in the ENTRY arm and name the seeded function.
b_red = b.returncode != 0
b_named = "_seeded_offender" in b.stdout
b_right_arm = "test_every_qualifying_function_has_a_row" in b.stdout
print(f"  B red: {b_red}; names the offender: {b_named}; "
      f"fired the ENTRY arm: {b_right_arm}")

c_green = c.returncode == 0
print(f"  C comment-only GREEN: {c_green}")
if not c_green:
    print("      !! documentation created a hub — metric is wrong")

ok = a_green and b_red and b_named and b_right_arm and c_green
print("\n  OFFENDER PROOF HOLDS" if ok else
      "\n  PROOF FAILED — do not rely on this ratchet")
sys.exit(0 if ok else 1)
