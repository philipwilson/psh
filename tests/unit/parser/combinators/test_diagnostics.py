"""Tests for parser-combinator diagnostic helpers."""

import pytest

from psh.lexer.token_types import Token, TokenType
from psh.parser.combinators.diagnostics import (
    error_context_for_token,
    is_missing_nested_terminator,
    raise_committed_error,
)
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


def _error_with_message(message: str) -> ParseError:
    token = make_token(TokenType.WORD, "x", position=0, line=1, column=1)
    return ParseError(error_context_for_token(token, message))


@pytest.mark.parametrize("message", [
    "Expected 'fi' to close if statement",
    "Expected 'done' to close while loop",
    "Expected 'esac' to close case statement",
    "expected 'done' to close FOR LOOP",  # case-insensitive
])
def test_is_missing_nested_terminator_true(message):
    assert is_missing_nested_terminator(_error_with_message(message)) is True


@pytest.mark.parametrize("message", [
    "Expected 'then' in if statement",
    "Expected command after pipe",
    "Expected 'do' in while loop",
    "Unexpected token after valid input",
])
def test_is_missing_nested_terminator_false(message):
    assert is_missing_nested_terminator(_error_with_message(message)) is False
