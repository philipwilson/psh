"""Recursive-descent vs combinator diagnostic parity.

This is narrower than full diagnostic equivalence.  It pins the stable subset
we have intentionally aligned: exception class, EOF signal, and offending
token identity plus source position.  Message text still differs for many cases
and is tracked as follow-up work.
"""

from dataclasses import dataclass

import pytest

from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.combinators.parser import ParserCombinatorShellParser


@dataclass(frozen=True)
class DiagnosticSummary:
    exception_type: str
    at_eof: bool
    token_type: str
    token_value: str
    position: int
    line: int | None
    column: int | None


STABLE_DIAGNOSTIC_CORPUS = [
    pytest.param('()', id='empty-subshell'),
    pytest.param('( )', id='empty-subshell-spaced'),
    pytest.param('{ }', id='empty-brace-group'),
    pytest.param('(', id='unterminated-subshell'),
    pytest.param('{ echo hi', id='unterminated-brace-group'),
    pytest.param('if true; then echo yes', id='unterminated-if'),
    pytest.param('if true echo yes; fi', id='if-missing-then'),
    pytest.param('if true; then; fi', id='if-empty-then'),
    pytest.param('if true; then if true; then echo x; fi', id='nested-if-missing-fi'),
    pytest.param('if true; then if true echo x; fi; fi', id='nested-if-missing-then'),
    pytest.param('while true; do echo x', id='unterminated-while'),
    pytest.param('while true; do while true; do echo x; done', id='nested-while-missing-done'),
    pytest.param('while true; do; done', id='while-empty-body'),
    pytest.param('until true; do; done', id='until-empty-body'),
    pytest.param('for x in a b; do echo $x', id='unterminated-for'),
    pytest.param('for x in a; do; done', id='for-empty-body'),
    pytest.param('case x in a) echo a', id='unterminated-case'),
    pytest.param('case x in ; esac', id='case-empty-pattern-list'),
    pytest.param('case x in a) case y in b) echo b ;; esac', id='nested-case-missing-esac'),
    pytest.param('case a b in x) echo x ;; esac', id='case-extra-subject-word'),
    pytest.param('a=(1 2', id='unterminated-array-initializer'),
    pytest.param('f() { echo hi', id='unterminated-posix-function'),
    pytest.param('function f {', id='unterminated-function-keyword'),
    pytest.param('function { echo hi; }', id='function-missing-name'),
    pytest.param('[[ -n $x', id='unterminated-enhanced-test'),
    pytest.param('[[ $x == ]]', id='enhanced-test-missing-rhs'),
    pytest.param('for ((i=0; i<3; i++); do echo $i; done', id='unterminated-c-style-for'),
    pytest.param('for ((i=0; i<1; i++)); do; done', id='c-style-for-empty-body'),
    pytest.param('echo >', id='redirect-missing-target-out'),
    pytest.param('cat <', id='redirect-missing-target-in'),
    pytest.param('cat <<', id='heredoc-missing-delimiter'),
    pytest.param('cat <<<', id='herestring-missing-content'),
    pytest.param('echo |', id='pipeline-missing-rhs'),
    pytest.param('echo |&', id='pipeline-stderr-missing-rhs'),
    pytest.param('echo &&', id='and-if-missing-rhs'),
    pytest.param('echo ||', id='or-if-missing-rhs'),
    pytest.param('&& echo', id='and-if-missing-lhs'),
    pytest.param('|| echo', id='or-if-missing-lhs'),
    pytest.param('echo ; && echo', id='and-if-after-separator'),
    pytest.param('echo ; | cat', id='pipe-after-separator'),
    pytest.param('echo | ;', id='pipe-before-separator'),
    pytest.param('echo && ;', id='and-if-before-separator'),
    pytest.param('if true; then echo x; fi >', id='if-trailing-redirect-missing-target'),
    pytest.param('{ echo x; } <', id='brace-trailing-redirect-missing-target'),
    pytest.param('while true; do echo x; done 2>', id='while-trailing-redirect-missing-target'),
    pytest.param('( echo x ) >', id='subshell-trailing-redirect-missing-target'),
]


def _recursive_descent_diagnostic(source):
    try:
        Parser(tokenize(source), source_text=source).parse()
    except Exception as error:
        return _summarize(error)
    raise AssertionError(f"recursive descent unexpectedly accepted {source!r}")


def _combinator_diagnostic(source):
    try:
        ParserCombinatorShellParser().parse(tokenize(source))
    except Exception as error:
        return _summarize(error)
    raise AssertionError(f"combinator unexpectedly accepted {source!r}")


def _summarize(error):
    context = getattr(error, 'error_context', None)
    token = getattr(context, 'token', None)
    return DiagnosticSummary(
        exception_type=type(error).__name__,
        at_eof=bool(getattr(error, 'at_eof', False)),
        token_type=token.type.name if token else '',
        token_value=token.value if token else '',
        position=getattr(context, 'position', -1),
        line=getattr(context, 'line', None),
        column=getattr(context, 'column', None),
    )


@pytest.mark.parametrize('source', STABLE_DIAGNOSTIC_CORPUS)
def test_combinator_diagnostic_summary_matches_recursive_descent(source):
    assert _combinator_diagnostic(source) == _recursive_descent_diagnostic(source)
