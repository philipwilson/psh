"""Centralized parser context for PSH.

This module provides the ParserContext class that consolidates all parser
state into a single object: the token stream and position, the parser
configuration, and source text for error messages.
"""
from dataclasses import dataclass, field
from typing import List, Mapping, Optional

from ...lexer.position import SourceMap
from ...lexer.token_types import Token, TokenType
from ..config import ParserConfig
from .helpers import (
    ErrorContext,
    ParseError,
    describe_token,
    token_display_name,
)


@dataclass
class ParserContext:
    """Centralized parser state management.

    Consolidates the parser's real state — token stream, position, config,
    and source context — behind one object shared by the main parser and all
    sub-parsers.
    """

    # Core parsing state
    tokens: List[Token]
    current: int = 0
    config: ParserConfig = field(default_factory=ParserConfig)

    # Pre-collected heredocs (the LexedUnit's id-keyed map of LexedHeredoc
    # entries: spec + collected body), keyed by the ``heredoc_id`` the lexer
    # stamped on each ``<<``/``<<-`` operator token. Present only on the
    # heredoc-aware parse path (``parse_with_heredocs`` / the interactive
    # trial parse); None otherwise. When present, RedirectionParser takes the
    # delimiter truth (raw spelling, quoted) and body from the spec entry and
    # attaches them to the ``Redirect`` node AS IT IS CONSTRUCTED (no second
    # AST walk); a heredoc redirect whose id is missing from the map is a
    # hard error.
    heredocs: Optional[Mapping[int, object]] = None

    # Lexer options (the shell option dict, e.g. ``{'extglob': True, ...}``) in
    # effect for this parse. A plain data dict, NOT a Shell reference. Used only
    # to RE-LEX the body of a nested command/process substitution with the same
    # option-sensitive lexing as the outer command (notably ``extglob``, which
    # governs whether ``@(a|b)`` is an extglob pattern). None outside the live
    # shell parse path (standalone parser use lexes with defaults).
    lexer_options: Optional[Mapping[str, object]] = None

    # Source context
    source_text: Optional[str] = None
    source_lines: Optional[List[str]] = None
    # Number of source lines BEFORE this fragment in the enclosing input
    # (0 when the fragment starts the input). Token .line values are
    # fragment-relative; error reporting adds this offset so a multi-line
    # script's diagnostics carry the ABSOLUTE line number. source_lines
    # indexing stays fragment-relative.
    line_offset: int = 0

    # Current compound-command nesting depth. Incremented/decremented by
    # CommandParser.parse_pipeline_component — the single chokepoint every
    # nested compound (brace group, subshell, if/while/for/case/select,
    # ((...)), [[...]]) parses through — and checked there against
    # MAX_NESTING_DEPTH so runaway nesting raises a clean ParseError
    # instead of a Python RecursionError (the statement-parser analogue of
    # ArithParser.MAX_DEPTH). Flat &&/||/pipe/`;` chains parse iteratively
    # and never accumulate depth.
    nesting_depth: int = 0

    # Nested modern-substitution depth (``$( $( ... ) )`` / process subs).
    # Incremented by one for each ``$(...)``/``<(...)``/``>(...)`` body parsed
    # at the outer parse (support/nested_parse.py), independently of
    # ``nesting_depth`` because a substitution is not a compound command. It is
    # capped so an adversarially deep substitution chain fails as a clean
    # ParseError rather than an O(n^2) re-parse cascade — the interim cost of
    # extracting-and-reparsing bodies until the lexer gains token-level
    # substitution recursion (a separate campaign).
    substitution_depth: int = 0

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

    # Cached synthetic EOF returned when the cursor is past the token list.
    # Built lazily on first past-end access (see _synthetic_eof) so repeated
    # out-of-range peeks return one stable object rather than a fresh token
    # each time. Not part of the public state; excluded from init/repr.
    _eof_token: Optional[Token] = field(default=None, init=False, repr=False,
                                        compare=False)
    # The source line-structure map for error display. Built from source_text;
    # None when the parser was handed a bare token list (no source). Excluded
    # from init/repr/compare like the EOF cache.
    _source_map: Optional[SourceMap] = field(default=None, init=False,
                                             repr=False, compare=False)

    def __post_init__(self):
        """Initialize derived state."""
        if self.source_text:
            self._source_map = SourceMap(self.source_text)
            if not self.source_lines:
                self.source_lines = self._source_map.lines

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

    def _synthetic_eof(self) -> Token:
        """Return a stable synthetic EOF token for out-of-range access.

        The lexer normally supplies a trailing EOF, but the parser is a
        public API that accepts any ``List[Token]``. When the cursor moves
        past the end of a sentinel-free stream we return a synthetic EOF
        (positioned just after the last real token so diagnostics point at
        end of input) rather than echoing the last real token — echoing
        caused non-termination, since ``at_end()`` never saw an EOF and
        ``advance()`` could not move forward.
        """
        if self._eof_token is None:
            if self.tokens:
                last = self.tokens[-1]
                pos = last.end_position or last.position
                self._eof_token = Token(
                    TokenType.EOF, "", pos, end_position=pos,
                    line=last.line, column=last.column)
            else:
                self._eof_token = Token(TokenType.EOF, "", 0)
        return self._eof_token

    def peek(self, offset: int = 0) -> Token:
        """Look at current token + offset without consuming.

        Positions past the end of the token list yield a stable synthetic
        EOF (see :meth:`_synthetic_eof`); this supports both EOF-terminated
        and sentinel-free token streams. Negative positions are rejected —
        the parser never looks before the start of the stream.
        """
        pos = self.current + offset
        if pos < 0:
            raise IndexError(
                f"Parser peek at negative token position {pos} "
                f"(current={self.current}, offset={offset})")
        if pos < len(self.tokens):
            return self.tokens[pos]
        return self._synthetic_eof()

    def advance(self) -> Token:
        """Consume and return current token.

        May advance to ``len(tokens)`` (one past the last token) so that a
        sentinel-free stream reaches the end and ``at_end()`` becomes true;
        further advances stay parked at the end and return synthetic EOF.
        """
        token = self.peek()
        if self.current < len(self.tokens):
            self.current += 1
        return token

    def at_end(self) -> bool:
        """Check if at end of tokens.

        True once the cursor reaches the end of the stream (``current >=
        len(tokens)``, the sentinel-free case) or lands on an explicit EOF
        token (the normal lexer-terminated case).
        """
        return self.current >= len(self.tokens) or \
            self.tokens[self.current].type == TokenType.EOF

    def match(self, *token_types: TokenType) -> bool:
        """Check if current token matches any of the given types."""
        return self.peek().type in token_types

    def consume(self, token_type: TokenType, error_message: Optional[str] = None) -> Token:
        """Consume token of expected type or raise error."""
        if self.match(token_type):
            return self.advance()

        current = self.peek()
        message = error_message or (
            f"Expected {token_display_name(token_type)}, "
            f"got {describe_token(current)}")

        # Create error with context and raise. (There is no error-collection
        # mode: a parse either succeeds or raises here — it never returns a
        # partial/fabricated AST after a missing required token.)
        error_context = self._create_error_context(message, current,
                                                   expected_type=token_type)
        raise ParseError(error_context)

    def _create_error_context(self, message: str, token: Token,
                              expected_type: Optional[TokenType] = None):
        """Create error context with source information.

        ``expected_type`` is the token type an expect()/consume() failed on,
        when known — the suggestion logic keys off it (never off the message
        string).
        """
        source_line = None
        if token.line:
            if self._source_map is not None:
                # The one source map provides the error-context line text.
                source_line = self._source_map.line_text(token.line)
            elif self.source_lines and 0 < token.line <= len(self.source_lines):
                # Fallback for a context handed source_lines without source_text.
                source_line = self.source_lines[token.line - 1]

        error_context = ErrorContext(
            token=token,
            message=message,
            position=token.position,
            # Absolute line in the enclosing input (token.line is
            # fragment-relative; line_offset counts the lines before it).
            line=token.line + self.line_offset if token.line else token.line,
            column=token.column,
            source_line=source_line
        )

        # Enhance error context with suggestions and context tokens
        self._enhance_error_context(error_context, token, expected_type)

        return error_context

    @staticmethod
    def _display_token(tok) -> str:
        """Human-readable token text for the "Context:" line.

        Renders the token's value when it has one; EOF and NEWLINE always
        use a placeholder (a NEWLINE token's value is a literal newline,
        which would break the one-line Context rendering), and other
        valueless tokens get a friendly placeholder rather than leaking a
        raw ``TokenType.EOF`` repr.
        """
        if tok.type == TokenType.EOF:
            return '<EOF>'
        if tok.type == TokenType.NEWLINE:
            return '<newline>'
        if tok.value:
            return tok.value
        return f'<{tok.type.name.lower()}>'

    # Suggestions attached when an expect() fails on these token types.
    # Keyed on the STRUCTURED expected type — never on the rendered
    # message string (the old string-matching was coupled to a leaky
    # "Expected TokenType.THEN" format).
    _EXPECT_SUGGESTIONS = {
        TokenType.THEN: "Add ';' before 'then' keyword",
        TokenType.DO: "Add ';' before 'do' keyword",
        TokenType.RPAREN: "Add ')' to close parentheses",
        TokenType.RBRACE: "Add '}' to close brace group",
        TokenType.FI: "Add 'fi' to close if statement",
        TokenType.DONE: "Add 'done' to close the loop",
        TokenType.ESAC: "Add 'esac' to close case statement",
    }

    def _enhance_error_context(self, error_context, token,
                               expected_type: Optional[TokenType] = None):
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

        # Add a contextual suggestion keyed on the expected token type.
        if expected_type is not None:
            suggestion = self._EXPECT_SUGGESTIONS.get(expected_type)
            if suggestion:
                error_context.suggestions.append(suggestion)
