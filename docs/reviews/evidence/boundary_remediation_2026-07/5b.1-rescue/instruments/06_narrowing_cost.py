#!/usr/bin/env python3
"""Slot 5B.1 instrument 06 — narrowing cost per full-``Shell`` param.

For each of the three analysis_session consumers, enumerate EVERY use of
the `shell` binding (and of `self.shell`), classified as:
  ATTR   shell.<x>            -> could a protocol expose <x>?
  CALL   type(shell)(...)     -> CONSTRUCTION: no protocol models this
  PASS   f(shell)             -> forwards; cost is the callee's
  STORE  self.shell = shell   -> stored; cost is every later read

The narrowing decision is then MEASURED (what the body actually needs)
rather than argued.

Portable: ROOT from argv[1] (default git toplevel).
"""
import ast
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                    subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                   capture_output=True, text=True
                                   ).stdout.strip()).resolve()

TARGETS = {
    "psh/scripting/analysis_session.py": [
        ("AnalysisSession.__init__", "shell"),
        ("AnalysisSession._build_carrier", "shell"),
        ("parse_for_analysis", "shell"),
    ],
}


def qualname_of(tree, target_line):
    """Find the enclosing def qualname for a line."""
    best = None
    def walk(node, prefix):
        nonlocal best
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, prefix + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(child, "end_lineno", child.lineno)
                if child.lineno <= target_line <= end:
                    cand = ".".join(prefix + [child.name])
                    if best is None or len(cand) > len(best):
                        best = cand
                walk(child, prefix + [child.name])
    walk(tree, [])
    return best


def classify(rel):
    path = ROOT / rel
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.splitlines()
    rows = []

    for node in ast.walk(tree):
        # shell.<attr>
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id == "shell":
            rows.append(("ATTR", node.lineno, f"shell.{node.attr}",
                         qualname_of(tree, node.lineno)))
        # self.shell.<attr>
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) \
                and node.value.attr == "shell" \
                and isinstance(node.value.value, ast.Name) \
                and node.value.value.id == "self":
            rows.append(("ATTR-SELF", node.lineno, f"self.shell.{node.attr}",
                         qualname_of(tree, node.lineno)))
        # type(shell)(...) — construction
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Call) \
                and isinstance(node.func.func, ast.Name) and node.func.func.id == "type":
            rows.append(("CONSTRUCT", node.lineno,
                         ast.unparse(node)[:90], qualname_of(tree, node.lineno)))
        # f(shell) / f(shell, ...) — forwarding
        if isinstance(node, ast.Call):
            for a in node.args:
                if isinstance(a, ast.Name) and a.id == "shell":
                    rows.append(("PASS", node.lineno,
                                 ast.unparse(node)[:90], qualname_of(tree, node.lineno)))
            for kw in node.keywords:
                if isinstance(kw.value, ast.Name) and kw.value.id == "shell":
                    rows.append(("PASS-KW", node.lineno,
                                 f"{ast.unparse(node.func)}({kw.arg}=shell)",
                                 qualname_of(tree, node.lineno)))
        # self.shell = shell  — storage
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == "shell" \
                        and isinstance(t.value, ast.Name) and t.value.id == "self":
                    rows.append(("STORE", node.lineno, ast.unparse(node)[:90],
                                 qualname_of(tree, node.lineno)))
        # bare `self.shell` read (not attribute access on it)
    return rows, lines


for rel, params in TARGETS.items():
    print("=" * 74)
    print(f"{rel}   (HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()})")
    print("=" * 74)
    rows, lines = classify(rel)
    for kind, lineno, what, qual in sorted(rows, key=lambda r: r[1]):
        print(f"  {kind:10s} L{lineno:<5d} [{qual}]")
        print(f"             {what}")
        print(f"             SRC: {lines[lineno-1].strip()[:100]}")
    print()
    print(f"  DISTINCT shell.<attr> touched:")
    attrs = sorted({w.split('.', 1)[1] for k, _, w, _ in rows
                    if k == "ATTR"})
    for a in attrs:
        print(f"    shell.{a}")
    selfattrs = sorted({w for k, _, w, _ in rows if k == "ATTR-SELF"})
    print(f"  DISTINCT self.shell.<attr> reads: {selfattrs or '(none)'}")
    constructs = [r for r in rows if r[0] == "CONSTRUCT"]
    print(f"  CONSTRUCTION sites (protocol-unmodelable): {len(constructs)}")
    for _, ln, w, q in constructs:
        print(f"    L{ln} [{q}] {w}")
