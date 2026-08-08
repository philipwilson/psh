#!/usr/bin/env python3
"""Slot 5B.1 instrument 11 — rename-target availability + recurrence-guard proof.

(1) NAME AVAILABILITY: for each proposed protocol rename target, prove the
    identifier is unused anywhere in psh/ + tests/ (a rename into an
    occupied name would just move the collision).

(2) RENAME TOUCH-SET: every line that would have to change per candidate
    side, so "which side is cheaper" is a measured number.

(3) RECURRENCE-GUARD PROOF: the proposed guard is
      "no class name defined in psh/ may be defined more than once
       when either definition is a Protocol"
    Run it against the CURRENT tree: it MUST be RED (both collisions are
    live), which proves the guard can fail. A guard that is green on the
    tree it was written for is not proven to work.

Portable: ROOT from argv[1] (default git toplevel).
"""
import ast
import collections
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                    subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                   capture_output=True, text=True
                                   ).stdout.strip()).resolve()

PROPOSED = ["ExpansionRuntime", "LocaleAccess", "ExpansionServices",
            "LocaleServices", "ExpansionAccess", "LocaleRuntime"]

print(f"ROOT={ROOT}")
print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()}")
print()

scan = []
for d in ("psh", "tests", "docs"):
    p = ROOT / d
    if p.exists():
        scan.extend(sorted(x for x in p.rglob("*")
                           if x.is_file() and x.suffix in (".py", ".md")
                           and "__pycache__" not in x.parts))

print("=" * 74)
print("(1) NAME AVAILABILITY for proposed rename targets")
print("=" * 74)
for name in PROPOSED:
    hits = []
    for path in scan:
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if name in line:
                hits.append(f"{path.relative_to(ROOT)}:{i}")
    status = "FREE" if not hits else f"OCCUPIED ({len(hits)})"
    print(f"  {name:22s} {status}")
    for h in hits[:5]:
        print(f"      {h}")

print()
print("=" * 74)
print("(2) RENAME TOUCH-SET per side (measured lines that must change)")
print("=" * 74)
SIDES = {
    "ExpansionContext PROTOCOL (psh/protocols/__init__.py:119)":
        ("ExpansionContext", "psh/protocols/__init__.py"),
    "ExpansionContext CONCRETE (psh/lexer/expansion_parser.py:387)":
        ("ExpansionContext", "psh/lexer/expansion_parser.py"),
    "LocaleContext PROTOCOL (psh/protocols/__init__.py:216)":
        ("LocaleContext", "psh/protocols/__init__.py"),
    "LocaleContext CONCRETE (psh/core/locale_service.py:90)":
        ("LocaleContext", "psh/core/locale_service.py"),
}
# Which files reference the name, split by which definition they resolve to.
# (Resolution came from instrument 07; here we count the raw touch surface.)
for label, (name, defining) in SIDES.items():
    print(f"\n  {label}")
    total = 0
    for path in scan:
        rel = str(path.relative_to(ROOT))
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        n = sum(1 for line in text.splitlines() if name in line)
        if n:
            print(f"      {rel}: {n} line(s)")
            total += n
    print(f"      RAW total lines mentioning '{name}': {total}")

print()
print("=" * 74)
print("(3) RECURRENCE-GUARD PROOF — must be RED on the current tree")
print("=" * 74)


def class_defs(root):
    """{name: [(rel, lineno, is_protocol)]} for every class defined in psh/."""
    out = collections.defaultdict(list)
    for path in sorted((root / "psh").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        rel = str(path.relative_to(root))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases]
                is_proto = any("Protocol" in b for b in bases)
                out[node.name].append((rel, node.lineno, is_proto))
    return out


defs = class_defs(ROOT)
offenders = {}
for name, sites in defs.items():
    if len(sites) < 2:
        continue
    if any(is_proto for _, _, is_proto in sites):
        offenders[name] = sites

print(f"  classes defined in psh/: {len(defs)}")
print(f"  names with >1 definition: {sum(1 for s in defs.values() if len(s) > 1)}")
print(f"  ... of which at least one is a Protocol (GUARD OFFENDERS): {len(offenders)}")
for name, sites in sorted(offenders.items()):
    print(f"\n    OFFENDER: {name}")
    for rel, lineno, is_proto in sites:
        print(f"      {'PROTOCOL' if is_proto else 'CONCRETE'}  {rel}:{lineno}")

print()
if offenders:
    print("  => GUARD IS RED ON BASE. It can fail; it is a real guard.")
    print("     After the ruled renames it goes green, and any future")
    print("     re-collision turns it red again.")
else:
    print("  => GUARD IS GREEN ON BASE — it would prove nothing. Redesign.")

print()
print("  CONTROL: all duplicate class names (protocol or not), for context —")
for name, sites in sorted(defs.items()):
    if len(sites) > 1:
        kinds = ",".join("P" if p else "C" for _, _, p in sites)
        print(f"    {name:34s} x{len(sites)} [{kinds}]  "
              f"{[f'{r}:{l}' for r, l, _ in sites]}")
