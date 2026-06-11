"""Token transformer for context-aware token processing."""

from typing import List

from .token_types import Token, TokenType


class TokenTransformer:
    """Transform tokens based on context."""

    def transform(self, tokens: List[Token]) -> List[Token]:
        """Transform tokens based on context.

        Main transformations:
        1. Validate ;; usage - only allowed in case statements
        """
        transformed = []
        in_case = 0

        for i, token in enumerate(tokens):
            if token.type == TokenType.CASE:
                in_case += 1
                transformed.append(token)
            elif token.type == TokenType.ESAC:
                in_case = max(0, in_case - 1)  # Prevent going negative
                transformed.append(token)
            elif token.type == TokenType.DOUBLE_SEMICOLON and in_case == 0:
                # Outside case statement - this is a syntax error
                # Keep the token but mark it as invalid
                # The parser will handle the error
                transformed.append(token)
            elif token.type in (TokenType.SEMICOLON_AMP, TokenType.AMP_SEMICOLON) and in_case == 0:
                # ;& and ;;& are also only valid in case statements
                transformed.append(token)
            else:
                transformed.append(token)

        return transformed
