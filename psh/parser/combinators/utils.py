"""Shared utility functions for parser combinators."""

from ...lexer.token_types import Token


def format_token_value(token: Token) -> str:
    """Format token value based on type ($ prefix for variables).

    Args:
        token: Token to format

    Returns:
        Formatted string representation
    """
    if token.type.name == 'VARIABLE':
        return f"${token.value}"
    return token.value
