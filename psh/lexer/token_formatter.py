"""Token formatting utilities for debugging.

Lives in ``psh.lexer`` (its sole dependency is ``Token``) so that ``psh.utils``
stays a runtime leaf that imports nothing from ``psh`` — the P4 layering lock
(reappraisal #19). Its one caller is ``scripting.source_processor`` (the
``--debug-tokens`` path).
"""
from typing import Any, List

from .token_types import Token


class TokenFormatter:
    """Formats token lists for debug output."""

    @staticmethod
    def format(tokens: List[Any]) -> str:
        """Format token list for debugging output."""
        result = []
        for i, token in enumerate(tokens):
            if isinstance(token, Token):
                fd_info = f" fd={token.fd}" if token.fd is not None else ""
                result.append(f"  [{i:3d}] {token.type.name:20s} '{token.value}'{fd_info}")
            else:
                result.append(f"  [{i:3d}] {str(token)}")
        return "\n".join(result)
