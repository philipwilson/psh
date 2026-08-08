#!/usr/bin/env python3
"""Q5 census 1 (MEDIUM-14): protocol inventory at ae871a16.

For every `class X(Protocol)` under psh/: file:line, members, whether any
member/param annotation mentions Shell/ShellState/Any; usage census = files
under psh/ (outside the defining file) that reference the protocol name.
Also: all class definitions named ExpansionContext / LocaleContext (collision
census). Pure stdlib; reads the WORKTREE tree passed as argv[1].
"""
import ast
import os
import sys

ROOT = sys.argv[1]
PSH = os.path.join(ROOT, "psh")

protocols = []   # (file, line, name, bases, members)
collisions = {"ExpansionContext": [], "LocaleContext": []}

def ann_text(node):
    return ast.unparse(node) if node is not None else None

for dirpath, dirnames, filenames in sorted(os.walk(PSH)):
    dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
    for fn in sorted(filenames):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(dirpath, fn)
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src, filename=rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name in collisions:
                collisions[node.name].append(f"{rel}:{node.lineno}")
            base_names = [ast.unparse(b) for b in node.bases]
            if not any("Protocol" in b for b in base_names):
                continue
            members = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    params = []
                    args = item.args
                    for a in (args.posonlyargs + args.args + args.kwonlyargs):
                        if a.arg in ("self", "cls"):
                            continue
                        params.append((a.arg, ann_text(a.annotation)))
                    members.append(("def", item.name, params, ann_text(item.returns)))
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    members.append(("attr", item.target.id, ann_text(item.annotation)))
            protocols.append((rel, node.lineno, node.name, base_names, members))

print("== PROTOCOL DEFINITIONS UNDER psh/ ==")
for rel, line, name, bases, members in protocols:
    print(f"\n{rel}:{line} class {name}({', '.join(bases)})")
    shellish = []
    anyish = []
    for m in members:
        if m[0] == "def":
            _, mname, params, ret = m
            ptxt = ", ".join(f"{p}: {a}" for p, a in params)
            print(f"  def {mname}({ptxt}) -> {ret}")
            for p, a in params:
                if a and ("Shell" in a):
                    shellish.append(f"{mname}.{p}: {a}")
                if a and a.strip("'\"") == "Any":
                    anyish.append(f"{mname}.{p}: {a}")
            if ret and "Shell" in ret:
                shellish.append(f"{mname} -> {ret}")
            if ret and ret.strip("'\"") == "Any":
                anyish.append(f"{mname} -> {ret}")
        else:
            _, aname, a = m
            print(f"  attr {aname}: {a}")
            if a and "Shell" in a:
                shellish.append(f"{aname}: {a}")
            if a and a.strip("'\"") == "Any":
                anyish.append(f"{aname}: {a}")
    print(f"  SHELL-TYPED MEMBERS: {shellish if shellish else 'none'}")
    print(f"  ANY-TYPED MEMBERS: {anyish if anyish else 'none'}")

print("\n== USAGE CENSUS (files under psh/ referencing each protocol name, excluding its defining file) ==")
proto_names = sorted({name for _, _, name, _, _ in protocols})
# collect all psh files once
psh_files = []
for dirpath, dirnames, filenames in sorted(os.walk(PSH)):
    dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
    for fn in sorted(filenames):
        if fn.endswith(".py"):
            psh_files.append(os.path.join(dirpath, fn))

for pname in proto_names:
    defining = {rel for rel, _, name, _, _ in protocols if name == pname}
    hits = []
    for path in psh_files:
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        if pname in src:
            hits.append(rel)
    outside = [h for h in hits if h not in defining]
    print(f"\n{pname}: referenced in {len(hits)} psh files total; outside defining file(s) {sorted(defining)}: {outside}")

print("\n== NAME-COLLISION CENSUS ==")
for cname, sites in collisions.items():
    print(f"{cname}: {len(sites)} class definitions: {sites}")
