#!/usr/bin/env python3
"""Q4 axis-1: per-module layering record for the campaign's named new/reworked
modules — runtime psh imports, deferred count, and cap entry (if any).

Usage: q4_07_new_modules_layering.py <tip_walker.json> <wt_root>
"""
import ast
import json
import sys
from pathlib import Path

MODULES = [
    "psh.expansion.procsub_render",
    "psh.io_redirect.input_cursor",
    "psh.executor.child_policy",
    "psh.scripting.analysis_session",
    "psh.expansion.operands",
    "psh.expansion.pattern_engine",
    "psh.ast_nodes.pattern_ast" ,  # pattern engine family (if present)
]

tip = json.loads(Path(sys.argv[1]).read_text())
wt = Path(sys.argv[2])

guard_src = (wt / "tests/unit/tooling/test_import_layering.py").read_text()
caps = None
for node in ast.walk(ast.parse(guard_src)):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "FUNC_IMPORT_CAPS":
                caps = ast.literal_eval(node.value)

deferred = tip["deferred_counts"]
dtargets = tip["deferred_targets"]

# recompute runtime edges for just these modules from source (readable record)
sys.path.insert(0, str(Path(__file__).parent))
from q4_01_import_walker import walk  # noqa: E402

_, runtime_edges, _, _ = walk(wt)

for m in MODULES:
    rel = Path(*m.split(".")).with_suffix(".py")
    p = wt / rel
    if not p.exists():
        p_pkg = wt / Path(*m.split(".")) / "__init__.py"
        if not p_pkg.exists():
            print(f"{m}: FILE ABSENT at tip")
            continue
    edges = sorted(runtime_edges.get(m, ()))
    print(f"{m}:")
    print(f"  runtime psh imports ({len(edges)}): {edges}")
    print(f"  deferred psh imports: {deferred.get(m, 0)} "
          f"{dtargets.get(m, [])}  cap entry: {caps.get(m, '(none -> 0)')}")
