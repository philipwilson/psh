#!/usr/bin/env python3
"""A7 — R1 item 5: sweep the WHOLE [tool.mypy] override set for bare-vs-star
asymmetries (the TESTINF-1 shape).

A "bare" override entry names a module that is actually a PACKAGE (a directory
with __init__.py). mypy's documented resolution makes such an entry cover ONLY
the package __init__, never its submodules — so a package covered bare for one
flag and starred for another has an asymmetric hole that opens the moment a
submodule is added. Reads ROOT from argv[1].
"""
import os
import sys
import tomllib

ROOT = os.path.abspath(sys.argv[1])
with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
    cfg = tomllib.load(f)

FLAGS = ["check_untyped_defs", "disallow_untyped_defs",
         "disallow_incomplete_defs"]

def is_package(dotted):
    if not dotted.startswith("psh"):
        return False
    p = os.path.join(ROOT, *dotted.split("."))
    return os.path.isdir(p) and os.path.isfile(os.path.join(p, "__init__.py"))

# pattern -> set of flags it sets, and whether starred
entries = {}
for section in cfg["tool"]["mypy"].get("overrides", []):
    mods = section["module"]
    mods = [mods] if isinstance(mods, str) else mods
    for pat in mods:
        rec = entries.setdefault(pat, set())
        for fl in FLAGS:
            if fl in section:
                rec.add(fl)

bare_packages = []
for pat, flags in sorted(entries.items()):
    if pat.endswith(".*"):
        continue
    if is_package(pat):
        starred = pat + ".*"
        bare_packages.append((pat, sorted(flags),
                              sorted(entries.get(starred, set()))))

print(f"override patterns: {len(entries)}")
print(f"BARE patterns naming a real PACKAGE: {len(bare_packages)}\n")
print(f"{'PACKAGE':28s} {'flags set BARE':46s} flags set STARRED")
print("-" * 110)
for pat, bare_flags, star_flags in bare_packages:
    asym = set(bare_flags) - set(star_flags)
    mark = "  <== ASYMMETRIC" if asym else ""
    print(f"{pat:28s} {','.join(bare_flags):46s} "
          f"{','.join(star_flags) or '(none)'}{mark}")

print()
# Every psh package, and whether ANY starred entry covers it for each flag.
print("Per-package coverage of the DISALLOW flags for a hypothetical submodule:")
sys.path.insert(0, os.path.join(ROOT, "tests/unit/tooling"))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "twin", os.path.join(ROOT, "tests/unit/tooling/test_mypy_untyped_defs_coverage.py"))
twin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(twin)
holes = []
for pat, bare_flags, star_flags in bare_packages:
    probe = pat + ".zzz_future_submodule"
    row = {fl: twin._resolves_flag(probe, fl) for fl in FLAGS}
    parent = {fl: twin._resolves_flag(pat, fl) for fl in FLAGS}
    lost = [fl for fl in FLAGS if parent[fl] and not row[fl]]
    if lost:
        holes.append((pat, lost))
    print(f"  {pat:28s} parent={ {k: v for k, v in parent.items()} }")
    print(f"  {'':28s} submod={ {k: v for k, v in row.items()} }"
          + (f"   LOST: {lost}" if lost else ""))
print(f"\nPACKAGES WITH A SUBMODULE HOLE: {len(holes)}")
for pat, lost in holes:
    print(f"  {pat}: a future submodule loses {lost}")
