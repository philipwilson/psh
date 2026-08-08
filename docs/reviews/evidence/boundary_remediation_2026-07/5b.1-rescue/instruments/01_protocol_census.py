#!/usr/bin/env python3
"""Slot 5B.1 instrument 01 — tree-wide Protocol DEFINITION census (AST).

Different method from the checkpoint-r q5 census (which counted NAME
references per file, grep-shaped). This one parses every psh/ module with
`ast` and reports, per class that lists `Protocol` among its bases:
  file:line, class name, member names (methods + annotated attributes),
  and which members are `Any`-typed / name `Shell`/`ShellState`.

D-3.5 joint lesson: verify with a DIFFERENT method than the one that
produced the number. q5 used grep-over-names; this uses AST-over-defs.

Usage: python3 tmp/w5b1-instruments/01_protocol_census.py [ROOT]
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()


def _ann_text(node):
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return "<unparseable>"


def protocol_defs(path, rel):
    src = path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"  !! {rel}: SyntaxError {e}")
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [_ann_text(b) for b in node.bases]
        if not any(b and "Protocol" in b for b in bases):
            continue
        members = []
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                ann = _ann_text(child.returns)
                members.append(("method", child.name, ann, child.lineno))
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                ann = _ann_text(child.annotation)
                members.append(("attr", child.target.id, ann, child.lineno))
        out.append((rel, node.lineno, node.name, bases, members))
    return out


def main():
    found = []
    for path in sorted((ROOT / "psh").rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        found.extend(protocol_defs(path, rel))

    print(f"ROOT={ROOT}")
    print(f"PROTOCOL DEFINITIONS FOUND: {len(found)}")
    print("=" * 72)
    by_name = {}
    for rel, lineno, name, bases, members in found:
        by_name.setdefault(name, []).append(f"{rel}:{lineno}")
        print(f"\n{name}  @ {rel}:{lineno}")
        print(f"  bases: {bases}")
        for kind, mname, ann, mline in members:
            flags = []
            if ann and "Any" in ann:
                flags.append("ANY")
            if ann and "ShellState" in ann:
                flags.append("SHELLSTATE")
            elif ann and "Shell" in ann:
                flags.append("SHELL")
            flag = ("  <<< " + ",".join(flags)) if flags else ""
            print(f"    {kind:6s} {mname:34s} -> {ann}{flag}")

    print("\n" + "=" * 72)
    print("NAME COLLISIONS AMONG PROTOCOL DEFINITIONS:")
    for name, locs in sorted(by_name.items()):
        if len(locs) > 1:
            print(f"  {name}: {locs}")
    print("\nDISTINCT PROTOCOL NAMES:", len(by_name))
    for name, locs in sorted(by_name.items()):
        print(f"  {name:32s} {locs}")


if __name__ == "__main__":
    main()
