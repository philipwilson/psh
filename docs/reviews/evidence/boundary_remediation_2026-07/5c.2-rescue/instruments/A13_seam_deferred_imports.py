#!/usr/bin/env python3
"""A13 — FENCE CHECK: deferred (function-body) imports inside candidate hubs.

The caps cell is cap==actual 66/177/177/0 with ZERO slack, so a seam that would
relocate a function-level import to another file is a stop-and-report, not an
edit. This enumerates every import statement occurring INSIDE the body of each
named function, so each seam design can state its exposure up front.

Usage: A13_seam_deferred_imports.py <tree_root> <file::qualname> [...]
"""
import ast
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()

for spec in sys.argv[2:]:
    rel, qual = spec.split("::")
    tree = ast.parse((ROOT / rel).read_text())

    target = {}

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{prefix}{child.name}"
                target[q] = child
                visit(child, f"{q}.")

    visit(tree, "")
    node = target.get(qual)
    if node is None:
        print(f"!! NOT FOUND: {spec}")
        continue

    imports = [n for n in ast.walk(node)
               if isinstance(n, (ast.Import, ast.ImportFrom))]
    print(f"=== {spec}: {len(imports)} deferred import(s) in body")
    for imp in imports:
        if isinstance(imp, ast.ImportFrom):
            mod = imp.module or ""
            names = ", ".join(a.name for a in imp.names)
            text = f"from {'.' * imp.level}{mod} import {names}"
        else:
            text = "import " + ", ".join(a.name for a in imp.names)
        psh = "PSH" if ("psh" in text or imp.__class__ is ast.ImportFrom
                        and getattr(imp, "level", 0)) else "stdlib"
        print(f"    :{imp.lineno:5d}  [{psh}] {text}")
