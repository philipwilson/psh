"""Per-module / per-spawn-site classifier for the oracle migration census.

AST walk that resolves each module's bash-path variable and labels every
subprocess argv[0] by WHAT it launches (bash / psh / python / var-argv), so
the census can separate BASH-DIFFERENTIAL modules from psh-only ones.
Cited by tests/harness/oracle_migration_census.md.
"""
import ast
import os
import re
import sys

SPAWN = {'run', 'Popen', 'call', 'check_output', 'check_call'}

def bash_var_names(tree):
    """Names bound to a bash oracle path (resolve_bash().path / _ORACLE.path)."""
    names=set(); oracle_objs=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Assign):
            txt=ast.unparse(n.value)
            if re.search(r'resolve_bash\(\)', txt):
                for t in n.targets:
                    if isinstance(t,ast.Name):
                        names.add(t.id)
                        if txt.strip().endswith('resolve_bash()'):
                            oracle_objs.add(t.id)
    # second pass: X.path where X in oracle_objs
    for n in ast.walk(tree):
        if isinstance(n,ast.Assign):
            txt=ast.unparse(n.value)
            for o in list(oracle_objs):
                if re.search(rf'\b{o}\.path\b', txt):
                    for t in n.targets:
                        if isinstance(t,ast.Name): names.add(t.id)
    return names

def spawn_kind(argv_src, bash_vars):
    s=argv_src
    if 'resolve_bash()' in s: return 'bash'
    for bv in bash_vars:
        if re.search(rf'\b{bv}\b', s): return 'bash'
    if re.search(r"sys\.executable.*'?-m'?.*psh|'-m', 'psh'|\bPSH\b|-m.*psh", s): return 'psh'
    if 'sys.executable' in s: return 'python'
    # helper-var argv like argv/shell_argv/exe: ambiguous - mark 'var'
    if re.fullmatch(r'[a-zA-Z_][\w]*(\s*\+\s*\[.*\])?', s.strip()): return 'var'
    return 'other'

def analyze(path):
    src=open(path,encoding='utf-8').read()
    try: tree=ast.parse(src)
    except SyntaxError: return None
    bvars=bash_var_names(tree)
    spawns=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.Call):
            is_spawn=False
            if isinstance(n.func,ast.Attribute) and n.func.attr in SPAWN: is_spawn=True
            if isinstance(n.func,ast.Attribute) and n.func.attr in ('system','popen') and isinstance(getattr(n.func,'value',None),ast.Name) and n.func.value.id=='os': is_spawn=True
            if is_spawn:
                a0=ast.unparse(n.args[0]) if n.args else 'NONE'
                spawns.append((n.lineno, spawn_kind(a0,bvars), a0))
    return dict(src=src, bvars=bvars, spawns=spawns,
        imp_oracle='shell_oracle' in src,
        imp_runner=bool(re.search(r'\brun_shell_case\b',src)),
        uses_fw=bool(re.search(r'ConformanceTest|assert_identical_behavior|assert_documented_difference|assert_psh_extension|check_behavior|compare_behavior',src)))

def collect(root):
    """{rel: analysis} for every bearing module under *root*."""
    mods = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d != '__pycache__']
        for f in sorted(fn):
            if not f.endswith('.py'):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            src = open(p, encoding='utf-8').read()
            if not (rel.startswith('conformance/') or 'shell_oracle' in src):
                continue
            a = analyze(p)
            if a:
                mods[rel] = a
    return mods


if __name__ == "__main__":
    _root = sys.argv[1] if len(sys.argv) > 1 else "tests"
    _mods = collect(_root)
    for _rel, _a in sorted(_mods.items()):
        if not _a['spawns']:
            continue
        _kinds = ', '.join(sorted({k for _, k, _ in _a['spawns']}))
        print(f"{_rel}: {len(_a['spawns'])} site(s) [{_kinds}]")
    print(f"TOTAL bearing modules with a direct spawn: "
          f"{len([m for m in _mods.values() if m['spawns']])}")
