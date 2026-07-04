"""Registry for token recognizers."""

import logging
from typing import Iterator, List, Optional, Tuple

from ..state_context import LexerContext
from ..token_types import Token
from .base import TokenRecognizer

logger = logging.getLogger(__name__)


class RecognizerRegistry:
    """Registry and dispatcher for token recognizers."""

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._recognizers: List[TokenRecognizer] = []
        self._sorted = False

    def register(self, recognizer: TokenRecognizer) -> None:
        """
        Register a new token recognizer.

        Args:
            recognizer: The recognizer to register
        """
        self._recognizers.append(recognizer)
        self._sorted = False  # Need to re-sort by priority

    def get_recognizers(self) -> List[TokenRecognizer]:
        """
        Get all registered recognizers, sorted by priority.

        Returns:
            List of recognizers sorted by priority (highest first)
        """
        if not self._sorted:
            self._recognizers.sort(key=lambda r: r.priority, reverse=True)
            self._sorted = True

        return self._recognizers.copy()

    def recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Optional[Tuple[Optional[Token], int, TokenRecognizer]]:
        """
        Try to recognize a token using registered recognizers.

        Args:
            input_text: The input string being lexed
            pos: Current position in the input
            context: Current lexer context/state

        Returns:
            Tuple of (token, new_position, recognizer) if recognized, None otherwise
        """
        if not self._sorted:
            self._recognizers.sort(key=lambda r: r.priority, reverse=True)
            self._sorted = True

        for recognizer in self._recognizers:
            try:
                if recognizer.can_recognize(input_text, pos, context):
                    result = recognizer.recognize(input_text, pos, context)
                    if result is not None:
                        token, new_pos = result
                        return token, new_pos, recognizer
            except Exception as e:
                # Recognizers are contracted to return None when they cannot
                # handle the input, not to raise. A raised exception therefore
                # signals a defect — surface it with context instead of silently
                # skipping the recognizer and mis-tokenizing.
                raise RuntimeError(
                    f"recognizer {recognizer.name!r} failed at position {pos}: {e}"
                ) from e

        return None

    def clear(self) -> None:
        """Remove all registered recognizers."""
        self._recognizers.clear()
        self._sorted = True

    def __len__(self) -> int:
        """Get the number of registered recognizers."""
        return len(self._recognizers)

    def __iter__(self) -> Iterator[TokenRecognizer]:
        """Iterate over recognizers in priority order."""
        return iter(self.get_recognizers())
