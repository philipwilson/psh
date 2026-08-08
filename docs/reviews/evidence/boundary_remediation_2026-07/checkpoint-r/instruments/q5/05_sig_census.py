#!/usr/bin/env python3
"""Q5 census 4 (MEDIUM-16): incomplete boundary-signature magnitude.

Methodology A (broad, matches #22's "623 of 3,073 without complete parameter
and return annotations"): a def is INCOMPLETE if any parameter other than
self/cls lacks an annotation OR the return annotation is missing. All defs
counted incl. nested/dunder/property.

Methodology B (narrow, the 510-style variant): same rule but EXCLUDING defs
whose name starts and ends with '__' (dunders) AND excluding nested defs
(functions defined inside functions) — the boundary-visible surface.

Prints totals, per-top-level-package split, and the top files under each
methodology. Reads tree root argv[1].
"""
import ast
import os
import sys
from collections import Counter

ROOT = sys.argv[1]
PSH = os.path.join(ROOT, "psh")

total = 0
inc_a = []   # all incomplete
inc_b = []   # non-dunder, non-nested incomplete
totals_b = 0

class V(ast.NodeVisitor):
    def __init__(self, rel):
        self.rel = rel
        self.fn_depth = 0

    def visit_ClassDef(self, node):
        self.generic_visit(node)

    def _do(self, node):
        global total, totals_b
        total += 1
        nested = self.fn_depth > 0
        dunder = node.name.startswith("__") and node.name.endswith("__")
        args = node.args
        missing_param = any(
            a.annotation is None
            for a in (args.posonlyargs + args.args + args.kwonlyargs
                      + ([args.vararg] if args.vararg else [])
                      + ([args.kwarg] if args.kwarg else []))
            if a.arg not in ("self", "cls")
        )
        incomplete = missing_param or node.returns is None
        if incomplete:
            inc_a.append((self.rel, node.lineno, node.name))
        if not nested and not dunder:
            totals_b += 1
            if incomplete:
                inc_b.append((self.rel, node.lineno, node.name))
        self.fn_depth += 1
        self.generic_visit(node)
        self.fn_depth -= 1

    visit_FunctionDef = _do
    visit_AsyncFunctionDef = _do

for dirpath, dirnames, filenames in sorted(os.walk(PSH)):
    dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
    for fn in sorted(filenames):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(dirpath, fn)
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as f:
            V(rel).visit(ast.parse(f.read(), filename=rel))

def pkg(rel):
    parts = rel.split(os.sep)
    return parts[1] if len(parts) > 2 else "(top)"

print(f"total defs: {total}")
print(f"METHOD A incomplete (any def, missing param-ann or return-ann): {len(inc_a)}")
print(f"METHOD B denominator (non-dunder, non-nested): {totals_b}; incomplete: {len(inc_b)}")
print(f"\nMETHOD A by package: {Counter(pkg(r) for r, _, _ in inc_a).most_common()}")
print(f"\nMETHOD A top files: {Counter(r for r, _, _ in inc_a).most_common(15)}")
