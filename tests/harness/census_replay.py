"""Replayable bearing-set census at a given SHA (default: base e52957d4).

Usage:  git archive <SHA> tests | tar -x -C <dir>
        python tests/harness/census_replay.py <dir>/tests
"""
import ast
import os
import sys


def imports_shell_oracle(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and "shell_oracle" in n.module:
            return True
        if isinstance(n, ast.Import) and any("shell_oracle" in a.name for a in n.names):
            return True
    return False

SPAWN = {"run", "Popen", "call", "check_output", "check_call"}
OS_SPAWN = {"system", "popen"}

def spawn_sites(tree):
    n_sites = 0
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name)):
            b, a = n.func.value.id, n.func.attr
            if (b == "subprocess" and a in SPAWN) or (b == "os" and a in OS_SPAWN):
                n_sites += 1
    return n_sites

root = sys.argv[1] if len(sys.argv) > 1 else "tests"
imports_conf = set(); guard_scope = set(); spawners = {}
for dp, dn, fn in os.walk(root):
    dn[:] = [d for d in dn if d != "__pycache__"]
    for f in sorted(fn):
        if not f.endswith(".py"):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        try:
            tree = ast.parse(open(p, encoding="utf-8").read())
        except SyntaxError:
            continue
        in_conf = rel.startswith("conformance/")
        in_harness = rel.startswith("harness/")
        imp = imports_shell_oracle(tree)
        if in_conf or imp:
            imports_conf.add(rel)
        if in_conf or imp or in_harness:
            guard_scope.add(rel)
            s = spawn_sites(tree)
            if s:
                spawners[rel] = s
print(f"imports_shell_oracle UNION conformance      : {len(imports_conf)}")
print(f"guard scope (that UNION harness/)           : {len(guard_scope)}")
sp_in_scope = {k: v for k, v in spawners.items() if k in guard_scope}
print(f"  ...of which SPAWN directly (modules)      : {len(sp_in_scope)}")
print(f"  ...total direct spawn SITES               : {sum(sp_in_scope.values())}")
print(f"  ...spawners excluding harness/shell_oracle.py: "
      f"{len([k for k in sp_in_scope if k != 'harness/shell_oracle.py'])}")
print(f"  ...non-spawners in the imports∪conformance set: "
      f"{len(imports_conf) - len([k for k in sp_in_scope if k in imports_conf])}")
