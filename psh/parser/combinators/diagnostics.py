"""Diagnostic helpers for parser-combinator commitment points."""

from typing import NoReturn, Sequence

from ...lexer.token_types import Token
from ..recursive_descent.helpers import ErrorContext, ParseError


def error_context_for_token(token: Token, message: str, *, expected: list[str] | None = None) -> ErrorContext:
    """Build an ErrorContext using source-position metadata from a token."""
    return ErrorContext(
        token=token,
        expected=expected or [],
        message=message,
        position=token.position,
        line=token.line,
        column=token.column,
    )


def raise_committed_error(tokens: Sequence[Token], pos: int, message: str) -> NoReturn:
    """Raise a hard parse error after a parser has committed to a construct."""
    error_pos = min(pos, len(tokens) - 1)
    raise ParseError(error_context_for_token(tokens[error_pos], message))


def is_missing_nested_terminator(error: ParseError) -> bool:
    """True if ``error`` is a missing closing keyword for a nested compound.

    Used at compound-body parse boundaries to decide whether a ``ParseError``
    raised while parsing a body should be remapped onto the outer construct's
    terminator token (matching recursive descent), rather than left pointing
    inside the nested body.
    """
    message = error.message.lower()
    return (
        "expected 'fi' to close" in message
        or "expected 'done' to close" in message
        or "expected 'esac' to close" in message
    )
