#!/usr/bin/env python3
"""A11 — BOUNDED dead-public-API census over the component-manager classes.

DENOMINATOR (stated, and deliberately narrow — this is a bounded sweep, not a
whole-tree claim): every PUBLIC def (name not starting with '_') declared on the
component-manager / boundary classes that ARCHITECTURE.md's Quick Map names as
the component owners, plus the two redirect boundary classes those managers
delegate to. Class list is explicit below and is the census's whole universe.

A member is a DEAD CANDIDATE when it has ZERO production references in psh/
outside its own definition. A "reference" is deliberately generous — attribute
access `.name` WITHOUT requiring a following '(' (so property reads and
callback passing count), plus the bare quoted string 'name' (so registry/getattr
dispatch counts). Generous = biased AGAINST finding deadness, which is the
correct bias for a census whose finds authorise deletions.

KNOWN TRAPS, handled explicitly rather than silently:
  - dynamic dispatch by name  -> quoted-string references are counted
  - property reads            -> '(' is not required after the attribute
  - visitor methods           -> visit_* excluded (framework dispatch by name)
  - protocol conformance      -> psh/protocols/ counted as production
  - test-only helpers         -> reported separately: a member used ONLY by
                                tests/ is NOT dead code, it is test-only API,
                                which is a different disposition
NOT SCANNED (declared, so no silent coverage claim): free functions, non-manager
classes, builtins, the lexer/parser/visitor trees, `tools/`, and any dispatch
that constructs a member name at runtime by concatenation.

Usage: A11_dead_public_api.py <tree_root>
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()

# The census universe. Each entry: file, class name.
TARGETS = [
    ("psh/expansion/manager.py", "ExpansionManager"),
    ("psh/io_redirect/manager.py", "IOManager"),
    ("psh/executor/job_control.py", "JobManager"),
    ("psh/executor/process_launcher.py", "ProcessLauncher"),
    ("psh/core/functions.py", "FunctionManager"),
    # RE-POINTED (R1 §5): my first pass guessed these two paths and both were
    # wrong. ARCHITECTURE's Quick Map is CORRECT — it places aliases.py inside
    # the expansion/ block and names scripting/ as a package without claiming a
    # file. No doc drift; the error was mine.
    ("psh/expansion/aliases.py", "AliasManager"),
    ("psh/io_redirect/file_redirect.py", "FileRedirector"),
    ("psh/scripting/base.py", "ScriptManager"),
]

prod_files = [p for p in (ROOT / "psh").rglob("*.py")
              if "__pycache__" not in p.parts]
test_files = [p for p in (ROOT / "tests").rglob("*.py")
              if "__pycache__" not in p.parts]
prod_text = {p: p.read_text() for p in prod_files}
test_text = {p: p.read_text() for p in test_files}


def members(rel, cls_name):
    path = ROOT / rel
    if not path.exists():
        return None
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            out = []
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    n = child.name
                    if n.startswith("_"):
                        continue
                    if n.startswith("visit_"):
                        continue
                    out.append((n, child.lineno))
            return out
    return None


def refs(name, corpus, def_path, def_line):
    """Every reference to `name` outside its own def line."""
    attr = re.compile(r"\." + re.escape(name) + r"\b")
    quoted = re.compile(r"['\"]" + re.escape(name) + r"['\"]")
    hits = []
    for path, text in corpus.items():
        for i, line in enumerate(text.splitlines(), 1):
            if path == def_path and i == def_line:
                continue
            if attr.search(line) or quoted.search(line):
                hits.append((path, i, line.strip()[:90]))
    return hits


total = dead = testonly = 0
print("=== BOUNDED dead-public-API census (component managers + redirect boundary)")
for rel, cls in TARGETS:
    ms = members(rel, cls)
    if ms is None:
        print(f"\n## {cls} ({rel}) — CLASS NOT FOUND AT THIS PATH (excluded)")
        continue
    print(f"\n## {cls} ({rel}) — {len(ms)} public defs")
    for name, line in ms:
        total += 1
        p = refs(name, prod_text, ROOT / rel, line)
        if p:
            continue
        t = refs(name, test_text, ROOT / rel, line)
        if t:
            testonly += 1
            print(f"   TEST-ONLY  {cls}.{name}  (def :{line}; "
                  f"{len(t)} test refs, 0 production) -> disposition: test-only API")
            for path, i, src in t[:3]:
                print(f"        {path.relative_to(ROOT)}:{i}: {src}")
        else:
            dead += 1
            print(f"   *** DEAD   {cls}.{name}  (def :{line}; "
                  f"0 production refs, 0 test refs)")

print(f"\n=== TOTALS: {total} public defs scanned; "
      f"{dead} zero-witness DEAD; {testonly} TEST-ONLY")
