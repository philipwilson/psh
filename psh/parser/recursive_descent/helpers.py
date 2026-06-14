"""Helper classes for the parser module."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set

from ...core.exceptions import PshError
from ...lexer.token_types import Token, TokenType


class ErrorSeverity(Enum):
    """Severity levels for parse errors."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class TokenGroups:
    """Groups of related tokens for cleaner matching."""

    # Word-like tokens that can appear as command arguments
    WORD_LIKE: Set[TokenType] = frozenset({
        TokenType.WORD, TokenType.STRING, TokenType.VARIABLE,
        TokenType.COMMAND_SUB, TokenType.COMMAND_SUB_BACKTICK,
        TokenType.ARITH_EXPANSION, TokenType.PARAM_EXPANSION,
        TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT,
        TokenType.LBRACKET, TokenType.RBRACKET,
        TokenType.LBRACE, TokenType.RBRACE, TokenType.COMPOSITE,
        TokenType.RETURN
    })

    # Redirect operators
    REDIRECTS: Set[TokenType] = frozenset({
        TokenType.REDIRECT_IN, TokenType.REDIRECT_OUT,
        TokenType.REDIRECT_APPEND, TokenType.HEREDOC,
        TokenType.HEREDOC_STRIP, TokenType.HERE_STRING,
        TokenType.REDIRECT_DUP,
        TokenType.REDIRECT_READWRITE,
        TokenType.REDIRECT_CLOBBER,
    })

    # Control structure keywords
    CONTROL_KEYWORDS: Set[TokenType] = frozenset({
        TokenType.IF, TokenType.WHILE, TokenType.UNTIL, TokenType.FOR,
        TokenType.CASE, TokenType.SELECT, TokenType.BREAK, TokenType.CONTINUE,
        TokenType.DOUBLE_LBRACKET, TokenType.DOUBLE_LPAREN
    })

    # Statement separators
    STATEMENT_SEPARATORS: Set[TokenType] = frozenset({
        TokenType.SEMICOLON, TokenType.NEWLINE
    })

    # Case statement terminators
    CASE_TERMINATORS: Set[TokenType] = frozenset({
        TokenType.DOUBLE_SEMICOLON, TokenType.SEMICOLON_AMP,
        TokenType.AMP_SEMICOLON
    })

    # Command list end tokens
    COMMAND_LIST_END: Set[TokenType] = frozenset({
        TokenType.EOF, TokenType.FI, TokenType.DONE,
        TokenType.ELSE, TokenType.ELIF, TokenType.ESAC,
        TokenType.RBRACE
    })

    # Keywords that can be valid case patterns
    CASE_PATTERN_KEYWORDS: Set[TokenType] = frozenset({
        TokenType.IF, TokenType.THEN, TokenType.ELSE, TokenType.FI, TokenType.ELIF,
        TokenType.WHILE, TokenType.UNTIL, TokenType.DO, TokenType.DONE, TokenType.FOR, TokenType.IN,
        TokenType.BREAK, TokenType.CONTINUE, TokenType.RETURN, TokenType.CASE, TokenType.ESAC,
        TokenType.SELECT, TokenType.FUNCTION
    })


# Note: ParseContext has been removed. Use ParserContext from context.py instead.
# All state tracking is now centralized in ParserContext.


@dataclass
class ErrorContext:
    """Enhanced error context for better error messages."""

    token: Token
    expected: List[str] = field(default_factory=list)
    message: str = ""
    position: int = 0
    line: Optional[int] = None
    column: Optional[int] = None
    source_line: Optional[str] = None

    # Enhanced error information (populated by ParserContext._enhance_error_context)
    suggestions: List[str] = field(default_factory=list)
    severity: ErrorSeverity = ErrorSeverity.ERROR
    context_tokens: List[str] = field(default_factory=list)  # Surrounding tokens for context
    # Tokens immediately before / after the error point, kept separate so
    # the "Context:" line renders them on the correct side of -> HERE <-.
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)

    def format_error(self) -> str:
        """Format a detailed error message."""
        # Main error message
        parts = []

        parts.append(f"Parse error at position {self.position}")

        if self.line is not None and self.column is not None:
            parts.append(f" (line {self.line}, column {self.column})")

        parts.append(": ")

        # Error description
        if self.expected:
            if len(self.expected) == 1:
                parts.append(f"Expected {self.expected[0]}")
            else:
                expected_str = ", ".join(self.expected[:-1]) + f" or {self.expected[-1]}"
                parts.append(f"Expected {expected_str}")
            parts.append(f", got {self._token_description(self.token)}")
        elif self.message:
            parts.append(self.message)
        else:
            parts.append(f"Unexpected {self._token_description(self.token)}")

        error_msg = "".join(parts)

        # Add source line context if available
        if self.source_line and self.column is not None:
            error_msg += f"\n\n{self.source_line}\n{' ' * (self.column - 1)}^"

        # Add suggestions if available
        if self.suggestions:
            error_msg += "\n\nSuggestions:"
            for suggestion in self.suggestions:
                error_msg += f"\n  • {suggestion}"

        # Add context tokens if available: tokens BEFORE the error point go
        # before "-> HERE <-", tokens AFTER go after it.
        if self.context_before or self.context_after:
            before = ' '.join(self.context_before)
            after = ' '.join(self.context_after)
            error_msg += f"\n\nContext: {before} -> HERE <- {after}"

        return error_msg

    def _token_description(self, token: Token) -> str:
        """Get human-readable token description."""
        if token.type == TokenType.EOF:
            return "end of input"
        elif token.type == TokenType.NEWLINE:
            return "newline"
        elif token.value:
            return f"'{token.value}'"
        else:
            return token.type.name.lower()


class ParseError(PshError):
    """Enhanced parse error with context."""

    def __init__(self, error_context: ErrorContext):
        self.error_context = error_context
        self.message = error_context.message or error_context.format_error()
        # Structural "incomplete input" signal: the parser failed AT the end
        # of the token stream, so more input could make the parse succeed.
        # Interactive/script line-continuation logic keys off this instead
        # of string-matching error messages.
        from ...lexer.token_types import TokenType
        token = error_context.token
        self.at_eof = bool(token is not None and token.type == TokenType.EOF)
        # Which expansion kind is unclosed ('command', 'parameter',
        # 'arithmetic', 'backtick'), when the error is an at_eof
        # unclosed-expansion error. Set by the raise site; a structured
        # signal for continuation hints (no message string-matching).
        self.unclosed_expansion: Optional[str] = None
        super().__init__(error_context.format_error())
