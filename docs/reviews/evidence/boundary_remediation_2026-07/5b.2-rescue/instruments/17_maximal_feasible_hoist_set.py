#!/usr/bin/env python3
"""Instrument 17 (slot 5B.2) — the MAXIMAL feasible hoist set, found empirically.

Instrument 16: 50 of 51 modules hoist fine ALONE (118 of 119 statements).
Instrument 15: all 119 together do NOT import. Individual feasibility does not
compose, because whether ``from X import Name`` succeeds depends on which
module the interpreter entered first.

Since no static predicate has survived contact with this question (four
attempts, §A5.4), this instrument stops predicting and searches: apply every
hoist, import; on ImportError, blame the module whose hoisted line is in the
final frame, drop it, retry. It converges on a set that demonstrably imports
and runs, which is the only property worth landing on.

Usage:  python 17_maximal_feasible_hoist_set.py <ROOT> <SCRATCH>
"""
import ast
import os
import pathlib
import re
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

    candidates = [m for m, c in sorted(counts.items()) if c > 0]
    excluded = set()

    def build(excl):
        if scratch.exists():
            shutil.rmtree(scratch)
        scratch.mkdir(parents=True)
        shutil.copytree(root / "psh", scratch / "psh",
                        ignore=shutil.ignore_patterns("__pycache__"))
        applied = {}
        for module in candidates:
            if module in excl:
                continue
            p, is_pkg = module_path(scratch, module)
            if p is None:
                continue
            new_src, n = hoisted_source(p.read_text(), module, is_pkg)
            if new_src:
                p.write_text(new_src)
                applied[module] = n
        return applied

    probe = ("import os, psh, psh.shell\n"
             f"assert os.path.dirname(psh.__file__) == {str(scratch / 'psh')!r}\n"
             "print('OK')")

    for attempt in range(1, 16):
        applied = build(excluded)
        r = subprocess.run([sys.executable, "-c", probe], cwd=str(scratch),
                           capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": str(scratch),
                                "PYTHONDONTWRITEBYTECODE": "1"})
        n_stmt = sum(applied.values())
        if r.returncode == 0:
            print(f"attempt {attempt}: IMPORTS OK with {len(applied)} modules / "
                  f"{n_stmt} statements  (excluded {len(excluded)})")
            break
        # blame the deepest frame that names a psh file
        frames = re.findall(r'File "([^"]+psh/[^"]+\.py)", line (\d+)', r.stderr)
        blamed = None
        for path, _ln in reversed(frames):
            rel = pathlib.Path(path).resolve().relative_to(scratch)
            mod = str(rel.with_suffix("")).replace("/", ".")
            if mod.endswith(".__init__"):
                mod = mod[:-len(".__init__")]
            if mod in applied:
                blamed = mod
                break
        err = r.stderr.strip().splitlines()[-1][:100]
        print(f"attempt {attempt}: FAIL ({len(applied)} modules / {n_stmt} stmt)"
              f" -> blame {blamed}")
        print(f"            {err}")
        if blamed is None:
            print("            cannot attribute the failure; stopping")
            break
        excluded.add(blamed)
    else:
        print("did not converge within the attempt budget")

    print()
    print("=" * 74)
    print("RESULT")
    print("=" * 74)
    applied = build(excluded)
    r = subprocess.run([sys.executable, "-c", probe], cwd=str(scratch),
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(scratch),
                            "PYTHONDONTWRITEBYTECODE": "1"})
    print(f"  feasible set : {len(applied)} modules, "
          f"{sum(applied.values())} statements")
    print(f"  excluded     : {sorted(excluded)}")
    print(f"  imports      : {r.returncode == 0}")
    if r.returncode == 0:
        s = subprocess.run(
            [sys.executable, "-m", "psh", "-c",
             "echo hi; x=5; echo $((x+1)); a=(p q); echo ${a[1]}; "
             "declare -A h; h[k]=v; echo ${h[k]}"],
            cwd=str(scratch), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(scratch),
                 "PYTHONDONTWRITEBYTECODE": "1"})
        print(f"  shell smoke  : rc={s.returncode} out={s.stdout.strip()!r}")
    print()
    print(f"  actual deferred count would fall {sum(counts.values())} -> "
          f"{sum(counts.values()) - sum(applied.values())}")


if __name__ == "__main__":
    main()
