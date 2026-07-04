"""Centralized parser context for PSH.

This module provides the ParserContext class that consolidates all parser
state into a single object: the token stream and position, the parser
configuration, error collection, and source text for error messages.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from ...lexer.token_types import Token, TokenType
from ..config import ParserConfig
from .helpers import ErrorContext, ErrorSeverity, ParseError


@dataclass
class ParserContext:
    """Centralized parser state management.

    Consolidates the parser's real state — token stream, position, config,
    error collection, and source context — behind one object shared by the
    main parser and all sub-parsers.
    """

    # Core parsing state
    tokens: List[Token]
    current: int = 0
    config: ParserConfig = field(default_factory=ParserConfig)

    # Error handling
    errors: List[ParseError] = field(default_factory=list)
    fatal_error: Optional[ParseError] = None

    # Source context
    source_text: Optional[str] = None
    source_lines: Optional[List[str]] = None

    # Current compound-command nesting depth. Incremented/decremented by
    # CommandParser.parse_pipeline_component — the single chokepoint every
    # nested compound (brace group, subshell, if/while/for/case/select,
    # ((...)), [[...]]) parses through — and checked there against
    # MAX_NESTING_DEPTH so runaway nesting raises a clean ParseError
    # instead of a Python RecursionError (the statement-parser analogue of
    # ArithParser.MAX_DEPTH). Flat &&/||/pipe/`;` chains parse iteratively
    # and never accumulate depth.
    nesting_depth: int = 0

    # Open-construct trail for incomplete-input hints. Parse methods push a
    # name when they consume an opening keyword ('if', 'while', 'case',
    # 'brace', ...), retitle it at internal transitions ('if' → 'then' →
    # 'else'), and pop it when the closer is consumed. NO parse decision
    # ever reads this list — the recursive call structure remains the
    # parser's real grammar context. It exists for exactly one consumer:
    # when a parse fails at end of input (ParseError.at_eof), the
    # CommandAccumulator snapshots it as the honest answer to "which
    # constructs are still open?", which drives the interactive
    # continuation prompt ("if> ", "for then> "). On a successful parse
    # it is balanced back to empty; after a failed parse the whole
    # context is discarded with its parser.
    open_constructs: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Initialize derived state."""
        if self.source_text and not self.source_lines:
            self.source_lines = self.source_text.splitlines()

    # === Open-construct trail (incomplete-input hints only) ===

    def push_construct(self, name: str) -> None:
        """Record that an opening keyword was consumed ('if', 'while', ...)."""
        self.open_constructs.append(name)

    def retitle_construct(self, name: str) -> None:
        """Rename the innermost open construct at an internal transition
        (e.g. 'if' → 'then' once THEN is consumed)."""
        if self.open_constructs:
            self.open_constructs[-1] = name

    def pop_construct(self) -> None:
        """Record that the innermost construct's closer was consumed."""
        if self.open_constructs:
            self.open_constructs.pop()

    # === Token Access Methods ===

    def peek(self, offset: int = 0) -> Token:
        """Look at current token + offset without consuming."""
        pos = self.current + offset
        if pos < len(self.tokens):
            return self.tokens[pos]
        return self.tokens[-1] if self.tokens else Token(TokenType.EOF, "", 0)

    def advance(self) -> Token:
        """Consume and return current token."""
        token = self.peek()
        if self.current < len(self.tokens) - 1:
            self.current += 1
        return token

    def at_end(self) -> bool:
        """Check if at end of tokens."""
        return self.peek().type == TokenType.EOF

    def match(self, *token_types: TokenType) -> bool:
        """Check if current token matches any of the given types."""
        return self.peek().type in token_types

    def consume(self, token_type: TokenType, error_message: Optional[str] = None) -> Token:
        """Consume token of expected type or raise error."""
        if self.match(token_type):
            return self.advance()

        current = self.peek()
        message = error_message or f"Expected {token_type}, got {current.type}"

        # Create error with context
        error_context = self._create_error_context(message, current)
        error = ParseError(error_context)

        if self.config.collect_errors:
            self.add_error(error)
            return current  # Return current token to continue parsing
        else:
            raise error

    def _create_error_context(self, message: str, token: Token):
        """Create error context with source information."""
        source_line = None
        if self.source_lines and token.line and 0 < token.line <= len(self.source_lines):
            source_line = self.source_lines[token.line - 1]

        error_context = ErrorContext(
            token=token,
            message=message,
            position=token.position,
            line=token.line,
            column=token.column,
            source_line=source_line
        )

        # Enhance error context with suggestions and context tokens
        self._enhance_error_context(error_context, token)

        return error_context

    @staticmethod
    def _display_token(tok) -> str:
        """Human-readable token text for the "Context:" line.

        Renders the token's value when it has one; for valueless tokens
        (EOF, NEWLINE) show a friendly placeholder rather than leaking a
        raw ``TokenType.EOF`` repr.
        """
        from ...lexer.token_types import TokenType
        if tok.value:
            return tok.value
        if tok.type == TokenType.EOF:
            return '<EOF>'
        if tok.type == TokenType.NEWLINE:
            return '<newline>'
        return f'<{tok.type.name.lower()}>'

    def _enhance_error_context(self, error_context, token):
        """Enhance error context with smart suggestions and context tokens."""
        # Add context tokens (up to 3 before and after current position),
        # kept on separate sides so they render correctly around -> HERE <-.
        context_before = []
        for i in range(max(0, self.current - 3), self.current):
            if i < len(self.tokens):
                context_before.append(self._display_token(self.tokens[i]))

        context_after = []
        for i in range(self.current + 1, min(len(self.tokens), self.current + 4)):
            context_after.append(self._display_token(self.tokens[i]))

        error_context.context_before = context_before
        error_context.context_after = context_after
        # Flat list retained for backward compatibility (before + after).
        error_context.context_tokens = context_before + context_after

        # Add contextual suggestions based on message
        if "Expected TokenType.THEN" in error_context.message:
            error_context.suggestions.append("Add ';' before 'then' keyword")
        elif "Expected TokenType.DO" in error_context.message:
            error_context.suggestions.append("Add ';' before 'do' keyword")
        elif "Expected TokenType.RPAREN" in error_context.message:
            error_context.suggestions.append("Add ')' to close parentheses")
        elif "Expected TokenType.RBRACE" in error_context.message:
            error_context.suggestions.append("Add '}' to close brace group")
        elif "Expected TokenType.FI" in error_context.message:
            error_context.suggestions.append("Add 'fi' to close if statement")

    # === Error Collection ===

    def should_collect_errors(self) -> bool:
        """Check if errors should be collected rather than thrown."""
        return self.config.collect_errors or bool(self.errors)

    def add_error(self, error: ParseError) -> None:
        """Add error to the error list, checking for fatal errors."""
        if len(self.errors) < self.config.max_errors:
            self.errors.append(error)

        # Check if this is a fatal error
        if (hasattr(error.error_context, 'severity') and
            error.error_context.severity == ErrorSeverity.FATAL):
            self.fatal_error = error

    def can_continue_parsing(self) -> bool:
        """Check if parsing can continue."""
        if self.at_end():
            return False

        if self.fatal_error:
            return False

        if self.config.collect_errors:
            return len(self.errors) < self.config.max_errors

        return True
