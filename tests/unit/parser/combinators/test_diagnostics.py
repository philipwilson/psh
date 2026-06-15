"""Tests for parser-combinator diagnostic helpers."""

import pytest

from psh.lexer.token_types import Token, TokenType
from psh.parser.combinators.diagnostics import raise_committed_error
from psh.parser.recursive_descent.helpers import ParseError


def make_token(
    token_type: TokenType,
    value: str,
    position: int = 0,
    line: int | None = None,
    column: int | None = None,
) -> Token:
    return Token(type=token_type, value=value, position=position, line=line, column=column)


def test_raise_committed_error_uses_reported_token():
    tokens = [
        make_token(TokenType.WORD, "echo", position=0, line=1, column=1),
        make_token(TokenType.PIPE, "|", position=5, line=1, column=6),
        make_token(TokenType.EOF, "", position=6, line=1, column=7),
    ]

    with pytest.raises(ParseError) as exc_info:
        raise_committed_error(tokens, 1, "Expected command after pipe")

    assert exc_info.value.error_context.token is tokens[1]
    assert exc_info.value.error_context.position == 5
    assert exc_info.value.error_context.line == 1
    assert exc_info.value.error_context.column == 6


def test_raise_committed_error_clamps_to_eof_token():
    tokens = [
        make_token(TokenType.WORD, "echo", position=0, line=1, column=1),
        make_token(TokenType.EOF, "", position=4, line=1, column=5),
    ]

    with pytest.raises(ParseError) as exc_info:
        raise_committed_error(tokens, 99, "Expected command")

    assert exc_info.value.error_context.token is tokens[-1]
    assert exc_info.value.error_context.position == 4
    assert exc_info.value.error_context.column == 5
    assert exc_info.value.at_eof is True
