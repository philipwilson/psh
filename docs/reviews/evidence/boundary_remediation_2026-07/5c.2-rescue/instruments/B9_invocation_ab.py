#!/usr/bin/env python3
"""B9 — A/B for parse_invocation: compare the FROZEN CONFIG OBJECT, not output.

The other seams compared shell stdout/stderr/rc. That is the wrong instrument
here: parse_invocation is a pure argv -> InvocationConfig function, and most of
its fields never surface as visible output, so a shell-level probe would be
consistent with a field silently changing. This imports BOTH trees' modules
under distinct names and compares every field of the resulting config — the
level the seam actually operates at (the _config helper's whole risk is a
field going missing).

Import discriminator asserted per tree (psh.__file__ must live under the tree
being measured) — the editable-install-imports-MAIN hazard.

Usage: B9_invocation_ab.py
"""
import dataclasses
import importlib
import subprocess
import sys
from pathlib import Path

BASE = Path("/Users/pwilson/src/psh-r5c-2/tmp/w5c2-scratch/base-3a3e0782")
NOW = Path("/Users/pwilson/src/psh-r5c-2")

CASES = [
    ["psh"],
    ["psh", "-c", "echo hi"],
    ["psh", "-c", "echo hi", "name"],
    ["psh", "-c", "echo hi", "name", "a", "b"],
    ["psh", "script.sh"],
    ["psh", "script.sh", "a", "b"],
    ["psh", "-s"],
    ["psh", "-s", "a", "b"],
    ["psh", "-i"],
    ["psh", "-i", "-c", "echo x"],
    ["psh", "--norc"],
    ["psh", "--rcfile", "/tmp/x"],
    ["psh", "--parser", "rd"],
    ["psh", "--parser", "pc"],
    ["psh", "--parser", "combinator", "-c", "true"],
    ["psh", "--validate", "f.sh"],
    ["psh", "--lint", "f.sh"],
    ["psh", "--help"],
    ["psh", "--version"],
    ["psh", "--help", "--validate", "--lint", "f.sh"],
    ["psh", "-e", "-u", "-c", "true"],
    ["psh", "-eu", "script.sh"],
    ["psh", "+e", "-c", "true"],
    ["psh", "-o", "pipefail", "-c", "true"],
    ["psh", "+o", "pipefail", "-c", "true"],
    ["psh", "-o"],
    ["psh", "--ast-format", "tree", "-c", "true"],
    ["psh", "--", "-c"],
    ["psh", "-", "a"],
    ["psh", "-c"],
    ["psh", "--parser", "bogus"],
    ["psh", "--validate", "--lint", "f.sh"],
    ["psh", "-z"],
    ["psh", "--nosuchopt"],
]


def load(tree: Path, alias: str):
    sys.path.insert(0, str(tree))
    for mod in [m for m in sys.modules if m == "psh" or m.startswith("psh.")]:
        del sys.modules[mod]
    psh = importlib.import_module("psh")
    assert str(tree) in psh.__file__, (
        f"DISCRIMINATOR FAILED for {alias}: imported {psh.__file__}, "
        f"expected a module under {tree}")
    inv = importlib.import_module("psh.invocation")
    sys.path.pop(0)
    return inv


def describe(inv, argv):
    try:
        cfg = inv.parse_invocation(argv)
    except inv.InvocationError as e:
        return ("InvocationError", tuple(e.args[0]))
    except Exception as e:  # any other escape is itself a difference
        return ("UNEXPECTED", type(e).__name__, str(e))
    return ("Config", tuple(sorted(
        (f.name, repr(getattr(cfg, f.name)))
        for f in dataclasses.fields(cfg))))


base_inv = load(BASE, "BASE")
base_results = [describe(base_inv, list(a)) for a in CASES]

now_inv = load(NOW, "NOW")
now_results = [describe(now_inv, list(a)) for a in CASES]

fail = 0
for argv, a, b in zip(CASES, base_results, now_results):
    if a != b:
        fail = 1
        print(f"  *** DIVERGED  {argv}")
        print(f"      base: {a}")
        print(f"      now : {b}")

nfields = len(base_results[0][1]) if base_results[0][0] == "Config" else 0
print(f"cases compared: {len(CASES)}; config fields compared per case: {nfields}")
print("VERDICT: identical on every field of every case" if not fail
      else "VERDICT: DIVERGENCE — zero-delta claim broken")
sys.exit(fail)
