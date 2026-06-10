"""Modular lexer using the token recognizer system."""

from typing import List, Optional

from ..token_types import Token, TokenType
from .command_position import COMMAND_GROUP_OPENERS, STATEMENT_SEPARATORS
from .expansion_parser import ExpansionContext, ExpansionParser
from .position import LexerConfig, Position, PositionTracker
from .quote_parser import UnifiedQuoteParser
from .recognizers import RecognizerRegistry
from .state_context import LexerContext
from .token_parts import RichToken, TokenPart
from .unicode_support import is_whitespace


class ModularLexer:
    """
    Modular lexer using pluggable token recognizers.

    This lexer combines the unified quote/expansion parsing from Phase 3
    with the modular token recognition system from Phase 4.
    """

    def __init__(self, input_string: str, config: Optional[LexerConfig] = None):
        """
        Initialize the modular lexer.

        Args:
            input_string: The input string to tokenize
            config: Optional lexer configuration
        """
        self.input = input_string
        # Lazy per-position "inside NAME[..." map (see
        # _build_array_assignment_map) — built once, O(n).
        self._array_assignment_map = None
        self.config = config or LexerConfig()
        self.tokens: List[Token] = []

        # Position tracking
        self.position_tracker = PositionTracker(input_string)

        # State management
        self.context = LexerContext()

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
            input_string, self.config, self.position_tracker
        )

        # Current token parts for composite tokens
        self.current_parts: List[TokenPart] = []

    def _setup_recognizers(self) -> None:
        """Set up the token recognizers based on configuration."""
        from .recognizers.comment import CommentRecognizer
        from .recognizers.literal import LiteralRecognizer
        from .recognizers.operator import OperatorRecognizer
        from .recognizers.process_sub import ProcessSubstitutionRecognizer
        from .recognizers.whitespace import WhitespaceRecognizer

        # Always add these core recognizers
        self.registry.register(WhitespaceRecognizer())
        self.registry.register(CommentRecognizer())

        # Create a custom operator recognizer that respects config
        operator_recognizer = OperatorRecognizer()
        operator_recognizer.config = self.config  # Pass config to recognizer
        self.registry.register(operator_recognizer)

        # Create a custom literal recognizer that respects config
        literal_recognizer = LiteralRecognizer()
        literal_recognizer.config = self.config  # Pass config to recognizer
        self.registry.register(literal_recognizer)

        self.registry.register(ProcessSubstitutionRecognizer())

    # Position management
    @property
    def position(self) -> int:
        """Get current absolute position."""
        return self.position_tracker.position

    @position.setter
    def position(self, value: int) -> None:
        """Set absolute position."""
        diff = value - self.position_tracker.position
        if diff > 0:
            self.position_tracker.advance(diff)
        elif diff < 0:
            # Reset and advance to target
            self.position_tracker = PositionTracker(self.input)
            self.position_tracker.advance(value)

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

        # Create token
        start_offset = start_pos.offset if isinstance(start_pos, Position) else start_pos
        end_offset = end_pos.offset if isinstance(end_pos, Position) else end_pos

        # Extract line/column information if we have Position objects
        line = start_pos.line if isinstance(start_pos, Position) else None
        column = start_pos.column if isinstance(start_pos, Position) else None

        # Compute adjacency: this token is adjacent if it starts where the previous token ended
        adjacent = False
        if self.tokens:
            prev = self.tokens[-1]
            adjacent = (start_offset == prev.end_position)

        token = Token(token_type, value, start_offset, end_offset, quote_type,
                      line, column, adjacent)

        # Convert to RichToken if we have parts
        if self.current_parts:
            rich_token = RichToken.from_token(token, self.current_parts)
            self.current_parts = []  # Clear parts after use
            self.tokens.append(rich_token)
        else:
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

    # Words whose values are keywords that set command position.
    # These are checked during tokenization before KeywordNormalizer runs.
    _COMMAND_POSITION_KEYWORDS = {
        'if', 'while', 'until', 'for', 'case',
        'then', 'do', 'else', 'elif',
    }

    def _update_command_position_context(self, token_type: TokenType, token_value: str = '') -> None:
        """Update command position tracking based on token type and value."""
        # Shared separator set plus structural openers. Reserved-word keywords
        # are still WORD tokens at this stage, so they are handled by the
        # value-based check against _COMMAND_POSITION_KEYWORDS below (the lexer
        # never sees keyword token TYPES here).
        command_starting_tokens = STATEMENT_SEPARATORS | COMMAND_GROUP_OPENERS

        neutral_tokens = {
            TokenType.REDIRECT_IN, TokenType.REDIRECT_OUT,
            TokenType.REDIRECT_APPEND, TokenType.HEREDOC,
            TokenType.HEREDOC_STRIP, TokenType.HERE_STRING
        }

        # Update bracket depth for [[ and ]]
        if token_type == TokenType.DOUBLE_LBRACKET:
            self.context.bracket_depth += 1
        elif token_type == TokenType.DOUBLE_RBRACKET:
            self.context.bracket_depth -= 1
        elif token_type == TokenType.DOUBLE_LPAREN:
            self.context.enter_arithmetic()
        elif token_type == TokenType.DOUBLE_RPAREN:
            self.context.exit_arithmetic()

        # Track case statement context for proper [ tokenization
        if token_type == TokenType.WORD and token_value == 'case':
            self.context.case_depth += 1
            self.context.case_expecting_in = True
        elif (token_type == TokenType.WORD and token_value == 'in'
              and self.context.case_expecting_in):
            self.context.case_expecting_in = False
            self.context.in_case_pattern = True
        elif (token_type == TokenType.WORD and token_value == 'esac'
              and self.context.case_depth > 0):
            self.context.case_depth -= 1
            self.context.in_case_pattern = False
        elif (token_type == TokenType.RPAREN
              and self.context.case_depth > 0
              and self.context.in_case_pattern):
            self.context.in_case_pattern = False
        elif (token_type in {TokenType.DOUBLE_SEMICOLON,
                             TokenType.SEMICOLON_AMP,
                             TokenType.AMP_SEMICOLON}
              and self.context.case_depth > 0):
            self.context.in_case_pattern = True

        if token_type in command_starting_tokens:
            self.context.set_command_position()
        elif (token_type == TokenType.WORD and
              token_value in self._COMMAND_POSITION_KEYWORDS):
            # Keywords are emitted as WORD during tokenization (before
            # KeywordNormalizer runs). Treat keyword-valued words as
            # command-position setters so that operators like [[ are
            # recognized correctly.
            self.context.set_command_position()
        elif token_type not in neutral_tokens:
            self.context.reset_command_position()

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

            # Try quotes and expansions first (from Phase 3)
            if self._try_quotes_and_expansions():
                continue

            # Try modular recognizers
            if self._try_recognizers():
                continue

            # Fallback: treat as word
            if self._handle_fallback_word():
                continue

            # If nothing worked, advance to avoid infinite loop. NOTE: this
            # silently DROPS the character from the token stream (no token,
            # no error). It is reached for stray characters every recognizer
            # declines (e.g. a lone ']' in some contexts); changing it to an
            # error would alter error-recovery behavior.
            self.advance()

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
        """Check if we're potentially inside an array assignment pattern.

        This is used to prevent quote/expansion parsing from breaking up
        array assignments like arr["key"]=value or arr['key']=value.

        The answer for every position is precomputed in ONE forward O(n)
        pass over the input (lazily, on first use). The old implementation
        scanned BACKWARD from each query position to the previous command
        separator, which was quadratic on long commands — a single line of
        N quoted words lexed in O(N^2).
        """
        if self.position == 0:
            return False
        if self._array_assignment_map is None:
            self._array_assignment_map = self._build_array_assignment_map()
        return bool(self._array_assignment_map[self.position])

    def _build_array_assignment_map(self) -> bytearray:
        """map[i] == 1 iff position i is inside an unmatched ``NAME[``.

        Forward scan tracking quote state and a stack of open brackets;
        each ``[`` records whether it directly follows a valid identifier
        at a word boundary (the array-assignment shape). A position is
        "inside" when the nearest unmatched ``[`` has that shape —
        mirroring what the old backward scan computed.
        """
        from .unicode_support import is_identifier_char, is_identifier_start

        text = self.input
        n = len(text)
        result = bytearray(n)
        posix_mode = self.config.posix_mode if self.config else False

        def is_array_open(i: int) -> bool:
            # `[` must directly follow an identifier that starts at a word
            # boundary: arr[index], not arr [index] or +x[.
            if i == 0 or text[i - 1] in ' \t\n':
                return False
            if not is_identifier_char(text[i - 1], posix_mode):
                return False
            id_start = i - 1
            while id_start > 0 and is_identifier_char(text[id_start - 1], posix_mode):
                id_start -= 1
            if not is_identifier_start(text[id_start], posix_mode):
                return False
            return id_start == 0 or text[id_start - 1] in ' \t\n;|&(){}'

        in_single = False
        in_double = False
        open_flags = []  # one entry per currently-unmatched '[' (outside quotes)

        for i, ch in enumerate(text):
            # State coming INTO position i (the old scan started at pos-1)
            result[i] = 1 if (open_flags and open_flags[-1]) else 0

            if ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "'" and not in_double:
                in_single = not in_single
            elif not in_single and not in_double:
                if ch == '[':
                    open_flags.append(is_array_open(i))
                elif ch == ']':
                    if open_flags:
                        open_flags.pop()
                elif ch in '|&;(){}' and not open_flags:
                    # Command separator outside any bracket: hard word
                    # boundary (matches the old scan's break condition).
                    pass

        return result

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

        # Emit token based on expansion type
        if expansion_part.is_variable:
            if expansion_part.expansion_type == 'parameter':
                # For parameter expansion, check if it's a complex form
                value = expansion_part.value
                # FRAGILE: classification by substring scan over the WHOLE
                # ${...} text. An operator character appearing anywhere —
                # including inside a default value or a quoted/nested part
                # (e.g. ${x:-a/b} matched by '/') — classifies the token as
                # PARAM_EXPANSION rather than VARIABLE. The parser accepts
                # both token types, so misclassification is currently
                # harmless, but don't rely on the distinction being precise.
                if any(op in value for op in [':-', ':=', ':?', ':+', '##', '#', '%%', '%', '//', '/']):
                    # Complex parameter expansion - use PARAM_EXPANSION token
                    self.emit_token(TokenType.PARAM_EXPANSION, value, start_pos)
                else:
                    # Simple ${var} form - treat as VARIABLE
                    # Strip the $ but keep the {} wrapper for parameter expansion
                    value = expansion_part.value[1:] if expansion_part.value.startswith('$') else expansion_part.value
                    self.emit_token(TokenType.VARIABLE, value, start_pos)
            else:
                # For simple variables, the value should already be just the variable name
                value = expansion_part.value
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

    def _handle_quote(self, quote_char: str) -> bool:
        """Handle quoted string."""
        start_pos = self.get_current_position()

        # Skip opening quote
        self.advance()

        # Get quote rules
        from .quote_parser import QUOTE_RULES
        rules = QUOTE_RULES.get(quote_char)
        if not rules:
            return False

        # Parse the quoted string content using unified parser
        parts, new_pos, found_closing = self.quote_parser.parse_quoted_string(
            self.input,
            self.position,  # Current position (after opening quote)
            rules,
            self.position_tracker
        )

        # Check if quote was closed
        if not found_closing:
            raise SyntaxError(f"Unclosed {quote_char} quote at position {start_pos}")

        # Update position
        self.position = new_pos

        # Build complete string value
        full_value = self._build_token_value(parts)

        # Store parts for later use
        self.current_parts = parts

        # Emit token
        self.emit_token(TokenType.STRING, full_value, start_pos, quote_char)
        return True

    def _handle_locale_string(self) -> bool:
        """Handle a locale string $\"...\".

        Without a message catalog bash treats $"..." exactly like "...",
        so lex it as a normal double-quoted STRING. The token spans the $
        so composite-word adjacency is preserved (pre$"mid"post).
        """
        start_pos = self.get_current_position()

        # Skip $"
        self.advance()  # Skip $
        self.advance()  # Skip "

        from .quote_parser import QUOTE_RULES
        rules = QUOTE_RULES.get('"')
        if not rules:
            return False

        parts, new_pos, found_closing = self.quote_parser.parse_quoted_string(
            self.input,
            self.position,  # Current position (after $")
            rules,
            self.position_tracker
        )

        if not found_closing:
            raise SyntaxError(f'Unclosed $" quote at position {start_pos}')

        self.position = new_pos
        full_value = self._build_token_value(parts)
        self.current_parts = parts
        self.emit_token(TokenType.STRING, full_value, start_pos, '"')
        return True

    def _handle_ansi_c_quote(self) -> bool:
        """Handle ANSI-C quoted string $'...'."""
        start_pos = self.get_current_position()

        # Skip $'
        self.advance()  # Skip $
        self.advance()  # Skip '

        # Get ANSI-C quote rules
        from .quote_parser import QUOTE_RULES
        rules = QUOTE_RULES.get("$'")
        if not rules:
            return False

        # Parse the ANSI-C quoted string content
        parts, new_pos, found_closing = self.quote_parser.parse_quoted_string(
            self.input,
            self.position,  # Current position (after $')
            rules,
            self.position_tracker,
            quote_type="$'"  # Pass quote type for proper escape handling
        )

        # Check if quote was closed
        if not found_closing:
            raise SyntaxError(f"Unclosed $' quote at position {start_pos}")

        # Update position
        self.position = new_pos

        # Build complete string value
        full_value = self._build_token_value(parts)

        # Store parts for later use
        self.current_parts = parts

        # Emit token - ANSI-C quotes produce STRING tokens
        self.emit_token(TokenType.STRING, full_value, start_pos, "$'")
        return True

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

            # Add line/column information to token if missing
            if token.line is None or token.column is None:
                # Get position at token start
                start_position = self.position_tracker.get_position_at_offset(token.position)
                token.line = start_position.line
                token.column = start_position.column

            # Compute adjacency
            if self.tokens:
                prev = self.tokens[-1]
                token.adjacent_to_previous = (token.position == prev.end_position)

            # Add token
            self.tokens.append(token)

            # Update command position context
            self._update_command_position_context(token.type, token.value)

            return True

        return False

    def _handle_fallback_word(self) -> bool:
        """Handle fallback word tokenization."""
        if self.position >= len(self.input):
            return False

        start_pos = self.get_current_position()
        value = ""

        # Read until whitespace or special character
        while self.position < len(self.input):
            char = self.current_char()

            # Stop at whitespace
            if is_whitespace(char, self.config.posix_mode):
                break

            # Stop at operators (but not brackets - they might be part of glob patterns)
            if char in '<>&|;(){}!':
                break

            # Stop at quotes and expansions
            if char in ['$', '`', '"', "'"]:
                break

            value += char
            self.advance()

        if value:
            self.emit_token(TokenType.WORD, value, start_pos)
            return True

        return False
