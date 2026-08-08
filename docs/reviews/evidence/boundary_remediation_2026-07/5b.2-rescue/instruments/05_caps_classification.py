#!/usr/bin/env python3
"""Instrument 05 (slot 5B.2) — deferred-import caps: per-entry classification
and a MEASURED hoistability verdict for every deferred site.

Ruling (d) needs a target actual/cap/slack triple that is derived, not guessed.
Every term here comes from the import-layering lock's OWN analyzer (the guard is
the authority on what counts as a deferred psh import), and every hoist verdict
is a SIMULATION against that guard's own graph rather than a reading of the
rules: for each deferred site ``M -> T`` we add the module-level edge to the
live graph and ask the guard's cycle finder + leaf rules whether it stays green.

Classes reported per entry:
  DEAD          cap entry with actual 0            -> delete the entry
  SLACK         cap > actual                        -> lower the cap to actual
  HOISTABLE     a site whose module-level edge keeps the lock green
  CYCLE-FORCED  a site whose module-level edge makes the lock red

A HOISTABLE site is a genuine actual-count reduction; a SLACK trim is
bookkeeping. The two are reported separately and never summed into one figure
(5B.1 lesson 3: every term needs its own source).

Usage:  python 05_caps_classification.py <ROOT>
"""
import ast
import pathlib
import subprocess
import sys


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(root))
    from tests.unit.tooling.test_import_layering import (  # noqa: E402
        CORE_MODULE_IMPORT_ALLOWLIST, FUNC_IMPORT_CAPS, PACKAGE_CYCLE_ALLOWLIST,
        _resolve_relative, _top_package, analyze_source, build_graph,
        find_cycles, package_edges,
    )

    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print()

    edges, counts = build_graph()
    actual_nonzero = {m: c for m, c in counts.items() if c > 0}
    cap_total = sum(FUNC_IMPORT_CAPS.values())
    act_total = sum(actual_nonzero.values())
    print("=" * 74)
    print("BASE FIGURES (re-derived with the guard's own analyzer)")
    print("=" * 74)
    print(f"  FUNC_IMPORT_CAPS entries : {len(FUNC_IMPORT_CAPS)}")
    print(f"  cap TOTAL                : {cap_total}")
    print(f"  ACTUAL total             : {act_total} "
          f"across {len(actual_nonzero)} modules")
    print(f"  SLACK (cap - actual)     : {cap_total - act_total}")
    print()

    # --- per-site enumeration (same rules as the analyzer, plus targets) ----
    def deferred_sites(path, module, is_pkg):
        tree = ast.parse(path.read_text())
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
                tgt = (_resolve_relative(module, node, is_pkg)
                       if node.level else node.module)
                self._rec([tgt], node.lineno)

        V().visit(tree)
        return out

    def module_path(module):
        rel = module.replace(".", "/")
        p = root / (rel + ".py")
        if p.exists():
            return p, False
        p = root / rel / "__init__.py"
        return (p, True) if p.exists() else (None, False)

    def module_cycles_with(e):
        """Cycles in the MODULE-level graph (find_cycles is graph-generic)."""
        return find_cycles(e)

    base_module_cycles = {frozenset(c) for c in module_cycles_with(edges)}

    def lock_green_with(extra_src, extra_dst):
        """Would a module-level edge src -> dst be safe to hoist?

        TWO tests, because the guard's rule alone is NOT sufficient.

        INSTRUMENT DEFECT FOUND AND FIXED BEFORE USE (recorded, not buried):
        the first version asked only the guard's package-cycle question and
        reported 136/177 sites hoistable. That is over-reporting by
        construction — ``package_edges`` DROPS intra-package edges (``if pd !=
        ps``), so an intra-package hoist such as ``psh.core.scope ->
        psh.core.exceptions`` can never produce a package cycle no matter what
        it does to the real import graph. A guard-green edge can still be an
        ImportError at runtime. The brief names this exact question under Pins
        ("each hoisted import's module still imports clean"), so the
        MODULE-level cycle test below is the necessary second condition, and a
        real ``import psh`` is the confirming third (Phase B, per hoist).
        """
        e = {m: set(d) for m, d in edges.items()}
        e.setdefault(extra_src, set()).add(extra_dst)
        # (1) the guard's own package-level rules
        cycles = [c for c in find_cycles(package_edges(e))
                  if c not in PACKAGE_CYCLE_ALLOWLIST]
        if cycles:
            return False, "package cycle: " + "; ".join(
                " <-> ".join(sorted(c)) for c in cycles)
        if extra_src.startswith("psh.utils") and \
                not extra_dst.startswith("psh.utils"):
            return False, "utils leaf rule"
        if extra_src.startswith("psh.core") and \
                not extra_dst.startswith("psh.core") and \
                _top_package(extra_dst) not in CORE_MODULE_IMPORT_ALLOWLIST:
            return False, "core near-leaf rule"
        # (2) runtime reality: no NEW module-level cycle
        new_cycles = {frozenset(c) for c in module_cycles_with(e)}
        introduced = new_cycles - base_module_cycles
        if introduced:
            return False, "MODULE-level cycle: " + "; ".join(
                " -> ".join(sorted(c)) for c in list(introduced)[:1])
        return True, "layering-legal AND no new module-level cycle"

    # source text, to spot the `# cycle-break:` marker near a site
    print("=" * 74)
    print("PER-SITE HOIST SIMULATION")
    print("=" * 74)
    hoistable, forced = [], []
    for module in sorted(actual_nonzero):
        p, is_pkg = module_path(module)
        if p is None:
            print(f"  !! cannot locate source for {module}")
            continue
        lines = p.read_text().splitlines()
        for tgt, lineno, fn in deferred_sites(p, module, is_pkg):
            ok, why = lock_green_with(module, tgt)
            marker = any("cycle-break" in ln for ln in
                         lines[max(0, lineno - 6):lineno])
            (hoistable if ok else forced).append(
                (module, tgt, lineno, fn, marker, why))

    print(f"  HOISTABLE sites   : {len(hoistable)}")
    print(f"  CYCLE-FORCED sites: {len(forced)}")
    print(f"  (sum = {len(hoistable) + len(forced)}; actual total = {act_total})")
    print()
    print("  --- HOISTABLE (module-level edge keeps the lock green) ---")
    for module, tgt, lineno, fn, marker, why in hoistable:
        print(f"    {module}:{lineno}  -> {tgt}   [{fn}]"
              f"{'  (has cycle-break comment!)' if marker else ''}")
    print()
    print("  --- CYCLE-FORCED (module-level edge turns the lock red) ---")
    for module, tgt, lineno, fn, marker, why in forced:
        print(f"    {module}:{lineno}  -> {tgt}   [{fn}]  {why[:60]}"
              f"{'  (cycle-break comment present)' if marker else ''}")
    print()

    print("=" * 74)
    print("PER-ENTRY TABLE (cap vs actual)")
    print("=" * 74)
    dead, slack_rows = [], []
    for module in sorted(FUNC_IMPORT_CAPS):
        cap = FUNC_IMPORT_CAPS[module]
        act = counts.get(module, 0)
        h = sum(1 for m, *_ in hoistable if m == module)
        tag = ""
        if act == 0:
            tag = "DEAD (delete entry)"
            dead.append(module)
        elif cap > act:
            tag = f"SLACK {cap - act}"
            slack_rows.append((module, cap, act))
        if h:
            tag += f"  hoistable:{h}"
        print(f"  {module:<55} cap={cap:<3} actual={act:<3} {tag}")
    print()
    print(f"  DEAD entries (actual 0): {len(dead)} -> {dead}")
    print(f"  SLACK entries          : {len(slack_rows)}, "
          f"total slack {sum(c - a for _, c, a in slack_rows)}")
    modules_no_entry = sorted(m for m in actual_nonzero
                              if m not in FUNC_IMPORT_CAPS)
    print(f"  modules with actual>0 and NO cap entry (would be red): "
          f"{modules_no_entry}")
    print()

    print("=" * 74)
    print("PROPOSED TARGET TRIPLE (ruling (d) input)")
    print("=" * 74)
    new_actual = act_total - len(hoistable)
    print(f"  actual : {act_total} - {len(hoistable)} hoisted = {new_actual}")
    print(f"  cap    : set every surviving entry to its post-hoist actual "
          f"=> {new_actual}")
    print(f"  slack  : {cap_total - act_total} -> 0")
    print(f"  entries: {len(FUNC_IMPORT_CAPS)} - {len(dead)} dead - "
          f"(entries whose actual falls to 0 by hoisting)")


if __name__ == "__main__":
    main()
