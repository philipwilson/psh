#!/usr/bin/env python3
"""Slot 5B.1 instrument 12 — R1 ruling 6, the two readings, MEASURED.

R1.6 says: "extend full_shell_consumers to class-level AnnAssign (Shell AND
ShellState annotations)". Two readings:

  READING A (consistent-with-parameters): scan class-level AnnAssign and
    apply the SAME rule the parameter path uses — flag `Shell`, never
    `ShellState` (which the ratchet calls "already a narrowing" and
    deliberately does not count). The parenthetical then means "handle both
    annotation TEXTS correctly", and the self-tests must cover both.

  READING B (literal-additive): flag class-level AnnAssign annotated with
    `Shell` OR `ShellState`.

These differ materially: reading B flags `JobRuntime.shell_state:
'Optional[ShellState]'` in psh/protocols/__init__.py — which is IN the newly
scanned set — creating a live hit whose migration ruling (b) assigns to 5B.2.
R1 also states "Expected zero new hits — verify, don't assume".

This instrument implements BOTH and sweeps the post-extension scanned set,
so the fork is decided on measurement, not on reading tea leaves.

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

spec = importlib.util.spec_from_file_location(
    "ratchet", ROOT / "tests/unit/tooling/test_shell_consumer_ratchet_q1.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

# The post-extension scanned set = current 20 + the 3 newly scanned.
SCANNED = R.TOUCHED_MODULES + [
    "psh/protocols/__init__.py",
    "psh/expansion/procsub_render.py",
    "psh/scripting/analysis_session.py",
]


def _ann_mentions_shellstate(node) -> bool:
    """True if an annotation mentions ShellState as an identifier."""
    if node is None:
        return False
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id == "ShellState":
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            try:
                sub = ast.parse(n.value, mode="eval")
            except SyntaxError:
                import re
                if re.search(r"\bShellState\b", n.value):
                    return True
                continue
            if _ann_mentions_shellstate(sub):
                return True
    return False


def consumers(src, module, include_shellstate_attrs):
    """Parameter rule (unchanged) + class-level AnnAssign under the chosen
    reading."""
    tree = ast.parse(src)
    found = set()

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                # class-level annotated attributes
                for stmt in child.body:
                    if isinstance(stmt, ast.AnnAssign) and \
                            isinstance(stmt.target, ast.Name):
                        hit = R._ann_mentions_shell(stmt.annotation)
                        if include_shellstate_attrs and not hit:
                            hit = _ann_mentions_shellstate(stmt.annotation)
                        if hit:
                            found.add((".".join(prefix + [child.name,
                                                          stmt.target.id]),
                                       stmt.lineno,
                                       ast.unparse(stmt.annotation)))
                visit(child, prefix + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, prefix + [child.name])

    visit(tree, [])
    return {(module, sym, ln, ann) for sym, ln, ann in found}


print(f"ROOT={ROOT}")
print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()}")
print(f"scanned set (post-extension): {len(SCANNED)} modules")
print()

for label, flag in (("READING A — Shell only (parameter-consistent)", False),
                    ("READING B — Shell OR ShellState (literal-additive)", True)):
    print("=" * 74)
    print(label)
    print("=" * 74)
    total = 0
    for rel in SCANNED:
        path = ROOT / rel
        if not path.exists():
            print(f"  !! missing {rel}")
            continue
        hits = consumers(path.read_text(), R._module_dotted(rel), flag)
        for mod, sym, ln, ann in sorted(hits):
            print(f"  NEW ATTRIBUTE HIT  {mod}.{sym}")
            print(f"      {rel}:{ln}   annotation: {ann}")
            total += 1
    print(f"\n  new class-attribute hits across the scanned set: {total}")
    if total == 0:
        print("  => matches R1's stated expectation of ZERO new hits")
    else:
        print("  => CONTRADICTS R1's stated expectation of ZERO new hits")
    print()

print("=" * 74)
print("CONTROL — the shapes each reading must classify")
print("=" * 74)
samples = {
    "param  shell: 'Shell'": "class F:\n    def m(self, shell: 'Shell') -> None: ...\n",
    "param  state: 'ShellState'": "class F:\n    def m(self, state: 'ShellState') -> None: ...\n",
    "attr   shell: 'Shell'": "class F:\n    shell: 'Shell'\n",
    "attr   state: 'ShellState'": "class F:\n    state: 'ShellState'\n",
    "attr   x: \"Optional[ShellState]\"": "class F:\n    x: 'Optional[ShellState]'\n",
    "attr   y: \"Optional['Shell']\"": "class F:\n    y: \"Optional['Shell']\"\n",
}
for desc, src in samples.items():
    a = consumers(src, "psh.fake", False)
    b = consumers(src, "psh.fake", True)
    p = R.full_shell_consumers(src, "psh.fake")
    print(f"  {desc:34s} params={'HIT' if p else '-  '}  "
          f"A={'HIT' if a else '-  '}  B={'HIT' if b else '-'}")
