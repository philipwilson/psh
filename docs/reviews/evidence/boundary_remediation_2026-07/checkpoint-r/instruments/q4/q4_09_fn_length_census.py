#!/usr/bin/env python3
"""Q4 axis-4: function-length census over a psh/ tree.

Methodology (stated for the report):
  - every FunctionDef/AsyncFunctionDef in every psh/**/*.py (methods included,
    nested functions included; a nested function's lines also count inside its
    parent — same convention at every SHA, so deltas are apples-to-apples)
  - length = node.end_lineno - node.lineno + 1 (source lines incl. decorators?
    NO — decorators excluded: lineno is the `def` line)
  - threshold report: count of functions >= 100 lines, full sorted list

Usage: q4_09_fn_length_census.py <tree_root> <label> [--json OUT]
"""
import ast
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
label = sys.argv[2]
out_json = None
if "--json" in sys.argv:
    out_json = sys.argv[sys.argv.index("--json") + 1]

rows = []
for path in sorted((root / "psh").rglob("*.py")):
    if "__pycache__" in path.parts:
        continue
    rel = str(path.relative_to(root))
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        continue

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{child.name}"
                length = child.end_lineno - child.lineno + 1
                rows.append((rel, qual, length))
                visit(child, f"{qual}.")

    visit(tree, "")

big = sorted([r for r in rows if r[2] >= 100], key=lambda r: -r[2])
print(f"[{label}] total functions: {len(rows)}; >=100 lines: {len(big)}")
for rel, qual, n in big:
    print(f"  {n:4d}  {rel}::{qual}")
if out_json:
    Path(out_json).write_text(json.dumps(
        {"label": label, "total_functions": len(rows),
         "ge100_count": len(big),
         "ge100": [{"file": r, "fn": q, "len": n} for r, q, n in big],
         "all": [{"file": r, "fn": q, "len": n} for r, q, n in rows]}))
    print(f"json: {out_json}")
