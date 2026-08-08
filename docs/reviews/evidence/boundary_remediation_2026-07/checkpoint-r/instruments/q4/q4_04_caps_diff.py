#!/usr/bin/env python3
"""Q4 axis-2: diff committed FUNC_IMPORT_CAPS between two git revisions of
tests/unit/tooling/test_import_layering.py, and reconcile each side's caps
against that side's walker-actual counts.

Usage: q4_04_caps_diff.py <repo> <rev_base> <rev_tip> <base_actuals.json> <tip_actuals.json>
"""
import ast
import json
import subprocess
import sys
from pathlib import Path

repo, rev_base, rev_tip, base_json, tip_json = sys.argv[1:6]
GUARD = "tests/unit/tooling/test_import_layering.py"


def caps_at(rev):
    src = subprocess.run(
        ["git", "-C", repo, "show", f"{rev}:{GUARD}"],
        capture_output=True, text=True, check=True).stdout
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "FUNC_IMPORT_CAPS":
                    return ast.literal_eval(node.value)
    raise SystemExit(f"FUNC_IMPORT_CAPS not found at {rev}")


cb, ct = caps_at(rev_base), caps_at(rev_tip)
ab = json.loads(Path(base_json).read_text())["deferred_counts"]
at = json.loads(Path(tip_json).read_text())["deferred_counts"]

print(f"caps@{rev_base}: {len(cb)} entries, sum {sum(cb.values())}")
print(f"caps@{rev_tip}: {len(ct)} entries, sum {sum(ct.values())}")
print("\n--- cap changes base -> tip ---")
changed = False
for m in sorted(set(cb) | set(ct)):
    vb, vt = cb.get(m), ct.get(m)
    if vb != vt:
        changed = True
        print(f"  {m}: {vb} -> {vt}")
if not changed:
    print("  (none)")

print(f"\n--- slack at BASE (actual < cap @{rev_base}) ---")
sb = {m: (ab.get(m, 0), c) for m, c in cb.items() if ab.get(m, 0) < c}
for m, (a, c) in sorted(sb.items()):
    print(f"  {m}: actual {a} < cap {c}")
print(f"  total slack: {sum(c - a for a, c in sb.values())}")

print(f"\n--- slack at TIP (actual < cap @{rev_tip}) ---")
st = {m: (at.get(m, 0), c) for m, c in ct.items() if at.get(m, 0) < c}
for m, (a, c) in sorted(st.items()):
    print(f"  {m}: actual {a} < cap {c}")
print(f"  total slack: {sum(c - a for a, c in st.values())}")
