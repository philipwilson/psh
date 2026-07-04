"""Helper classes for the parser module."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional

from ...core.exceptions import PshError
from ...lexer.token_types import Token, TokenType


class ErrorSeverity(Enum):
    """Severity levels for parse errors."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


# Human-readable spellings for token types in parse-error messages.
# This is the ONE map every error path shares: the default expect()
# message, ErrorContext's token descriptions, and the suggestion logic
# all key off token types rendered through here, so a raw enum repr
# ("TokenType.THEN") can never leak into a user-facing diagnostic.
TOKEN_DISPLAY_NAMES: Dict[TokenType, str] = {
    TokenType.EOF: "end of input",
    TokenType.NEWLINE: "newline",
    # Reserved words
    TokenType.IF: "'if'", TokenType.THEN: "'then'", TokenType.ELSE: "'else'",
    TokenType.ELIF: "'elif'", TokenType.FI: "'fi'",
    TokenType.WHILE: "'while'", TokenType.UNTIL: "'until'",
    TokenType.DO: "'do'", TokenType.DONE: "'done'",
    TokenType.FOR: "'for'", TokenType.IN: "'in'",
    TokenType.CASE: "'case'", TokenType.ESAC: "'esac'",
    TokenType.SELECT: "'select'", TokenType.FUNCTION: "'function'",
    TokenType.TIME: "'time'",
    # Grouping / operators
    TokenType.LPAREN: "'('", TokenType.RPAREN: "')'",
    TokenType.LBRACE: "'{'", TokenType.RBRACE: "'}'",
    TokenType.LBRACKET: "'['", TokenType.RBRACKET: "']'",
    TokenType.DOUBLE_LPAREN: "'(('", TokenType.DOUBLE_RPAREN: "'))'",
    TokenType.DOUBLE_LBRACKET: "'[['", TokenType.DOUBLE_RBRACKET: "']]'",
    TokenType.SEMICOLON: "';'", TokenType.DOUBLE_SEMICOLON: "';;'",
    TokenType.SEMICOLON_AMP: "';&'", TokenType.AMP_SEMICOLON: "';;&'",
    TokenType.AMPERSAND: "'&'", TokenType.PIPE: "'|'",
    TokenType.PIPE_AND: "'|&'", TokenType.AND_AND: "'&&'",
    TokenType.OR_OR: "'||'", TokenType.EXCLAMATION: "'!'",
    # Word-ish
    TokenType.WORD: "word", TokenType.STRING: "string",
}


def token_display_name(token_type: TokenType) -> str:
    """Friendly display name for a token type ("'then'", "end of input")."""
    return TOKEN_DISPLAY_NAMES.get(token_type, token_type.name.lower())


def describe_token(token: Token) -> str:
    """Human-readable description of a concrete token for error messages.

    Prefers the token's actual text (quoted); valueless tokens (EOF,
    NEWLINE) fall back to the friendly type name.
    """
    if token.type == TokenType.EOF:
        return "end of input"
    if token.type == TokenType.NEWLINE:
        return "newline"
    if token.value:
        return f"'{token.value}'"
    return token_display_name(token.type)


def unexpected_token_message(token: Token) -> str:
    """bash-style "syntax error near unexpected token 'X'" for *token*.

    EOF gets bash's dedicated phrasing ("unexpected end of file") instead
    of quoting the EOF token's empty value as ``token ''``, and NEWLINE
    renders as the word ``newline`` (bash) rather than a literal line
    break inside the quotes.
    """
    if token.type == TokenType.EOF:
        return "syntax error: unexpected end of file"
    if token.type == TokenType.NEWLINE:
        return "syntax error near unexpected token 'newline'"
    return f"syntax error near unexpected token '{token.value}'"


class TokenGroups:
    """Groups of related tokens for cleaner matching."""

    # Word-like tokens that can appear as command arguments
    WORD_LIKE: FrozenSet[TokenType] = frozenset({
        TokenType.WORD, TokenType.STRING, TokenType.VARIABLE,
        TokenType.COMMAND_SUB, TokenType.COMMAND_SUB_BACKTICK,
        TokenType.ARITH_EXPANSION, TokenType.PARAM_EXPANSION,
        TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT,
        TokenType.LBRACKET, TokenType.RBRACKET,
        TokenType.LBRACE, TokenType.RBRACE, TokenType.COMPOSITE,
    })

    # Redirect operators
    REDIRECTS: FrozenSet[TokenType] = frozenset({
        TokenType.REDIRECT_IN, TokenType.REDIRECT_OUT,
        TokenType.REDIRECT_APPEND, TokenType.HEREDOC,
        TokenType.HEREDOC_STRIP, TokenType.HERE_STRING,
        TokenType.REDIRECT_DUP,
        TokenType.REDIRECT_READWRITE,
        TokenType.REDIRECT_CLOBBER,
    })

    # Control structure keywords
    CONTROL_KEYWORDS: FrozenSet[TokenType] = frozenset({
        TokenType.IF, TokenType.WHILE, TokenType.UNTIL, TokenType.FOR,
        TokenType.CASE, TokenType.SELECT,
        TokenType.DOUBLE_LBRACKET, TokenType.DOUBLE_LPAREN
    })

    # Statement separators
    STATEMENT_SEPARATORS: FrozenSet[TokenType] = frozenset({
        TokenType.SEMICOLON, TokenType.NEWLINE
    })

    # Case statement terminators
    CASE_TERMINATORS: FrozenSet[TokenType] = frozenset({
        TokenType.DOUBLE_SEMICOLON, TokenType.SEMICOLON_AMP,
        TokenType.AMP_SEMICOLON
    })

    # Keywords that can be valid case patterns
    CASE_PATTERN_KEYWORDS: FrozenSet[TokenType] = frozenset({
        TokenType.IF, TokenType.THEN, TokenType.ELSE, TokenType.FI, TokenType.ELIF,
        TokenType.WHILE, TokenType.UNTIL, TokenType.DO, TokenType.DONE, TokenType.FOR, TokenType.IN,
        TokenType.CASE, TokenType.ESAC,
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
        return describe_token(token)


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
        # The closing keyword a compound construct failed to find ('fi',
        # 'done', 'esac'), when this is a missing-nested-terminator error.
        # Set by the raise site; a structured signal the combinator parser
        # uses to remap a nested-body error onto the outer terminator token
        # so no caller has to string-match the message.
        self.missing_terminator: Optional[str] = None
        super().__init__(error_context.format_error())
