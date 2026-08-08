#!/usr/bin/env python3
"""Slot 5B.1 instrument 05 — live full-``Shell`` consumer sweep.

Runs the ratchet's OWN detector (`full_shell_consumers`) over:
  (a) the 20 currently-scanned modules  -> baseline, must equal ALLOWLIST
  (b) the 3 unscanned modules            -> what extension will FIND
so the disposition matrix is measured, not assumed.

Uses the ratchet's real detector (imported from the test module) rather
than a re-implementation: a re-implemented detector could disagree with
the real one and the sweep would be evidence about the wrong thing.

Portable: ROOT from argv[1] (default git toplevel). No hardcoded paths.
"""
import importlib.util
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                    subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                   capture_output=True, text=True
                                   ).stdout.strip()).resolve()

spec = importlib.util.spec_from_file_location(
    "ratchet", ROOT / "tests/unit/tooling/test_shell_consumer_ratchet_q1.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

UNSCANNED = [
    "psh/protocols/__init__.py",
    "psh/expansion/procsub_render.py",
    "psh/scripting/analysis_session.py",
]

print(f"ROOT={ROOT}")
print(f"HEAD={subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()}")
print(f"detector source: {ROOT}/tests/unit/tooling/test_shell_consumer_ratchet_q1.py")
print()

print("=" * 72)
print(f"(a) BASELINE — the {len(R.TOUCHED_MODULES)} currently-scanned modules")
print("=" * 72)
live = set()
for rel in R.TOUCHED_MODULES:
    path = ROOT / rel
    hits = R.full_shell_consumers(path.read_text(), R._module_dotted(rel))
    if hits:
        for mod, sym in sorted(hits):
            in_allow = (mod, sym) in R.ALLOWLIST
            print(f"  {'ALLOWLISTED' if in_allow else 'UNRECORDED!!'}  {mod}.{sym}")
    live |= hits
print(f"\n  live consumers in scanned scope : {len(live)}")
print(f"  ALLOWLIST entries               : {len(R.ALLOWLIST)}")
print(f"  live - ALLOWLIST (unrecorded)   : {sorted(live - set(R.ALLOWLIST))}")
print(f"  ALLOWLIST - live (stale)        : {sorted(set(R.ALLOWLIST) - live)}")
print(f"  RATCHET GREEN TODAY             : "
      f"{live == set(R.ALLOWLIST)}")

print()
print("=" * 72)
print("(b) THE GAP — what extending the scope would FIND")
print("=" * 72)
total_new = 0
for rel in UNSCANNED:
    path = ROOT / rel
    assert path.exists(), rel
    hits = R.full_shell_consumers(path.read_text(), R._module_dotted(rel))
    print(f"\n  {rel}")
    print(f"    full-Shell consumers found: {len(hits)}")
    for mod, sym in sorted(hits):
        print(f"      >>> {mod}.{sym}")
    total_new += len(hits)
    if not hits:
        print("      (none — nothing for the ratchet to record here)")
print(f"\n  TOTAL new consumers entering scope: {total_new}")

print()
print("=" * 72)
print("(c) PER-PARAM DETAIL for every hit (which param triggered, and how)")
print("=" * 72)
import ast
for rel in UNSCANNED:
    src = (ROOT / rel).read_text()
    tree = ast.parse(src)

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, prefix + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = child.args
                params = (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs))
                if a.vararg:
                    params.append(a.vararg)
                if a.kwarg:
                    params.append(a.kwarg)
                for p in params:
                    ann_hit = R._ann_mentions_shell(p.annotation)
                    unann_hit = (p.annotation is None and p.arg == "shell")
                    if ann_hit or unann_hit:
                        anntxt = (ast.unparse(p.annotation)
                                  if p.annotation is not None else "<unannotated>")
                        why = "ANNOTATION-MENTIONS-Shell" if ann_hit else "UNANNOTATED-NAMED-shell"
                        print(f"  {rel}:{child.lineno}  "
                              f"{'.'.join(prefix+[child.name])}  "
                              f"param={p.arg}  ann={anntxt}  [{why}]")
                walk(child, prefix + [child.name])
    walk(tree, [])
