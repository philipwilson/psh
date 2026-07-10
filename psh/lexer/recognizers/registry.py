"""Registry for token recognizers."""

import logging
from typing import Iterator, List, Optional, Tuple

from ..state_context import LexerContext
from ..token_types import Token
from .base import TokenRecognizer

logger = logging.getLogger(__name__)


class RecognizerRegistry:
    """Registry and dispatcher for token recognizers.

    Recognizers are tried in **registration order** — the first one to match
    wins. There is no priority sorting: the caller registers recognizers in the
    exact order they should be dispatched (see
    ``ModularLexer._setup_recognizers``, the one place that order is declared).
    This makes the dispatch sequence a single, readable list instead of a set
    of numeric priorities spread across the recognizer classes.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._recognizers: List[TokenRecognizer] = []

    def register(self, recognizer: TokenRecognizer) -> None:
        """
        Register a new token recognizer.

        The recognizer is appended to the dispatch order; recognizers are tried
        in the order they were registered.

        Args:
            recognizer: The recognizer to register
        """
        self._recognizers.append(recognizer)

    def get_recognizers(self) -> List[TokenRecognizer]:
        """
        Get all registered recognizers, in dispatch (registration) order.

        Returns:
            List of recognizers in the order they are tried
        """
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
        for recognizer in self._recognizers:
            try:
                if recognizer.can_recognize(input_text, pos, context):
                    result = recognizer.recognize(input_text, pos, context)
                    if result is not None:
                        token, new_pos = result
                        return token, new_pos, recognizer
            except RecursionError:
                # The interpreter recursion limit is psh's implicit FUNCNEST
                # (an EXPECTED shell error — see core/internal_errors.py), not
                # a recognizer defect. Let it propagate unwrapped so the
                # nearest function-call boundary can convert runaway recursion
                # (e.g. `f(){ eval f; }; f`, whose ceiling can land inside the
                # lexer) into bash's "maximum function nesting level exceeded".
                raise
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

    def __len__(self) -> int:
        """Get the number of registered recognizers."""
        return len(self._recognizers)

    def __iter__(self) -> Iterator[TokenRecognizer]:
        """Iterate over recognizers in dispatch (registration) order."""
        return iter(self.get_recognizers())
