"""Base classes for token recognizers."""

from abc import ABC, abstractmethod
from typing import Optional, Tuple

from ..state_context import LexerContext
from ..token_types import Token


class TokenRecognizer(ABC):
    """Base class for token recognizers."""

    @abstractmethod
    def can_recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> bool:
        """
        Check if this recognizer can handle the current position.

        This is a fast check to determine if the recognizer should
        attempt recognition. Should be efficient as it's called frequently.

        Args:
            input_text: The input string being lexed
            pos: Current position in the input
            context: Current lexer context/state

        Returns:
            True if this recognizer might be able to recognize a token
        """
        pass

    @abstractmethod
    def recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Optional[Tuple[Token, int]]:
        """
        Attempt to recognize a token at the current position.

        Args:
            input_text: The input string being lexed
            pos: Current position in the input
            context: Current lexer context/state

        Returns:
            Tuple of (token, new_position) if recognized, None otherwise
        """
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """
        Recognition priority (higher = checked first).

        Suggested priority ranges:
        - 100-200: Operators and structural tokens
        - 80-99: Keywords and reserved words
        - 60-79: Literals and quoted strings
        - 40-59: Identifiers and variable names
        - 20-39: Whitespace and formatting
        - 1-19: Fallback recognizers
        """
        pass

    @property
    def name(self) -> str:
        """Human-readable name for this recognizer."""
        return self.__class__.__name__


class ContextualRecognizer(TokenRecognizer):
    """Base class for recognizers that need context awareness."""

    def is_valid_in_context(
        self,
        candidate: str,
        context: LexerContext
    ) -> bool:
        """
        Check if the candidate token is valid in the current context.

        Args:
            candidate: The candidate token string
            context: Current lexer context

        Returns:
            True if the token is valid in this context
        """
        return True
