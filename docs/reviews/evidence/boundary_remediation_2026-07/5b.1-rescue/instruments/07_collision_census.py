#!/usr/bin/env python3
"""Slot 5B.1 instrument 07 — collision census disambiguated PER DEFINITION.

The checkpoint-r q5 census counted NAME references per file. That cannot
tell a reference to the PROTOCOL `ExpansionContext` from a reference to
the CONCRETE lexer class of the same name (brief point 4 CAUTION). This
instrument resolves each reference to WHICH definition it means, using
import provenance from the AST:

  - collect every `from X import Name` / `import X` binding per module
  - a bare `Name` reference resolves to whatever that module IMPORTED
  - a reference in the DEFINING module resolves to the local definition
  - string annotations are parsed and resolved the same way

Output per colliding name: definition sites, and per referencing file
which definition it binds + the reference kind.

Portable: ROOT from argv[1] (default git toplevel).
"""
import ast
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                    subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                   capture_output=True, text=True
                                   ).stdout.strip()).resolve()

NAMES = ["ExpansionContext", "LocaleContext"]


def module_dotted(path):
    rel = path.relative_to(ROOT)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def resolve_relative(cur_mod, level, mod):
    """Resolve `from ..x import y` to an absolute dotted module."""
    if level == 0:
        return mod or ""
    base = cur_mod.split(".")
    # for a package __init__, the module IS the package
    pkg = base[:len(base) - (level - 1)] if level > 1 else base
    # `from . import x` inside pkg.mod -> pkg
    parent = base[:-1] if level >= 1 else base
    for _ in range(level - 1):
        parent = parent[:-1]
    return ".".join(parent + ([mod] if mod else []))


# --- 1. Find every DEFINITION of each name (any class, not just Protocol) ---
definitions = {n: [] for n in NAMES}
all_files = sorted((ROOT / "psh").rglob("*.py"))
for path in all_files:
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        continue
    modname = module_dotted(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in NAMES:
            bases = [ast.unparse(b) for b in node.bases]
            kind = "PROTOCOL" if any("Protocol" in b for b in bases) else "CONCRETE"
            definitions[node.name].append(
                (modname, str(path.relative_to(ROOT)), node.lineno, kind, bases))

print(f"ROOT={ROOT}")
print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()}")
print()
print("=" * 74)
print("1. DEFINITIONS (all class defs, protocol AND concrete)")
print("=" * 74)
for n in NAMES:
    print(f"\n{n}: {len(definitions[n])} definition(s)")
    for modname, rel, lineno, kind, bases in definitions[n]:
        print(f"   {kind:8s} {rel}:{lineno}   module={modname}  bases={bases}")

# --- 2. Per-file import provenance + reference sites ---
print()
print("=" * 74)
print("2. REFERENCE SITES, RESOLVED PER DEFINITION")
print("=" * 74)

for path in all_files:
    src = path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    modname = module_dotted(path)
    rel = str(path.relative_to(ROOT))
    lines = src.splitlines()

    # bindings: name -> source module
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            src_mod = resolve_relative(modname, node.level or 0, node.module)
            for a in node.names:
                if a.name in NAMES:
                    bindings[a.asname or a.name] = src_mod
        elif isinstance(node, ast.Import):
            pass

    # references
    refs = []

    def note(name, lineno, kind):
        refs.append((name, lineno, kind))

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in NAMES:
            note(node.id, node.lineno, "NAME")
        elif isinstance(node, ast.Attribute) and node.attr in NAMES:
            note(node.attr, node.lineno, "ATTR")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for n in NAMES:
                if n in node.value:
                    note(n, node.lineno, "STRING-ANN")

    if not refs and not bindings:
        continue

    interesting = [r for r in refs]
    if not interesting:
        continue

    print(f"\n--- {rel}  (module {modname})")
    if bindings:
        for k, v in sorted(bindings.items()):
            print(f"    IMPORTS: {k}  <-  {v}")
    else:
        print("    IMPORTS: (none of the colliding names)")

    seen = set()
    for name, lineno, kind in sorted(set(interesting)):
        if (name, lineno) in seen:
            continue
        seen.add((name, lineno))
        # resolve
        local_def = [d for d in definitions[name] if d[0] == modname]
        if name in bindings:
            target = bindings[name]
            resolved = f"IMPORTED from {target}"
            matches = [d for d in definitions[name] if d[0] == target]
            if matches:
                resolved += f"  => {matches[0][3]} @ {matches[0][1]}:{matches[0][2]}"
        elif local_def:
            resolved = (f"LOCAL definition => {local_def[0][3]} @ "
                        f"{local_def[0][1]}:{local_def[0][2]}")
        else:
            resolved = "UNRESOLVED (no import, no local def — prose/docstring?)"
        srcline = lines[lineno - 1].strip()[:88] if lineno <= len(lines) else ""
        print(f"    L{lineno:<5d} {kind:11s} {name:17s} {resolved}")
        print(f"             SRC: {srcline}")

print()
print("=" * 74)
print("3. SUMMARY — importers per definition")
print("=" * 74)
for n in NAMES:
    print(f"\n{n}:")
    for modname, rel, lineno, kind, _ in definitions[n]:
        importers = []
        for path in all_files:
            try:
                t = ast.parse(path.read_text())
            except SyntaxError:
                continue
            m = module_dotted(path)
            if m == modname:
                continue
            for node in ast.walk(t):
                if isinstance(node, ast.ImportFrom):
                    sm = resolve_relative(m, node.level or 0, node.module)
                    if sm == modname and any(a.name == n for a in node.names):
                        importers.append(str(path.relative_to(ROOT)))
        print(f"   {kind:8s} {rel}:{lineno}")
        print(f"     importers ({len(set(importers))}): {sorted(set(importers)) or '(NONE)'}")
