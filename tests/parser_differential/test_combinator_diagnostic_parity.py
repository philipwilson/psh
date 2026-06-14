"""Recursive-descent vs combinator diagnostic parity.

This is narrower than full diagnostic equivalence.  It pins the stable subset
we have intentionally aligned: exception class, EOF signal, and offending
token identity.  Message text and position formatting still differ for many
cases and are tracked as follow-up work.
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


STABLE_DIAGNOSTIC_CORPUS = [
    pytest.param('()', id='empty-subshell'),
    pytest.param('( )', id='empty-subshell-spaced'),
    pytest.param('{ }', id='empty-brace-group'),
    pytest.param('(', id='unterminated-subshell'),
    pytest.param('echo >', id='redirect-missing-target-out'),
    pytest.param('cat <', id='redirect-missing-target-in'),
    pytest.param('cat <<', id='heredoc-missing-delimiter'),
    pytest.param('cat <<<', id='herestring-missing-content'),
    pytest.param('&& echo', id='and-if-missing-lhs'),
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
    )


@pytest.mark.parametrize('source', STABLE_DIAGNOSTIC_CORPUS)
def test_combinator_diagnostic_summary_matches_recursive_descent(source):
    assert _combinator_diagnostic(source) == _recursive_descent_diagnostic(source)
