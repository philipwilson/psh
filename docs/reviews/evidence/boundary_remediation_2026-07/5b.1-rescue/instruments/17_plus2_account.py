#!/usr/bin/env python3
"""Slot 5B.1 instrument 17 — account for the gate's +22 vs my pre-registered +20.

Method (deliberately NOT the method that produced the wrong number): the
pre-registration was hand-derived from per-file pytest runs. This re-derives
from TWO independent sources and cross-checks them:

  TIP  : the phase manifests the gate itself wrote (authoritative node IDs
         actually collected and run).
  BASE : `git show <base>:<path>` parsed with ast, counting test functions
         and test methods, for every test file this slot touched.

A file this slot did not touch cannot contribute, so the account must close
using only the touched set. If it does not close, the account is wrong and
says so.

Portable: ROOT from argv[1] (default git toplevel).
"""
import ast
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                    subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                   capture_output=True, text=True
                                   ).stdout.strip()).resolve()
BASE = "8af29e6d"

TOUCHED_TEST_FILES = [
    "tests/unit/tooling/test_shell_consumer_ratchet_q1.py",
    "tests/unit/tooling/test_protocol_name_collision_q5.py",   # new
    "tests/unit/tooling/test_posix_class_table_ownership.py",  # new
    "tests/unit/protocols/test_protocol_conformance_q1.py",
    "tests/unit/tooling/test_protocol_layering_q1.py",
    "tests/unit/tooling/test_import_layering.py",
    "tests/unit/core/test_locale_service.py",
    "tests/unit/scripting/test_analysis_session.py",
]


def count_tests_in_source(src):
    """Test functions + test methods in a module source."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith("test"):
            n += 1
    return n


def base_source(rel):
    out = subprocess.run(["git", "show", f"{BASE}:{rel}"],
                         cwd=ROOT, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


print(f"ROOT={ROOT}")
print(f"BASE={BASE}  TIP={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()}")
print()

# --- Source A: static count, base vs tip, over the touched set ---
print("=" * 74)
print("(A) STATIC COUNT over the touched test files (git show vs worktree)")
print("=" * 74)
total_delta = 0
for rel in TOUCHED_TEST_FILES:
    bsrc = base_source(rel)
    tsrc = (ROOT / rel).read_text() if (ROOT / rel).exists() else None
    b = count_tests_in_source(bsrc) if bsrc is not None else 0
    t = count_tests_in_source(tsrc) if tsrc is not None else 0
    tag = "" if bsrc is not None else "   (NEW FILE)"
    d = t - b
    total_delta += d
    print(f"  {rel}")
    print(f"      base={b:<4d} tip={t:<4d} delta={d:+d}{tag}")
print(f"\n  TOTAL static delta over touched files: {total_delta:+d}")

# --- Source B: the gate's own manifests ---
print()
print("=" * 74)
print("(B) THE GATE'S OWN PHASE MANIFESTS (node IDs actually collected)")
print("=" * 74)
mdir = ROOT / "tmp/phase-manifests"
manifests = sorted(mdir.glob("*.json")) if mdir.exists() else []
if not manifests:
    print("  !! no phase manifests found")
else:
    all_ids = set()
    for m in manifests:
        try:
            data = json.loads(m.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"  !! {m.name}: {type(e).__name__}")
            continue
        ids = data if isinstance(data, list) else (
            data.get("node_ids") or data.get("tests") or data.get("collected") or [])
        if isinstance(ids, dict):
            ids = list(ids)
        print(f"  {m.name}: {len(ids)} node IDs")
        all_ids |= {str(i) for i in ids}
    print(f"  UNION across manifests: {len(all_ids)}")

    print("\n  node IDs in the touched files (tip side):")
    grand = 0
    for rel in TOUCHED_TEST_FILES:
        n = sum(1 for i in all_ids if i.startswith(rel + "::"))
        grand += n
        print(f"    {rel}: {n}")
    print(f"    total: {grand}")

# --- Reconcile ---
print()
print("=" * 74)
print("(C) RECONCILIATION")
print("=" * 74)
PRE_REGISTERED_DELTA = 20
GATE_BASE = 23896
GATE_TIP = 23918
print(f"  pre-registered delta (ledger B5) : +{PRE_REGISTERED_DELTA}")
print(f"  gate-observed delta              : +{GATE_TIP - GATE_BASE}"
      f"   ({GATE_BASE} -> {GATE_TIP})")
print(f"  static delta over touched files  : {total_delta:+d}")
print()
if total_delta == GATE_TIP - GATE_BASE:
    print("  => The touched-file static delta EXACTLY equals the gate's delta.")
    print("     The gate is right; the PRE-REGISTRATION was wrong.")
else:
    print("  => Static delta does NOT match the gate delta — the account does")
    print("     not close on the touched set alone. Do not ship this account.")
