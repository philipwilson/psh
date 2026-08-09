#!/usr/bin/env python3
"""C2 — re-source the hub-ledger docstring's figures from the CANONICAL metric.

N13: the guard's body promises that every figure comes from its own
``executable_lines``, while its docstring quoted A9's numbers. That is
NAME-VS-BODY inside the guard's own docstring — the exact charge this campaign
brings against other people's work.

This imports the guard's canonical metric and recomputes every figure the
docstring states, at the trees the docstring is talking about (base for the
census claims, v0.776→v0.777 for the two grower deltas). Whatever this prints
is what the docstring will say.
"""
import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path("/Users/pwilson/src/psh-r5c-2")
SCRATCH = ROOT / "tmp/w5c2-scratch"
GUARD = ROOT / "tests/unit/tooling/test_hub_ledger_5c2.py"

sys.path.insert(0, str(ROOT))  # the guard imports tests.unit.tooling.*
spec = importlib.util.spec_from_file_location("hl", GUARD)
hl = importlib.util.module_from_spec(spec)
sys.modules["hl"] = hl
spec.loader.exec_module(hl)


def measure(tree_root, rel, qual):
    """(executable, nominal, comment) via the GUARD's canonical metric."""
    path = Path(tree_root) / rel
    source = path.read_text()
    comments = hl._comment_start_lines(source)
    for q, node in hl.iter_functions(source, rel):
        if q != qual:
            continue
        ex = hl.executable_lines(node, source, comments)
        nom = hl.nominal_lines(node)
        span = set(range(node.lineno, node.end_lineno + 1))
        body = list(node.body)
        doc_span = set()
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            d = body[0]
            doc_span = set(range(d.lineno, d.end_lineno + 1))
        cmt = len(comments & (span - doc_span))
        return ex, nom, cmt
    return None


BASE = SCRATCH / "base-3a3e0782"
V776 = SCRATCH / "v0776-d8166242"
V777 = SCRATCH / "v0777-67261b29"

print("=== canonical metric (the guard's own executable_lines)")

# 1. how many of the 60 base census rows are below 100 EXECUTABLE lines
import json  # noqa: E402
census = json.loads((ROOT / "tmp/w5c2-instruments/A1_census_base.json").read_text())
rows = [(r["file"], r["fn"]) for r in census["ge100"]]
below = 0
for rel, qual in rows:
    m = measure(BASE, rel, qual)
    if m and m[0] < 100:
        below += 1
print(f"base census rows: {len(rows)}; below 100 EXECUTABLE: {below}")

# 2. ShellState.__init__
m = measure(BASE, "psh/core/state.py", "ShellState.__init__")
print(f"ShellState.__init__ (base): nominal={m[1]} executable={m[0]} comment={m[2]}")

# 3. the two growers, v0.776 -> v0.777
for rel, qual, label in (
    ("psh/builtins/read_builtin.py", "ReadBuiltin.execute", "read_builtin"),
    ("psh/builtins/parse_tree.py", "ParseTreeBuiltin.execute", "parse_tree"),
):
    a = measure(V776, rel, qual)
    b = measure(V777, rel, qual)
    print(f"{label}: nominal {a[1]}->{b[1]} ({b[1]-a[1]:+d})  "
          f"executable {a[0]}->{b[0]} ({b[0]-a[0]:+d})  "
          f"comment {a[2]}->{b[2]} ({b[2]-a[2]:+d})")
