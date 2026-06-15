"""Tests for parser-combinator diagnostic helpers."""

import pytest

from psh.lexer.token_types import Token, TokenType
from psh.parser.combinators.diagnostics import raise_committed_error
from psh.parser.recursive_descent.helpers import ParseError


def make_token(token_type: TokenType, value: str, position: int = 0) -> Token:
    return Token(type=token_type, value=value, position=position)


def test_raise_committed_error_uses_reported_token():
    tokens = [
        make_token(TokenType.WORD, "echo"),
        make_token(TokenType.PIPE, "|"),
        make_token(TokenType.EOF, ""),
    ]

    with pytest.raises(ParseError) as exc_info:
        raise_committed_error(tokens, 1, "Expected command after pipe")

    assert exc_info.value.error_context.token is tokens[1]
    assert exc_info.value.error_context.position == 1


def test_raise_committed_error_clamps_to_eof_token():
    tokens = [
        make_token(TokenType.WORD, "echo"),
        make_token(TokenType.EOF, ""),
    ]

    with pytest.raises(ParseError) as exc_info:
        raise_committed_error(tokens, 99, "Expected command")

    assert exc_info.value.error_context.token is tokens[-1]
    assert exc_info.value.at_eof is True
