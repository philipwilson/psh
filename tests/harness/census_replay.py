"""Replayable bearing-set census at a given SHA (default: base e52957d4).

Usage:  git archive <SHA> tests | tar -x -C <dir>
        python tests/harness/census_replay.py <dir>/tests

The predicates are IMPORTED FROM THE GUARD
(``tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py``) rather than
re-implemented here.  Round-4 verification caught this file carrying WEAKER
private copies (no ImportFrom-alias branch, no getoutput/getstatusoutput) while
the census billed it as "the guard's OWN predicates" — a replay tool that drifts
from the thing it replays proves nothing.  Importing is what keeps the claim true.
"""
import ast
import os
import sys

_GUARD_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "unit", "tooling")
if _GUARD_DIR not in sys.path:
    sys.path.insert(0, _GUARD_DIR)

from test_no_direct_spawn_in_oracle_modules import (  # noqa: E402
    _imports_shell_oracle as imports_shell_oracle,
)
from test_no_direct_spawn_in_oracle_modules import (
    find_direct_spawns,
    find_non_subprocess_spawns,
)


def spawn_sites(src):
    """Number of DIRECT (subprocess/os) spawn sites, via the guard's detector.

    Takes SOURCE TEXT, not a parsed tree: the detectors report real line
    numbers, and round-tripping through ``ast.unparse`` would renumber every
    site (the census records e.g. ``:78``/``:92`` and must keep matching).
    """
    return len(find_direct_spawns(src))

def census(root="tests"):
    """Print the bearing-set counts for the tree rooted at *root*."""
    imports_conf = set()
    guard_scope = set()
    spawners = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in sorted(fn):
            if not f.endswith(".py"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            src = open(p, encoding="utf-8").read()
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            in_conf = rel.startswith("conformance/")
            in_harness = rel.startswith("harness/")
            imp = imports_shell_oracle(tree)
            if in_conf or imp:
                imports_conf.add(rel)
            if in_conf or imp or in_harness:
                guard_scope.add(rel)
                n = spawn_sites(src)
                if n:
                    spawners[rel] = n
    sp = {k: v for k, v in spawners.items() if k in guard_scope}
    print(f"imports_shell_oracle UNION conformance      : {len(imports_conf)}")
    print(f"guard scope (that UNION harness/)           : {len(guard_scope)}")
    print(f"  ...of which SPAWN directly (modules)      : {len(sp)}")
    print(f"  ...total direct spawn SITES               : {sum(sp.values())}")
    print(f"  ...spawners excluding harness/shell_oracle.py: "
          f"{len([k for k in sp if k != 'harness/shell_oracle.py'])}")
    print(f"  ...non-spawners in the imports∪conformance set: "
          f"{len(imports_conf) - len([k for k in sp if k in imports_conf])}")


# --- non-subprocess (PTY/fork/exec) family: guard's detector ---


def pty_audit(root="tests"):
    """Print every bearing-set module creating a process outside subprocess."""
    found = 0
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in sorted(fn):
            if not f.endswith(".py"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            src = open(p, encoding="utf-8").read()
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            bearing = (rel.startswith("conformance/") or rel.startswith("harness/")
                       or imports_shell_oracle(tree))
            if not bearing:
                continue
            for lineno, kind in find_non_subprocess_spawns(src):
                print(f"{rel}:{lineno}: {kind}")
                found += 1
    print(f"TOTAL non-subprocess spawn sites in the BEARING SET: {found}")


if __name__ == "__main__":
    _root = sys.argv[1] if len(sys.argv) > 1 else "tests"
    census(_root)
    print()
    pty_audit(_root)
