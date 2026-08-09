#!/usr/bin/env python3
"""A8 — dump each of the 24 `except Exception` handlers with the context a
classification needs: enclosing function, what the try body CALLS, whether the
handler re-raises, and what it returns/does. ROOT from argv[1]."""
import ast, os, sys
ROOT = os.path.abspath(sys.argv[1]); PSH = os.path.join(ROOT, "psh")

def mentions_exception(t):
    if t is None: return False
    if isinstance(t, ast.Tuple): return any(mentions_exception(e) for e in t.elts)
    return isinstance(t, ast.Name) and t.id == "Exception"

rows = []
for dirpath, dirnames, filenames in sorted(os.walk(PSH)):
    dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
    for fn in sorted(filenames):
        if not fn.endswith(".py"): continue
        path = os.path.join(dirpath, fn); rel = os.path.relpath(path, ROOT)
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src, filename=rel)
        parent = {}
        for n in ast.walk(tree):
            for c in ast.iter_child_nodes(n): parent[id(c)] = n
        def enclosing_fn(node):
            cur = parent.get(id(node))
            while cur is not None:
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)): return cur.name
                cur = parent.get(id(cur))
            return "(module level)"
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try): continue
            for h in node.handlers:
                if not mentions_exception(h.type): continue
                calls = sorted({(c.func.attr if isinstance(c.func, ast.Attribute)
                                 else c.func.id if isinstance(c.func, ast.Name) else "?")
                                for st in node.body for c in ast.walk(st) if isinstance(c, ast.Call)})
                reraises = any(isinstance(x, ast.Raise) for x in ast.walk(h))
                hcalls = sorted({(c.func.attr if isinstance(c.func, ast.Attribute)
                                  else c.func.id if isinstance(c.func, ast.Name) else "?")
                                 for c in ast.walk(h) if isinstance(c, ast.Call)})
                exits = sorted({n2.__class__.__name__ for n2 in ast.walk(h)
                                if isinstance(n2, (ast.Return, ast.Pass, ast.Continue, ast.Break))})
                rows.append((rel, h.lineno, enclosing_fn(node), len(node.body),
                             calls, reraises, hcalls, exits))

rows.sort()
print(f"except-Exception handlers: {len(rows)}\n")
for rel, ln, fn, nstmt, calls, rr, hcalls, exits in rows:
    print(f"--- {rel}:{ln}  in {fn}()   try-body stmts={nstmt}  re-raises={rr}")
    print(f"      try calls  : {', '.join(calls[:12])}{' …' if len(calls) > 12 else ''}")
    print(f"      handler does: calls={', '.join(hcalls[:8]) or '(none)'}  exits={','.join(exits) or '(falls through)'}")
