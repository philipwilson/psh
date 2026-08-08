#!/usr/bin/env python3
"""Slot 5B.1 instrument 08 — POSIX-table move design evidence.

Measures, rather than asserts:
  (1) the ACTUAL deferred-psh-import count for psh.core.locale_service
      (using the layering guard's OWN analyzer) vs its cap -> the exact
      expected cap-table diff;
  (2) every consumer of _POSIX_CLASSES and _POSIX_CLASSES_PATHNAME
      tree-wide (the disposition census);
  (3) candidate neutral owners, each tested against the layering rules
      that actually exist in test_import_layering.py (leaf/near-leaf
      allowlist, package cycles);
  (4) a byte-identical content fingerprint of both tables (the pin's
      reference value).

Portable: ROOT from argv[1] (default git toplevel).
"""
import ast
import hashlib
import importlib.util
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                    subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                   capture_output=True, text=True
                                   ).stdout.strip()).resolve()

spec = importlib.util.spec_from_file_location(
    "layering", ROOT / "tests/unit/tooling/test_import_layering.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

print(f"ROOT={ROOT}")
print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()}")
print()

# --- (1) deferred-import count for locale_service, by the guard's analyzer ---
print("=" * 74)
print("(1) DEFERRED-IMPORT COUNT — measured with the layering guard's analyzer")
print("=" * 74)
target = ROOT / "psh/core/locale_service.py"
src = target.read_text()
runtime, func_count = L.analyze_source(src, "psh.core.locale_service", False)
cap = L.FUNC_IMPORT_CAPS.get("psh.core.locale_service")
print(f"  psh.core.locale_service")
print(f"    module-level psh imports (runtime): {sorted(runtime)}")
print(f"    ACTUAL deferred psh imports       : {func_count}")
print(f"    CAP in FUNC_IMPORT_CAPS           : {cap}")
print(f"    slack (cap - actual)              : {cap - func_count}")

# enumerate them individually so the -2 is attributable
tree = ast.parse(src)
deferred = []


class V(ast.NodeVisitor):
    def __init__(self):
        self.depth = 0
        self.tc = 0
        self.fn = []

    def visit_FunctionDef(self, node):
        self.depth += 1
        self.fn.append(node.name)
        self.generic_visit(node)
        self.fn.pop()
        self.depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node):
        if L._is_type_checking_test(node.test):
            self.tc += 1
            for s in node.body:
                self.visit(s)
            self.tc -= 1
            for s in node.orelse:
                self.visit(s)
        else:
            self.generic_visit(node)

    def visit_ImportFrom(self, node):
        t = L._resolve_relative("psh.core.locale_service", node, False)
        if L._is_psh(t) and self.depth > 0:
            deferred.append((node.lineno, ".".join(self.fn), t,
                             [a.name for a in node.names]))
        self.generic_visit(node)

    def visit_Import(self, node):
        for a in node.names:
            if L._is_psh(a.name) and self.depth > 0:
                deferred.append((node.lineno, ".".join(self.fn), a.name, []))
        self.generic_visit(node)


V().visit(tree)
print(f"\n    ENUMERATED deferred imports ({len(deferred)}):")
for lineno, fn, mod, names in sorted(deferred):
    mark = "  <<< THE PRIVATE IMPORT (removed by the move)" \
        if mod == "psh.expansion.glob" else ""
    print(f"      L{lineno:<5d} in {fn:24s} from {mod} import {names}{mark}")
removed = [d for d in deferred if d[2] == "psh.expansion.glob"]
print(f"\n    imports the move REMOVES: {len(removed)}")
print(f"    post-move ACTUAL        : {func_count - len(removed)}")
print(f"    => EXPECTED CAP-TABLE DIFF: 'psh.core.locale_service': "
      f"{cap} -> {func_count - len(removed)}   "
      f"(a genuine -{len(removed)} on the ACTUAL count; cap follows it down)")

# --- (2) consumer census for both tables ---
print()
print("=" * 74)
print("(2) CONSUMER CENSUS — _POSIX_CLASSES / _POSIX_CLASSES_PATHNAME")
print("=" * 74)
for sym in ("_POSIX_CLASSES_PATHNAME", "_POSIX_CLASSES"):
    print(f"\n  {sym}:")
    hits = []
    for path in sorted(ROOT.rglob("*.py")):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if sym in line:
                # exclude the longer symbol when scanning the shorter one
                if sym == "_POSIX_CLASSES" and "_POSIX_CLASSES_PATHNAME" in line:
                    continue
                hits.append((str(path.relative_to(ROOT)), i, line.strip()[:88]))
    for rel, i, line in hits:
        print(f"    {rel}:{i}")
        print(f"        {line}")
    print(f"    total reference lines: {len(hits)}")

# --- (3) candidate neutral owners vs the REAL layering rules ---
print()
print("=" * 74)
print("(3) CANDIDATE NEUTRAL OWNERS vs the layering rules that exist")
print("=" * 74)
print(f"  CORE_MODULE_IMPORT_ALLOWLIST = {sorted(L.CORE_MODULE_IMPORT_ALLOWLIST)}")
print(f"  PACKAGE_CYCLE_ALLOWLIST      = {L.PACKAGE_CYCLE_ALLOWLIST or 'EMPTY (by design)'}")
print()
candidates = [
    ("psh/utils/posix_classes.py", "psh.utils",
     "TRUE LEAF (imports nothing from psh). In CORE_MODULE_IMPORT_ALLOWLIST, "
     "so core may import it at MODULE level. expansion importing utils is "
     "downward. Pure data, zero deps."),
    ("psh/core/posix_classes.py", "psh.core",
     "intra-core import for locale_service (same package); expansion->core "
     "is already a live module-level edge (glob.py:6). Also legal."),
    ("psh/expansion/<stay>", "psh.expansion",
     "STATUS QUO — keeps the core->expansion deferred import. Rejected: this "
     "is the defect."),
]
for path, pkg, note in candidates:
    print(f"  {path}")
    print(f"    package: {pkg}")
    print(f"    {note}")
    print()

print("  Does psh.utils currently import anything from psh at module level?")
utils_dir = ROOT / "psh/utils"
for path in sorted(utils_dir.rglob("*.py")):
    rel = str(path.relative_to(ROOT))
    is_pkg = path.name == "__init__.py"
    mod = rel[:-3].replace("/", ".")
    if is_pkg:
        mod = mod[:-len(".__init__")]
    r, fc = L.analyze_source(path.read_text(), mod, is_pkg)
    if r or fc:
        print(f"    {rel}: module-level={sorted(r)} deferred={fc}")
print("    (blank above = psh.utils is a clean leaf)")

# --- (4) byte-identical content fingerprint ---
print()
print("=" * 74)
print("(4) TABLE CONTENT FINGERPRINT (the pin's reference value)")
print("=" * 74)
sys.path.insert(0, str(ROOT))
gspec = importlib.util.spec_from_file_location(
    "globmod", ROOT / "psh/expansion/glob.py")
try:
    import psh.expansion.glob as G
    tables = {"_POSIX_CLASSES": G._POSIX_CLASSES,
              "_POSIX_CLASSES_PATHNAME": G._POSIX_CLASSES_PATHNAME}
    for name, tbl in tables.items():
        canon = repr(sorted(tbl.items()))
        h = hashlib.sha256(canon.encode()).hexdigest()
        print(f"  {name}:")
        print(f"    keys ({len(tbl)}): {sorted(tbl)}")
        print(f"    sha256(sorted items repr) = {h}")
    same = {k for k in tables['_POSIX_CLASSES']
            if tables['_POSIX_CLASSES'][k] == tables['_POSIX_CLASSES_PATHNAME'][k]}
    diff = set(tables['_POSIX_CLASSES']) - same
    print(f"\n  PATHNAME variant differs ONLY in: {sorted(diff)}")
    for k in sorted(diff):
        print(f"    {k}: base={tables['_POSIX_CLASSES'][k]!r}  "
              f"pathname={tables['_POSIX_CLASSES_PATHNAME'][k]!r}")
    print(f"  psh.expansion.glob resolved from: {G.__file__}")
except Exception as e:
    print(f"  !! could not import psh.expansion.glob: {type(e).__name__}: {e}")
