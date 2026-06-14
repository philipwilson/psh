"""Recursive-descent vs combinator AST parity.

This is the first production-readiness gate for the combinator parser.  The
goal is stricter than "both parsers accept the input": both parsers must produce
the same canonical AST shape for the same token stream.

Known combinator drifts should be added as strict xfails while they are being
worked down, then moved into PARITY_CORPUS when fixed.
"""

import dataclasses
from enum import Enum

import pytest

from psh.ast_nodes import ASTNode, StatementList, TopLevel
from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.combinators.parser import ParserCombinatorShellParser

PARITY_CORPUS = [
    pytest.param('echo hello world', id='simple-command'),
    pytest.param('echo "a b" c', id='quoted-word'),
    pytest.param("echo 'lit $x'", id='single-quoted-literal'),
    pytest.param('echo a"b"$c', id='composite-word'),
    pytest.param('echo $x ${x:-d} ${#x} a${x}b',
                 id='parameter-expansions'),
    pytest.param('echo $(date) `pwd` $((1 + 2))',
                 id='command-and-arithmetic-substitution'),
    pytest.param('cat <(echo a) >(cat)', id='process-substitution-args'),
    pytest.param('cmd1 -o v | cmd2 |& cmd3', id='pipeline-and-pipe-stderr'),
    pytest.param('NAME=val cmd arg', id='prefix-assignment-command'),
    pytest.param('a=1 b=$x echo c', id='multiple-prefix-assignments'),
    pytest.param('for x in a b c; do echo $x; done',
                 id='for-loop-explicit-items'),
    pytest.param('for x; do echo $x; done',
                 id='for-loop-default-positional-params'),
    pytest.param('select x in a b; do echo $x; done', id='select-loop'),
    pytest.param('for ((i=0; i<3; i++)); do echo $i; done',
                 id='c-style-for-loop'),
    pytest.param('case $x in a) ;; b|c) ;; *) ;; esac',
                 id='case-patterns'),
    pytest.param('if true; then echo yes; else echo no; fi',
                 id='if-else'),
    pytest.param('echo hi > out.txt 2>&1', id='redirect-target-metadata'),
    pytest.param('cat <<< "$payload"', id='here-string-quoted-word'),
    pytest.param('f() { echo hi; } > out.txt',
                 id='function-definition-redirect'),
    pytest.param('(echo hi)', id='subshell-group'),
    pytest.param('{ echo hi; }', id='brace-group'),
    pytest.param('a=(1 2 3)', id='indexed-array-init'),
    pytest.param('a=("x y" z)', id='quoted-array-init'),
    pytest.param('a=([2]=x [5]=y)', id='explicit-index-array-init'),
    pytest.param('declare -a a=(1 2 3)', id='declaration-array-init'),
    pytest.param('a=()', id='empty-array-init'),
    pytest.param('a+=(four five)', id='append-array-init'),
    pytest.param('a[0]=x', id='array-element-assignment'),
    pytest.param('a[i+1]=y', id='array-element-arithmetic-index'),
    pytest.param('echo hi >> out.txt', id='redirect-append'),
    pytest.param('echo hi 2> err.txt', id='redirect-stderr-file'),
    pytest.param('echo hi >&2', id='redirect-dup-word'),
    pytest.param('echo hi 2>&-', id='redirect-close-fd'),
    pytest.param('echo hi &> both.txt', id='combined-redirect'),
    pytest.param('echo hi <> rw.txt', id='readwrite-redirect'),
    pytest.param('cat < input.txt > output.txt', id='multiple-file-redirects'),
    pytest.param('cat <<EOF\nhello\nEOF', id='heredoc-basic'),
    pytest.param('a=("x""y" z)', id='array-adjacent-quoted-element'),
    pytest.param('a=($(echo one) $((2+3)) ${name:-fallback})',
                 id='array-expansion-elements'),
    pytest.param('a=([foo]=bar [baz]="qux")',
                 id='array-assoc-key-like-elements'),
    pytest.param('a[0]="x y"', id='array-element-quoted-value'),
    pytest.param('a[0]=pre$var"post"', id='array-element-composite-value'),
    pytest.param('arr += (one two)', id='array-spaced-append-init'),
    pytest.param('(echo hi) > out.txt', id='subshell-redirect'),
    pytest.param('{ echo hi; } > out.txt', id='brace-redirect'),
    pytest.param('(echo hi) &', id='subshell-background'),
    pytest.param('{ echo hi; } &', id='brace-background'),
    pytest.param('if true; then echo yes; fi > out.txt', id='if-redirect'),
    pytest.param('case $x in "a b") echo spaced ;; esac',
                 id='case-quoted-pattern'),
    pytest.param('function f { echo hi; }', id='function-keyword-brace'),
    pytest.param('function f() { echo hi; }', id='function-keyword-parens'),
    pytest.param('f() { echo hi; }', id='function-posix'),
    pytest.param('f() { echo hi; } 2>err', id='function-stderr-redirect'),
    pytest.param('[[ -n $x ]]', id='enhanced-test-unary'),
    pytest.param('[[ $x == a* ]]', id='enhanced-test-binary-glob'),
    pytest.param('(( count += 1 ))', id='arithmetic-evaluation'),
    pytest.param('! echo no', id='negated-pipeline'),
    pytest.param('echo a && echo b || echo c', id='and-or-chain'),
    pytest.param('break', id='break-statement'),
    pytest.param('continue', id='continue-statement'),
    pytest.param('while true; do break; done > out.txt',
                 id='while-redirect-break-body'),
    pytest.param('while true; do continue; done',
                 id='while-continue-body'),
]


def _parse_rd(source):
    return Parser(tokenize(source), source_text=source).parse()


def _parse_combinator(source):
    return ParserCombinatorShellParser().parse(tokenize(source))


def _program_items(ast):
    """Normalize parser-root wrappers without hiding nested AST differences."""
    if isinstance(ast, TopLevel):
        return ast.items
    if isinstance(ast, StatementList):
        return ast.statements
    return [ast]


def _canonical_ast(value):
    """Convert AST dataclasses into plain nested values for equality checks."""
    if isinstance(value, Enum):
        return value.name
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, list):
        return [_canonical_ast(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_canonical_ast(item) for item in value)
    if isinstance(value, (TopLevel, StatementList)):
        return {
            'type': 'Program',
            'items': _canonical_ast(_program_items(value)),
        }
    if isinstance(value, ASTNode) and dataclasses.is_dataclass(value):
        return {
            'type': type(value).__name__,
            **{
                field.name: _canonical_ast(getattr(value, field.name))
                for field in dataclasses.fields(value)
            },
        }
    if dataclasses.is_dataclass(value):
        return {
            'type': type(value).__name__,
            **{
                field.name: _canonical_ast(getattr(value, field.name))
                for field in dataclasses.fields(value)
            },
        }
    return repr(value)


def assert_combinator_matches_recursive_descent(source):
    rd_ast = _canonical_ast(_parse_rd(source))
    combinator_ast = _canonical_ast(_parse_combinator(source))
    assert combinator_ast == rd_ast


@pytest.mark.parametrize('source', PARITY_CORPUS)
def test_combinator_ast_matches_recursive_descent(source):
    assert_combinator_matches_recursive_descent(source)
