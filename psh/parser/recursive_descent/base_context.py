"""Base parser class using centralized ParserContext."""

from typing import AbstractSet, Optional

from ...lexer.token_types import Token, TokenType
from .context import ParserContext
from .helpers import ParseError


class ContextBaseParser:
    """Base parser with ParserContext for centralized state management.

    This is the new base parser that uses ParserContext instead of managing
    state directly. It provides cleaner interfaces and better maintainability.
    """

    def __init__(self, ctx: ParserContext):
        self.ctx = ctx

    # === Token Operations (delegated to context) ===

    def peek(self, offset: int = 0) -> Token:
        """Look at current token + offset without consuming."""
        return self.ctx.peek(offset)

    def advance(self) -> Token:
        """Consume and return current token."""
        return self.ctx.advance()

    def at_end(self) -> bool:
        """Check if at end of tokens."""
        return self.ctx.at_end()

    def match(self, *token_types: TokenType) -> bool:
        """Check if current token matches any of the given types."""
        return self.ctx.match(*token_types)

    def expect(self, token_type: TokenType, message: Optional[str] = None) -> Token:
        """Consume token of expected type or raise error."""
        return self.ctx.consume(token_type, message)

    def consume_if(self, token_type: TokenType) -> Optional[Token]:
        """Consume token if it matches type, otherwise return None."""
        if self.match(token_type):
            return self.advance()
        return None

    # === Error Handling ===

    def error(self, message: str, token: Optional[Token] = None) -> ParseError:
        """Create a ParseError with context."""
        if token is None:
            token = self.peek()

        error_context = self.ctx._create_error_context(message, token)
        return ParseError(error_context)

    def should_collect_errors(self) -> bool:
        """Check if errors should be collected rather than thrown."""
        return self.ctx.should_collect_errors()

    def add_error(self, error: ParseError) -> bool:
        """Add error to context and return whether parsing should continue."""
        if self.ctx.config.collect_errors:
            self.ctx.add_error(error)
            return self.ctx.can_continue_parsing()
        else:
            raise error

    # === Utility Methods ===

    def skip_newlines(self):
        """Skip over newline tokens."""
        while self.match(TokenType.NEWLINE):
            self.advance()

    def skip_separators(self):
        """Skip over statement separators (newlines, semicolons)."""
        while self.match(TokenType.NEWLINE, TokenType.SEMICOLON):
            self.advance()

    def match_any(self, token_types: AbstractSet[TokenType]) -> bool:
        """Check if current token matches any in the set."""
        return self.peek().type in token_types


