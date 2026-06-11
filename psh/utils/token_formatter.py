"""Token formatting utilities for debugging."""
from ..lexer.token_types import Token


class TokenFormatter:
    """Formats token lists for debug output."""

    @staticmethod
    def format(tokens):
        """Format token list for debugging output."""
        result = []
        for i, token in enumerate(tokens):
            if isinstance(token, Token):
                fd_info = f" fd={token.fd}" if token.fd is not None else ""
                result.append(f"  [{i:3d}] {token.type.name:20s} '{token.value}'{fd_info}")
            else:
                result.append(f"  [{i:3d}] {str(token)}")
        return "\n".join(result)
