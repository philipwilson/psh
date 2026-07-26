"""B10 combinatorial coverage matrix — SHA-portable.

SPACE STATEMENT: construct families x positions, generated, not hand-picked.
Families (each embeds ONE undefined `$y` in a specific region kind):
  modern       $(echo $y)          y structurally reachable (parsed program)
  backtick     `echo $y`           y ONLY in backtick source text (program=None)
  arith-var    $(($y + 1))         y ONLY in arithmetic expression text
  arith-sub    $(( $(echo $y) ))   y structurally reachable (template sub)
  bt-in-mod    $(echo `echo $y`)   y in backtick source nested under parsed program
  mod-in-bt    `echo $(echo $y)`   y inside an unparsed backtick source
  op-mod       ${x:-$(echo $y)}    operand carrying modern sub
  op-bt        ${x:-`echo $y`}     operand carrying deferred backtick
  op-nested    ${x:-$(echo `echo $y`)}  operand: backtick nested under validated sub
Positions: cmd-arg, assign, assign-export, assign-local(fn), assign-quoted,
  assign-concat, redirect-target, for-item, case-subject.
(Heredoc bodies excluded here: bare parse doesn't collect them; their textual
reader is untouched by the B6 seams — separate subprocess spot-check.)

Prints one row per shape: undef-'y' finding count for ENH/LNT/VAL/SEC and
whether metrics recorded variable 'y'.
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

FAMILIES = [
    ("plain-var", "$y"),
    ("modern", "$(echo $y)"),
    ("backtick", "`echo $y`"),
    ("arith-var", "$(($y + 1))"),
    ("arith-sub", "$(( $(echo $y) ))"),
    ("bt-in-mod", "$(echo `echo $y`)"),
    ("mod-in-bt", "`echo $(echo $y)`"),
    ("op-mod", "${x:-$(echo $y)}"),
    ("op-bt", "${x:-`echo $y`}"),
    ("op-nested", "${x:-$(echo `echo $y`)}"),
    ("procsub", "<(echo $y)"),
]

POSITIONS = [
    ("cmd-arg", 'echo {f}'),
    ("assign", 'FOO={f}'),
    ("assign-export", 'export FOO={f}'),
    ("assign-local", 'fn() {{ local FOO={f}; }}; fn'),
    ("assign-quoted", 'FOO="{f}"'),
    ("assign-concat", 'FOO=a{f}b'),
    ("redirect", 'echo hi > {f}.log'),
    ("for-item", 'for i in {f}; do :; done'),
    ("case-subject", 'case "{f}" in a) :;; esac'),
]


def undef_y(visitor_cls, src):
    v = visitor_cls()
    v.visit(parse(tokenize(src)))
    return sum(1 for i in v.issues
               if 'undefined' in i.message
               and ("'$y'" in i.message or "'y'" in i.message))


for fname, fsrc in FAMILIES:
    for pname, ptpl in POSITIONS:
        src = ptpl.format(f=fsrc)
        try:
            counts = [undef_y(c, src) for c in
                      (EnhancedValidatorVisitor, LinterVisitor,
                       ValidatorVisitor, SecurityVisitor)]
            m = MetricsVisitor()
            m.visit(parse(tokenize(src)))
            met = 1 if 'y' in m.metrics.variable_names else 0
            print(f"{fname:10s} {pname:14s} ENH={counts[0]} LNT={counts[1]} "
                  f"VAL={counts[2]} SEC={counts[3]} METy={met}")
        except Exception as e:  # noqa: BLE001 — parse rejects are data too
            print(f"{fname:10s} {pname:14s} PARSE-ERROR {type(e).__name__}")
