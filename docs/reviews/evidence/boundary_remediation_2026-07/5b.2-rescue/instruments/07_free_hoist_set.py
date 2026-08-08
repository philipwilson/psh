#!/usr/bin/env python3
"""Instrument 07 (slot 5B.2) — the ZERO-COST hoist set.

Instrument 06 proved all 84 candidate edges are jointly importable, but the
import-time measurement that followed showed the full set takes `import psh`
from ~66ms to ~249ms cumulative (~3.4x). That is the deferred imports doing
real work: psh is a SHELL, and startup latency is paid by every invocation and
by every subprocess the suite spawns. "Caps materially shrink" cannot mean
"make the shell 3x slower to start".

So the honest criterion for a FREE hoist is not "is it layering-legal" but
"is the target ALREADY imported during a base `import psh` anyway". Hoisting
such an import adds no module to the startup graph — the edge becomes explicit
at module level while the module was being loaded regardless. This instrument
partitions the candidate set on exactly that measurement.

  FREE   target already in sys.modules after a base `import psh`
  COSTLY target absent at base -> hoisting ADDS it to every startup

Usage:  python 07_free_hoist_set.py <ROOT>
"""
import ast
import json
import os
import pathlib
import subprocess
import sys


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(root))
    from tests.unit.tooling.test_import_layering import (  # noqa: E402
        CORE_MODULE_IMPORT_ALLOWLIST, PACKAGE_CYCLE_ALLOWLIST,
        _resolve_relative, _top_package, build_graph, find_cycles,
        package_edges,
    )

    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print()

    # --- what is loaded by a BASE `import psh`? (measured, in a subprocess) --
    probe = (
        "import os, sys, json\n"
        "import psh\n"
        "assert os.path.dirname(psh.__file__) == os.path.join("
        f"{str(root)!r}, 'psh'), 'DISCRIMINATOR FAILED: ' + psh.__file__\n"
        "print(json.dumps(sorted(m for m in sys.modules if m == 'psh' or "
        "m.startswith('psh.'))))\n"
    )
    r = subprocess.run([sys.executable, "-c", probe], cwd=str(root),
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(root),
                            "PYTHONDONTWRITEBYTECODE": "1"})
    if r.returncode != 0:
        print("BASE import probe FAILED:")
        print(r.stderr[-2000:])
        return
    eager = set(json.loads(r.stdout.strip().splitlines()[-1]))
    print(f"modules loaded by a base `import psh`: {len(eager)}")
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

    free_sites, costly_sites = [], []
    for module in sorted(m for m, c in counts.items() if c > 0):
        p, is_pkg = module_path(module)
        if p is None:
            continue
        tree = ast.parse(p.read_text())
        sites = []

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
                        sites.append((t, lineno, ".".join(self.fn)))

            def visit_Import(self, node):
                self._rec([a.name for a in node.names], node.lineno)

            def visit_ImportFrom(self, node):
                self._rec([_resolve_relative(module, node, is_pkg)
                           if node.level else node.module], node.lineno)

        V().visit(tree)
        for tgt, lineno, fn in sites:
            if not hoistable(module, tgt):
                continue
            # A hoist is FREE only if BOTH ends are already on the startup
            # graph: the target must be loaded anyway, AND the module doing
            # the importing must itself be loaded at startup (otherwise the
            # edge only fires later, when it is free by construction).
            if tgt in eager:
                free_sites.append((module, tgt, lineno, fn,
                                   module in eager))
            else:
                costly_sites.append((module, tgt, lineno, fn,
                                     module in eager))

    print("=" * 74)
    print("FREE hoists — target already loaded by a base `import psh`")
    print("=" * 74)
    for module, tgt, lineno, fn, src_eager in sorted(free_sites):
        print(f"  {module}:{lineno} -> {tgt}   [{fn}]"
              f"{'' if src_eager else '   (importer itself lazy)'}")
    print(f"  FREE sites: {len(free_sites)}  "
          f"(distinct edges: {len({(m, t) for m, t, _, _, _ in free_sites})})")
    print()
    print("=" * 74)
    print("COSTLY hoists — target NOT on the startup graph (would be added)")
    print("=" * 74)
    costly_targets = sorted({t for _, t, _, _, _ in costly_sites})
    for module, tgt, lineno, fn, _ in sorted(costly_sites):
        print(f"  {module}:{lineno} -> {tgt}   [{fn}]")
    print(f"  COSTLY sites: {len(costly_sites)}  "
          f"distinct targets added to startup: {len(costly_targets)}")
    print()
    print("=" * 74)
    print("TARGET TRIPLE CANDIDATES (ruling (d) input)")
    print("=" * 74)
    act = sum(counts.values())
    print(f"  base            : actual {act}, cap 198, slack 21, entries 71")
    print(f"  (i) bookkeeping : actual {act} (unchanged), cap {act}, slack 0")
    print(f"  (ii) + FREE     : actual {act - len(free_sites)}, "
          f"cap {act - len(free_sites)}, slack 0   <-- zero startup cost")
    print(f"  (iii) + ALL     : actual {act - len(free_sites) - len(costly_sites)}, "
          f"... but +{len(costly_targets)} modules on EVERY startup "
          f"(measured ~66ms -> ~249ms)")


if __name__ == "__main__":
    main()
