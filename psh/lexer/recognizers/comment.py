"""Comment token recognizer."""

from typing import Optional, Tuple

from ..state_context import LexerContext
from ..token_types import Token
from .base import ContextualRecognizer

# Operators/metacharacters after which a '#' begins a comment (besides
# whitespace and start-of-input). NOTE: ')' and '}' are deliberately NOT
# in this set. This is the single comment-start definition shared by
# CommentRecognizer and LiteralRecognizer: because LiteralRecognizer runs
# at higher priority and collects any '#' this predicate rejects into the
# current word, both recognizers must agree — a wider set here would be
# unreachable (the literal recognizer would have consumed the '#' first)
# and a wider set in the literal recognizer would split words like the
# extglob pattern a@(b)#c.
_COMMENT_PRECEDING_OPS = frozenset('|&;({')


def is_comment_start(input_text: str, pos: int) -> bool:
    """Return True when ``#`` at ``pos`` starts a comment.

    A ``#`` starts a comment at the beginning of input, after whitespace,
    or after one of the operators in ``_COMMENT_PRECEDING_OPS``.
    """
    if pos == 0:
        return True

    prev_char = input_text[pos - 1]
    return prev_char in ' \t\n\r' or prev_char in _COMMENT_PRECEDING_OPS


class CommentRecognizer(ContextualRecognizer):
    """Recognizes shell comments."""

    @property
    def priority(self) -> int:
        """Medium priority for comments."""
        return 60

    def can_recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> bool:
        """Check if current position starts a comment."""
        if pos >= len(input_text):
            return False

        char = input_text[pos]

        # Comments start with #
        if char != '#':
            return False

        # Check if # is actually starting a comment (not part of a word)
        return is_comment_start(input_text, pos)

    def recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Optional[Tuple[Token, int]]:
        """Skip past comment, returning (None, new_pos)."""
        # Advance past all characters until end of line
        while pos < len(input_text) and input_text[pos] != '\n':
            pos += 1

        # Return None token with new position to indicate skip
        return None, pos
