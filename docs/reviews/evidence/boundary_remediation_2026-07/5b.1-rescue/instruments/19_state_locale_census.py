#!/usr/bin/env python3
"""Slot 5B.1 instrument 19 — the TRUE `state.locale` reader census (R4 nit 7).

`psh/protocols/__init__.py` claims "the three ``state.locale`` readers". The
verifier counted SIX production files. R4 requires me to re-derive it MYSELF
rather than adopt either number — 5B.2's migration set starts from this census,
so a wrong count here misdirects the next slot.

Method: AST, not grep. Finds every attribute access whose final `.locale` is
reached through a `state`-ish base, so `self.state.locale`, `shell.state.locale`
and a bare `state.locale` all count, and a variable merely NAMED locale does
not. Reports the FILE set (what the prose quantifies over) and the site count
separately — those are different numbers and conflating them is how "three"
survived.

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

print(f"ROOT={ROOT}")
print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()}")
print()


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


sites = []
for path in sorted((ROOT / "psh").rglob("*.py")):
    if "__pycache__" in path.parts:
        continue
    rel = str(path.relative_to(ROOT))
    src = path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    lines = src.splitlines()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and node.attr == "locale"):
            continue
        chain = base_chain(node)
        if chain is None:
            continue
        # the access must come THROUGH a state-ish base, not be a bare name
        parent_parts = chain.split(".")
        if len(parent_parts) < 2:
            continue
        if parent_parts[-2] != "state":
            continue
        sites.append((rel, node.lineno, chain,
                      lines[node.lineno - 1].strip()[:88]))

print("=" * 74)
print("SITES: every `<...>.state.locale` access in psh/")
print("=" * 74)
for rel, lineno, chain, text in sites:
    print(f"  {rel}:{lineno}   {chain}")
    print(f"      {text}")

files = sorted({rel for rel, _, _, _ in sites})
print()
print("=" * 74)
print("SUMMARY")
print("=" * 74)
print(f"  total ACCESS SITES : {len(sites)}")
print(f"  distinct FILES     : {len(files)}")
for f in files:
    n = sum(1 for r, _, _, _ in sites if r == f)
    print(f"    {f}  ({n} site{'s' if n != 1 else ''})")

print()
print("  The protocol docstring quantifies over FILES ('readers'), so the")
print(f"  prose number must be {len(files)}, not the site count {len(sites)}.")
print()
print("  Files named in the CURRENT prose (expansion/glob.py,")
print("  expansion/parameter_expansion.py, executor/enhanced_test_evaluator.py):")
claimed = {"psh/expansion/glob.py",
           "psh/expansion/parameter_expansion.py",
           "psh/executor/enhanced_test_evaluator.py"}
for f in sorted(claimed):
    print(f"    {'PRESENT' if f in files else 'ABSENT '}  {f}")
print()
print("  Files the prose OMITS:")
for f in files:
    if f not in claimed:
        print(f"    MISSING FROM PROSE  {f}")
