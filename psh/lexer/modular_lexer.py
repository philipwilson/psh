"""Modular lexer using the token recognizer system."""

from dataclasses import replace
from typing import List, Optional

from .command_position import advance_lexical_state
from .expansion_parser import ExpansionContext, ExpansionParser
from .position import LexerConfig, Position, PositionTracker, UnclosedQuoteError
from .quote_parser import UnifiedQuoteParser
from .recognizers import RecognizerRegistry
from .recognizers.word_scanners import cached_assignment_prefix_map
from .state_context import LexicalState
from .token_parts import TokenPart
from .token_types import Token, TokenType
from .unicode_support import is_whitespace


class ModularLexer:
    """
    Modular lexer using pluggable token recognizers.

    Quotes and expansions are consumed whole by dedicated parsers
    (UnifiedQuoteParser, ExpansionParser); everything else is dispatched
    to pluggable recognizers tried in registration order (process
    substitution, operators, literals/words, comments, operator debris) —
    the single declaration is ``_setup_recognizers``.
    """

    def __init__(self, input_string: str, config: Optional[LexerConfig] = None,
                 initial_context: Optional[LexicalState] = None):
        """
        Initialize the modular lexer.

        Args:
            input_string: The input string to tokenize
            config: Optional lexer configuration
            initial_context: Optional cross-line state to resume from. The
                heredoc driver passes the context left by the previous logical
                command so a per-command tokenization behaves exactly like the
                tail of a single from-scratch pass over the joined command
                text — without re-lexing the accumulated prefix. It is used
                as-is (and mutated during tokenization), so callers pass a
                fresh :meth:`LexicalState.copy`; it must already carry the
                intended ``posix_mode``. When omitted a fresh context is
                created and seeded from ``config``.
        """
        self.input = input_string
        self.config = config or LexerConfig()
        self.tokens: List[Token] = []

        # Position tracking
        self.position_tracker = PositionTracker(input_string)

        # State management
        if initial_context is not None:
            self.context = initial_context
        else:
            self.context = LexicalState()
            # Set posix_mode in context from config
            self.context.posix_mode = self.config.posix_mode

        # Token recognizer system
        self.registry = RecognizerRegistry()
        self._setup_recognizers()

        # Unified parsers for quotes and expansions
        self.expansion_parser = ExpansionParser(self.config)
        self.quote_parser = UnifiedQuoteParser(self.expansion_parser)

        # Parsing contexts
        self.expansion_context = ExpansionContext(
            input_string, self.config
        )

        # Current token parts for composite tokens
        self.current_parts: List[TokenPart] = []

    def _setup_recognizers(self) -> None:
        """Set up the token recognizers in dispatch order.

        Recognizers are tried in the order registered here (the registry does
        no priority sorting — see RecognizerRegistry). This list is therefore
        the single, readable declaration of the dispatch sequence:

        1. ProcessSubstitution — ``<(…)`` / ``>(…)`` before the operator
           recognizer claims the leading ``<`` / ``>``.
        2. Operator — structural operators and redirections.
        3. Literal — words, identifiers, assignments.
        4. Comment — ``#`` to end of line.
        5. OperatorDebris — stray operator characters (``]``, ``+``, ``=``,
           ``[``) that the literal recognizer rejects as word starts; tried
           strictly LAST so it only fires after every other recognizer declines.

        (Whitespace is not a recognizer: the main loop skips it directly via
        ``_skip_whitespace()`` before dispatch, so a whitespace recognizer here
        was never reached.)
        """
        from .recognizers.comment import CommentRecognizer
        from .recognizers.literal import LiteralRecognizer
        from .recognizers.operator import OperatorRecognizer
        from .recognizers.operator_debris import OperatorDebrisWordRecognizer
        from .recognizers.process_sub import ProcessSubstitutionRecognizer

        self.registry.register(ProcessSubstitutionRecognizer())

        # Operator and literal recognizers respect the lexer config.
        operator_recognizer = OperatorRecognizer()
        operator_recognizer.config = self.config
        self.registry.register(operator_recognizer)

        literal_recognizer = LiteralRecognizer()
        literal_recognizer.config = self.config
        self.registry.register(literal_recognizer)

        self.registry.register(CommentRecognizer())

        self.registry.register(OperatorDebrisWordRecognizer())

    # Position management
    @property
    def position(self) -> int:
        """Get current absolute position."""
        return self.position_tracker.position

    @position.setter
    def position(self, value: int) -> None:
        """Set absolute position (forward-only; the cursor never seeks backward)."""
        diff = value - self.position_tracker.position
        if diff < 0:
            # Fail loudly, matching the census-verified guard in tokenize():
            # every position write in the tree is a forward-scanning parser
            # result (r19-D1 audit, 2026-07-11); a backward seek means a new
            # recognizer broke that contract.
            raise RuntimeError(
                f"lexer cursor seeked backward ({self.position_tracker.position} -> {value}); "
                "position writes must be forward-only"
            )
        if diff:
            self.position_tracker.advance(diff)

    def current_char(self) -> Optional[str]:
        """Get character at current position."""
        if self.position >= len(self.input):
            return None
        return self.input[self.position]

    def peek_char(self, offset: int = 1) -> Optional[str]:
        """Look ahead at character."""
        pos = self.position + offset
        if pos >= len(self.input):
            return None
        return self.input[pos]

    def advance(self, count: int = 1) -> None:
        """Move position forward."""
        self.position_tracker.advance(count)

    def get_current_position(self) -> Position:
        """Get current position as a Position object."""
        return self.position_tracker.get_current_position()

    # Token emission
    def emit_token(
        self,
        token_type: TokenType,
        value: str,
        start_pos: Optional[Position] = None,
        quote_type: Optional[str] = None,
        end_pos: Optional[Position] = None
    ) -> None:
        """Emit a token with current parts and context updates."""
        if start_pos is None:
            start_pos = self.get_current_position()
        if end_pos is None:
            end_pos = self.get_current_position()

        # Create token (start_pos/end_pos are always Position objects here —
        # either passed by the caller or defaulted above).
        start_offset = start_pos.offset
        end_offset = end_pos.offset
        line = start_pos.line
        column = start_pos.column

        # Compute adjacency: this token is adjacent if it starts where the previous token ended
        adjacent = False
        if self.tokens:
            prev = self.tokens[-1]
            adjacent = (start_offset == prev.end_position)

        # A token carries its parts directly (the base Token has a parts field);
        # RichToken was retired with the WordToken refactor.
        token = Token(token_type, value, start_offset, end_offset, quote_type,
                      line, column, adjacent, parts=self.current_parts)
        self.current_parts = []  # Clear parts after use
        self.tokens.append(token)

        # Update command position context
        self._update_command_position_context(token_type, value)

    def _build_token_value(self, parts: List[TokenPart]) -> str:
        """Build complete token value from parts."""
        full_value = ""
        for part in parts:
            if part.is_variable:
                # Special case: when the variable name is just '$' (for $$),
                # we always need to add the prefix
                if part.value == '$':
                    full_value += '$$'
                elif not part.value.startswith('$'):
                    # Only add $ if it's not already there (simple variables)
                    full_value += '$' + part.value
                else:
                    # Already has $, use as-is
                    full_value += part.value
            else:
                # For expansions and literals, use value as-is
                full_value += part.value
        return full_value

    def _update_command_position_context(self, token_type: TokenType, token_value: str = '') -> None:
        """Advance the lexical state after emitting a token.

        A thin adapter over :func:`command_position.advance_lexical_state`, the
        ONE lexer-stage command-position / case transition function. All the
        transition logic (bracket / arithmetic depth, the case FSM, and the
        command-position rule) lives there; see that function's docstring for
        why the lexer, keyword normalizer, and cmdsub scanner deliberately keep
        SEPARATE transitions.
        """
        advance_lexical_state(self.context, token_type, token_value)

    # Main tokenization
    def tokenize(self) -> List[Token]:
        """Main tokenization method using modular recognizers."""
        while self.position < len(self.input):
            # Skip whitespace
            if self._skip_whitespace():
                continue

            # Check for end of input
            if self.position >= len(self.input):
                break

            # Try quotes and expansions first: they must be consumed whole
            # (a recognizer matching inside a quoted region would corrupt it)
            if self._try_quotes_and_expansions():
                continue

            # Try modular recognizers (in registration order). The last one
            # registered is OperatorDebrisWordRecognizer, which
            # collects operator-debris words (`echo ]`, `set +x`) that the
            # literal recognizer rejects as word starts — see
            # recognizers/operator_debris.py.
            if self._try_recognizers():
                continue

            # Nothing consumed this character. An instrumented census
            # (2026-06-12, B6: the 15k-input characterization corpus, the
            # full test suite, and ~71k fuzz inputs including [[ / (( /
            # case-pattern contexts) found ZERO inputs that reach this
            # point — every stray character is consumed by the
            # operator-debris recognizer above. A silent self.advance()
            # here used to DROP the character from the token stream; per
            # the v0.300 fail-loudly policy an unreachable recovery path
            # must not hide future recognizer bugs as vanished characters.
            raise RuntimeError(
                f"lexer made no progress at position {self.position} "
                f"({self.current_char()!r}) — no recognizer or expansion "
                f"parser consumed the character; this is a "
                f"psh bug, please report the input")

        # Add EOF token
        self.emit_token(TokenType.EOF, '', self.get_current_position())

        return self.tokens

    def _skip_whitespace(self) -> bool:
        """Skip whitespace and return True if any was skipped."""
        start_pos = self.position

        while self.position < len(self.input):
            char = self.current_char()
            if not char or char == '\n':  # Stop at newlines
                break

            if not is_whitespace(char, self.config.posix_mode):
                break

            self.advance()

        return self.position > start_pos

    def _try_quotes_and_expansions(self) -> bool:
        """Try to handle quotes and expansions using unified parsers."""
        char = self.current_char()
        if not char:
            return False

        # Check for ANSI-C quoting $'...'
        if (char == '$' and self.position + 1 < len(self.input) and
            self.input[self.position + 1] == "'"):
            return self._handle_ansi_c_quote()

        # Locale string $"..." — without a message catalog bash treats it
        # exactly like "...".
        if (char == '$' and self.position + 1 < len(self.input) and
                self.input[self.position + 1] == '"' and
                not self._is_inside_potential_array_assignment()):
            return self._handle_locale_string()

        # Handle expansions (unless in array assignment context)
        if char == '$' and self.expansion_context.is_expansion_start(self.position):
            # Check if we're inside a potential array assignment - if so, let literal recognizer handle it
            if self._is_inside_potential_array_assignment():
                return False
            return self._handle_expansion()

        # Handle backticks (command substitution)
        if char == '`' and self.expansion_context.is_expansion_start(self.position):
            return self._handle_backtick()

        # Handle quotes (unless in array assignment context)
        if char in ('"', "'"):
            # Check if we're inside a potential array assignment - if so, let literal recognizer handle it
            if self._is_inside_potential_array_assignment():
                return False
            return self._handle_quote(char)

        return False

    def _is_inside_potential_array_assignment(self) -> bool:
        """Check if we're inside a confirmed array-assignment subscript.

        This is used to prevent quote/expansion parsing from breaking up
        array assignments like arr["key"]=value or arr['key']=value.

        Only confirmed assignment subscripts count: a ``NAME[`` whose
        matching ``]`` is immediately followed by ``=`` or ``+=``. A quote
        inside any other bracket-looking word keeps its normal meaning
        (bash: ``echo x["ok"]`` prints ``x[ok]``; ``echo x["oops`` is an
        unterminated-quote error).

        The answer for every position is precomputed in ONE forward O(n)
        pass over the input (lazily, on first use; see
        word_scanners.build_assignment_prefix_map) and cached on the
        LexicalState, where the literal recognizer's
        scan_assignment_prefix consults the same map. The pre-map
        implementation scanned BACKWARD from each query position to the
        previous command separator, which was quadratic on long commands —
        a single line of N quoted words lexed in O(N^2).
        """
        if self.position == 0:
            return False
        assignment_map = cached_assignment_prefix_map(
            self.input, self.config.posix_mode, self.context)
        return bool(assignment_map[self.position])

    def _handle_expansion(self) -> bool:
        """Handle variable/command/arithmetic expansion."""
        start_pos = self.get_current_position()

        # Parse the expansion
        expansion_part, new_pos = self.expansion_context.parse_expansion_at_position(
            self.position
        )

        # If it's not actually an expansion (just a literal), let other recognizers handle it
        if not expansion_part.is_expansion:
            return False

        # Update position
        self.position = new_pos

        # Preserve the "unclosed" marker as a token part: the truncated text
        # can still end with ')' (e.g. `$(# comment with )` swallowed by the
        # comment), so the parser cannot infer incompleteness from the token
        # value alone — it keys off part.expansion_type to raise an
        # incomplete-input error and gather more lines.
        if (expansion_part.expansion_type and
                expansion_part.expansion_type.endswith('_unclosed')):
            self.current_parts.append(expansion_part)

        # Emit token based on expansion type
        if expansion_part.is_variable:
            # Every $-variable form — simple `$var` and braced `${...}` alike —
            # emits ONE `VARIABLE` token. The WordBuilder classifies a braced
            # value precisely (`WordBuilder.parse_expansion_token`: a simple
            # name → `VariableExpansion`, anything with operators → the shared
            # `param_parser`). The lexer used to guess VARIABLE-vs-PARAM_EXPANSION
            # by scanning the whole `${...}` text for operator substrings — a
            # heuristic with false positives (`${x:-a/b}` matched `/`) that the
            # WordBuilder re-classified anyway. (`PARAM_EXPANSION` was retired
            # with WordToken — every `${...}` is a VARIABLE token.)
            value = expansion_part.value
            if expansion_part.expansion_type == 'parameter' and value.startswith('$'):
                # Braced `${...}`: strip the leading `$` to the `{...}` shape
                # (matching what simple `${var}` already produced).
                value = value[1:]
            self.emit_token(TokenType.VARIABLE, value, start_pos)
        else:
            # Command substitution or arithmetic
            if expansion_part.expansion_type == 'arithmetic':
                token_type = TokenType.ARITH_EXPANSION
            else:
                token_type = TokenType.COMMAND_SUB
            self.emit_token(token_type, expansion_part.value, start_pos)

        return True

    def _handle_backtick(self) -> bool:
        """Handle backtick command substitution."""
        start_pos = self.get_current_position()

        # Parse the backtick substitution
        backtick_part, new_pos = self.expansion_parser.parse_backtick_substitution(
            self.input, self.position
        )

        # Update position
        self.position = new_pos

        # Emit token
        self.emit_token(TokenType.COMMAND_SUB_BACKTICK, backtick_part.value, start_pos)
        return True

    def _lex_quoted(self, prefix_len: int, rules_key: str,
                    quote_type: str, label: Optional[str] = None) -> bool:
        """Lex ONE quoted string and emit a STRING token — the shared flow for
        all three quote handlers.

        ``prefix_len`` chars of opener are skipped (1 for ``'``/``"``, 2 for
        ``$'``/``$"``); the body is parsed by ``QUOTE_RULES[rules_key]`` with
        ``quote_type`` as the escape context (equal to ``rules.quote_char`` for
        the plain forms, so passing it is a no-op there; ``$'`` needs it for
        ANSI-C escapes). ``quote_type`` is stamped on the emitted token;
        ``label`` (defaulting to ``quote_type``) names the opener in the
        unclosed-quote error — it differs only for ``$"``, which lexes as a
        plain ``"`` STRING but must report ``$"`` when unterminated.
        """
        if label is None:
            label = quote_type
        start_pos = self.get_current_position()
        for _ in range(prefix_len):
            self.advance()

        from .quote_parser import QUOTE_RULES
        rules = QUOTE_RULES[rules_key]
        parts, new_pos, found_closing = self.quote_parser.parse_quoted_string(
            self.input,
            self.position,  # current position (after the opener)
            rules,
            quote_type=quote_type,
        )
        if not found_closing:
            raise UnclosedQuoteError(
                f"Unclosed {label} quote at position {start_pos}", label)

        self.position = new_pos
        self.current_parts = parts  # stashed for the caller
        self.emit_token(TokenType.STRING, self._build_token_value(parts),
                        start_pos, quote_type)
        return True

    def _handle_quote(self, quote_char: str) -> bool:
        """Handle a plain single/double quoted string."""
        return self._lex_quoted(1, quote_char, quote_char)

    def _handle_locale_string(self) -> bool:
        """Handle a locale string $\"...\".

        Without a message catalog bash treats $"..." exactly like "...", so lex
        it as a normal double-quoted STRING. The token spans the $ so
        composite-word adjacency is preserved (pre$"mid"post).
        """
        return self._lex_quoted(2, '"', '"', label='$"')

    def _handle_ansi_c_quote(self) -> bool:
        """Handle ANSI-C quoted string $'...'."""
        return self._lex_quoted(2, "$'", "$'")

    def _try_recognizers(self) -> bool:
        """Try modular recognizers."""
        result = self.registry.recognize(self.input, self.position, self.context)

        if result is not None:
            token, new_pos, recognizer = result

            # Handle special cases where recognizers return None
            # (e.g., whitespace and comments that should be skipped)
            if token is None:
                self.position = new_pos
                return True

            # Update position
            self.position = new_pos

            # Finalize line/column and adjacency on the recognizer's token.
            # Tokens are immutable, so accumulate the changes and rebuild once.
            updates: dict = {}
            if token.line is None or token.column is None:
                start_position = self.position_tracker.get_position_at_offset(token.position)
                updates['line'] = start_position.line
                updates['column'] = start_position.column
            if self.tokens:
                prev = self.tokens[-1]
                updates['adjacent_to_previous'] = (token.position == prev.end_position)
            if updates:
                token = replace(token, **updates)

            # Add token
            self.tokens.append(token)

            # Update command position context
            self._update_command_position_context(token.type, token.value)

            return True

        return False
