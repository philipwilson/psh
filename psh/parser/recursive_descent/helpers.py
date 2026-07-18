"""Helper classes for the parser module."""
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional

from ...core.exceptions import PshError
from ...lexer.token_types import Token, TokenType

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
        TokenType.ARITH_EXPANSION,
        TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT,
        TokenType.LBRACKET, TokenType.RBRACKET,
        TokenType.LBRACE, TokenType.RBRACE,
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

    # Statement separators
    STATEMENT_SEPARATORS: FrozenSet[TokenType] = frozenset({
        TokenType.SEMICOLON, TokenType.NEWLINE
    })

    # Case statement terminators
    CASE_TERMINATORS: FrozenSet[TokenType] = frozenset({
        TokenType.DOUBLE_SEMICOLON, TokenType.SEMICOLON_AMP,
        TokenType.AMP_SEMICOLON
    })

    # Keywords that can be valid case patterns. Every reserved-word type is a
    # legal pattern in bash (a pattern position is not a command start, but a
    # pattern after `;;`/`(`/newline IS normalized at command position, so it
    # arrives keyword-typed): `case time in a) :;; time) echo t;; esac`
    # prints t, and `case in in (in) ...` matches. TIME included (S1; was the
    # one omission — bash accepts it, probed red-on-base).
    CASE_PATTERN_KEYWORDS: FrozenSet[TokenType] = frozenset({
        TokenType.IF, TokenType.THEN, TokenType.ELSE, TokenType.FI, TokenType.ELIF,
        TokenType.WHILE, TokenType.UNTIL, TokenType.DO, TokenType.DONE, TokenType.FOR, TokenType.IN,
        TokenType.CASE, TokenType.ESAC,
        TokenType.SELECT, TokenType.FUNCTION, TokenType.TIME
    })

    # Precomputed unions the parse hot loops match against, so a per-token
    # check names a ready-made frozenset instead of rebuilding the union on
    # every call (`WORD_LIKE | REDIRECTS` was reallocated once per argument /
    # redirect match). Built once here at class-definition time.
    WORD_LIKE_OR_REDIRECTS: FrozenSet[TokenType] = WORD_LIKE | REDIRECTS
    WORD_LIKE_OR_CASE_PATTERNS: FrozenSet[TokenType] = (
        WORD_LIKE | CASE_PATTERN_KEYWORDS)


@dataclass
class ErrorContext:
    """Enhanced error context for better error messages."""

    token: Token
    message: str = ""
    position: int = 0
    line: Optional[int] = None
    column: Optional[int] = None
    source_line: Optional[str] = None

    # Enhanced error information (populated by ParserContext._enhance_error_context)
    suggestions: List[str] = field(default_factory=list)
    # Tokens immediately before / after the error point, kept separate so
    # the "Context:" line renders them on the correct side of -> HERE <-.
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """The short reason clause only — no position, caret, or suggestions.

        This is the one-line "what went wrong" ("Expected 'then', got end of
        input"). :meth:`format_error` prefixes it with position/line/column and
        appends the caret, suggestions, and token context.
        """
        if self.message:
            return self.message
        return f"Unexpected {self._token_description(self.token)}"

    def format_error(self) -> str:
        """Format a detailed error message (position, caret, suggestions).

        ONE declared coordinate system (campaign S4 handoff 2): the user-facing
        error coordinate is ``(line, column)`` in the ORIGINAL source, and the
        caret below is drawn at ``column`` under the source line looked up by
        ``line``. The token byte ``position`` is an INTERNAL token-stream offset
        — for heredoc-bearing input the token stream is stripped of heredoc
        bodies, so ``position`` indexes the stripped stream, not the shown
        (body-bearing) source. It is therefore NOT presented as a source
        coordinate: it appears only as the fallback when no ``line``/``column``
        is available (a bare token list with no source context).
        """
        if self.line is not None and self.column is not None:
            parts = [f"Parse error (line {self.line}, column {self.column})"]
        else:
            parts = [f"Parse error at position {self.position}"]

        parts.append(": ")
        parts.append(self.summary())

        error_msg = "".join(parts)

        # Add source line context if available. The caret is drawn at COLUMN
        # (line-relative) under the source line — never at the token-stream
        # `position` — so it stays in the same coordinate system as line/column
        # even when the token stream was stripped of heredoc bodies.
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
    """Enhanced parse error with context.

    One unambiguous diagnostic interface:

    * :attr:`summary` — the short reason ("Expected 'then', got end of input").
    * :meth:`render` — the rich presentation (position, source line, caret,
      suggestions, token context).
    * ``str(error)`` delegates to :meth:`render`.

    ``.message`` is kept as an alias of :attr:`summary` (the short reason) so a
    caller never has to guess whether it is the raw reason or the full render.
    """

    #: Whether this parse error originated in the BODY of a modern command or
    #: process substitution ($(...), <(...), >(...)). False for every ordinary
    #: parse error; True only on :class:`SubstitutionSyntaxError`. It is the
    #: typed I3 PRODUCER CONTRACT: a substitution-body syntax error is fatal to
    #: bash's string-execution frames (-c/eval/source, rc 127) while an ordinary
    #: syntax error is not. Carrying that origin as a TYPE — not by re-parsing or
    #: string-matching the message — is the semantic fact this boundary used to
    #: lose. psh keeps its uniform exit code 2 today (the 127/frame-abort mapping
    #: is I3's consumer job); this flag is behaviorally inert until then.
    substitution_origin: bool = False

    def __init__(self, error_context: ErrorContext):
        self.error_context = error_context
        # .message is the SHORT reason (== summary), never the full render.
        self.message = error_context.summary()
        # Structural "incomplete input" signal: the parser failed AT the end
        # of the token stream, so more input could make the parse succeed.
        # Interactive/script line-continuation logic keys off this instead
        # of string-matching error messages.
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

    @property
    def summary(self) -> str:
        """The short reason clause (no position/caret/suggestions)."""
        return self.error_context.summary()

    def render(self) -> str:
        """The rich diagnostic: position, source line, caret, suggestions."""
        return self.error_context.format_error()


class SubstitutionSyntaxError(ParseError):
    """A read-time syntax error in a modern substitution body (``$(...)`` etc.).

    A subclass of :class:`ParseError` and therefore BEHAVIORALLY INERT today:
    every ``except ParseError`` / ``isinstance(e, ParseError)`` site treats it
    identically, the rendered diagnostic is the same, and psh's uniform
    syntax-error exit code (2) is unchanged. Its only added fact is
    ``substitution_origin = True`` — the typed I3 producer contract (see the
    base attribute). Raised at the ONE chokepoint that parses substitution
    bodies (``support/nested_parse.parse_nested_command``) and re-raised from
    the S3 region validator, so no substitution-body syntax error escapes
    untagged.

    ``from_parse_error`` preserves the original error's structural signals
    (``at_eof``, ``unclosed_expansion``, ``missing_terminator``) so
    interactive/script continuation logic that keys on them is unaffected.
    """

    substitution_origin: bool = True

    @classmethod
    def from_parse_error(cls, err: 'ParseError') -> 'SubstitutionSyntaxError':
        """Re-type an ordinary body ``ParseError`` as substitution-origin.

        Copies the structural continuation signals verbatim so retyping is
        inert. If *err* is already a ``SubstitutionSyntaxError`` (a
        substitution nested in a substitution) it is returned unchanged, so the
        INNERMOST origin is preserved rather than re-wrapped.
        """
        if isinstance(err, SubstitutionSyntaxError):
            return err
        new = cls(err.error_context)
        new.at_eof = err.at_eof
        new.unclosed_expansion = err.unclosed_expansion
        new.missing_terminator = err.missing_terminator
        return new


def is_substitution_origin(err: BaseException) -> bool:
    """THE named predicate: did this error originate in a substitution body?

    The single seam I3 (and any consumer) uses to recognise the fatal-in-
    string-channels class, instead of ``isinstance`` checks scattered across
    call sites or message string-matching.
    """
    return getattr(err, 'substitution_origin', False)
