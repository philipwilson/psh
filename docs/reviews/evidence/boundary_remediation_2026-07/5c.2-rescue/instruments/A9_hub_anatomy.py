#!/usr/bin/env python3
"""A9 — anatomy of every census hub: what those ">=100 lines" actually ARE.

The q4_09 census metric is `end_lineno - lineno + 1` over every FunctionDef,
NESTED FUNCTIONS INCLUDED (its own methodology block says so, and says a nested
function's lines also count inside its parent). Two consequences the ledger
design has to face, neither of which is visible in the census output:

  (1) DOUBLE COUNTING — a nested def >=100 lines appears as its OWN row AND
      inside its parent's row. A ledger keyed per row would then carry two
      dispositions for one body.
  (2) METRIC INFLATION — the metric counts docstring and comment lines, so a
      one-statement function with a 100-line maintenance contract scores as a
      "hub" identically to a 100-statement dispatch chain.

For each >=100 row this reports: nominal length, docstring lines, comment lines,
blank lines, EXECUTABLE statement lines (the union of lineno..end_lineno spans of
the body's statements, minus docstring/comment/blank), the nesting relation to
other rows, and the count of direct child statements.

Usage: A9_hub_anatomy.py <census.json> <tree_root>
"""
import ast
import json
import sys
import tokenize
from pathlib import Path

census = json.loads(Path(sys.argv[1]).read_text())
root = Path(sys.argv[2]).resolve()

ge100 = {(r["file"], r["fn"]): r["len"] for r in census["ge100"]}

# Per file: locate every function node and its qualname, so nesting is exact.
by_file: dict[str, dict[str, ast.AST]] = {}
src_lines: dict[str, list[str]] = {}
comment_lines: dict[str, set[int]] = {}

for rel in sorted({f for f, _ in ge100}):
    path = root / rel
    text = path.read_text()
    src_lines[rel] = text.splitlines()
    tree = ast.parse(text)
    nodes: dict[str, ast.AST] = {}

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{child.name}"
                nodes[qual] = child
                visit(child, f"{qual}.")

    visit(tree, "")
    by_file[rel] = nodes

    # real comment lines, from the tokenizer (never from a '#' substring search)
    cl = set()
    with open(path, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type == tokenize.COMMENT:
                cl.add(tok.start[0])
    comment_lines[rel] = cl


def anatomy(rel, qual):
    node = by_file[rel][qual]
    lo, hi = node.lineno, node.end_lineno
    span = set(range(lo, hi + 1))

    doc_span: set[int] = set()
    body = list(node.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        d = body[0]
        doc_span = set(range(d.lineno, d.end_lineno + 1))
        body = body[1:]
    doc = len(doc_span)

    # comment/blank lines are counted ONLY outside the docstring span, or a
    # blank line inside a docstring would be subtracted twice (it is already
    # inside `doc`) and drive `exec` negative.
    rest = span - doc_span
    comments = len(comment_lines[rel] & rest)
    blanks = sum(1 for n in rest if not src_lines[rel][n - 1].strip())
    executable = (hi - lo + 1) - doc - comments - blanks
    return {
        "len": hi - lo + 1,
        "doc": doc,
        "comment": comments,
        "blank": blanks,
        "exec": executable,
        "stmts": len(body),
        "lo": lo,
        "hi": hi,
    }


rows = []
for (rel, qual), length in ge100.items():
    a = anatomy(rel, qual)
    # nesting: is this qualname a strict descendant of ANOTHER >=100 row?
    parents = [q for (f, q) in ge100
               if f == rel and q != qual and qual.startswith(q + ".")]
    children = [q for (f, q) in ge100
                if f == rel and q != qual and q.startswith(qual + ".")]
    a.update(file=rel, fn=qual, parents=parents, children=children)
    rows.append(a)

rows.sort(key=lambda r: -r["len"])

print(f"{'len':>4} {'exec':>5} {'doc':>4} {'cmt':>4} {'blk':>4} {'stmt':>5}  nest  file::fn")
for r in rows:
    nest = "CHILD" if r["parents"] else ("PARENT" if r["children"] else "  -  ")
    print(f"{r['len']:4d} {r['exec']:5d} {r['doc']:4d} {r['comment']:4d} "
          f"{r['blank']:4d} {r['stmts']:5d}  {nest} {r['file']}::{r['fn']}")

print()
kids = [r for r in rows if r["parents"]]
print(f"=== NESTED-PAIR DOUBLE COUNTING: {len(kids)} of {len(rows)} rows are a "
      f"nested def inside ANOTHER >=100 row")
for r in kids:
    print(f"    {r['file']}::{r['fn']}  (inside {', '.join(r['parents'])})")
distinct = len(rows) - len(kids)
print(f"    => DISTINCT BODIES: {distinct} (census rows: {len(rows)})")

print()
print("=== METRIC INFLATION: rows whose EXECUTABLE lines are < 100")
infl = [r for r in rows if r["exec"] < 100]
for r in sorted(infl, key=lambda r: r["exec"]):
    print(f"    len={r['len']:4d} exec={r['exec']:4d} "
          f"(doc {r['doc']}, cmt {r['comment']}, blk {r['blank']})  "
          f"{r['file']}::{r['fn']}")
print(f"    => {len(infl)} of {len(rows)} census rows fall below 100 EXECUTABLE lines")

print()
print("=== rows that are >=100 EXECUTABLE lines AND not nested (the hard core)")
core = [r for r in rows if r["exec"] >= 100 and not r["parents"]]
for r in core:
    print(f"    len={r['len']:4d} exec={r['exec']:4d} stmts={r['stmts']:3d}  "
          f"{r['file']}::{r['fn']}")
print(f"    => {len(core)} rows")
