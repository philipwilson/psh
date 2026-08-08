#!/usr/bin/env python3
"""Instrument 02 (slot 5B.2) — `state.locale` reader census by a SECOND method,
plus the `core/scope.py` adoption-route layering probe.

Part 1 REPRODUCES 5B.1 instrument 19 (committed, READ-ONLY; logic transcribed
here, the only edit being that ROOT comes from argv). Part 2 re-derives the same
census by a DIFFERENT method (D-3.5 joint lesson: an instrument that mirrors the
claim's method cannot find the claim's error). 19 filters to chains whose
second-to-last element is literally ``state``; part 2 collects EVERY ``.locale``
attribute access in ``psh/`` with no base filter at all, so a reader reached
through a differently-named binding (``self._state.locale``, ``st.locale``, a
held ``LocaleService`` local) shows up as a DIFFERENCE rather than as silence.
The prose was already undercounted once (three -> six); a second undercount
would misdirect the migration set again.

Part 3 probes the ADOPTION ROUTE for the layering-critical CORE reader using the
import-layering lock's OWN analyzer (`analyze_source`) rather than by reading the
rules: it asks the guard what it classifies a TYPE_CHECKING-only protocol import
in a core module as. `CORE_MODULE_IMPORT_ALLOWLIST` does NOT contain
`psh.protocols`, so whether an annotation import needs an allowlist edit (a
FENCE) is a measurement, not an argument.

Usage:  python 02_locale_census_and_layering.py <ROOT>
"""
import ast
import pathlib
import subprocess
import sys


def head(root):
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                          capture_output=True, text=True).stdout.strip()


def base_chain(node):
    """Render an attribute chain like `self.state.locale` as text, or None."""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    elif isinstance(cur, ast.Call):
        parts.append("<call>")
    else:
        return None
    return ".".join(reversed(parts))


def all_locale_accesses(root):
    """EVERY `.locale` attribute access in psh/, unfiltered (method 2)."""
    out = []
    for path in sorted((root / "psh").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root))
        src = path.read_text()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "locale":
                out.append((rel, node.lineno, base_chain(node) or "<complex>",
                            lines[node.lineno - 1].strip()[:88]))
    return out


def method19_filter(sites):
    """5B.1 instrument 19's filter: chain[-2] must be exactly `state`."""
    keep = []
    for rel, lineno, chain, text in sites:
        parts = chain.split(".")
        if len(parts) >= 2 and parts[-2] == "state":
            keep.append((rel, lineno, chain, text))
    return keep


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    print(f"ROOT={root}")
    print(f"HEAD={head(root)}")
    print()

    # --- Part 1/2: the two methods, and their DIFFERENCE -------------------
    every = all_locale_accesses(root)
    m19 = method19_filter(every)

    print("=" * 74)
    print("PART 1 — method 19 (chain[-2] == 'state'), the BINDING census")
    print("=" * 74)
    files19 = sorted({r for r, _, _, _ in m19})
    for f in files19:
        n = sum(1 for r, _, _, _ in m19 if r == f)
        print(f"  {f}  ({n} site{'s' if n != 1 else ''})")
    print(f"  TOTAL: {len(files19)} files, {len(m19)} sites")
    print()

    print("=" * 74)
    print("PART 2 — method 2: EVERY `.locale` access, no base filter")
    print("=" * 74)
    files_all = sorted({r for r, _, _, _ in every})
    for f in files_all:
        n = sum(1 for r, _, _, _ in every if r == f)
        print(f"  {f}  ({n} site{'s' if n != 1 else ''})")
    print(f"  TOTAL: {len(files_all)} files, {len(every)} sites")
    print()

    print("=" * 74)
    print("DIFFERENCE — accesses method 19 does NOT count (its blind spot)")
    print("=" * 74)
    seen19 = {(r, ln) for r, ln, _, _ in m19}
    diff = [s for s in every if (s[0], s[1]) not in seen19]
    if not diff:
        print("  (none — the two methods agree exactly)")
    for rel, lineno, chain, text in diff:
        print(f"  {rel}:{lineno}   chain={chain}")
        print(f"      {text}")
    print()
    print(f"  files ONLY in method 2: "
          f"{sorted(set(files_all) - set(files19))}")
    print()

    # --- Part 3: layering probe with the LOCK'S OWN analyzer ---------------
    print("=" * 74)
    print("PART 3 — adoption-route layering probe (the guard's own analyzer)")
    print("=" * 74)
    sys.path.insert(0, str(root))
    from tests.unit.tooling.test_import_layering import (  # noqa: E402
        CORE_MODULE_IMPORT_ALLOWLIST, _top_package, analyze_source,
    )

    print(f"  CORE_MODULE_IMPORT_ALLOWLIST = "
          f"{sorted(CORE_MODULE_IMPORT_ALLOWLIST)}")
    print(f"  'psh.protocols' in allowlist? "
          f"{'psh.protocols' in CORE_MODULE_IMPORT_ALLOWLIST}")
    print()

    variants = {
        "A: RUNTIME module-level import (illegal shape)":
            "from ..protocols import LocaleAccess\n"
            "def f(x: LocaleAccess) -> None: ...\n",
        "B: TYPE_CHECKING-only import (candidate route)":
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from ..protocols import LocaleAccess\n"
            "def f(x: 'LocaleAccess') -> None: ...\n",
        "C: function-body deferred import (costs a cap)":
            "def f():\n"
            "    from ..protocols import LocaleAccess\n"
            "    return LocaleAccess\n",
    }
    for label, src in variants.items():
        runtime, fcount = analyze_source(src, "psh.core.scope", False)
        bad = sorted(d for d in runtime
                     if not d.startswith("psh.core")
                     and _top_package(d) not in CORE_MODULE_IMPORT_ALLOWLIST)
        print(f"  {label}")
        print(f"      runtime module-level psh edges : {sorted(runtime)}")
        print(f"      deferred (func-body) count     : {fcount}")
        print(f"      near-leaf rule OFFENDERS       : {bad}")
        print(f"      => test_core_is_near_leaf would "
              f"{'FAIL' if bad else 'PASS'}; "
              f"FUNC_IMPORT_CAPS impact: {fcount}")
        print()

    # What does core/scope.py import today, and how?
    scope = root / "psh/core/scope.py"
    runtime, fcount = analyze_source(scope.read_text(), "psh.core.scope", False)
    print(f"  LIVE psh/core/scope.py: runtime psh edges={sorted(runtime)}, "
          f"deferred count={fcount}")
    tree = ast.parse(scope.read_text())
    tc = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and (
                (isinstance(node.test, ast.Name)
                 and node.test.id == "TYPE_CHECKING")
                or (isinstance(node.test, ast.Attribute)
                    and node.test.attr == "TYPE_CHECKING")):
            for s in node.body:
                if isinstance(s, (ast.Import, ast.ImportFrom)):
                    tc.append((s.lineno, ast.unparse(s)))
    print("  existing TYPE_CHECKING block in core/scope.py:")
    for ln, txt in tc:
        print(f"      L{ln}: {txt}")
    if not tc:
        print("      (none — the route would ADD the block)")


if __name__ == "__main__":
    main()
