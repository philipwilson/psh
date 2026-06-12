"""Literal token recognizer for strings, numbers, and identifiers."""

from typing import Optional, Tuple

from ..state_context import LexerContext
from ..token_types import Token, TokenType
from ..unicode_support import is_identifier_char, is_identifier_start, is_whitespace
from .base import ContextualRecognizer
from .comment import is_comment_start


class _ArrayAssignmentTracker:
    """Incrementally tracks whether the value collected so far ends inside
    an unmatched ``[`` (outside quotes).

    This replaces the old ``_is_inside_array_assignment(value)`` helper,
    which re-scanned the whole accumulated value for every character —
    O(n^2) per word. Feeding each appended character exactly once runs the
    same quote-aware bracket automaton in O(n) total.

    Note this is NOT the same predicate as the lexer-level array-assignment
    map (``ModularLexer._build_array_assignment_map``): that map requires a
    confirmed ``NAME[...]=`` assignment shape, while this tracker counts any
    unmatched bracket — which is what keeps glob character classes like
    ``*[[:upper:]]*`` intact (the second ``]`` must not terminate the word).
    """

    __slots__ = ('_bracket_count', '_has_opening_bracket',
                 '_in_single', '_in_double', '_fed_len')

    def __init__(self):
        self._bracket_count = 0
        self._has_opening_bracket = False
        self._in_single = False
        self._in_double = False
        self._fed_len = 0

    def sync(self, value: str) -> None:
        """Feed any not-yet-seen suffix of ``value`` (which only grows)."""
        for char in value[self._fed_len:]:
            if char == "'" and not self._in_double:
                self._in_single = not self._in_single
            elif char == '"' and not self._in_single:
                self._in_double = not self._in_double
            elif not self._in_single and not self._in_double:
                if char == '[':
                    self._bracket_count += 1
                    self._has_opening_bracket = True
                elif char == ']':
                    self._bracket_count -= 1
        self._fed_len = len(value)

    @property
    def inside(self) -> bool:
        return self._has_opening_bracket and self._bracket_count > 0


class LiteralRecognizer(ContextualRecognizer):
    """Recognizes literal tokens: strings, numbers, identifiers."""

    def __init__(self):
        super().__init__()
        self.config = None  # Will be set by ModularLexer

    # Characters that can terminate a word
    WORD_TERMINATORS = {
        ' ', '\t', '\n', '\r', '\f', '\v',  # Whitespace
        '|', '&', ';', '(', ')', '{', '}',       # Operators
        '<', '>', '=', '+',                      # More operators
        '[', ']',                                # Bracket operators
        '$', '`', "'",  '"',                     # Special characters
    }

    @property
    def priority(self) -> int:
        """Medium priority for literals."""
        return 70

    def can_recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> bool:
        """Check if current position might be a literal."""
        if pos >= len(input_text):
            return False

        char = input_text[pos]

        # Skip whitespace and operators (handled by other recognizers),
        # with a few exceptions that start words.
        if char in self.WORD_TERMINATORS:
            # A $ that cannot start a valid expansion is a literal word char
            if char == '$' and not self._can_start_valid_expansion(input_text, pos):
                return True  # Can be part of word (invalid expansion)
            # Inside [[ ]], < and > are comparison operators that should be tokenized as words
            if char in ['<', '>'] and context.bracket_depth > 0:
                return True  # Can be part of word
            # Inside (( )), < and > are arithmetic comparisons, not redirects.
            # The operator recognizer already rejects them, but the literal
            # recognizer must accept them as word-start characters — otherwise
            # they are silently dropped from the token stream.
            if char in ['<', '>'] and context.arithmetic_depth > 0:
                return True  # Can be part of word
            # Extglob: +( should be treated as word start, not operator.
            # ('!' is not in WORD_TERMINATORS; !( is handled below.)
            if char == '+' and self.config and self.config.enable_extglob:
                if pos + 1 < len(input_text) and input_text[pos + 1] == '(':
                    return True  # Start of extglob pattern
            # { and } are operators only when standalone (followed by
            # whitespace/delimiter/EOF).  When adjacent to word chars
            # (e.g. {a..1}) they start a word.  {} is always a word.
            if char in ('{', '}'):
                next_pos = pos + 1
                # {} is a word, not operators
                if char == '{' and next_pos < len(input_text) and input_text[next_pos] == '}':
                    return True
                # } at non-command position is always a word character
                if char == '}' and not context.command_position:
                    return True
                # A brace is "standalone" (operator) only when followed by
                # whitespace, a command operator, or EOF. When followed by
                # another brace (e.g. {{1..3},...} nesting) or word chars, it is
                # part of a word — note '{'/'}' are NOT in this set.
                if next_pos >= len(input_text) or input_text[next_pos] in ' \t\n\r;|&()<>':
                    return False  # Standalone brace — let operator handle it
                return True  # Attached to word chars — part of word
            return False

        # Anything else (including '!', which the operator recognizer
        # declines when it isn't a standalone token) can start a literal.
        return True

    def recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Optional[Tuple[Token, int]]:
        """Recognize literal tokens."""
        start_pos = pos

        # Collect the literal value using helper method
        value, pos, saw_inline_ansi = self._collect_literal_value(input_text, pos, context)

        if not value:
            return None

        # Determine token type
        token_type = TokenType.WORD

        token = Token(
            token_type,
            value,
            start_pos,
            pos
        )

        if saw_inline_ansi and token.quote_type is None:
            token.quote_type = 'mixed'

        return token, pos

    def _collect_literal_value(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Tuple[str, int, bool]:
        """Collect literal value characters until a terminator is reached.

        Returns:
            Tuple of (collected_value, new_position, saw_inline_ansi)
        """
        value = ""
        saw_inline_ansi = False
        in_glob_bracket = False  # Track if we're inside [...] glob pattern
        # Incremental "inside unmatched [" state over the collected value
        # (replaces a per-character full re-scan of value — see
        # _ArrayAssignmentTracker).
        tracker = _ArrayAssignmentTracker()

        while pos < len(input_text):
            tracker.sync(value)
            char = input_text[pos]

            # Handle glob bracket expressions [...]
            # When we see '[', collect until ']' as part of the word
            if char == '[' and not in_glob_bracket:
                # Check if this looks like a glob pattern (not array assignment)
                if not self._is_potential_array_assignment_start(value, input_text, pos):
                    in_glob_bracket = True
                    value += char
                    pos += 1
                    continue

            if in_glob_bracket:
                # Inside a non-assignment [...] word, quotes and expansions
                # keep their normal meaning (bash: `echo x["ok"]` prints
                # `x[ok]`, `echo x[$USER]` expands, and `echo x["oops` is an
                # unterminated-quote error). End the literal here so the
                # quote/expansion machinery takes over; the parser re-joins
                # adjacent parts into one composite word. Only confirmed
                # array-assignment subscripts (`NAME[...]=`) collect quotes
                # literally — see _collect_array_assignment.
                if char == '\\' and pos + 1 < len(input_text):
                    # Escaped character (e.g. x[\"]) stays literal.
                    value += char + input_text[pos + 1]
                    pos += 2
                    continue
                if char in ('"', "'", '`') or (
                        char == '$' and self._can_start_valid_expansion(input_text, pos)):
                    break
                value += char
                pos += 1
                if char == ']':
                    in_glob_bracket = False
                continue

            # Handle invalid $ expansions as literal characters
            if char == '$' and not self._can_start_valid_expansion(input_text, pos):
                value += char
                pos += 1
                continue

            # Extglob: when we see '(' and value ends with an extglob prefix,
            # collect the balanced parenthesized group as part of this word
            if (char == '(' and self.config and self.config.enable_extglob
                    and value and value[-1] in '?*+@!'):
                collected, new_pos = self._collect_extglob_parens(input_text, pos)
                if collected is not None:
                    value += collected
                    pos = new_pos
                    continue

            # Extglob: + and ! are in WORD_TERMINATORS but when extglob is
            # enabled and they are followed by (, they are part of the word
            if (char in ('+', '!') and self.config and self.config.enable_extglob
                    and pos + 1 < len(input_text) and input_text[pos + 1] == '('):
                value += char
                pos += 1
                continue

            # Check for word terminators with special case handling
            if self._is_word_terminator(char, context):
                result = self._handle_terminator_special_cases(
                    char, value, input_text, pos, context, tracker.inside
                )
                if result is not None:
                    action, value, pos, ansi_flag = result
                    if ansi_flag:
                        saw_inline_ansi = True
                    if action == 'continue':
                        continue
                    elif action == 'break':
                        break
                else:
                    break

            # Handle quotes inside array assignments
            if tracker.inside:
                if char in ["'", '"', '$', '`']:
                    value += char
                    pos += 1
                    continue

            # Check for quotes/expansions that would end the word
            should_break, value, pos, ansi_flag = self._handle_quote_or_expansion(
                char, value, input_text, pos
            )
            if ansi_flag:
                saw_inline_ansi = True
            if should_break:
                break
            if pos > len(input_text) - 1 or input_text[pos] != char:
                # Position advanced, continue loop
                continue

            # Check if # starts a comment (shared definition with
            # CommentRecognizer — see comment.is_comment_start)
            if char == '#' and is_comment_start(input_text, pos):
                break

            # Handle escape sequences
            if char == '\\' and pos + 1 < len(input_text):
                next_char = input_text[pos + 1]
                value += char + next_char
                pos += 2
                continue

            value += char
            pos += 1

        return value, pos, saw_inline_ansi

    def _handle_terminator_special_cases(
        self,
        char: str,
        value: str,
        input_text: str,
        pos: int,
        context: LexerContext,
        in_array_assignment: bool
    ) -> Optional[Tuple[str, str, int, bool]]:
        """Handle special cases where we don't break on word terminators.

        Returns:
            None if should break normally, otherwise tuple of:
            (action, new_value, new_pos, saw_ansi) where action is 'continue' or 'break'
        """
        # += operator handling
        if char == '=' and value.endswith('+'):
            return ('continue', value + char, pos + 1, False)

        # Variable assignment (VAR=value)
        if char == '=' and self._is_variable_assignment_start(value):
            return ('continue', value + char, pos + 1, False)

        # Array assignment start (arr[key]=value)
        if char == '[' and self._is_potential_array_assignment_start(value, input_text, pos):
            array_part, new_pos = self._collect_array_assignment(input_text, pos)
            if array_part:
                return ('continue', value + array_part, new_pos, False)
            return ('continue', value + char, pos + 1, False)

        # Inside array assignment - don't break on these characters
        if in_array_assignment:
            if char in [']', '$', '(', ')', '+', '-', '*', '/', '%']:
                return ('continue', value + char, pos + 1, False)

        # Array assignment before +=
        if char == '+' and self._looks_like_array_assignment_before_plus_equals(value, input_text, pos):
            return ('continue', value + char, pos + 1, False)

        # ANSI-C quote in assignment or concatenation
        if (char == '$' and pos + 1 < len(input_text) and input_text[pos + 1] == "'" and
            (self._is_in_variable_assignment_value(value) or self._is_in_string_concatenation(value))):
            ansi_c_content, new_pos = self._parse_ansi_c_quote_inline(input_text, pos)
            if ansi_c_content is not None:
                return ('continue', value + ansi_c_content, new_pos, True)

        return None  # Normal break

    def _handle_quote_or_expansion(
        self,
        char: str,
        value: str,
        input_text: str,
        pos: int
    ) -> Tuple[bool, str, int, bool]:
        """Handle quotes or expansions that might end the word.

        Returns:
            Tuple of (should_break, new_value, new_pos, saw_ansi)
        """
        # Check for ANSI-C quotes in variable assignments
        if char == '$':
            if (pos + 1 < len(input_text) and input_text[pos + 1] == "'" and
                self._is_in_variable_assignment_value(value)):
                ansi_c_content, new_pos = self._parse_ansi_c_quote_inline(input_text, pos)
                if ansi_c_content is not None:
                    return (False, value + ansi_c_content, new_pos, True)
            return (True, value, pos, False)

        if char in ('`', "'", '"'):
            return (True, value, pos, False)

        return (False, value, pos, False)

    def _is_word_terminator(self, char: str, context: LexerContext) -> bool:
        """Check if character terminates a word in current context."""
        # In arithmetic context, only semicolon and parentheses are terminators
        if context.arithmetic_depth > 0:
            # Only these characters terminate words in arithmetic
            if char in [';', '(', ')', '\n']:
                return True
            else:
                return False

        # Check for Unicode whitespace (which should terminate words)
        if is_whitespace(char, posix_mode=context.posix_mode):
            return True

        # Basic word terminators
        if char in self.WORD_TERMINATORS:
            # Inside [[ ]], < and > are comparison operators that should be treated as word chars
            if char in ['<', '>'] and context.bracket_depth > 0:
                return False  # Treat as word character
            # { and } are operators only when standalone; inside words
            # (e.g. {a..1}) they are literal characters.  The operator
            # recognizer handles the standalone check, so here we just
            # need to check if we're already mid-word — if the literal
            # collector has accumulated any value, the brace is
            # continuation, not a terminator.  If we're at word start,
            # the operator recognizer already declined (otherwise we
            # wouldn't be here), so treat as literal.
            if char in ('{', '}'):
                return False
            return True

        # Context-specific terminators
        if context.bracket_depth > 0:
            # Inside [[ ]], some characters have special meaning
            if char in ['[', ']']:
                return True

        return False

    def _is_variable_assignment_start(self, value: str) -> bool:
        """Check if value looks like the start of a variable assignment (NAME=... or NAME[INDEX]=...)."""
        if not value:
            return False

        # Get posix_mode from config
        posix_mode = self.config.posix_mode if self.config else False

        # Check for array assignment pattern: NAME[...]
        if '[' in value:
            return self._is_array_assignment_start(value, posix_mode)

        # Variable names must start with letter or underscore
        if not is_identifier_start(value[0], posix_mode):
            return False

        # Rest must be valid identifier characters (valid shell variable name)
        return all(is_identifier_char(c, posix_mode) for c in value)

    def _is_array_assignment_start(self, value: str, posix_mode: bool) -> bool:
        """Check if value looks like the start of an array assignment (NAME[INDEX])."""
        bracket_pos = value.find('[')
        if bracket_pos == -1:
            return False

        # Extract the variable name before the bracket
        var_name = value[:bracket_pos]
        if not var_name:
            return False

        # Variable name must be valid
        if not is_identifier_start(var_name[0], posix_mode):
            return False
        if not all(is_identifier_char(c, posix_mode) for c in var_name):
            return False

        # The rest after '[' can contain any characters (index expression)
        # We don't validate the index contents here, just that it's an array pattern
        return True

    def _can_start_valid_expansion(self, input_text: str, pos: int) -> bool:
        """Check if $ at given position can start a valid expansion."""
        if pos >= len(input_text) or input_text[pos] != '$':
            return False

        if pos + 1 >= len(input_text):
            # Lone $ at end cannot start a valid expansion
            return False

        next_char = input_text[pos + 1]

        # Check for specific expansion patterns
        if next_char == '(':
            # Command substitution $(...) or arithmetic $((...))
            return True
        elif next_char == '{':
            # Parameter expansion ${...}
            return True
        elif next_char == "'":
            # ANSI-C quoting $'...'
            return True
        elif next_char == '"':
            # Locale string $"..." (lexed as a plain double-quoted string)
            return True
        else:
            # Simple variable $VAR - check if next character can start a variable name
            from ..constants import SPECIAL_VARIABLES
            from ..unicode_support import is_identifier_start

            # Special single-character variables
            if next_char in SPECIAL_VARIABLES:
                return True

            # Regular variable names
            posix_mode = self.config.posix_mode if self.config else False
            return is_identifier_start(next_char, posix_mode)

    def _is_potential_array_assignment_start(self, value: str, input_text: str, pos: int) -> bool:
        """Check if [ at current position starts an array assignment pattern."""
        if not value:
            return False

        # Get posix_mode from config
        posix_mode = self.config.posix_mode if self.config else False

        # Check if the value so far is a valid variable name
        if not is_identifier_start(value[0], posix_mode):
            return False
        if not all(is_identifier_char(c, posix_mode) for c in value):
            return False

        # Look ahead to see if this looks like arr[...]=... pattern.
        # We're at position of '[', scan forward (quote-aware, so arr["key"]=v
        # works; expansion-aware, so the space in a[$(echo 1 + 1)]=v doesn't
        # break the word) for a closing ] followed by = or +=.
        from ..pure_helpers import QuoteState, skip_expansion_region

        remaining = input_text[pos:]
        bracket_count = 0
        state = QuoteState()
        i = 0

        while i < len(remaining):
            char = remaining[i]
            if state.consume(char):  # active (outside quotes, not quote/escape)
                if char in ('$', '`'):
                    # $(...), ${...}, `...`: opaque — their contents
                    # (including whitespace) are part of the subscript.
                    skip = skip_expansion_region(remaining, i)
                    if skip is not None:
                        i = skip
                        continue
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        # Found closing bracket, check if followed by = or +=
                        if i + 1 < len(remaining):
                            if remaining[i + 1] == '=':
                                return True
                            elif i + 2 < len(remaining) and remaining[i + 1:i + 3] == '+=':
                                return True
                        return False
                elif char in (' ', '\t', '\n', '\r'):
                    # Whitespace breaks the pattern (outside quotes)
                    return False
            i += 1

        return False

    def _looks_like_array_assignment_before_plus_equals(self, value: str, input_text: str, pos: int) -> bool:
        """Check if + at current position is part of array assignment += pattern."""
        if not value or not value.endswith(']'):
            return False

        # Check if next character is =
        if pos + 1 >= len(input_text) or input_text[pos + 1] != '=':
            return False

        # Check if value looks like array assignment pattern (var[...])
        if '[' not in value:
            return False

        # Extract variable name before first [
        bracket_pos = value.find('[')
        var_name = value[:bracket_pos]

        if not var_name:
            return False

        # Get posix_mode from config
        posix_mode = self.config.posix_mode if self.config else False

        # Variable name must be valid
        if not is_identifier_start(var_name[0], posix_mode):
            return False
        if not all(is_identifier_char(c, posix_mode) for c in var_name):
            return False

        # Check brackets are balanced
        bracket_count = 0
        for char in value:
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1

        # Should have balanced brackets ending with ]
        return bracket_count == 0 and value.endswith(']')

    def _is_in_variable_assignment_value(self, value: str) -> bool:
        """Check if we are currently reading the value part of a variable assignment."""
        if not value or '=' not in value:
            return False

        # Simple case: var= (just found the equals)
        if value.endswith('='):
            return True

        # Array assignment case: arr[index]= or arr[index]+=
        if value.endswith('+=') or (']=' in value and value.endswith('=')):
            return True

        # Check if we have found an = and are now reading the value
        equals_pos = value.rfind('=')  # Find last equals in case of multiple
        if equals_pos == -1:
            return False

        # Check if what comes before = looks like a valid variable assignment start
        before_equals = value[:equals_pos]

        # Handle += case
        if before_equals.endswith('+'):
            before_equals = before_equals[:-1]

        # Check if it's a simple variable assignment or array assignment
        return self._is_variable_assignment_start(before_equals) or self._is_array_assignment_start(before_equals,
                                                                                                    self.config.posix_mode if self.config else False)

    def _parse_ansi_c_quote_inline(self, input_text: str, pos: int) -> Tuple[Optional[str], int]:
        """Parse an ANSI-C quote $\'...\' at pos via the unified quote parser.

        Returns (processed_content, new_position); content is None when pos
        doesn't start $' or the quote is unclosed. Delegates to
        UnifiedQuoteParser so escape semantics live in exactly one place.
        """
        if pos + 1 >= len(input_text) or input_text[pos:pos+2] != "$'":
            return None, pos

        from ..quote_parser import QUOTE_RULES, UnifiedQuoteParser
        parts, new_pos, closed = UnifiedQuoteParser().parse_quoted_string(
            input_text, pos + 2, QUOTE_RULES["$'"], None, quote_type="$'")
        if not closed:
            return None, pos
        return ''.join(part.value for part in parts), new_pos

    def _is_in_string_concatenation(self, value: str) -> bool:
        """Check if we are currently reading a string that could be concatenated with quotes."""
        if not value:
            return False

        # If the value contains only valid word characters (no special shell characters),
        # then it's likely a string that could be concatenated with quotes
        # Examples: "prefix", "hello", "path"

        # Get posix_mode from config
        posix_mode = self.config.posix_mode if self.config else False

        # Check if it's a valid identifier-like string (could be concatenated)
        # This includes simple words that could have quotes appended
        from ..unicode_support import is_identifier_char, is_identifier_start

        # Must start with a valid character for word
        if not value:
            return False

        # Allow strings that are valid identifiers or contain path-like characters
        for i, char in enumerate(value):
            if i == 0:
                if not (is_identifier_start(char, posix_mode) or char in '/.~'):
                    return False
            else:
                if not (is_identifier_char(char, posix_mode) or char in '/.~-'):
                    # If we hit special characters like =, we're probably not in simple concatenation
                    if char in '=[](){}|&;<>!':
                        return False

        return True

    def _collect_array_assignment(self, input_text: str, pos: int) -> Tuple[str, int]:
        """Collect an array assignment prefix: ``[index]=`` or ``[index]+=``.

        Starting at a '[', collect until we find ']=', ']+=' or hit a
        terminator. This is quote-aware and will include quoted keys.
        Collection stops right after the ``=`` so the VALUE tokenizes
        exactly like a scalar assignment value (``a[0]=$x`` becomes
        WORD ``a[0]=`` + VARIABLE ``x``, mirroring ``v=$x``); plain
        literal characters simply continue the same word.

        Returns (collected_string, new_position) or ("", pos) if not an array assignment.
        """
        if pos >= len(input_text) or input_text[pos] != '[':
            return "", pos

        from ..pure_helpers import QuoteState

        start_pos = pos
        result = ""
        bracket_count = 0
        state = QuoteState()

        while pos < len(input_text):
            char = input_text[pos]

            # Non-active chars (quote toggles, escapes, anything inside quotes)
            # are simply collected.
            if not state.consume(char):
                result += char
                pos += 1
                continue

            # Active (outside quotes): track brackets and look for assignment.
            if char == '[':
                bracket_count += 1
                result += char
                pos += 1
            elif char == ']':
                bracket_count -= 1
                result += char
                pos += 1

                # Check if this closes the array index
                if bracket_count == 0:
                    # Look for = or += and stop right after it: the value
                    # part is tokenized by the normal lexer machinery so
                    # expansions/quotes become proper adjacent tokens.
                    if pos < len(input_text):
                        if input_text[pos] == '=':
                            result += '='
                            pos += 1
                            return result, pos
                        elif pos + 1 < len(input_text) and input_text[pos:pos+2] == '+=':
                            result += '+='
                            pos += 2
                            return result, pos
                    # Not an assignment, return what we have
                    return result, pos
            elif char in ' \t\n\r|&;(){}' and bracket_count == 0:
                # Hit a terminator outside of brackets
                return "", start_pos
            else:
                result += char
                pos += 1

        # Reached end of input without finding assignment
        return "", start_pos

    def _collect_extglob_parens(self, input_text: str, pos: int) -> Tuple[Optional[str], int]:
        """Collect balanced parenthesized group for extglob patterns.

        Called when pos points to '(' and the preceding character was an
        extglob prefix (?*+@!). Collects the entire (...) including
        nested extglob and regular parens.

        Returns (collected_string, new_position) or (None, pos) if unbalanced.
        """
        if pos >= len(input_text) or input_text[pos] != '(':
            return None, pos

        depth = 1
        result = '('
        i = pos + 1

        while i < len(input_text) and depth > 0:
            ch = input_text[i]

            if ch == '\\' and i + 1 < len(input_text):
                result += ch + input_text[i + 1]
                i += 2
                continue

            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1

            result += ch
            i += 1

        if depth != 0:
            # Unbalanced parentheses
            return None, pos

        return result, i
