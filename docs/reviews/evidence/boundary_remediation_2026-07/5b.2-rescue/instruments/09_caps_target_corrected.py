#!/usr/bin/env python3
"""Instrument 09 (slot 5B.2) — the CORRECTED caps target derivation.

DEFECT CHAIN, recorded in full rather than buried (4B.3 rule 6; D-3.5):

  05 v1  asked only the guard's PACKAGE-cycle question      -> 136 hoistable
         (over-reported: package_edges drops intra-package edges, so an
         intra-package hoist can never fail that test)
  05 v2  added "introduces no NEW module-level cycle"       -> 119 hoistable
  06     real import with ALL 119 applied                   -> SUCCEEDED
  07     partitioned by startup cost, inferred 94 "free"
  08     real import with ONLY the 94 free applied          -> **ImportError**
         (psh.parser.parse_outcome, a documented `# cycle-break:` site)

A SUBSET failing where the SUPERSET succeeded is the tell: 05 v2's test was
still wrong. It subtracted PRE-EXISTING module cycles, so an edge hoisted INTO
an already-cyclic region passed — the cycle was not "new". Whether such an edge
explodes depends on which module the interpreter enters first, which is why the
full set happened to survive and the subset did not. Import order is not a
property this analysis may rely on.

CORRECTED PREDICATE: an edge src -> dst is hoistable only if, with the edge
added, src and dst are NOT in the same cyclic strongly-connected component of
the MODULE-level graph — existing or new. That is the condition under which
importing dst at src's module level cannot re-enter src.

Every number below is re-derived under the corrected predicate and then
CONFIRMED by a real import of a scratch tree; the timing is reported only for a
tree that actually imports.

Usage:  python 09_caps_target_corrected.py <ROOT> <SCRATCH>
"""
import ast
import json
import os
import pathlib
import shutil
import statistics
import subprocess
import sys


def cumulative_import_ms(tree_root, runs=5):
    vals = []
    for _ in range(runs):
        r = subprocess.run(
            [sys.executable, "-X", "importtime", "-c", "import psh"],
            cwd=str(tree_root), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(tree_root),
                 "PYTHONDONTWRITEBYTECODE": "1"})
        if r.returncode != 0:
            return None          # never report a timing for a broken tree
        for line in r.stderr.splitlines():
            parts = line.split("|")
            if len(parts) == 3 and parts[2].strip() == "psh":
                vals.append(int(parts[1].strip()) / 1000.0)
    return vals


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    scratch = pathlib.Path(sys.argv[2]).resolve()
    sys.path.insert(0, str(root))
    from tests.unit.tooling.test_import_layering import (  # noqa: E402
        CORE_MODULE_IMPORT_ALLOWLIST, FUNC_IMPORT_CAPS, PACKAGE_CYCLE_ALLOWLIST,
        _resolve_relative, _top_package, build_graph, find_cycles,
        package_edges,
    )

    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print()

    raw_edges, counts = build_graph()

    # DEFECT 3 (found by instrument 09 v1's real import, same way as 1 and 2):
    # importing `X.Y.Z` also EXECUTES the ancestor packages `X` and `X.Y`, so a
    # module-level import of a deep module drags every ancestor __init__ onto
    # the import path. The graph modelled only the exact target, so the
    # `psh.parser.parse_outcome -> ...recursive_descent.helpers` hoist looked
    # acyclic while it actually re-enters parse_outcome through
    # recursive_descent/__init__ -> recursive_descent.parser. Expanding every
    # edge to its ancestors is the faithful graph.
    _known = set(raw_edges)

    def expand(dst):
        out = {dst}
        parts = dst.split(".")
        for i in range(1, len(parts)):
            anc = ".".join(parts[:i])
            if anc in _known:
                out.add(anc)
        return out

    edges = {m: {a for d in dsts for a in expand(d)}
             for m, dsts in raw_edges.items()}

    probe = ("import sys, json, psh\n"
             "print(json.dumps(sorted(m for m in sys.modules "
             "if m == 'psh' or m.startswith('psh.'))))\n")
    r = subprocess.run([sys.executable, "-c", probe], cwd=str(root),
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(root),
                            "PYTHONDONTWRITEBYTECODE": "1"})
    eager = set(json.loads(r.stdout.strip().splitlines()[-1]))
    print(f"modules on the base startup graph: {len(eager)}")

    def hoistable(src_mod, dst):
        """CORRECTED: no shared cyclic SCC, existing or new."""
        e = {m: set(d) for m, d in edges.items()}
        e.setdefault(src_mod, set()).update(expand(dst))
        if [c for c in find_cycles(package_edges(e))
                if c not in PACKAGE_CYCLE_ALLOWLIST]:
            return False, "package cycle"
        if src_mod.startswith("psh.utils") and not dst.startswith("psh.utils"):
            return False, "utils leaf rule"
        if src_mod.startswith("psh.core") and not dst.startswith("psh.core") \
                and _top_package(dst) not in CORE_MODULE_IMPORT_ALLOWLIST:
            return False, "core near-leaf rule"
        for c in find_cycles(e):
            if src_mod in c and (expand(dst) & set(c)):
                return False, "src shares a module-level cycle with the target "
        return True, "ok"

    def module_path(base, module):
        rel = module.replace(".", "/")
        p = base / (rel + ".py")
        if p.exists():
            return p, False
        p = base / rel / "__init__.py"
        return (p, True) if p.exists() else (None, False)

    def sites_of(base, module):
        p, is_pkg = module_path(base, module)
        if p is None:
            return []
        out = []

        class V(ast.NodeVisitor):
            def __init__(self):
                self.depth = 0
                self.fn = []

            def visit_FunctionDef(self, node):
                self.depth += 1
                self.fn.append(node.name)
                self.generic_visit(node)
                self.fn.pop()
                self.depth -= 1

            visit_AsyncFunctionDef = visit_FunctionDef

            def _rec(self, targets, lineno):
                if self.depth <= 0:
                    return
                for t in targets:
                    if t and (t == "psh" or t.startswith("psh.")):
                        out.append((t, lineno, ".".join(self.fn)))

            def visit_Import(self, node):
                self._rec([a.name for a in node.names], node.lineno)

            def visit_ImportFrom(self, node):
                self._rec([_resolve_relative(module, node, is_pkg)
                           if node.level else node.module], node.lineno)

        V().visit(ast.parse(p.read_text()))
        return out

    free, costly, forced = [], [], []
    for module in sorted(m for m, c in counts.items() if c > 0):
        for tgt, lineno, fn in sites_of(root, module):
            ok, why = hoistable(module, tgt)
            if not ok:
                forced.append((module, tgt, lineno, fn, why))
            elif tgt in eager:
                free.append((module, tgt, lineno, fn))
            else:
                costly.append((module, tgt, lineno, fn))

    act = sum(counts.values())
    cap_total = sum(FUNC_IMPORT_CAPS.values())
    print()
    print("=" * 74)
    print("CORRECTED CLASSIFICATION")
    print("=" * 74)
    print(f"  actual deferred sites : {act}")
    print(f"  FREE   (hoistable, target already on startup graph): {len(free)}"
          f"   edges={len({(m, t) for m, t, _, _ in free})}")
    print(f"  COSTLY (hoistable, adds modules to startup)        : "
          f"{len(costly)}   targets="
          f"{len({t for _, t, _, _ in costly})}")
    print(f"  CYCLE-FORCED (must stay deferred)                  : "
          f"{len(forced)}")
    print()
    for module, tgt, lineno, fn, why in sorted(forced):
        print(f"    FORCED {module}:{lineno} -> {tgt}  ({why})")
    print()

    # --- build + REALLY import the FREE-only tree --------------------------
    freemap = {}
    for module, tgt, _, _ in free:
        freemap.setdefault(module, set()).add(tgt)
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    shutil.copytree(root / "psh", scratch / "psh",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for module, targets in freemap.items():
        p, _ = module_path(scratch, module)
        src = p.read_text()
        lines = src.splitlines(keepends=True)
        tree = ast.parse(src)
        insert_at = 0
        for stmt in tree.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                    and isinstance(stmt.value.value, str):
                insert_at = stmt.end_lineno
                continue
            if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
                insert_at = stmt.end_lineno
                continue
            break
        lines.insert(insert_at, "".join(f"import {t}  # 5B.2-free-hoist\n"
                                        for t in sorted(targets)))
        p.write_text("".join(lines))

    chk = subprocess.run(
        [sys.executable, "-c",
         "import os, psh, psh.shell\n"
         f"assert os.path.dirname(psh.__file__) == {str(scratch / 'psh')!r}, psh.__file__\n"
         "print('IMPORT_OK')"],
        cwd=str(scratch), capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(scratch),
             "PYTHONDONTWRITEBYTECODE": "1"})
    print("=" * 74)
    print("REAL IMPORT of the corrected FREE-only tree")
    print("=" * 74)
    print(f"  {chk.stdout.strip() or chk.stderr.strip()[-500:]}")
    print(f"  returncode={chk.returncode}")
    print()

    base_ms = cumulative_import_ms(root)
    free_ms = cumulative_import_ms(scratch)
    print("=" * 74)
    print("`import psh` CUMULATIVE COST (ms) — median of 5")
    print("=" * 74)
    print(f"  base        : {statistics.median(base_ms):8.1f}   {base_ms}")
    if free_ms is None:
        print("  FREE hoists :  N/A — tree does not import; no timing reported")
    else:
        print(f"  FREE hoists : {statistics.median(free_ms):8.1f}   {free_ms}")
        print(f"  ratio       : "
              f"{statistics.median(free_ms)/statistics.median(base_ms):.2f}x")
    print()
    print("=" * 74)
    print("TARGET TRIPLE MENU (ruling (d) input)")
    print("=" * 74)
    dead = [m for m in FUNC_IMPORT_CAPS if counts.get(m, 0) == 0]
    dead_cap = sum(FUNC_IMPORT_CAPS[m] for m in dead)
    print(f"  base             : actual {act}, cap {cap_total}, "
          f"slack {cap_total - act}, entries {len(FUNC_IMPORT_CAPS)}")
    print(f"  dead entries     : {len(dead)} entries / {dead_cap} cap -> {dead}")
    print(f"  (i)  bookkeeping : actual {act}, cap {act}, slack 0, "
          f"entries {len(FUNC_IMPORT_CAPS) - len(dead)}")
    print(f"  (ii) + FREE      : actual {act - len(free)}, "
          f"cap {act - len(free)}, slack 0")
    print(f"  (iii)+ FREE+COSTLY: actual {act - len(free) - len(costly)} "
          f"(adds {len({t for _, t, _, _ in costly})} modules to every startup)")
    print()
    print("  PROVENANCE: scratch copies under this worktree, not a detached")
    print("  checkout (B71). Phase A decision probes; re-measured detached in")
    print("  Phase B if a ruling turns on the timing.")


if __name__ == "__main__":
    main()
