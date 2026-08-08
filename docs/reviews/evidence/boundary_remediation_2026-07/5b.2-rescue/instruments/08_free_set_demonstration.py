#!/usr/bin/env python3
"""Instrument 08 (slot 5B.2) — DEMONSTRATE that the FREE hoist set is free.

Instrument 07 partitions candidate hoists by whether the target is already on
the startup graph, and INFERS that the "free" partition costs nothing. An
inference is not a measurement (and the whole reason this partition exists is
that instrument 06's static verdict was contradicted by a real timing). So this
instrument builds a scratch tree with ONLY the free edges hoisted and measures
the same two things the costly set was rejected on: does it import, and what
does `import psh` cost.

Reported as a three-way comparison against the base and the all-hoists tree, so
the free set's claim is falsifiable in the same units that falsified the max
set.

Usage:  python 08_free_set_demonstration.py <ROOT> <SCRATCH>
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
    """`import psh` cumulative time in ms, from -X importtime's psh row."""
    vals = []
    for _ in range(runs):
        r = subprocess.run(
            [sys.executable, "-X", "importtime", "-c", "import psh"],
            cwd=str(tree_root), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(tree_root),
                 "PYTHONDONTWRITEBYTECODE": "1"})
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
        CORE_MODULE_IMPORT_ALLOWLIST, PACKAGE_CYCLE_ALLOWLIST,
        _resolve_relative, _top_package, build_graph, find_cycles,
        package_edges,
    )

    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print()

    probe = ("import sys, json, psh\n"
             "print(json.dumps(sorted(m for m in sys.modules "
             "if m == 'psh' or m.startswith('psh.'))))\n")
    r = subprocess.run([sys.executable, "-c", probe], cwd=str(root),
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(root),
                            "PYTHONDONTWRITEBYTECODE": "1"})
    eager = set(json.loads(r.stdout.strip().splitlines()[-1]))

    edges, counts = build_graph()
    base_cycles = {frozenset(c) for c in find_cycles(edges)}

    def hoistable(src_mod, dst):
        e = {m: set(d) for m, d in edges.items()}
        e.setdefault(src_mod, set()).add(dst)
        if [c for c in find_cycles(package_edges(e))
                if c not in PACKAGE_CYCLE_ALLOWLIST]:
            return False
        if src_mod.startswith("psh.utils") and not dst.startswith("psh.utils"):
            return False
        if src_mod.startswith("psh.core") and not dst.startswith("psh.core") \
                and _top_package(dst) not in CORE_MODULE_IMPORT_ALLOWLIST:
            return False
        return not ({frozenset(c) for c in find_cycles(e)} - base_cycles)

    def module_path(base, module):
        rel = module.replace(".", "/")
        p = base / (rel + ".py")
        if p.exists():
            return p, False
        p = base / rel / "__init__.py"
        return (p, True) if p.exists() else (None, False)

    free = {}
    n_free_sites = 0
    for module in sorted(m for m, c in counts.items() if c > 0):
        p, is_pkg = module_path(root, module)
        if p is None:
            continue
        tree = ast.parse(p.read_text())

        class V(ast.NodeVisitor):
            def __init__(self):
                self.depth = 0

            def visit_FunctionDef(self, node):
                self.depth += 1
                self.generic_visit(node)
                self.depth -= 1

            visit_AsyncFunctionDef = visit_FunctionDef

            def _rec(self, targets):
                nonlocal n_free_sites
                if self.depth <= 0:
                    return
                for t in targets:
                    if t and t.startswith("psh") and hoistable(module, t) \
                            and t in eager:
                        free.setdefault(module, set()).add(t)
                        n_free_sites += 1

            def visit_Import(self, node):
                self._rec([a.name for a in node.names])

            def visit_ImportFrom(self, node):
                self._rec([_resolve_relative(module, node, is_pkg)
                           if node.level else node.module])

        V().visit(tree)

    edge_count = sum(len(v) for v in free.values())
    print(f"FREE set: {n_free_sites} sites, {edge_count} distinct edges, "
          f"{len(free)} modules")
    print()

    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    shutil.copytree(root / "psh", scratch / "psh",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for module, targets in free.items():
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
    print("REAL IMPORT of the FREE-only tree")
    print("=" * 74)
    print(f"  {chk.stdout.strip() or chk.stderr.strip()[-400:]}")
    print(f"  returncode={chk.returncode}")
    print()

    base_ms = cumulative_import_ms(root)
    free_ms = cumulative_import_ms(scratch)
    allh = root / "tmp/hoist-scratch"
    all_ms = cumulative_import_ms(allh) if (allh / "psh").is_dir() else []

    print("=" * 74)
    print("`import psh` CUMULATIVE COST (ms) — median of 5")
    print("=" * 74)
    print(f"  base          : {statistics.median(base_ms):8.1f}   {base_ms}")
    print(f"  FREE hoists   : {statistics.median(free_ms):8.1f}   {free_ms}")
    if all_ms:
        print(f"  ALL hoists    : {statistics.median(all_ms):8.1f}   {all_ms}")
    print()
    print(f"  FREE vs base  : "
          f"{statistics.median(free_ms) / statistics.median(base_ms):.2f}x")
    if all_ms:
        print(f"  ALL  vs base  : "
              f"{statistics.median(all_ms) / statistics.median(base_ms):.2f}x")
    print()
    print("  PROVENANCE: measured in a scratch COPY of the tree under this")
    print("  worktree, not at a detached checkout of a declared tip (B71). It")
    print("  is a Phase A decision probe, not a certification figure; if the")
    print("  ruling turns on it, it gets re-measured detached in Phase B.")


if __name__ == "__main__":
    main()
