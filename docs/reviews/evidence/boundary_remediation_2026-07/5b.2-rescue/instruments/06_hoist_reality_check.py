#!/usr/bin/env python3
"""Instrument 06 (slot 5B.2) — do the simulated hoists SURVIVE A REAL IMPORT?

Instrument 05 classifies a deferred import as hoistable when a module-level edge
keeps the layering guard green AND introduces no new module-level cycle. Both
are static tests; neither executes an import. Python's actual behaviour on a
cyclic module-level import depends on ACCESS ORDER at import time, so a static
verdict can be wrong in both directions. The brief's Pins section asks the
question directly ("each hoisted import's module still imports clean"), so this
instrument answers it by DOING it.

Method, chosen so the risky half is what gets tested: for every candidate site
we ADD the import at module level in a scratch COPY of the tree, leaving the
deferred import in place. Adding the module-level edge is the operation that can
raise ImportError; deleting a now-redundant function-body import afterwards
cannot. If `import psh` succeeds with all candidate edges added, the set is
jointly feasible.

The scratch copy means nothing is edited in the worktree during Phase A, and the
discriminator is asserted explicitly: the psh that gets imported must be the
COPY, not the editable install (which points at MAIN and has burned prior devs).

Usage:  python 06_hoist_reality_check.py <ROOT> <SCRATCH>
"""
import ast
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
    print(f"SCRATCH={scratch}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print()

    edges, counts = build_graph()
    base_module_cycles = {frozenset(c) for c in find_cycles(edges)}

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
        if {frozenset(c) for c in find_cycles(e)} - base_module_cycles:
            return False
        return True

    def module_path(module):
        rel = module.replace(".", "/")
        p = root / (rel + ".py")
        if p.exists():
            return p, False
        p = root / rel / "__init__.py"
        return (p, True) if p.exists() else (None, False)

    # --- collect candidate (module -> target) pairs -------------------------
    candidates = {}
    for module in sorted(m for m, c in counts.items() if c > 0):
        p, is_pkg = module_path(module)
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
                if self.depth <= 0:
                    return
                for t in targets:
                    if t and (t == "psh" or t.startswith("psh.")):
                        if hoistable(module, t):
                            candidates.setdefault(module, set()).add(t)

            def visit_Import(self, node):
                self._rec([a.name for a in node.names])

            def visit_ImportFrom(self, node):
                self._rec([_resolve_relative(module, node, is_pkg)
                           if node.level else node.module])

        V().visit(tree)

    n_sites = sum(len(v) for v in candidates.values())
    print(f"candidate MODULES: {len(candidates)}   distinct edges: {n_sites}")
    print()

    # --- build the scratch copy with every candidate edge ADDED ------------
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    shutil.copytree(root / "psh", scratch / "psh",
                    ignore=shutil.ignore_patterns("__pycache__"))

    for module, targets in candidates.items():
        rel = module.replace(".", "/")
        p = scratch / (rel + ".py")
        if not p.exists():
            p = scratch / rel / "__init__.py"
        src = p.read_text()
        lines = src.splitlines(keepends=True)
        # insert after the module docstring, before any other statement
        tree = ast.parse(src)
        # After the docstring AND after any `from __future__ import ...`
        # (a __future__ import must be the first statement after the
        # docstring, so inserting above one is a SyntaxError — caught by the
        # first run of this instrument, recorded rather than silently fixed).
        insert_at = 0
        for stmt in tree.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value,
                                                         ast.Constant) \
                    and isinstance(stmt.value.value, str):
                insert_at = stmt.end_lineno
                continue
            if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
                insert_at = stmt.end_lineno
                continue
            break
        block = "".join(f"import {t}  # 5B.2-hoist-probe\n"
                        for t in sorted(targets))
        lines.insert(insert_at, block)
        p.write_text("".join(lines))

    # --- the real import, with the discriminator asserted ------------------
    probe = (
        "import sys, os\n"
        "import psh\n"
        "print('RESOLVED_PSH=' + os.path.dirname(psh.__file__))\n"
        f"assert os.path.dirname(psh.__file__) == {str(scratch / 'psh')!r}, \\\n"
        "    'DISCRIMINATOR FAILED: imported the wrong psh'\n"
        "import psh.shell\n"
        "print('IMPORT_OK')\n"
    )
    r = subprocess.run([sys.executable, "-c", probe], cwd=str(scratch),
                       capture_output=True, text=True,
                       env={**__import__("os").environ,
                            "PYTHONPATH": str(scratch),
                            "PYTHONDONTWRITEBYTECODE": "1"})
    print("=" * 74)
    print("REAL IMPORT with every candidate edge added at module level")
    print("=" * 74)
    print(r.stdout.strip())
    if r.returncode != 0:
        print("--- STDERR (tail) ---")
        print("\n".join(r.stderr.strip().splitlines()[-25:]))
    print(f"  returncode={r.returncode}   "
          f"=> {'ALL JOINTLY FEASIBLE' if r.returncode == 0 else 'NOT feasible as a set'}")
    print()
    print(f"  If feasible, the achievable ACTUAL reduction is {n_sites} "
          f"distinct edges across {len(candidates)} modules.")
    print("  NOTE: distinct EDGES, not sites — several sites in one module may")
    print("  share a target, so the site-count reduction is >= the edge count.")


if __name__ == "__main__":
    main()
