#!/usr/bin/env python3
"""A5 — USAGE census (not a reach census) for the whole-Shell forwards named by
D-5B.2-s2: ``evaluate_arithmetic`` (`expansion/arithmetic/`) and
``PromptExpander`` (`interactive/prompt.py`).

5B.2 lesson 1 binds: *a REACH census is not a USAGE census — measure what
consumers call ON the reached object.* So this reports, per subject:

  (1) DIRECT member usage: every ``<param>.<member>`` access, with the full
      dotted chain actually written (``shell.state.scope_manager``), so a
      protocol design can be read off the members rather than guessed.
  (2) FORWARDS: every call that passes the shell parameter ONWARD as an
      argument. A forward means the callee's own usage is part of this
      subject's true surface — a protocol that covers only (1) would fail to
      type the forward. Each forward is resolved to its callee where the
      callee is in the same package, and the callee's own direct usage is
      folded in transitively (bounded, cycle-safe).

ROOT from argv[1]; the psh package path is asserted before measuring.
"""
import ast
import os
import sys
from collections import defaultdict

ROOT = os.path.abspath(sys.argv[1])
PSH = os.path.join(ROOT, "psh")
assert os.path.isdir(PSH), f"no psh/ under {ROOT}"
print(f"tree: {ROOT}")


def parse(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return ast.parse(f.read(), filename=rel)


def dotted(node):
    """Full dotted chain for an Attribute/Name expression, or None."""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


class Usage(ast.NodeVisitor):
    """Direct member usage of, and forwards of, a named parameter."""

    def __init__(self, param, rel, fnname):
        self.param = param
        self.rel = rel
        self.fnname = fnname
        self.members = defaultdict(list)   # dotted chain -> [lines]
        self.forwards = []                 # (callee, argpos/kw, line)
        self.bare_uses = []                # the param used as a value

    def visit_Attribute(self, node):
        d = dotted(node)
        if d and (d == self.param or d.startswith(self.param + ".")):
            self.members[d].append(node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node):
        for i, a in enumerate(node.args):
            if isinstance(a, ast.Name) and a.id == self.param:
                self.forwards.append((dotted(node.func) or "?", f"arg{i}",
                                      node.lineno))
        for kw in node.keywords:
            if isinstance(kw.value, ast.Name) and kw.value.id == self.param:
                self.forwards.append((dotted(node.func) or "?",
                                      f"kw:{kw.arg}", node.lineno))
        self.generic_visit(node)


def defs_in(rel):
    """{qualname: FunctionDef} for one module."""
    out = {}

    def walk(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, ast.ClassDef):
                walk(ch, prefix + [ch.name])
            elif isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[".".join(prefix + [ch.name])] = ch
                walk(ch, prefix + [ch.name])
    walk(parse(rel), [])
    return out


def shell_param_of(fn):
    """The parameter named shell/parent_shell, or None."""
    a = fn.args
    for p in a.posonlyargs + a.args + a.kwonlyargs:
        if p.arg in ("shell", "parent_shell"):
            return p.arg
    return None


def census(files, title):
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")
    all_members = defaultdict(list)
    all_forwards = defaultdict(list)
    carriers = []
    for rel in files:
        for qual, fn in sorted(defs_in(rel).items()):
            param = shell_param_of(fn)
            # A method that stores the shell reaches it through self.<field>.
            names = [param] if param else []
            if not names:
                continue
            for nm in names:
                u = Usage(nm, rel, qual)
                for st in fn.body:
                    u.visit(st)
                if u.members or u.forwards:
                    carriers.append((rel, qual, nm))
                    for m, lines in u.members.items():
                        all_members[m].extend(
                            f"{rel}:{ln}" for ln in lines)
                    for callee, pos, ln in u.forwards:
                        all_forwards[callee].append(f"{rel}:{ln}({pos})")

    print(f"\ncarrier defs (take a shell param and use it): {len(carriers)}")
    for rel, qual, nm in carriers:
        print(f"  {rel}::{qual}({nm})")

    print(f"\nDIRECT member usage ({len(all_members)} distinct chains):")
    for m, sites in sorted(all_members.items(),
                           key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"  {len(sites):3d}x  {m:52s} {sites[0]}"
              + (f" (+{len(sites) - 1} more)" if len(sites) > 1 else ""))

    print(f"\nFORWARDS of the shell to another callable "
          f"({len(all_forwards)} distinct callees):")
    for callee, sites in sorted(all_forwards.items(),
                                key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"  {len(sites):3d}x  -> {callee:40s} {', '.join(sites[:4])}")
    return all_members, all_forwards


def stored_shell_census(files, title):
    """The arm the first version of this instrument LACKED.

    INSTRUMENT DEFECT FOUND AND RECORDED: censusing only defs that take a
    ``shell`` PARAMETER reported 5 member chains for the arithmetic package and
    **ZERO** for ``PromptExpander`` — a class that takes the shell in
    ``__init__`` and then uses it as ``self.shell.<member>`` everywhere. A
    zero from an instrument blind to the dominant shape is not a measurement of
    a small surface, it is a measurement of the instrument. This is 5B.2
    lesson 1 in its own right: the parameter is the REACH, ``self.shell.x`` is
    the USAGE. Same blindness hid ``ArithmeticEvaluator``, which the
    parameter arm saw only as an opaque forward.
    """
    print(f"\n{'=' * 74}\nSTORED-FIELD ARM — {title}\n{'=' * 74}")
    for rel in files:
        tree = parse(rel)
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            # Which self.<field> holds a shell parameter?
            fields = set()
            for fn in [n for n in cls.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                param = shell_param_of(fn)
                if not param:
                    continue
                for node in ast.walk(fn):
                    if isinstance(node, ast.Assign):
                        for tgt in node.targets:
                            if (isinstance(tgt, ast.Attribute)
                                    and isinstance(tgt.value, ast.Name)
                                    and tgt.value.id == "self"
                                    and isinstance(node.value, ast.Name)
                                    and node.value.id == param):
                                fields.add(tgt.attr)
            if not fields:
                continue
            for field in sorted(fields):
                pref = f"self.{field}"
                members = defaultdict(list)
                for node in ast.walk(cls):
                    if isinstance(node, ast.Attribute):
                        d = dotted(node)
                        if d and d.startswith(pref + "."):
                            members[d].append(node.lineno)
                print(f"\n{rel}::{cls.name} stores the shell as {pref}")
                print(f"  distinct member chains: {len(members)}")
                for m, lines in sorted(members.items(),
                                       key=lambda kv: (-len(kv[1]), kv[0])):
                    short = m[len(pref) + 1:]
                    print(f"    {len(lines):3d}x  .{short:46s} "
                          f"{rel}:{lines[0]}")


def rels(pkg):
    out = []
    for dirpath, dirnames, filenames in sorted(os.walk(os.path.join(PSH, pkg))):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(dirpath, fn), ROOT))
    return out


arith = rels("expansion/arithmetic")
census(arith, "SUBJECT 1: evaluate_arithmetic + the whole arithmetic package")
census(["psh/interactive/prompt.py"], "SUBJECT 2: PromptExpander")
stored_shell_census(arith, "arithmetic package")
stored_shell_census(["psh/interactive/prompt.py"], "PromptExpander")
