#!/usr/bin/env python3
"""Instrument 03 (slot 5B.2) — which MEMBERS the six `state.locale` readers use.

The `LocaleAccess` witness adoption only lands if every reader's usage fits the
protocol's declared surface. A reader that calls a LocaleService method
`LocaleAccess` does not declare is a FENCE (widening a protocol is a ruling, not
a default), so this is measured per site, not assumed from the docstring.

Method: for every `<...>.state.locale` access (the binding census shape), walk
UP to whatever is done with it — a method call `.locale.foo(...)`, an attribute
read `.locale.bar`, or a bare pass/assign of the service itself.

Usage:  python 03_locale_member_usage.py <ROOT>
"""
import ast
import collections
import pathlib
import subprocess
import sys


def base_chain(node):
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


def protocol_members(root):
    """The members LocaleAccess declares (read from the protocol source)."""
    tree = ast.parse((root / "psh/protocols/__init__.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "LocaleAccess":
            return {n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return set()


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    declared = protocol_members(root)
    print(f"LocaleAccess declares: {sorted(declared)}")
    print()

    per_file = collections.defaultdict(list)
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
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[id(child)] = node
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Attribute) and node.attr == "locale"):
                continue
            chain = base_chain(node)
            if chain is None:
                continue
            parts = chain.split(".")
            if len(parts) < 2 or parts[-2] != "state":
                continue
            p = parents.get(id(node))
            if isinstance(p, ast.Attribute):
                member = p.attr
                gp = parents.get(id(p))
                kind = "CALL" if isinstance(gp, ast.Call) else "ATTR"
            else:
                member = "<the service itself>"
                kind = "BARE-" + type(p).__name__
            per_file[rel].append((node.lineno, member, kind,
                                  lines[node.lineno - 1].strip()[:84]))

    outside = []
    for rel in sorted(per_file):
        print("=" * 74)
        print(f"{rel}   ({len(per_file[rel])} site(s))")
        print("=" * 74)
        for ln, member, kind, text in sorted(per_file[rel]):
            ok = (member in declared) if member != "<the service itself>" \
                else None
            flag = ("in-surface" if ok else
                    ("BARE" if ok is None else "*** OUTSIDE SURFACE ***"))
            print(f"  L{ln:<6} .{member:<24} {kind:<12} {flag}")
            print(f"         {text}")
            if ok is False:
                outside.append((rel, ln, member))
        print()

    print("=" * 74)
    print("VERDICT")
    print("=" * 74)
    used = {m for sites in per_file.values() for _, m, _, _ in sites
            if m != "<the service itself>"}
    print(f"  members actually used by the six readers: {sorted(used)}")
    print(f"  declared but UNUSED by them             : "
          f"{sorted(declared - used)}")
    print(f"  used but NOT declared (fence if any)    : "
          f"{sorted(used - declared)}")
    if outside:
        print("  *** OUTSIDE-SURFACE SITES (each a fence row) ***")
        for rel, ln, member in outside:
            print(f"      {rel}:{ln}  .{member}")
    else:
        print("  => every reader's usage fits LocaleAccess as declared.")


if __name__ == "__main__":
    main()
