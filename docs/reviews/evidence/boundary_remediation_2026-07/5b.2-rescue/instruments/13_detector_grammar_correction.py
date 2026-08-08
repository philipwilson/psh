#!/usr/bin/env python3
"""Instrument 13 (slot 5B.2) — CORRECTION to the D-5B.1-s3 detector grammar.

My Phase A design (instrument 04) keyed the instance-assignment arm on the
SOURCE: ``self.<attr> = <a full-Shell parameter>``. Writing the real arm
exposed that this grammar is SUBSUMED by the shipped parameter arm and can
never fire independently — to assign ``self.x = shell`` the value must be a
full-``Shell`` parameter, and any function with one is ALREADY a hit. That is
why the Phase A sweep found exactly one in-scope site and it was already
recorded: not because the tree is clean, but because the grammar could not say
anything new.

The gap D-5B.1-s3 actually names is the opposite keying. 5B.1's own docstring
says the blind shape is "a shell stored by plain ASSIGNMENT in a method body
(``self.shell = shell``, NO ANNOTATION ANYWHERE)". The case the parameter arm
misses is therefore:

    def wire(self, s):        # unannotated AND not named 'shell' -> param arm silent
        self.shell = s        # ...but the FIELD is the whole shell

so the arm must key on the TARGET — an instance attribute named ``shell`` /
``_shell`` — exactly as the shipped class-attribute arm keys on the declared
attribute rather than on where the value came from.

This instrument runs BOTH grammars over both scopes so the correction is
visible as a measurement rather than asserted.

Usage:  python 13_detector_grammar_correction.py <ROOT>
"""
import ast
import pathlib
import re
import subprocess
import sys

SHELL_FIELD_NAMES = {"shell", "_shell"}


def _string_mentions_shell(s):
    try:
        return _ann(ast.parse(s, mode="eval"))
    except SyntaxError:
        return re.search(r"\bShell\b", s) is not None


def _ann(node):
    if node is None:
        return False
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id == "Shell":
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                and _string_mentions_shell(n.value):
            return True
    return False


def full_shell_params(fn):
    a = fn.args
    ps = list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
    if a.vararg:
        ps.append(a.vararg)
    if a.kwarg:
        ps.append(a.kwarg)
    return {p.arg for p in ps
            if _ann(p.annotation) or (p.annotation is None and p.arg == "shell")}


def grammar_A(fn):
    """SOURCE-keyed (my Phase A design): self.<attr> = <full-Shell param>."""
    sp = full_shell_params(fn)
    if not sp:
        return []
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if (isinstance(t, ast.Attribute)
                        and isinstance(t.value, ast.Name) and t.value.id == "self"
                        and isinstance(n.value, ast.Name) and n.value.id in sp):
                    out.append((t.attr, n.lineno))
    return out


def grammar_B(fn):
    """TARGET-keyed (the corrected arm): an instance attribute named
    shell/_shell, or annotated Shell, bound to a bare NAME.

    Bare-NAME is the discriminator that keeps the narrowings out: the campaign
    WANTS ``self.mgr = shell.expansion_manager`` and ``self.state = shell.state``
    to be legal, and both are attribute accesses, not names. ``self.shell = None``
    is likewise not a name.
    """
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if (isinstance(t, ast.Attribute)
                        and isinstance(t.value, ast.Name) and t.value.id == "self"
                        and t.attr in SHELL_FIELD_NAMES
                        and isinstance(n.value, ast.Name)):
                    out.append((t.attr, n.lineno))
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            t = n.target
            if (isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name) and t.value.id == "self"
                    and (t.attr in SHELL_FIELD_NAMES or _ann(n.annotation))):
                out.append((t.attr, n.lineno))
    return out


def scan(src, module, grammar):
    tree = ast.parse(src)
    hits = set()

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, prefix + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = ".".join(prefix + [child.name])
                for attr, ln in grammar(child):
                    hits.add((module, qual, attr, ln))
                walk(child, prefix + [child.name])

    walk(tree, [])
    return hits


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(root))
    from tests.unit.tooling.test_shell_consumer_ratchet_q1 import (  # noqa
        ALLOWLIST, TOUCHED_MODULES, full_shell_consumers,
    )
    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print()

    def dotted(rel):
        return rel[:-3].replace("/", ".")

    # --- the subsumption claim, demonstrated on synthetic sources ----------
    print("=" * 74)
    print("SUBSUMPTION DEMONSTRATION (why grammar A adds nothing)")
    print("=" * 74)
    smuggled = ("class C:\n"
                "    def wire(self, s):\n"
                "        self.shell = s\n")
    a = scan(smuggled, "psh.fake", grammar_A)
    b = scan(smuggled, "psh.fake", grammar_B)
    shipped = full_shell_consumers(smuggled, "psh.fake")
    print("  source: `def wire(self, s): self.shell = s`  "
          "(param unannotated AND not named 'shell')")
    print(f"    shipped param/class-attr detector : {sorted(shipped)}")
    print(f"    grammar A (source-keyed)          : {sorted(a)}")
    print(f"    grammar B (target-keyed)          : {sorted(b)}")
    print("    => only grammar B sees it; A is silent because the param arm's"
          " own condition is absent")
    print()
    canonical = ("class C:\n"
                 "    def __init__(self, shell: 'Shell'):\n"
                 "        self.shell = shell\n")
    print("  source: `def __init__(self, shell: 'Shell'): self.shell = shell`")
    print(f"    shipped detector : {sorted(full_shell_consumers(canonical, 'psh.fake'))}")
    print(f"    grammar A        : {sorted(scan(canonical, 'psh.fake', grammar_A))}")
    print("    => A fires, but the shipped detector ALREADY flagged this def:"
          " no new key")
    print()

    # --- controls ---------------------------------------------------------
    print("=" * 74)
    print("GRAMMAR B CONTROLS (must NOT fire)")
    print("=" * 74)
    controls = {
        "narrowing (the thing we WANT)":
            "class C:\n    def __init__(self, shell: 'Shell'):\n"
            "        self.mgr = shell.expansion_manager\n",
        "state narrowing":
            "class C:\n    def __init__(self, shell: 'Shell'):\n"
            "        self.state = shell.state\n",
        "None store":
            "class C:\n    def __init__(self):\n        self.shell = None\n",
        "attribute source (not a bare name)":
            "class C:\n    def __init__(self, other):\n"
            "        self.shell = other.shell\n",
    }
    for label, src in controls.items():
        got = scan(src, "psh.fake", grammar_B)
        print(f"  [{'ok ' if not got else 'FIRES'}] {label}: {sorted(got)}")
    print()

    # --- the real sweeps --------------------------------------------------
    for label, mods in (("IN SCOPE (ratchet's scanned modules)",
                         list(TOUCHED_MODULES)),
                        ("TREE-WIDE",
                         [str(p.relative_to(root))
                          for p in sorted((root / "psh").rglob("*.py"))
                          if "__pycache__" not in p.parts])):
        print("=" * 74)
        print(f"SWEEP — {label}")
        print("=" * 74)
        A, B = set(), set()
        for rel in mods:
            src = (root / rel).read_text()
            A |= scan(src, dotted(rel), grammar_A)
            B |= scan(src, dotted(rel), grammar_B)
        only_b = {h for h in B if (h[0], h[1]) not in
                  {(x[0], x[1]) for x in A}}
        print(f"  grammar A hits: {len(A)}   grammar B hits: {len(B)}")
        print(f"  defs found by B but NOT by A: {len(only_b)}")
        for mod, qual, attr, ln in sorted(only_b):
            recorded = (mod, qual) in ALLOWLIST
            # is the def ALREADY a hit of the shipped detector (via its param)?
            rel = mod.replace(".", "/") + ".py"
            p = root / rel
            if not p.exists():
                p = root / mod.replace(".", "/") / "__init__.py"
            shipped_hit = (mod, qual) in full_shell_consumers(p.read_text(), mod)
            tag = ("ALLOWLISTED" if recorded else
                   ("already a shipped-detector hit" if shipped_hit
                    else "*** GENUINELY NEW ***"))
            print(f"    {mod}.{qual}  self.{attr} @L{ln}  [{tag}]")
        print()


if __name__ == "__main__":
    main()
