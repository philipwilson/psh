#!/usr/bin/env python3
"""A10 — the BOUNDARY-SEAM set among the 648 (MEDIUM-16, ruling (d)).

The brief asks for the seam enumeration to be DERIVABLE, not curated. So the
definition is operational and stated as a predicate over the tree:

  A def is a BOUNDARY SEAM iff ALL of:
   (S1) it is incomplete under Method A (the census's own rule: a non-self/cls
        param lacks an annotation, or the return annotation is missing);
   (S2) it is PUBLIC — neither the def nor any enclosing scope starts with '_'
        (a private helper is not a seam; it is per-package depth, which §11
        defers to post-campaign);
   (S3) it is TOP-LEVEL or a method of a top-level class (not nested inside a
        function — a closure is not an importable surface);
   (S4) its defining module is IMPORTED BY AT LEAST ONE MODULE IN A DIFFERENT
        top-level psh package. This is the "cross-package" half: the surface is
        reachable from outside its own package, which is what makes it a seam
        rather than an internal detail.

(S4) is measured from the real module-level + deferred import graph, reusing
the import-layering guard's own analyzer idea (AST, nothing executed), so the
seam set moves with the code rather than with a hand-kept list.

Reports the seam set, its per-package and per-file split, and the residue
(incomplete-but-not-seam) so the reduction target can be sourced per file.
ROOT from argv[1].
"""
import ast
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(sys.argv[1])
PSH = os.path.join(ROOT, "psh")


def modname(rel):
    parts = list(os.path.splitext(rel)[0].split(os.sep))
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def toppkg(mod):
    return ".".join(mod.split(".")[:2])


files = []
for dirpath, dirnames, filenames in sorted(os.walk(PSH)):
    dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
    for fn in sorted(filenames):
        if fn.endswith(".py"):
            files.append(os.path.relpath(os.path.join(dirpath, fn), ROOT))

trees = {}
for rel in files:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        trees[rel] = ast.parse(f.read(), filename=rel)


# --- (S4) who imports whom (module level AND deferred; TYPE_CHECKING excluded:
#     a type-only import is not a runtime consumer, but it IS a signature
#     consumer, so it is counted — recorded here so the choice is visible).
def resolve_rel(cur_mod, node, is_pkg):
    parts = cur_mod.split(".")
    pkg = list(parts) if is_pkg else parts[:-1]
    up = node.level - 1
    if up > 0:
        pkg = pkg[:-up] if up <= len(pkg) else []
    tgt = ".".join(pkg)
    if node.module:
        tgt = tgt + "." + node.module if tgt else node.module
    return tgt


importers = defaultdict(set)          # module -> {importing modules}
for rel in files:
    mod = modname(rel)
    is_pkg = os.path.basename(rel) == "__init__.py"
    for n in ast.walk(trees[rel]):
        tgt = None
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("psh"):
                    importers[a.name].add(mod)
        elif isinstance(n, ast.ImportFrom):
            tgt = (resolve_rel(mod, n, is_pkg) if (n.level or 0) > 0
                   else n.module)
            if tgt and tgt.startswith("psh"):
                importers[tgt].add(mod)
                # `from psh.pkg.mod import Name` also makes psh.pkg.mod.Name a
                # target spelling; record the parent module only.


def cross_package_consumed(mod):
    mine = toppkg(mod)
    return any(toppkg(o) != mine for o in importers.get(mod, ()))


# --- the def census with the seam predicate ---------------------------------
seams, residue = [], []
for rel in files:
    mod = modname(rel)
    xpkg = cross_package_consumed(mod)

    def walk(node, prefix, fn_depth):
        # INSTRUMENT DEFECT FIXED (recorded, not buried): the first version
        # recursed only through ClassDef/FunctionDef children, so a def nested
        # inside an `if`/`try`/`with` block was never visited. Total came to
        # 643 against the reference census's 648 -- a 5-def blind spot that
        # could have hidden a seam. The reference instrument (05_sig_census)
        # uses NodeVisitor/generic_visit, which descends through every
        # statement; this now does the same, and the totals reconcile.
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, ast.ClassDef):
                walk(ch, prefix + [ch.name], fn_depth)
            elif not isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(ch, prefix, fn_depth)
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = ch.args
                params = (a.posonlyargs + a.args + a.kwonlyargs
                          + ([a.vararg] if a.vararg else [])
                          + ([a.kwarg] if a.kwarg else []))
                missing = any(p.annotation is None for p in params
                              if p.arg not in ("self", "cls"))
                incomplete = missing or ch.returns is None
                qual = ".".join(prefix + [ch.name])
                public = not any(part.startswith("_") for part in prefix + [ch.name])
                dunder = ch.name.startswith("__") and ch.name.endswith("__")
                if incomplete:
                    row = (rel, ch.lineno, qual)
                    if (public and not dunder and fn_depth == 0 and xpkg):
                        seams.append(row)
                    else:
                        residue.append(row)
                walk(ch, prefix + [ch.name], fn_depth + 1)
    walk(trees[rel], [], 0)

print(f"tree: {ROOT}")
print(f"Method-A incomplete total (S1 only): {len(seams) + len(residue)}")
print(f"BOUNDARY SEAMS (S1..S4):             {len(seams)}")
print(f"residue (incomplete, not a seam):    {len(residue)}")

print(f"\nSEAMS by package: "
      f"{Counter(r[0].split(os.sep)[1] for r in seams).most_common()}")
print(f"\nSEAMS by file (all {len(set(r[0] for r in seams))} files):")
for f2, c in Counter(r[0] for r in seams).most_common():
    print(f"  {c:4d}  {f2}")
