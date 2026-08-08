#!/usr/bin/env python3
"""Q4 axis-2: per-module deferred-import delta between two walker JSONs,
plus reconciliation of tip actual counts against the committed
FUNC_IMPORT_CAPS in tests/unit/tooling/test_import_layering.py at tip.

Usage: q4_02_deferred_delta.py <base.json> <tip.json> <wt_root>
"""
import ast
import json
import sys
from pathlib import Path

base = json.loads(Path(sys.argv[1]).read_text())
tip = json.loads(Path(sys.argv[2]).read_text())
wt = Path(sys.argv[3])

b = base["deferred_counts"]
t = tip["deferred_counts"]

print(f"base total: {base['deferred_import_total']} across "
      f"{base['deferred_module_count']} modules")
print(f"tip  total: {tip['deferred_import_total']} across "
      f"{tip['deferred_module_count']} modules")
print("\n--- per-module deltas (base -> tip), only changed ---")
for mod in sorted(set(b) | set(t)):
    vb, vt = b.get(mod, 0), t.get(mod, 0)
    if vb != vt:
        tag = "GREW" if vt > vb else "shrank"
        print(f"{mod}: {vb} -> {vt}  [{tag}]")

# Reconcile against committed caps at tip
guard_src = (wt / "tests/unit/tooling/test_import_layering.py").read_text()
tree = ast.parse(guard_src)
caps = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id == "FUNC_IMPORT_CAPS":
                caps = ast.literal_eval(node.value)
assert caps is not None, "FUNC_IMPORT_CAPS not found"
print(f"\ncommitted caps: {len(caps)} entries, sum {sum(caps.values())}")

over = {m: (c, caps.get(m, 0)) for m, c in t.items() if c > caps.get(m, 0)}
slack = {m: (t.get(m, 0), c) for m, c in caps.items() if t.get(m, 0) < c}
print(f"modules OVER cap (walker-actual > cap): {len(over)}")
for m, (actual, cap) in sorted(over.items()):
    print(f"  {m}: actual {actual} > cap {cap}")
print(f"modules with slack (actual < cap): {len(slack)}")
for m, (actual, cap) in sorted(slack.items()):
    print(f"  {m}: actual {actual} < cap {cap}")
