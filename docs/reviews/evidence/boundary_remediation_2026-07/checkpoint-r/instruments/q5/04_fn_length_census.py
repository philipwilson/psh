#!/usr/bin/env python3
"""Q5 census 3 (MEDIUM-15): function-length and file-size census.

Methodology (stated): for every FunctionDef/AsyncFunctionDef under <root>/psh
(nested and methods included), length = node.end_lineno - node.lineno + 1
(decorators excluded). Threshold >= 100 lines. Also: top-20 files by wc -l
(total physical lines). Baseline for comparison: #22 at v0.749.0 counted 54
fns >= 100 lines, top offenders ShellState.__init__ 303 / _run_command 211 /
_execute_pipeline 200 / history expansion 194 / ReadBuiltin.execute 178; files
core/state.py 1384, core/scope.py 1351, executor/job_control.py 1169,
io_redirect/file_redirect.py 1140, executor/command.py 1060.
Usage: 04_fn_length_census.py <tree-root> ; run once for tip worktree and once
for the extracted 0215279c base tree.
"""
import ast
import os
import sys

ROOT = sys.argv[1]
PSH = os.path.join(ROOT, "psh")

rows = []  # (length, rel, qualname, lineno)
file_lines = []  # (lines, rel)
total_fns = 0

class V(ast.NodeVisitor):
    def __init__(self, rel):
        self.rel = rel
        self.stack = []

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _do(self, node):
        global total_fns
        total_fns += 1
        self.stack.append(node.name)
        length = node.end_lineno - node.lineno + 1
        rows.append((length, self.rel, ".".join(self.stack), node.lineno))
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _do
    visit_AsyncFunctionDef = _do

nfiles = 0
for dirpath, dirnames, filenames in sorted(os.walk(PSH)):
    dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
    for fn in sorted(filenames):
        if not fn.endswith(".py"):
            continue
        nfiles += 1
        path = os.path.join(dirpath, fn)
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        file_lines.append((src.count("\n") + (0 if src.endswith("\n") or not src else 1), rel))
        V(rel).visit(ast.parse(src, filename=rel))

big = sorted([r for r in rows if r[0] >= 100], reverse=True)
print(f"files scanned: {nfiles}; total defs: {total_fns}; total lines: {sum(l for l, _ in file_lines)}")
print(f"FUNCTIONS >= 100 LINES: {len(big)}")
for length, rel, qual, lineno in big:
    print(f"  {length:4d}  {rel}:{lineno}  {qual}")
print("\nTOP 20 FILES BY LINES:")
for lines, rel in sorted(file_lines, reverse=True)[:20]:
    print(f"  {lines:5d}  {rel}")
