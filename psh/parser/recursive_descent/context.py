"""Centralized parser context for PSH.

``ParserContext`` composes the two campaign-S4 halves of a parse call and owns
the token stream that sits between them:

* :class:`~psh.parser.parse_inputs.ParseInputs` — the FROZEN caller context
  (source text, line offset, lexer options, collected heredocs, config).
* :class:`~psh.parser.parse_inputs.ParserState` — the MUTABLE per-call state
  (cursor, nesting/substitution depth, open-construct trail).
* ``tokens`` — the parse SUBJECT: a private list the parser reads and (only for
  the observationally-pure non-leading ``time`` → WORD slot rewrite) mutates.

The historical flat accessor surface (``ctx.current``, ``ctx.tokens``,
``ctx.source_text``, ``ctx.nesting_depth``, ...) is preserved as properties that
delegate to ``inputs``/``state``, so no sub-parser changed. Because ``inputs``
and ``state`` are built once per context and dropped with it, a parser instance
retains no per-call state after ``parse()`` returns.
"""
from typing import List, Mapping, Optional

from ...lexer.position import SourceMap
from ...lexer.token_types import Token, TokenType
from ..config import ParserConfig
from ..parse_inputs import ParseInputs, ParserState
from .helpers import (
    ErrorContext,
    ParseError,
    describe_token,
    token_display_name,
)


class ParserContext:
    """Centralized parser state management.

    Consolidates the parser's real state — the token stream and cursor, config,
    source context, and nesting/open-construct trail — behind one object shared
    by the main parser and all sub-parsers. Internally the immutable caller
    context lives in :attr:`inputs` (a frozen :class:`ParseInputs`) and the
    mutable per-call state in :attr:`state` (a :class:`ParserState`); the flat
    ``ctx.<field>`` surface is delegated to them.

    The constructor keeps the historical keyword surface (``tokens=``,
    ``config=``, ``source_text=``, ``line_offset=``, ``heredocs=``,
    ``lexer_options=``, and the initial ``current``/``nesting_depth``/
    ``substitution_depth`` seeds) so ``create_context`` and direct test
    construction are unchanged.
    """

    def __init__(
        self,
        tokens: List[Token],
        current: int = 0,
        config: Optional[ParserConfig] = None,
        heredocs: "Optional[Mapping[int, object]]" = None,
        lexer_options: Optional[Mapping[str, object]] = None,
        source_text: Optional[str] = None,
        source_lines: Optional[List[str]] = None,
        line_offset: int = 0,
        nesting_depth: int = 0,
        substitution_depth: int = 0,
    ) -> None:
        # Immutable caller context (frozen). The sole ParseInputs construction
        # site (guarded by test_parse_inputs_state_s4).
        self.inputs = ParseInputs(
            source_text=source_text,
            line_offset=line_offset,
            lexer_options=lexer_options,
            heredocs=heredocs,
            config=config or ParserConfig(),
        )
        # Mutable per-call state. Fresh for every context; nothing carries over.
        self.state = ParserState(
            cursor=current,
            nesting_depth=nesting_depth,
            substitution_depth=substitution_depth,
        )
        # The parse subject: a private token list the parser owns.
        self.tokens = tokens

        # Derived error-display caches (excluded from the typed split; rebuilt
        # from the immutable source_text). Built at construction below.
        self._eof_token: Optional[Token] = None
        self._source_map: Optional[SourceMap] = None
        self._source_lines: Optional[List[str]] = source_lines
        if source_text:
            self._source_map = SourceMap(source_text)
            if not self._source_lines:
                self._source_lines = self._source_map.lines

    # === Immutable-input delegation (read-only) ===

    @property
    def config(self) -> ParserConfig:
        return self.inputs.config

    @property
    def source_text(self) -> Optional[str]:
        return self.inputs.source_text

    @property
    def line_offset(self) -> int:
        return self.inputs.line_offset

    @property
    def lexer_options(self) -> "Optional[Mapping[str, object]]":
        return self.inputs.lexer_options

    @property
    def heredocs(self) -> "Optional[Mapping[int, object]]":
        return self.inputs.heredocs

    @property
    def source_lines(self) -> Optional[List[str]]:
        return self._source_lines

    # === Mutable-state delegation (read/write) ===

    @property
    def current(self) -> int:
        return self.state.cursor

    @current.setter
    def current(self, value: int) -> None:
        self.state.cursor = value

    @property
    def nesting_depth(self) -> int:
        return self.state.nesting_depth

    @nesting_depth.setter
    def nesting_depth(self, value: int) -> None:
        self.state.nesting_depth = value

    @property
    def substitution_depth(self) -> int:
        return self.state.substitution_depth

    @substitution_depth.setter
    def substitution_depth(self, value: int) -> None:
        self.state.substitution_depth = value

    @property
    def open_constructs(self) -> List[str]:
        return self.state.open_constructs

    # === Open-construct trail (incomplete-input hints only) ===

    def push_construct(self, name: str) -> None:
        """Record that an opening keyword was consumed ('if', 'while', ...)."""
        self.state.open_constructs.append(name)

    def retitle_construct(self, name: str) -> None:
        """Rename the innermost open construct at an internal transition
        (e.g. 'if' → 'then' once THEN is consumed)."""
        if self.state.open_constructs:
            self.state.open_constructs[-1] = name

    def pop_construct(self) -> None:
        """Record that the innermost construct's closer was consumed."""
        if self.state.open_constructs:
            self.state.open_constructs.pop()

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
        pos = self.state.cursor + offset
        if pos < 0:
            raise IndexError(
                f"Parser peek at negative token position {pos} "
                f"(current={self.state.cursor}, offset={offset})")
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
        if self.state.cursor < len(self.tokens):
            self.state.cursor += 1
        return token

    def at_end(self) -> bool:
        """Check if at end of tokens.

        True once the cursor reaches the end of the stream (``current >=
        len(tokens)``, the sentinel-free case) or lands on an explicit EOF
        token (the normal lexer-terminated case).
        """
        return self.state.cursor >= len(self.tokens) or \
            self.tokens[self.state.cursor].type == TokenType.EOF

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
        cursor = self.state.cursor
        context_before = []
        for i in range(max(0, cursor - 3), cursor):
            if i < len(self.tokens):
                context_before.append(self._display_token(self.tokens[i]))

        context_after = []
        for i in range(cursor + 1, min(len(self.tokens), cursor + 4)):
            context_after.append(self._display_token(self.tokens[i]))

        error_context.context_before = context_before
        error_context.context_after = context_after

        # Add a contextual suggestion keyed on the expected token type.
        if expected_type is not None:
            suggestion = self._EXPECT_SUGGESTIONS.get(expected_type)
            if suggestion:
                error_context.suggestions.append(suggestion)
