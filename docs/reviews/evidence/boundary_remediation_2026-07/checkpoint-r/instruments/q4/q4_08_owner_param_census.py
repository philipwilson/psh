#!/usr/bin/env python3
"""Q4 axis-3: census of full-owner (Shell / ShellState) parameters in function
signatures, diffed between two trees over a file list (the wave-touched set).

Methodology (stated for the report):
  - every FunctionDef/AsyncFunctionDef (methods included; qualname carries
    class nesting)
  - a parameter is a FULL-OWNER param if:
      (a) its annotation (ast.unparse'd) matches \\bShell\\b or \\bShellState\\b
          (word-boundary regex: matches Shell, 'Shell', Optional[Shell],
          psh.shell.Shell — does NOT match ShellFormatter/ShellState-like
          longer identifiers other than ShellState itself), OR
      (b) it is UNANNOTATED and named exactly 'shell' or 'shell_state'
          (recorded separately as name-based)
  - `self`/`cls` are skipped
  - keys are (relpath, qualname, param). NEW = present at tip, absent at base.
    (A file rename shows as remove+add; the wave-touched list is diff-derived
    so this is visible, not silent.)

Usage: q4_08_owner_param_census.py <base_root> <tip_root> <filelist>
"""
import ast
import re
import sys
from pathlib import Path

OWNER_RE = re.compile(r"\b(Shell|ShellState)\b")


def census(root, files):
    found = {}  # (relpath, qualname, param) -> kind
    sigs = set()  # (relpath, qualname) for existence diff
    for rel in files:
        p = root / rel
        if not p.exists() or p.suffix != ".py":
            continue
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            continue

        def visit(node, prefix):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, f"{prefix}{child.name}.")
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qual = f"{prefix}{child.name}"
                    sigs.add((rel, qual))
                    a = child.args
                    all_args = (list(a.posonlyargs) + list(a.args)
                                + list(a.kwonlyargs))
                    for arg in all_args:
                        if arg.arg in ("self", "cls"):
                            continue
                        kind = None
                        if arg.annotation is not None:
                            ann = ast.unparse(arg.annotation)
                            if OWNER_RE.search(ann):
                                kind = f"annotated:{ann}"
                        elif arg.arg in ("shell", "shell_state"):
                            kind = "name-based(unannotated)"
                        if kind:
                            found[(rel, qual, arg.arg)] = kind
                    visit(child, f"{qual}.")

        visit(tree, "")
    return found, sigs


base_root, tip_root, filelist = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
files = [ln.strip() for ln in Path(filelist).read_text().splitlines()
         if ln.strip().endswith(".py")]

fb, sb = census(base_root, files)
ft, st = census(tip_root, files)

print(f"wave-touched .py files examined: {len(files)}")
print(f"owner-params at BASE: {len(fb)}   at TIP: {len(ft)}")

new = {k: v for k, v in ft.items() if k not in fb}
gone = {k: v for k, v in fb.items() if k not in ft}
new_in_new_fn = {k: v for k, v in new.items() if (k[0], k[1]) not in sb}
new_in_old_fn = {k: v for k, v in new.items() if (k[0], k[1]) in sb}

print(f"\nNEW owner-params at tip (not at base): {len(new)}")
print(f"  ... in functions NEW at tip: {len(new_in_new_fn)}")
for (rel, qual, param), kind in sorted(new_in_new_fn.items()):
    print(f"    {rel}::{qual}({param})  [{kind}]")
print(f"  ... added to pre-existing functions: {len(new_in_old_fn)}")
for (rel, qual, param), kind in sorted(new_in_old_fn.items()):
    print(f"    {rel}::{qual}({param})  [{kind}]")
print(f"\nREMOVED owner-params (at base, gone at tip): {len(gone)}")
for (rel, qual, param), kind in sorted(gone.items()):
    print(f"    {rel}::{qual}({param})  [{kind}]")
