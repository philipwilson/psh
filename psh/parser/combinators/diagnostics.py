"""Diagnostic helpers for parser-combinator commitment points."""

from typing import NoReturn, Sequence

from ...lexer.token_types import Token
from ..recursive_descent.helpers import ErrorContext, ParseError


def raise_committed_error(tokens: Sequence[Token], pos: int, message: str) -> NoReturn:
    """Raise a hard parse error after a parser has committed to a construct."""
    error_pos = min(pos, len(tokens) - 1)
    raise ParseError(ErrorContext(
        token=tokens[error_pos],
        message=message,
        position=error_pos,
    ))
