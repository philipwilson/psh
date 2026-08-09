#!/usr/bin/env python3
"""B5 — per-file accounting for the Method A/B census delta.

Ruling (d) ratified 648->642 / 488->483 as a FLOOR, and requires any ADDITIONAL
completion to be accounted per file BEFORE the gate — no reasoned-to terms
(5B.1 lesson 3). This enumerates the exact defs that changed state between two
trees, so every term in the final figure has a file:line source.

Usage: B5_census_delta.py <BASE_ROOT> <TIP_ROOT>
"""
import ast
import os
import sys

def census(root):
    """{(relpath, name): (lineno, incomplete, methodB)} for every def."""
    out = {}
    psh = os.path.join(root, "psh")
    for dirpath, dirnames, filenames in sorted(os.walk(psh)):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            tree = ast.parse(open(path, encoding="utf-8").read(), filename=rel)

            def walk(node, prefix, depth):
                for ch in ast.iter_child_nodes(node):
                    if isinstance(ch, ast.ClassDef):
                        walk(ch, prefix + [ch.name], depth)
                    elif not isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        walk(ch, prefix, depth)
                    if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        a = ch.args
                        ps = (a.posonlyargs + a.args + a.kwonlyargs
                              + ([a.vararg] if a.vararg else [])
                              + ([a.kwarg] if a.kwarg else []))
                        miss = any(p.annotation is None for p in ps
                                   if p.arg not in ("self", "cls"))
                        inc = miss or ch.returns is None
                        dunder = ch.name.startswith("__") and ch.name.endswith("__")
                        mb = (depth == 0) and not dunder
                        out[(rel, ".".join(prefix + [ch.name]))] = (
                            ch.lineno, inc, mb)
                        walk(ch, prefix + [ch.name], depth + 1)
            walk(tree, [], 0)
    return out


base, tip = census(os.path.abspath(sys.argv[1])), census(os.path.abspath(sys.argv[2]))

fixed  = [k for k in base if k in tip and base[k][1] and not tip[k][1]]
broke  = [k for k in base if k in tip and not base[k][1] and tip[k][1]]
gone   = [k for k in base if k not in tip and base[k][1]]
added_inc = [k for k in tip if k not in base and tip[k][1]]
added_ok  = [k for k in tip if k not in base and not tip[k][1]]

def mb(store, keys):
    return [k for k in keys if store[k][2]]

print(f"BASE Method A incomplete: {sum(1 for v in base.values() if v[1])}")
print(f"TIP  Method A incomplete: {sum(1 for v in tip.values() if v[1])}")
print(f"BASE Method B incomplete: {sum(1 for v in base.values() if v[1] and v[2])}")
print(f"TIP  Method B incomplete: {sum(1 for v in tip.values() if v[1] and v[2])}")

print(f"\n--- COMPLETED (was incomplete, now complete): {len(fixed)} "
      f"[Method B: {len(mb(tip, fixed))}] ---")
for rel, name in sorted(fixed):
    print(f"  {rel}:{tip[(rel,name)][0]}  {name}"
          + ("   [B]" if tip[(rel, name)][2] else ""))

print(f"\n--- REMOVED while incomplete: {len(gone)} ---")
for rel, name in sorted(gone):
    print(f"  {rel}:{base[(rel,name)][0]}  {name}")

print(f"\n--- NEW defs, still incomplete: {len(added_inc)} ---")
for rel, name in sorted(added_inc):
    print(f"  {rel}:{tip[(rel,name)][0]}  {name}")

print(f"\n--- NEW defs, complete (no census cost): {len(added_ok)} ---")
for rel, name in sorted(added_ok):
    print(f"  {rel}:{tip[(rel,name)][0]}  {name}")

print(f"\n--- REGRESSED (was complete, now incomplete): {len(broke)} ---")
for rel, name in sorted(broke):
    print(f"  {rel}:{tip[(rel,name)][0]}  {name}")
