#!/usr/bin/env python3
"""Instrument 18 (slot 5B.2) — apply the verified hoist set to the WORKTREE.

R2 condition 1: "the landing diff is mechanically identical to the verified
set: either script-apply the same instrument that produced the verified scratch
tree, or diff branch-vs-scratch over the 50 modules and assert EMPTY."

This does BOTH. It re-uses instrument 17's transformation verbatim (same
predicate, same exclusion, same edit) against the real worktree, and then
asserts every touched file is BYTE-IDENTICAL to the corresponding file in the
verified scratch tree. If a single byte differs the script fails without
leaving the tree half-edited (it stages every rewrite in memory first).

Usage:  python 18_apply_hoist_to_worktree.py <ROOT> <VERIFIED_SCRATCH> [--apply]
"""
import ast
import pathlib
import subprocess
import sys

EXCLUDED = {"psh.expansion.glob"}   # breaks the joint set (instrument 17)


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    verified = pathlib.Path(sys.argv[2]).resolve()
    apply = "--apply" in sys.argv
    sys.path.insert(0, str(root))
    from tests.unit.tooling.test_import_layering import (  # noqa: E402
        CORE_MODULE_IMPORT_ALLOWLIST, PACKAGE_CYCLE_ALLOWLIST,
        _resolve_relative, _top_package, build_graph, find_cycles,
        package_edges,
    )

    print(f"ROOT={root}")
    print(f"VERIFIED={verified}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print(f"mode={'APPLY' if apply else 'DRY-RUN'}")
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
            return p, False, rel + ".py"
        p = base / rel / "__init__.py"
        if p.exists():
            return p, True, rel + "/__init__.py"
        return None, False, None

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

    planned = {}      # abs path -> new source
    stmt_total = 0
    for module in sorted(m for m, c in counts.items() if c > 0):
        if module in EXCLUDED:
            continue
        p, is_pkg, rel = module_path(root, module)
        if p is None:
            continue
        new_src, n = hoisted_source(p.read_text(), module, is_pkg)
        if new_src:
            planned[rel] = new_src
            stmt_total += n

    print(f"planned: {len(planned)} modules, {stmt_total} statements moved")
    print(f"excluded: {sorted(EXCLUDED)}")
    print()

    # --- byte-identity against the VERIFIED tree --------------------------
    print("=" * 74)
    print("IDENTITY CHECK vs the verified scratch tree")
    print("=" * 74)
    mismatches = []
    for rel, new_src in sorted(planned.items()):
        vfile = verified / "psh" / pathlib.Path(rel).relative_to("psh") \
            if rel.startswith("psh/") else None
        vfile = verified / rel
        if not vfile.exists():
            mismatches.append((rel, "missing in verified tree"))
            continue
        if vfile.read_text() != new_src:
            mismatches.append((rel, "BYTES DIFFER"))
    if mismatches:
        for rel, why in mismatches:
            print(f"  MISMATCH {rel}: {why}")
        print(f"  {len(mismatches)} mismatch(es) — NOT applying")
        sys.exit(1)
    print(f"  all {len(planned)} planned files byte-identical to the verified "
          "tree")
    print()

    if not apply:
        print("DRY-RUN: nothing written. Re-run with --apply to land.")
        return

    for rel, new_src in sorted(planned.items()):
        (root / rel).write_text(new_src)
    print(f"APPLIED {len(planned)} files.")

    # post-apply: the worktree must now equal the verified tree over psh/
    diff = subprocess.run(
        ["diff", "-r", "-q", str(root / "psh"), str(verified / "psh"),
         "-x", "__pycache__"],
        capture_output=True, text=True)
    print()
    print("=" * 74)
    print("POST-APPLY: diff -r worktree/psh vs verified/psh")
    print("=" * 74)
    print(diff.stdout.strip() or "  (identical)")
    print(f"  diff returncode={diff.returncode} (0 = identical)")


if __name__ == "__main__":
    main()
