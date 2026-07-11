"""Diagnostic helpers for parser-combinator commitment points."""

from typing import NoReturn, Optional, Sequence

from ...lexer.token_types import Token
from ..recursive_descent.helpers import ErrorContext, ParseError


def error_context_for_token(token: Token, message: str) -> ErrorContext:
    """Build an ErrorContext using source-position metadata from a token."""
    return ErrorContext(
        token=token,
        message=message,
        position=token.position,
        line=token.line,
        column=token.column,
    )


def raise_committed_error(
    tokens: Sequence[Token],
    pos: int,
    message: str,
    *,
    terminator: Optional[str] = None,
) -> NoReturn:
    """Raise a hard parse error after a parser has committed to a construct.

    Pass ``terminator`` (the closing keyword: ``'fi'``/``'done'``/``'esac'``)
    when the error is a compound construct failing to find its terminator; it
    tags the ``ParseError`` structurally so :func:`is_missing_nested_terminator`
    can recognise it without matching the message text.
    """
    error_pos = min(pos, len(tokens) - 1)
    error = ParseError(error_context_for_token(tokens[error_pos], message))
    error.missing_terminator = terminator
    raise error


def is_missing_nested_terminator(error: ParseError) -> bool:
    """True if ``error`` is a missing closing keyword for a nested compound.

    Used at compound-body parse boundaries to decide whether a ``ParseError``
    raised while parsing a body should be remapped onto the outer construct's
    terminator token (matching recursive descent), rather than left pointing
    inside the nested body. Reads the structured ``missing_terminator`` tag set
    by :func:`raise_committed_error` (no message string-matching).
    """
    return error.missing_terminator is not None
