#!/usr/bin/env python3
"""Instrument 04 (slot 5B.2) — D-5B.1-s3 instance-assignment detector: SHAPE
GRAMMAR + pre-build sweep.

D-5B.1-s3: the shipped detector reads DECLARATIONS (parameters + class-level
AnnAssign) and is blind to a shell stored by plain assignment in a method body
(``self.shell = shell``). This instrument designs the new arm and runs its sweep
BEFORE the arm is built, so the expected new-hit set is enumerated with per-hit
dispositions rather than discovered by a red test.

SHAPE GRAMMAR (keyed on the SOURCE, not the attribute name)
-----------------------------------------------------------
A hit is ``self.<attr> = <value>`` inside a method whose enclosing function has
a FULL-SHELL parameter (by the SHIPPED detector's own rules: an annotation
mentioning ``Shell`` as an identifier, or an unannotated parameter named exactly
``shell``), where ``<value>`` resolves to that parameter.

Keying on the attribute NAME would be wrong and this is not hypothetical:
``psh/core/scope.py:149`` stores the whole shell as ``self._shell = shell``. A
``self.shell``-only grammar reports zero there while the service-locator reach
is live one underscore away.

Resolved forms (each an arm):
  1. direct         self.shell = shell
  2. renamed attr   self._shell = shell
  3. annotated      self.shell: 'Shell' = shell      (AnnAssign in a method body)
  4. aliased        s = shell; self.shell = s        (one hop, same function)
  5. tuple          self.shell, self.x = shell, y

Deliberate NON-hits (control arms — the refinement must not over-fire):
  A. self.state = state                    (ShellState is never a hit)
  B. self.mgr = shell.expansion_manager    (a NARROWING, the thing we want)
  C. self.shell = None                     (no full-Shell value)
  D. self.shell = other                    (unrelated local, not the parameter)

Usage:  python 04_instance_assign_sweep.py <ROOT>
"""
import ast
import pathlib
import re
import subprocess
import sys


# --- the SHIPPED detector's annotation rules (transcribed, not imported, so a
# --- change to either side shows up as a disagreement rather than silently) ---
def _string_mentions_shell(s):
    try:
        sub = ast.parse(s, mode="eval")
    except SyntaxError:
        return re.search(r"\bShell\b", s) is not None
    return _ann_mentions_shell(sub)


def _ann_mentions_shell(node):
    if node is None:
        return False
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id == "Shell":
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            if _string_mentions_shell(n.value):
                return True
    return False


def full_shell_params(fn):
    """Names of *fn*'s parameters that are full-``Shell`` by the shipped rules."""
    a = fn.args
    params = list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
    if a.vararg:
        params.append(a.vararg)
    if a.kwarg:
        params.append(a.kwarg)
    return {p.arg for p in params
            if _ann_mentions_shell(p.annotation)
            or (p.annotation is None and p.arg == "shell")}


def instance_assign_hits(src, module):
    """{(module, qualname, attr, lineno, arm)} for the instance-assignment shape."""
    tree = ast.parse(src)
    hits = set()
    stack = []

    def scan_function(fn, qual):
        shell_params = full_shell_params(fn)
        if not shell_params:
            return
        # one hop of aliasing: local = <shell param>
        aliases = set(shell_params)
        for _ in range(2):
            for n in ast.walk(fn):
                if (isinstance(n, ast.Assign) and len(n.targets) == 1
                        and isinstance(n.targets[0], ast.Name)
                        and isinstance(n.value, ast.Name)
                        and n.value.id in aliases):
                    aliases.add(n.targets[0].id)

        def is_shell_value(v):
            return isinstance(v, ast.Name) and v.id in aliases

        for n in ast.walk(fn):
            # forms 1/2/4: self.<attr> = <shell>
            if isinstance(n, ast.Assign):
                for tgt in n.targets:
                    if (isinstance(tgt, ast.Attribute)
                            and isinstance(tgt.value, ast.Name)
                            and tgt.value.id == "self"
                            and is_shell_value(n.value)):
                        arm = "direct" if tgt.attr == "shell" else "renamed"
                        if isinstance(n.value, ast.Name) and \
                                n.value.id not in shell_params:
                            arm = "aliased"
                        hits.add((module, qual, tgt.attr, n.lineno, arm))
                    # form 5: tuple target
                    if isinstance(tgt, ast.Tuple) and isinstance(n.value,
                                                                 ast.Tuple):
                        for t, v in zip(tgt.elts, n.value.elts):
                            if (isinstance(t, ast.Attribute)
                                    and isinstance(t.value, ast.Name)
                                    and t.value.id == "self"
                                    and is_shell_value(v)):
                                hits.add((module, qual, t.attr, n.lineno,
                                          "tuple"))
            # form 3: annotated instance assign
            if isinstance(n, ast.AnnAssign) and n.value is not None:
                t = n.target
                if (isinstance(t, ast.Attribute)
                        and isinstance(t.value, ast.Name)
                        and t.value.id == "self"
                        and (is_shell_value(n.value)
                             or _ann_mentions_shell(n.annotation))):
                    hits.add((module, qual, t.attr, n.lineno, "annotated"))

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, prefix + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scan_function(child, ".".join(prefix + [child.name]))
                visit(child, prefix + [child.name])

    visit(tree, [])
    return hits


SELF_TESTS = [
    ("1 direct", "class C:\n def __init__(self, shell: 'Shell'):\n"
                 "  self.shell = shell\n", True),
    ("2 renamed attr", "class C:\n def set_shell(self, shell):\n"
                       "  self._shell = shell\n", True),
    ("3 annotated", "class C:\n def __init__(self, shell: 'Shell'):\n"
                    "  self.shell: 'Shell' = shell\n", True),
    ("4 aliased", "class C:\n def __init__(self, shell: 'Shell'):\n"
                  "  s = shell\n  self.shell = s\n", True),
    ("5 tuple", "class C:\n def __init__(self, shell: 'Shell', y):\n"
                "  self.shell, self.y = shell, y\n", True),
    ("A ShellState", "class C:\n def __init__(self, state: 'ShellState'):\n"
                     "  self.state = state\n", False),
    ("B narrowing", "class C:\n def __init__(self, shell: 'Shell'):\n"
                    "  self.mgr = shell.expansion_manager\n", False),
    ("C none", "class C:\n def __init__(self, shell: 'Shell'):\n"
               "  self.shell = None\n", False),
    ("D unrelated", "class C:\n def __init__(self, shell: 'Shell', other):\n"
                    "  self.shell = other\n", False),
]


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print()

    print("=" * 74)
    print("GRAMMAR SELF-TESTS (offender arms fire; control arms do NOT)")
    print("=" * 74)
    bad = 0
    for label, src, expect in SELF_TESTS:
        got = bool(instance_assign_hits(src, "psh.fake"))
        ok = got == expect
        bad += not ok
        print(f"  [{'ok ' if ok else 'BAD'}] {label:<16} "
              f"expect={'HIT' if expect else 'no '} got={'HIT' if got else 'no '}")
    print(f"  self-test failures: {bad}")
    print()

    sys.path.insert(0, str(root))
    from tests.unit.tooling.test_shell_consumer_ratchet_q1 import (  # noqa
        ALLOWLIST, TOUCHED_MODULES,
    )

    def dotted(rel):
        return rel[:-3].replace("/", ".")

    print("=" * 74)
    print(f"SWEEP A — the ratchet's CURRENT scan scope ({len(TOUCHED_MODULES)} modules)")
    print("=" * 74)
    in_scope = set()
    for rel in TOUCHED_MODULES:
        p = root / rel
        in_scope |= instance_assign_hits(p.read_text(), dotted(rel))
    for mod, qual, attr, ln, arm in sorted(in_scope):
        recorded = (mod, qual) in ALLOWLIST
        print(f"  {mod}.{qual}  self.{attr} @L{ln}  [{arm}]  "
              f"{'ALREADY IN ALLOWLIST' if recorded else '*** NEW HIT ***'}")
    if not in_scope:
        print("  (no hits in the current scan scope)")
    new_in_scope = {(m, q) for m, q, _, _, _ in in_scope} - set(ALLOWLIST)
    print(f"  hits: {len(in_scope)}; NEW (unrecorded) defs: {len(new_in_scope)}")
    print(f"  new defs: {sorted(new_in_scope)}")
    print()

    print("=" * 74)
    print("SWEEP B — TREE-WIDE (information: what a scope extension would meet)")
    print("=" * 74)
    tree_hits = set()
    for path in sorted((root / "psh").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root))
        try:
            tree_hits |= instance_assign_hits(path.read_text(), dotted(rel))
        except SyntaxError:
            continue
    scoped = {dotted(r) for r in TOUCHED_MODULES}
    outside = sorted(h for h in tree_hits if h[0] not in scoped)
    for mod, qual, attr, ln, arm in outside:
        print(f"  {mod}.{qual}  self.{attr} @L{ln}  [{arm}]")
    print(f"  tree-wide hits: {len(tree_hits)}  "
          f"(in current scope: {len(tree_hits) - len(outside)}, "
          f"outside: {len(outside)})")


if __name__ == "__main__":
    main()
