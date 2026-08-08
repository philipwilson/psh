#!/usr/bin/env python3
"""Instrument 15 (slot 5B.2) — verify the hoist set with the REAL edit shape.

DEFECT IN MY OWN EARLIER VERIFICATION (instruments 06/09), recorded because it
would have justified a 119-site production change on evidence that did not
cover the change:

Those instruments verified hoistability by ADDING ``import psh.some.module`` at
module level. A real hoist does something different and STRICTER — it MOVES the
existing statement, which is almost always ``from ..pkg.mod import Name``. The
two are not interchangeable under a cycle: ``import X`` binds the module object
and tolerates X being partially initialised, whereas ``from X import Name``
requires ``Name`` to already EXIST on a partially-initialised X and raises
ImportError when it does not. That is precisely the failure the earlier probe
hit once (``cannot import name 'ParseOutcome' from partially initialized
module``) — with the weaker form.

So this instrument performs the ACTUAL edit in a scratch tree: delete each
deferred import statement from its function body and re-insert the identical
statement at module level. Then it imports psh and runs the shell.

Usage:  python 15_real_hoist_verification.py <ROOT> <SCRATCH>
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

    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    shutil.copytree(root / "psh", scratch / "psh",
                    ignore=shutil.ignore_patterns("__pycache__"))

    moved_total = 0
    touched_modules = 0
    for module in sorted(m for m, c in counts.items() if c > 0):
        p, is_pkg = module_path(scratch, module)
        if p is None:
            continue
        src = p.read_text()
        tree = ast.parse(src)
        lines = src.splitlines(keepends=True)

        # collect deferred import statements that are hoistable
        to_move = []           # (start_lineno, end_lineno, statement text)

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
                if not tg or not all(hoistable(module, t) for t in tg):
                    return
                to_move.append((node.lineno, node.end_lineno))

            def visit_Import(self, node):
                self._consider(node, [a.name for a in node.names])

            def visit_ImportFrom(self, node):
                self._consider(node, [_resolve_relative(module, node, is_pkg)
                                      if node.level else node.module])

        V().visit(tree)
        if not to_move:
            continue

        # Extract the statement text, DEDENTED, then blank the original lines.
        stmts = []
        for start, end in to_move:
            block = "".join(lines[start - 1:end])
            stmts.append("\n".join(ln.strip() for ln in block.splitlines()) + "\n")
            for i in range(start - 1, end):
                lines[i] = ""
        moved_total += len(to_move)
        touched_modules += 1

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
        p.write_text("".join(lines))

    print(f"REAL hoists applied: {moved_total} statements across "
          f"{touched_modules} modules")
    print()

    probe = ("import os, psh, psh.shell\n"
             f"assert os.path.dirname(psh.__file__) == {str(scratch / 'psh')!r}, psh.__file__\n"
             "print('IMPORT_OK')")
    r = subprocess.run([sys.executable, "-c", probe], cwd=str(scratch),
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(scratch),
                            "PYTHONDONTWRITEBYTECODE": "1"})
    print("=" * 74)
    print("REAL IMPORT (statements MOVED, not duplicated)")
    print("=" * 74)
    print(r.stdout.strip() or "")
    if r.returncode != 0:
        print("--- STDERR (tail) ---")
        print("\n".join(r.stderr.strip().splitlines()[-12:]))
    print(f"returncode={r.returncode}")
    print()

    if r.returncode == 0:
        s = subprocess.run(
            [sys.executable, "-m", "psh", "-c",
             "echo hi; x=5; echo $((x+1)); a=(p q); echo ${a[1]}"],
            cwd=str(scratch), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(scratch),
                 "PYTHONDONTWRITEBYTECODE": "1"})
        print(f"shell smoke: rc={s.returncode} out={s.stdout.strip()!r}")
        if s.stderr.strip():
            print("stderr:", s.stderr.strip()[-400:])


if __name__ == "__main__":
    main()
