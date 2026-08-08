#!/usr/bin/env python3
"""Q4 axis-1 instrument: independent stdlib-only import-graph walker for psh/.

Usage: python3 q4_01_import_walker.py <tree-root> [--json OUT.json]

<tree-root> is a directory containing a `psh/` package. The walker:
  - AST-parses every psh module (nothing under psh is imported/executed)
  - classifies each `psh.*` import as RUNTIME (module/class level, outside
    `if TYPE_CHECKING:`) or DEFERRED (inside a function/method body)
  - resolves relative imports to absolute psh.* names
  - for `from X import a`, records an edge to X and, when X.a is a real
    module in the tree, an edge to X.a as well (both are real import-time
    edges at runtime)
  - reports cycles (Tarjan SCC) at MODULE granularity and at depth-2
    PACKAGE granularity (intra-package edges dropped)
  - reports the per-module deferred-import census

Written independently of tests/unit/tooling/test_import_layering.py (same
question, fresh implementation) per the Q4 charter.
"""
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path


def module_name(root, path):
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def is_type_checking(test):
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


class ImportCollector(ast.NodeVisitor):
    """Collect (target, is_deferred, names) tuples for psh imports."""

    def __init__(self, mod, is_pkg):
        self.mod = mod
        self.is_pkg = is_pkg
        self.fdepth = 0
        self.tc_depth = 0
        self.records = []  # (abs_target_or_None, from_names_or_None, deferred)

    def visit_FunctionDef(self, node):
        self.fdepth += 1
        self.generic_visit(node)
        self.fdepth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        self.fdepth += 1
        self.generic_visit(node)
        self.fdepth -= 1

    def visit_If(self, node):
        if is_type_checking(node.test):
            self.tc_depth += 1
            for stmt in node.body:
                self.visit(stmt)
            self.tc_depth -= 1
            for stmt in node.orelse:
                self.visit(stmt)
        else:
            self.generic_visit(node)

    def _resolve_rel(self, node):
        parts = self.mod.split(".")
        anchor = list(parts) if self.is_pkg else parts[:-1]
        up = node.level - 1
        if up > 0:
            anchor = anchor[:-up] if up <= len(anchor) else []
        base = ".".join(anchor)
        if node.module:
            return f"{base}.{node.module}" if base else node.module
        return base

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name == "psh" or alias.name.startswith("psh."):
                self.records.append((alias.name, None, self.fdepth > 0,
                                     self.tc_depth > 0))

    def visit_ImportFrom(self, node):
        if node.level and node.level > 0:
            target = self._resolve_rel(node)
        else:
            target = node.module
        if target and (target == "psh" or target.startswith("psh.")):
            names = [a.name for a in node.names]
            self.records.append((target, names, self.fdepth > 0,
                                 self.tc_depth > 0))


def walk(root):
    psh_dir = root / "psh"
    modules = {}     # name -> (path, is_pkg)
    for path in sorted(psh_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        name = module_name(root, path)
        modules[name] = (path, path.name == "__init__.py")

    known = set(modules)
    runtime_edges = defaultdict(set)
    deferred_counts = defaultdict(int)
    deferred_targets = defaultdict(list)

    for name, (path, is_pkg) in modules.items():
        col = ImportCollector(name, is_pkg)
        col.visit(ast.parse(path.read_text()))
        for target, from_names, deferred, tc in col.records:
            if tc:
                continue  # TYPE_CHECKING-only: not an import-time edge
            edge_targets = {target}
            if from_names:
                for n in from_names:
                    sub = f"{target}.{n}"
                    if sub in known:
                        edge_targets.add(sub)
            if deferred:
                deferred_counts[name] += 1
                deferred_targets[name].append(target)
            else:
                for t in edge_targets:
                    if t != name:
                        runtime_edges[name].add(t)
    return modules, runtime_edges, deferred_counts, deferred_targets


def tarjan(edges):
    index, low, onstack, order, sccs = {}, {}, set(), [], []
    stack = []
    counter = [0]
    nodes = set(edges) | {d for ds in edges.values() for d in ds}

    def strong(v):
        # iterative Tarjan to dodge recursion limits
        work = [(v, iter(sorted(edges.get(v, ()))))]
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        onstack.add(v)
        while work:
            node, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    onstack.add(w)
                    work.append((w, iter(sorted(edges.get(w, ())))))
                    advanced = True
                    break
                elif w in onstack:
                    low[node] = min(low[node], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    onstack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                sccs.append(comp)

    for v in sorted(nodes):
        if v not in index:
            strong(v)
    cycles = [sorted(c) for c in sccs if len(c) > 1]
    self_loops = [c[0] for c in sccs
                  if len(c) == 1 and c[0] in edges.get(c[0], set())]
    return cycles, self_loops


def to_package(mod, depth=2):
    return ".".join(mod.split(".")[:depth])


def main():
    root = Path(sys.argv[1]).resolve()
    out_json = None
    if "--json" in sys.argv:
        out_json = sys.argv[sys.argv.index("--json") + 1]

    modules, runtime_edges, deferred_counts, deferred_targets = walk(root)

    mod_cycles, mod_selfloops = tarjan(runtime_edges)

    pkg_edges = defaultdict(set)
    for src, dsts in runtime_edges.items():
        ps = to_package(src)
        for d in dsts:
            pd = to_package(d)
            if pd != ps:
                pkg_edges[ps].add(pd)
    pkg_cycles, pkg_selfloops = tarjan(pkg_edges)

    total_deferred = sum(deferred_counts.values())
    result = {
        "tree_root": str(root),
        "module_count": len(modules),
        "runtime_edge_count": sum(len(v) for v in runtime_edges.values()),
        "module_level_cycles": mod_cycles,
        "module_self_loops": mod_selfloops,
        "package_level_cycles": pkg_cycles,
        "package_self_loops": pkg_selfloops,
        "deferred_import_total": total_deferred,
        "deferred_module_count": len(deferred_counts),
        "deferred_counts": dict(sorted(deferred_counts.items())),
        "deferred_targets": {k: sorted(v) for k, v in
                             sorted(deferred_targets.items())},
    }
    print(f"tree: {root}")
    print(f"modules: {len(modules)}  runtime psh->psh edges: "
          f"{result['runtime_edge_count']}")
    print(f"MODULE-level cycles: {len(mod_cycles)}  self-loops: "
          f"{len(mod_selfloops)}")
    for c in mod_cycles:
        print("  CYCLE: " + " <-> ".join(c))
    print(f"PACKAGE-level (depth-2) cycles: {len(pkg_cycles)}  self-loops: "
          f"{len(pkg_selfloops)}")
    for c in pkg_cycles:
        print("  PKG-CYCLE: " + " <-> ".join(c))
    print(f"deferred psh imports: {total_deferred} across "
          f"{len(deferred_counts)} modules")
    if out_json:
        Path(out_json).write_text(json.dumps(result, indent=1))
        print(f"json written: {out_json}")


if __name__ == "__main__":
    main()
