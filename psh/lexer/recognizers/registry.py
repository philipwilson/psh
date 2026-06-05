"""Registry for token recognizers."""

import logging
from typing import Dict, List, Optional, Tuple

from ...token_types import Token
from ..state_context import LexerContext
from .base import TokenRecognizer

logger = logging.getLogger(__name__)


class RecognizerRegistry:
    """Registry and dispatcher for token recognizers."""

    def __init__(self):
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

    def unregister(self, recognizer: TokenRecognizer) -> bool:
        """
        Unregister a recognizer.

        Args:
            recognizer: The recognizer to remove

        Returns:
            True if the recognizer was found and removed
        """
        try:
            self._recognizers.remove(recognizer)
            return True
        except ValueError:
            return False

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
    ) -> Optional[Tuple[Token, int, TokenRecognizer]]:
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

    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about registered recognizers.

        Returns:
            Dictionary with statistics
        """
        stats = {
            'total_recognizers': len(self._recognizers),
            'recognizer_types': {}
        }

        for recognizer in self._recognizers:
            recognizer_type = type(recognizer).__name__
            stats['recognizer_types'][recognizer_type] = (
                stats['recognizer_types'].get(recognizer_type, 0) + 1
            )

        return stats

    def clear(self) -> None:
        """Remove all registered recognizers."""
        self._recognizers.clear()
        self._sorted = True

    def __len__(self) -> int:
        """Get the number of registered recognizers."""
        return len(self._recognizers)

    def __iter__(self):
        """Iterate over recognizers in priority order."""
        return iter(self.get_recognizers())


# Default registry instance
default_registry = RecognizerRegistry()


def get_default_registry() -> RecognizerRegistry:
    """Get the default registry instance."""
    return default_registry


def setup_default_recognizers() -> RecognizerRegistry:
    """Set up the default registry with standard recognizers."""
    from .comment import CommentRecognizer
    from .literal import LiteralRecognizer
    from .operator import OperatorRecognizer
    from .process_sub import ProcessSubstitutionRecognizer
    from .whitespace import WhitespaceRecognizer

    registry = get_default_registry()
    registry.clear()

    # Register recognizers in order (priority determines actual order)
    registry.register(ProcessSubstitutionRecognizer())  # Priority 160
    registry.register(OperatorRecognizer())
    registry.register(LiteralRecognizer())
    registry.register(WhitespaceRecognizer())
    registry.register(CommentRecognizer())

    return registry
