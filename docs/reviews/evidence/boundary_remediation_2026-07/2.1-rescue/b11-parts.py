"""B11: part shapes + quote context per quoting form (no shell-escaping traps)."""
import dataclasses
import os
import sys

sys.path.insert(0, os.getcwd())

from psh.ast_nodes import ASTNode, ExpansionPart, LiteralPart  # noqa: E402
from psh.lexer import tokenize  # noqa: E402
from psh.parser import parse  # noqa: E402


def walk(n):
    yield n
    if dataclasses.is_dataclass(n):
        for f in dataclasses.fields(n):
            v = getattr(n, f.name, None)
            if isinstance(v, ASTNode):
                yield from walk(v)
            elif isinstance(v, (list, tuple)):
                for i in v:
                    if isinstance(i, ASTNode):
                        yield from walk(i)


CASES = {
    'unquoted-live': '[[ $(echo hi) == y ]]',
    'unquoted-esc': '[[ \\$(echo hi) == y ]]',
    'dquoted-live': '[[ "$(echo hi)" == y ]]',
    'dquoted-esc': '[[ "\\$(echo hi)" == y ]]',
    'dquoted-bt': '[[ "`echo hi`" == y ]]',
    'dollarsq-live': "[[ $'$(echo hi)' == y ]]",
    'dollarsq-esc': "[[ $'\\$(echo hi)' == y ]]",
    'dollarsq-bt': "[[ $'`echo hi`' == y ]]",
    'sq-live': "[[ '$(echo hi)' == y ]]",
}

for name, src in CASES.items():
    try:
        ast = parse(tokenize(src))
    except Exception as e:  # noqa: BLE001
        print(f"{name:15s} PARSE-ERROR {type(e).__name__}: {e}")
        continue
    parts = []
    for n in walk(ast):
        if isinstance(n, LiteralPart):
            parts.append(('LIT', n.text, n.quote_char))
        elif isinstance(n, ExpansionPart):
            parts.append(('EXP', type(n.expansion).__name__, n.quote_char))
    print(f"{name:15s} {parts}")
