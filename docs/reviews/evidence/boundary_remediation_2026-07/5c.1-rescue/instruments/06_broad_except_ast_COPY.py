#!/usr/bin/env python3
"""Q5 census 5 (MEDIUM-12/Q2 debt): AST census of broad exception handlers.

Counts ExceptHandler nodes under <root>/psh whose type is exactly `Exception`
(incl. `except Exception as e` and tuple members) plus bare `except:`.
Prose/docstring mentions excluded by construction. Reads tree root argv[1].
"""
import ast
import os
import sys

ROOT = sys.argv[1]
PSH = os.path.join(ROOT, "psh")

sites = []
bare = []

def mentions_exception(t):
    if t is None:
        return False
    if isinstance(t, ast.Tuple):
        return any(mentions_exception(e) for e in t.elts)
    return isinstance(t, ast.Name) and t.id == "Exception"

for dirpath, dirnames, filenames in sorted(os.walk(PSH)):
    dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
    for fn in sorted(filenames):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(dirpath, fn)
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    bare.append(f"{rel}:{node.lineno}")
                elif mentions_exception(node.type):
                    sites.append(f"{rel}:{node.lineno}")

print(f"except-Exception handlers: {len(sites)}")
for s in sites:
    print(f"  {s}")
print(f"bare-except handlers: {len(bare)}")
for s in bare:
    print(f"  {s}")
