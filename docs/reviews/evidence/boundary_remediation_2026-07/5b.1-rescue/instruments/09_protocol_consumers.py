#!/usr/bin/env python3
"""Slot 5B.1 instrument 09 — per-protocol CONSUMER census (all 9).

For each protocol name, find every site that ADOPTS it (imports it, or
uses it as a parameter/attribute/variable annotation) OUTSIDE its own
defining module. Distinguishes:
  IMPORT      - the module imports the name
  ANNOTATION  - a def parameter / return / AnnAssign names it
  ISINSTANCE  - a runtime isinstance check
  TEST-ONLY   - the referencing file lives under tests/

A protocol with zero non-test, non-defining-module consumers is
"defined but unused" — which 5B's exit criterion forbids.

Also (part 2) proves a SECOND detector blind spot: the ratchet's
`full_shell_consumers` scans function PARAMETERS only, so a class-level
`shell: 'Shell'` ANNOTATION (exactly VariableExpanderProtocol's shape) is
invisible to it even in a scanned module. Mutation-proven here.

Portable: ROOT from argv[1] (default git toplevel).
"""
import ast
import importlib.util
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                    subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                   capture_output=True, text=True
                                   ).stdout.strip()).resolve()

PROTOCOLS = {
    "VariableAccess": "psh/protocols/__init__.py",
    "ExpansionContext": "psh/protocols/__init__.py",
    "IOContext": "psh/protocols/__init__.py",
    "JobRuntime": "psh/protocols/__init__.py",
    "LocaleContext": "psh/protocols/__init__.py",
    "VariableExpanderProtocol": "psh/expansion/_protocols.py",
    "CommandParsersProtocol": "psh/parser/combinators/commands/_protocols.py",
    "ControlStructureProtocol": "psh/parser/combinators/control_structures/_protocols.py",
    "_TemplateCtx": "psh/parser/recursive_descent/support/syntax_templates.py",
}

print(f"ROOT={ROOT}")
print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()}")
print()

scan_dirs = [ROOT / "psh", ROOT / "tests"]
files = []
for d in scan_dirs:
    files.extend(sorted(p for p in d.rglob("*.py")
                        if "__pycache__" not in p.parts))

print("=" * 74)
print("PER-PROTOCOL CONSUMER CENSUS")
print("=" * 74)

summary = {}
for name, defining in PROTOCOLS.items():
    rows = []
    for path in files:
        rel = str(path.relative_to(ROOT))
        if rel == defining:
            continue
        try:
            src = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if name not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        is_test = rel.startswith("tests/")
        kinds = set()
        lines = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if any(a.name == name for a in node.names):
                    kinds.add("IMPORT")
                    lines.append((node.lineno, "IMPORT"))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                anns = [a.annotation for a in
                        (list(node.args.posonlyargs) + list(node.args.args)
                         + list(node.args.kwonlyargs))]
                anns.append(node.returns)
                for a in anns:
                    if a is None:
                        continue
                    txt = ast.unparse(a)
                    if name in txt:
                        kinds.add("ANNOTATION")
                        lines.append((node.lineno, f"ANNOTATION {txt[:40]}"))
            if isinstance(node, ast.AnnAssign) and node.annotation is not None:
                if name in ast.unparse(node.annotation):
                    kinds.add("ANNOTATION")
                    lines.append((node.lineno, "ANNOTATION(attr)"))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "isinstance":
                if any(name in ast.unparse(a) for a in node.args):
                    kinds.add("ISINSTANCE")
                    lines.append((node.lineno, "ISINSTANCE"))
        if kinds:
            rows.append((rel, is_test, sorted(kinds), sorted(set(lines))))

    prod = [r for r in rows if not r[1]]
    tst = [r for r in rows if r[1]]
    summary[name] = (len(prod), len(tst))
    print(f"\n{name}   (defined in {defining})")
    print(f"  PRODUCTION consumers: {len(prod)}")
    for rel, _, kinds, lines in prod:
        print(f"    {rel}   {kinds}")
        for ln, k in lines[:6]:
            print(f"        L{ln}: {k}")
    if not prod:
        print("    (NONE — 'defined but unused' by 5B's exit criterion)")
    print(f"  TEST references: {len(tst)}")
    for rel, _, kinds, _ in tst:
        print(f"    {rel}   {kinds}")

print()
print("=" * 74)
print("SUMMARY (production consumers, test references)")
print("=" * 74)
for name, (p, t) in summary.items():
    flag = "  <<< ZERO PRODUCTION CONSUMERS" if p == 0 else ""
    print(f"  {name:28s} prod={p:<3d} tests={t}{flag}")

# --- part 2: the detector's SECOND blind spot (class-level annotations) ---
print()
print("=" * 74)
print("PART 2 — detector blind spot: class-level `shell: 'Shell'` attribute")
print("=" * 74)
spec = importlib.util.spec_from_file_location(
    "ratchet", ROOT / "tests/unit/tooling/test_shell_consumer_ratchet_q1.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

param_form = (
    "class Foo:\n"
    "    def bar(self, shell: 'Shell') -> None: ...\n"
)
attr_form = (
    "class Foo:\n"
    "    shell: 'Shell'\n"          # exactly VariableExpanderProtocol's shape
    "    state: 'ShellState'\n"
)
print("  A. PARAMETER form  `def bar(self, shell: 'Shell')`")
print(f"     detector result: {sorted(R.full_shell_consumers(param_form, 'psh.fake'))}")
print("  B. CLASS-ATTRIBUTE form  `shell: 'Shell'` (VariableExpanderProtocol:28)")
print(f"     detector result: {sorted(R.full_shell_consumers(attr_form, 'psh.fake'))}")
print()
print("  => The ratchet detects PARAMETERS only. A full-`Shell` reference held")
print("     as a class ATTRIBUTE is invisible to it, in scanned modules too.")
print("     This is a SECOND blind spot, independent of the scan-scope gap:")
print("     widening scope alone would NOT catch VariableExpanderProtocol's")
print("     `shell: 'Shell'` member if expansion/_protocols.py entered scope.")
