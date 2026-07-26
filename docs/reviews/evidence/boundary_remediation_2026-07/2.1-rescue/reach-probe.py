"""Slot 2.1 reach probe — runnable at BOTH base (a765f1a0) and tip.

For each HIGH-2 position, parses the probe source, locates the embedded
danger node with an INDEPENDENT full-reflection walker (not walk_ast — the
instrument must not depend on the machinery under test), then instruments
SecurityVisitor.visit and reports whether the danger node is dispatched.
Prints one RED/GREEN line per case plus the issue count.
"""
import dataclasses
import os
import sys

sys.path.insert(0, os.getcwd())

import psh  # noqa: E402
from psh.ast_nodes import Redirect, SimpleCommand  # noqa: E402
from psh.lexer import tokenize  # noqa: E402
from psh.parser import parse  # noqa: E402
from psh.visitor.security_visitor import SecurityVisitor  # noqa: E402

print(f"# psh import discriminator: {psh.__file__}")
print(f"# python: {sys.version.split()[0]}")


def full_walk(node):
    """Independent reflection walk: every ASTNode anywhere reachable,
    including through lists, tuples-in-lists, and template subs."""
    from psh.ast_nodes import ASTNode
    seen = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        yield n
        if not dataclasses.is_dataclass(n):
            continue
        for f in dataclasses.fields(n):
            v = getattr(n, f.name, None)
            vals = []
            if isinstance(v, ASTNode):
                vals = [v]
            elif isinstance(v, (list, tuple)):
                for item in v:
                    if isinstance(item, ASTNode):
                        vals.append(item)
                    elif isinstance(item, tuple):
                        vals.extend(x for x in item if isinstance(x, ASTNode))
            elif v is not None and hasattr(v, 'subs'):  # SyntaxTemplate carrier
                vals.extend(s.expansion for s in v.subs)
            stack.extend(vals)


def find_danger(root, pred, label):
    hits = [n for n in full_walk(root) if pred(n)]
    assert hits, f"{label}: probe source did not produce the expected node"
    return hits


def check(label, src, pred):
    ast = parse(tokenize(src))
    targets = find_danger(ast, pred, label)
    v = SecurityVisitor()
    seen = set()
    orig = v.visit
    v.visit = lambda n: (seen.add(id(n)), orig(n))[1]
    v.visit(ast)
    reached = all(id(t) in seen for t in targets)
    print(f"{label}: dispatch={'GREEN (reached)' if reached else 'RED (missed)'} "
          f"issues={len(v.issues)}")


def is_rm(n):
    return isinstance(n, SimpleCommand) and n.args[:1] == ['rm']


def is_redirect(n):
    return isinstance(n, Redirect)


check("p1 redirect-only cmd (Redirect node) ", ">/tmp/x", is_redirect)
check("p2 redirect target $(rm ...)         ",
      "echo >$(rm -rf /tmp/psh-never-created)", is_rm)
check("p3 for subject word \"$(rm ...)\"      ",
      'for x in "$(rm -rf /tmp/psh-never-created)"; do :; done', is_rm)
check("p4 case subject word \"$(rm ...)\"     ",
      'case "$(rm -rf /tmp/psh-never-created)" in x) :;; esac', is_rm)
check("t1 param-operand template ${x:-$(rm)}",
      'echo "${x:-$(rm -rf /tmp/psh-never-created)}"', is_rm)
check("t2 arith template $(( $(rm) ))       ",
      'echo "$(( $(rm -rf /tmp/psh-never-created) ))"', is_rm)
