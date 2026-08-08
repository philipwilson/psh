#!/usr/bin/env python3
"""Instrument 16 (slot 5B.2) — per-module hoist feasibility, REAL edit shape.

Instrument 15 showed the full 119-statement hoist set is NOT importable once
the edit is performed the way a real hoist performs it (statement MOVED, so
``from X import Name`` runs at module level). This instrument bounds what is
actually available: it applies each module's hoists ALONE, in a scratch tree,
and asks whether psh still imports and runs.

Per-module success does NOT compose — instrument 09 already demonstrated that a
subset can fail where a superset passed, because import order decides — so this
is an UPPER BOUND on a safe tranche and a candidate list, not a landing set.
Any tranche that lands must be verified AS the tranche that lands.

Usage:  python 16_per_module_hoist_feasibility.py <ROOT> <SCRATCH>
"""
import ast
import os
import pathlib
import shutil
import subprocess
import sys


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

    def hoisted_source(src, module, is_pkg):
        tree = ast.parse(src)
        lines = src.splitlines(keepends=True)
        to_move = []

        class V(ast.NodeVisitor):
            def __init__(self):
                self.depth = 0

            def visit_FunctionDef(self, node):
                self.depth += 1
                self.generic_visit(node)
                self.depth -= 1

            visit_AsyncFunctionDef = visit_FunctionDef

            def _consider(self, node, targets):
                if self.depth <= 0:
                    return
                tg = [t for t in targets if t and t.startswith("psh")]
                if tg and all(hoistable(module, t) for t in tg):
                    to_move.append((node.lineno, node.end_lineno))

            def visit_Import(self, node):
                self._consider(node, [a.name for a in node.names])

            def visit_ImportFrom(self, node):
                self._consider(node, [_resolve_relative(module, node, is_pkg)
                                      if node.level else node.module])

        V().visit(tree)
        if not to_move:
            return None, 0
        stmts = []
        for start, end in to_move:
            block = "".join(lines[start - 1:end])
            stmts.append("\n".join(ln.strip() for ln in block.splitlines()) + "\n")
            for i in range(start - 1, end):
                lines[i] = ""
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
        lines.insert(insert_at, "".join(stmts))
        return "".join(lines), len(to_move)

    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    shutil.copytree(root / "psh", scratch / "psh",
                    ignore=shutil.ignore_patterns("__pycache__"))

    probe = ("import os, psh, psh.shell\n"
             f"assert os.path.dirname(psh.__file__) == {str(scratch / 'psh')!r}\n"
             "print('OK')")

    def imports_ok():
        r = subprocess.run([sys.executable, "-c", probe], cwd=str(scratch),
                           capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": str(scratch),
                                "PYTHONDONTWRITEBYTECODE": "1"})
        return r.returncode == 0, r.stderr.strip().splitlines()[-1:] or [""]

    ok, _ = imports_ok()
    print(f"scratch baseline imports: {ok}")
    assert ok, "scratch baseline broken; results would be noise"
    print()

    feasible, infeasible = [], []
    for module in sorted(m for m, c in counts.items() if c > 0):
        p, is_pkg = module_path(scratch, module)
        if p is None:
            continue
        backup = p.read_text()
        new_src, n = hoisted_source(backup, module, is_pkg)
        if not new_src:
            continue
        p.write_text(new_src)
        ok, err = imports_ok()
        p.write_text(backup)
        (feasible if ok else infeasible).append((module, n, err[0][:90]))

    print("=" * 74)
    print("FEASIBLE ALONE (module's hoists applied by themselves)")
    print("=" * 74)
    for m, n, _ in feasible:
        print(f"  {m}  ({n} statement(s))")
    print(f"  modules: {len(feasible)}   statements: {sum(n for _, n, _ in feasible)}")
    print()
    print("=" * 74)
    print("INFEASIBLE ALONE — a real hoist here breaks the import")
    print("=" * 74)
    for m, n, err in infeasible:
        print(f"  {m}  ({n} stmt)  {err}")
    print(f"  modules: {len(infeasible)}   statements: {sum(n for _, n, _ in infeasible)}")
    print()
    print("NOTE: per-module success does NOT compose (a subset can fail where a")
    print("superset passed — import order decides). This is an UPPER BOUND on a")
    print("safe tranche, not a landing set.")


if __name__ == "__main__":
    main()
