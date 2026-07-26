"""B6 surface probe — SHA-portable (base a765f1a0 and tip both).

For each textual-reader entry point x nested-substitution shape, runs the
issue-producing analysis visitors and prints the FINDING count (and the
undefined-variable finding count specifically), so base-vs-tip diffs expose
every duplicate-diagnostics site, not just the verifier's operand list.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

import psh  # noqa: E402
from psh.lexer import tokenize  # noqa: E402
from psh.parser import parse  # noqa: E402
from psh.visitor.enhanced_validator_visitor import EnhancedValidatorVisitor  # noqa: E402
from psh.visitor.linter_visitor import LinterVisitor  # noqa: E402
from psh.visitor.metrics_visitor import MetricsVisitor  # noqa: E402
from psh.visitor.security_visitor import SecurityVisitor  # noqa: E402
from psh.visitor.validator_visitor import ValidatorVisitor  # noqa: E402

print(f"# psh: {psh.__file__}")

CASES = [
    # (label, source) — every $y is undefined; count how often each analyzer says so.
    ("operand :-      ", 'echo "${x:-$(echo $y)}"'),
    ("operand :+      ", 'echo "${x:+$(echo $y)}"'),
    ("operand -       ", 'echo "${x-$(echo $y)}"'),
    ("operand :?      ", 'echo "${x:?$(echo $y)}"'),
    ("operand replace ", 'echo "${x/$(echo $y)/z}"'),
    ("operand plainvar", 'echo "${x:-$y}"'),          # no substitution: control
    ("assign value    ", 'FOO=$(echo $y)'),
    ("assign plainvar ", 'FOO=$y'),                   # control
    ("redirect target ", 'echo hi > $(echo $y).log'),
    ("redirect plain  ", 'echo hi > $y.log'),         # control
    ("for item        ", 'for i in $(echo $y); do :; done'),
    ("case subject    ", 'case "$(echo $y)" in a) :;; esac'),
    ("arith template  ", 'echo "$(( $(echo $y) ))"'),
    ("subscript templ ", 'a[$(echo $y)]=v'),
    ("cmd arg         ", 'echo $(echo $y)'),          # plain word-part sub: control
]


def undef_count(issues, getmsg):
    # Validator family: "Possible use of undefined variable '$y'";
    # Linter: "Variable 'y' may be undefined".
    return sum(1 for i in issues
               if "undefined" in getmsg(i)
               and ("'$y'" in getmsg(i) or "'y'" in getmsg(i)))


for label, src in CASES:
    ast = parse(tokenize(src))
    row = [label]
    for name, mk, get_issues, getmsg in [
        ("VAL", ValidatorVisitor, lambda v: v.issues, lambda i: i.message),
        ("ENH", EnhancedValidatorVisitor, lambda v: v.issues, lambda i: i.message),
        ("LNT", LinterVisitor, lambda v: v.issues, lambda i: i.message),
        ("SEC", SecurityVisitor, lambda v: v.issues, lambda i: i.message),
    ]:
        v = mk()
        v.visit(parse(tokenize(src)))
        issues = get_issues(v)
        row.append(f"{name}:total={len(issues)},undef$y={undef_count(issues, getmsg)}")
    m = MetricsVisitor()
    m.visit(parse(tokenize(src)))
    row.append(f"MET:cmds={m.metrics.total_commands}")
    print("  ".join(row))
