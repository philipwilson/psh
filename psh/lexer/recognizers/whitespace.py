"""Whitespace token recognizer."""

from typing import Optional, Tuple

from ..state_context import LexerContext
from ..token_types import Token
from ..unicode_support import is_whitespace
from .base import TokenRecognizer


class WhitespaceRecognizer(TokenRecognizer):
    """Recognizes whitespace tokens.

    Whitespace is skipped (not emitted as tokens). This recognizer
    advances past whitespace and returns (None, new_pos) so the
    lexer knows where to continue.
    """

    @property
    def priority(self) -> int:
        """Low priority for whitespace."""
        return 30

    def can_recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> bool:
        """Check if current position is whitespace."""
        if pos >= len(input_text):
            return False

        char = input_text[pos]

        # Skip newlines (handled by operator recognizer)
        if char == '\n':
            return False

        # Check for whitespace (excluding newlines)
        return is_whitespace(char, posix_mode=context.posix_mode)

    def recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Optional[Tuple[Token, int]]:
        """Skip past whitespace, returning (None, new_pos)."""
        # Advance past all consecutive whitespace (except newlines)
        while pos < len(input_text):
            char = input_text[pos]
            if char == '\n' or not is_whitespace(char, posix_mode=context.posix_mode):
                break
            pos += 1

        # Return None token with new position to indicate skip
        return None, pos
