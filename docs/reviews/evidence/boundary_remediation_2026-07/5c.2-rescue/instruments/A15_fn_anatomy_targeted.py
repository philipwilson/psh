#!/usr/bin/env python3
"""A15 — A9's anatomy, but for EXPLICITLY NAMED functions in ANY tree.

A9 only walks the >=100 census rows, so it cannot measure a function that was
BELOW 100 at an earlier SHA (e.g. apply_var_fd_redirect was 52 lines at
v0.750.0). This takes explicit `file::qualname` targets and one tree root, so
the same classification runs at any SHA.

Classification is IDENTICAL to A9 by construction (same code path, lifted):
comments from `tokenize` (never a '#' substring search); docstring-internal
blanks not double-subtracted.

Usage: A15_fn_anatomy_targeted.py <tree_root> <file::qualname> [...]
"""
import ast
import sys
import tokenize
from pathlib import Path

def anatomy(rel, qual, ROOT):
    ROOT = Path(ROOT).resolve()
    path = ROOT / rel
    if not path.exists():
        return None
    text = path.read_text()
    src = text.splitlines()
    tree = ast.parse(text)

    comment_lines = set()
    with open(path, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type == tokenize.COMMENT:
                comment_lines.add(tok.start[0])

    found = {}

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{prefix}{child.name}"
                found[q] = child
                visit(child, f"{q}.")

    visit(tree, "")
    node = found.get(qual)
    if node is None:
        return None

    lo, hi = node.lineno, node.end_lineno
    span = set(range(lo, hi + 1))
    doc_span = set()
    body = list(node.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        d = body[0]
        doc_span = set(range(d.lineno, d.end_lineno + 1))
    doc = len(doc_span)
    rest = span - doc_span
    comments = len(comment_lines & rest)
    blanks = sum(1 for n in rest if not src[n - 1].strip())
    return {"len": hi - lo + 1, "doc": doc, "comment": comments,
            "blank": blanks, "exec": (hi - lo + 1) - doc - comments - blanks}


def main():
    """CLI. Guarded so A14 can IMPORT `anatomy` instead of reimplementing the
    metric — the c-1 one-implementation discipline applied to Phase A's own
    instruments."""
    ROOT = Path(sys.argv[1]).resolve()
    print(f"tree: {ROOT}")
    print(f"{'len':>5} {'exec':>5} {'doc':>4} {'cmt':>4} {'blk':>4}  file::fn")
    for spec in sys.argv[2:]:
        rel, qual = spec.split("::")
        a = anatomy(rel, qual, ROOT)
        if a is None:
            print(f"{'--':>5} {'--':>5} {'--':>4} {'--':>4} {'--':>4}  {spec}"
                  "  (ABSENT at this tree)")
            continue
        print(f"{a['len']:5d} {a['exec']:5d} {a['doc']:4d} {a['comment']:4d} "
              f"{a['blank']:4d}  {spec}")


if __name__ == "__main__":
    main()
