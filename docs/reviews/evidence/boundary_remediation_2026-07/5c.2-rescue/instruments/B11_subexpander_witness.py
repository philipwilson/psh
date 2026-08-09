#!/usr/bin/env python3
"""B11 — mypy-load-bearing witnesses for the three typed sub-expander members.

5B.2 lesson 2: "mypy-clean on a zero-consumer surface means UNOBSERVED".
Changing `-> Any` to a concrete type is worth nothing unless a WRONG-TYPED USE
now fails type checking. This proves it per member: seed a use that is wrong
for that member's real type, run mypy, require an error AT THAT LINE; then
restore and require clean.

The control matters as much as the arms: with `-> Any` (the pre-change state)
every one of these seeded uses type-checks fine, which is exactly why the
change is needed and exactly what makes these witnesses load-bearing rather
than decorative.

Tree restored in a finally, byte-identity asserted.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/pwilson/src/psh-r5c-2")
PROBE = REPO / "psh/expansion/_subexpander_witness_probe.py"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

HEADER = '''"""TEMPORARY witness probe (instrument B11) — never committed."""
from __future__ import annotations

from ..protocols import ExpansionSubExpanders


def _probe(subs: ExpansionSubExpanders) -> None:
'''

# member -> a use that is WRONG for that member's real type
ARMS = {
    "subscript": "    x: int = subs.subscript\n",
    "command_sub": "    x: int = subs.command_sub\n",
    "tilde_expander": "    x: int = subs.tilde_expander\n",
}


def run_mypy():
    return subprocess.run(["mypy"], cwd=REPO, env=ENV,
                          capture_output=True, text=True)


results = {}
try:
    for member, body in ARMS.items():
        PROBE.write_text(HEADER + body)
        p = run_mypy()
        hit = [ln for ln in p.stdout.splitlines()
               if "_subexpander_witness_probe" in ln and "error:" in ln]
        results[member] = (p.returncode != 0, hit)
        print(f"  {member}: mypy rc={p.returncode}; errors at probe: {len(hit)}")
        for ln in hit[:2]:
            print(f"      {ln.strip()}")
finally:
    if PROBE.exists():
        PROBE.unlink()
    st = subprocess.run(["git", "status", "--short"], cwd=REPO,
                        capture_output=True, text=True).stdout.strip()
    print(f"\n[restore] probe removed; git status --short:\n{st or '  (clean)'}")
    assert not PROBE.exists(), "probe file outlived the instrument"

clean = run_mypy()
print(f"\n  post-restore mypy: rc={clean.returncode} "
      f"({clean.stdout.strip().splitlines()[-1] if clean.stdout.strip() else ''})")

# CONTROL, proven rather than asserted: with the pre-change `-> Any` the very
# same seeded use type-checks CLEAN. Without this, "the annotation is
# load-bearing" rests on the assumption that Any would have let it through.
PROTO = REPO / "psh/protocols/__init__.py"
proto_orig = PROTO.read_text()
control_ok = False
try:
    reverted = proto_orig.replace(
        'def subscript(self) -> "SubscriptEvaluator":',
        'def subscript(self) -> Any:', 1)
    assert reverted != proto_orig, "control anchor did not match"
    PROTO.write_text(reverted)
    PROBE.write_text(HEADER + ARMS["subscript"])
    c = run_mypy()
    hits = [ln for ln in c.stdout.splitlines()
            if "_subexpander_witness_probe" in ln and "error:" in ln]
    control_ok = not hits
    print(f"\n  CONTROL (subscript back to `-> Any`): probe errors = {len(hits)} "
          f"-> {'CLEAN, as predicted' if control_ok else 'STILL ERRORS (!)'}")
finally:
    PROTO.write_text(proto_orig)
    if PROBE.exists():
        PROBE.unlink()
    assert PROTO.read_text() == proto_orig, "RESTORE FAILED on protocols"
    st = subprocess.run(["git", "status", "--short"], cwd=REPO,
                        capture_output=True, text=True).stdout.strip()
    print(f"[restore] git status --short:\n{st or '  (clean)'}")

ok = (all(bit and hits for bit, hits in results.values())
      and clean.returncode == 0 and control_ok)
print("\n  ALL THREE MEMBERS ARE MYPY-LOAD-BEARING (control confirms Any was not)"
      if ok else "\n  WITNESS FAILED — a member's type is not observed")
sys.exit(0 if ok else 1)
