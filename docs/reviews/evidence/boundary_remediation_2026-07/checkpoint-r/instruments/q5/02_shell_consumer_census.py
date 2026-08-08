#!/usr/bin/env python3
"""Q5 census 2 (MEDIUM-14): functions/methods under psh/ whose parameters are
annotated with the broad owners `Shell` or `ShellState` (incl. quoted forward
refs and Optional[...] wrappers) at ae871a16.

Methodology: AST walk; a parameter counts if its annotation's unparsed text
contains the identifier Shell or ShellState (word-boundary via regex, so
ShellState is counted separately from Shell; `Shell` does NOT match
`ShellState`). __init__ storing self.shell without annotation is NOT counted
(annotation-based census only — stated limitation). Reports totals and top
files. Reads worktree root argv[1].
"""
import ast
import os
import re
import sys
from collections import Counter

ROOT = sys.argv[1]
PSH = os.path.join(ROOT, "psh")

WORD_SHELL = re.compile(r"(?<![A-Za-z0-9_])Shell(?![A-Za-z0-9_])")
WORD_STATE = re.compile(r"(?<![A-Za-z0-9_])ShellState(?![A-Za-z0-9_])")

shell_sites = []   # (rel, line, qualname, param, ann)
state_sites = []

class V(ast.NodeVisitor):
    def __init__(self, rel):
        self.rel = rel
        self.stack = []

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _do_func(self, node):
        self.stack.append(node.name)
        qual = ".".join(self.stack)
        args = node.args
        for a in (args.posonlyargs + args.args + args.kwonlyargs
                  + ([args.vararg] if args.vararg else [])
                  + ([args.kwarg] if args.kwarg else [])):
            if a.annotation is None:
                continue
            txt = ast.unparse(a.annotation)
            plain = txt.replace("'", "").replace('"', "")
            if WORD_STATE.search(plain):
                state_sites.append((self.rel, node.lineno, qual, a.arg, txt))
            elif WORD_SHELL.search(plain):
                shell_sites.append((self.rel, node.lineno, qual, a.arg, txt))
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _do_func
    visit_AsyncFunctionDef = _do_func

for dirpath, dirnames, filenames in sorted(os.walk(PSH)):
    dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
    for fn in sorted(filenames):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(dirpath, fn)
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=rel)
        V(rel).visit(tree)

print(f"TOTAL params annotated Shell (not ShellState): {len(shell_sites)}")
print(f"TOTAL params annotated ShellState:            {len(state_sites)}")
print(f"\nTOP FILES (Shell): {Counter(s[0] for s in shell_sites).most_common(12)}")
print(f"\nTOP FILES (ShellState): {Counter(s[0] for s in state_sites).most_common(12)}")
print("\n-- ALL Shell param sites --")
for rel, line, qual, arg, txt in shell_sites:
    print(f"{rel}:{line} {qual}({arg}: {txt})")
print("\n-- ALL ShellState param sites --")
for rel, line, qual, arg, txt in state_sites:
    print(f"{rel}:{line} {qual}({arg}: {txt})")
