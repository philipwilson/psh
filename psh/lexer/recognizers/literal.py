"""Literal token recognizer for strings, numbers, and identifiers."""

from typing import Optional, Tuple

from ...token_types import Token, TokenType
from ..state_context import LexerContext
from ..unicode_support import is_identifier_char, is_identifier_start, is_whitespace
from .base import ContextualRecognizer


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

        # Skip whitespace and operators (handled by other recognizers)
        # But allow disabled quotes to be part of words
        if char in self.WORD_TERMINATORS:
            # Allow disabled quotes/expansions/operators to be recognized as word chars
            if char == "'" and self.config and not self.config.enable_single_quotes:
                return True  # Can be part of word
            if char == '"' and self.config and not self.config.enable_double_quotes:
                return True  # Can be part of word
            if char == '$' and self.config and not self.config.enable_variable_expansion:
                return True  # Can be part of word
            if char == '$' and self.config and self.config.enable_variable_expansion and not self._can_start_valid_expansion(input_text, pos):
                return True  # Can be part of word (invalid expansion)
            if char == '`' and self.config and not self.config.enable_command_substitution:
                return True  # Can be part of word
            if char == '|' and self.config and not self.config.enable_pipes:
                return True  # Can be part of word
            if char in ['<', '>'] and self.config and not self.config.enable_redirections:
                return True  # Can be part of word
            if char == '&' and self.config and not self.config.enable_background:
                return True  # Can be part of word
            # Inside [[ ]], < and > are comparison operators that should be tokenized as words
            if char in ['<', '>'] and context.bracket_depth > 0:
                return True  # Can be part of word
            # Inside (( )), < and > are arithmetic comparisons, not redirects.
            # The operator recognizer already rejects them, but the literal
            # recognizer must accept them as word-start characters — otherwise
            # they are silently dropped from the token stream.
            if char in ['<', '>'] and context.arithmetic_depth > 0:
                return True  # Can be part of word
            # Extglob: !( and +( should be treated as word start, not operator
            if char in ('!', '+') and self.config and self.config.enable_extglob:
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

        # Skip quotes and expansions based on configuration, but only if they can be fully handled
        # For $ and `, we need to check if they can actually form valid expansions
        if char == '$' and self.config and self.config.enable_variable_expansion:
            # Only skip if this can actually start a valid expansion
            # Otherwise, let literal recognizer handle it as a regular character
            if self._can_start_valid_expansion(input_text, pos):
                return False  # Let expansion parser handle it
        if char == '`' and self.config and self.config.enable_command_substitution:
            return False  # Let expansion parser handle it
        if char == "'" and self.config and self.config.enable_single_quotes:
            return False  # Let quote parser handle it
        if char == '"' and self.config and self.config.enable_double_quotes:
            return False  # Let quote parser handle it

        # If we get here, it might be a literal
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

        while pos < len(input_text):
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
                # Inside [...], collect everything including ! and other special chars
                value += char
                pos += 1
                if char == ']':
                    in_glob_bracket = False
                continue

            # Handle invalid $ expansions as literal characters
            if (char == '$' and self.config and self.config.enable_variable_expansion and
                not self._can_start_valid_expansion(input_text, pos)):
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
                    char, value, input_text, pos, context
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
            if self._is_inside_array_assignment(value):
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

            # Check if # starts a comment
            if char == '#' and self._is_comment_start(input_text, pos, context):
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
        context: LexerContext
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
        if self._is_inside_array_assignment(value):
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
        if char == '$' and self.config and self.config.enable_variable_expansion:
            if (pos + 1 < len(input_text) and input_text[pos + 1] == "'" and
                self._is_in_variable_assignment_value(value)):
                ansi_c_content, new_pos = self._parse_ansi_c_quote_inline(input_text, pos)
                if ansi_c_content is not None:
                    return (False, value + ansi_c_content, new_pos, True)
            return (True, value, pos, False)

        if char == '`' and self.config and self.config.enable_command_substitution:
            return (True, value, pos, False)

        if char == "'" and self.config and self.config.enable_single_quotes:
            return (True, value, pos, False)

        if char == '"' and self.config and self.config.enable_double_quotes:
            return (True, value, pos, False)

        return (False, value, pos, False)

    def _is_comment_start(self, input_text: str, pos: int, context: LexerContext) -> bool:
        """Check if # at current position starts a comment."""
        if pos == 0:
            return True

        prev_char = input_text[pos - 1]

        # After whitespace
        if prev_char in [' ', '\t', '\n', '\r']:
            return True

        # After operators that can be followed by comments
        comment_preceding_ops = {'|', '&', ';', '(', '{'}
        if prev_char in comment_preceding_ops:
            return True

        return False

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

        # Basic word terminators, but check configuration for quotes
        if char in self.WORD_TERMINATORS:
            # Check if quotes/operators should be treated as word characters when disabled
            if char == "'" and self.config and not self.config.enable_single_quotes:
                return False  # Treat as word character
            if char == '"' and self.config and not self.config.enable_double_quotes:
                return False  # Treat as word character
            if char == '$' and self.config and not self.config.enable_variable_expansion:
                return False  # Treat as word character
            if char == '`' and self.config and not self.config.enable_command_substitution:
                return False  # Treat as word character
            if char == '|' and self.config and not self.config.enable_pipes:
                return False  # Treat as word character
            if char in ['<', '>'] and self.config and not self.config.enable_redirections:
                return False  # Treat as word character
            if char == '&' and self.config and not self.config.enable_background:
                return False  # Treat as word character
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

    def _is_identifier(self, value: str) -> bool:
        """Check if value is a valid identifier."""
        if not value:
            return False

        # Get posix_mode from config
        posix_mode = self.config.posix_mode if self.config else False

        # Must start with valid identifier start character
        if not is_identifier_start(value[0], posix_mode):
            return False

        # Rest must be valid identifier characters
        return all(is_identifier_char(c, posix_mode) for c in value[1:])

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
        # works) for a closing ] followed by = or +=.
        from ..pure_helpers import QuoteState

        remaining = input_text[pos:]
        bracket_count = 0
        state = QuoteState()
        i = 0

        while i < len(remaining):
            char = remaining[i]
            if state.consume(char):  # active (outside quotes, not quote/escape)
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

    def _is_inside_array_assignment(self, value: str) -> bool:
        """Check if we're currently inside an array assignment pattern."""
        if not value or '[' not in value:
            return False

        # Check if we have unmatched opening bracket and this looks like array pattern
        bracket_count = 0
        has_opening_bracket = False
        in_single_quote = False
        in_double_quote = False

        for char in value:
            # Track quotes to ignore brackets inside them
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif not in_single_quote and not in_double_quote:
                if char == '[':
                    bracket_count += 1
                    has_opening_bracket = True
                elif char == ']':
                    bracket_count -= 1

        # We're inside array assignment if we have unmatched opening brackets
        return has_opening_bracket and bracket_count > 0

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
        """
        Parse an ANSI-C quote $'...' starting at the given position.

        Returns (processed_content, new_position) where processed_content is None if parsing failed.
        The processed_content has escape sequences converted to their actual characters.
        """
        if pos + 1 >= len(input_text) or input_text[pos:pos+2] != "$'":
            return None, pos

        # Import the pure helpers for ANSI-C quote processing
        from .. import pure_helpers

        # Start after the $'
        quote_start = pos + 2
        quote_pos = quote_start
        processed_content = ""

        # Find the closing quote and process escape sequences
        while quote_pos < len(input_text):
            char = input_text[quote_pos]

            if char == "'":
                # Found closing quote - return the processed content (not the literal $'...')
                return processed_content, quote_pos + 1

            if char == '\\' and quote_pos + 1 < len(input_text):
                # Handle escape sequence using existing helper
                escaped_str, new_pos = pure_helpers.handle_escape_sequence(
                    input_text, quote_pos, "$'"
                )
                processed_content += escaped_str
                quote_pos = new_pos
            else:
                processed_content += char
                quote_pos += 1

        # Unclosed quote - return None to indicate parsing failure
        return None, pos

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
        """Collect the complete array assignment pattern including quotes.

        Starting at a '[', collect until we find ']=', ']+=' or hit a terminator.
        This is quote-aware and will include quoted keys.

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
                    # Look for = or +=
                    if pos < len(input_text):
                        if input_text[pos] == '=':
                            result += '='
                            pos += 1
                            value_part, value_pos = self._collect_assignment_value(input_text, pos)
                            result += value_part
                            return result, value_pos
                        elif pos + 1 < len(input_text) and input_text[pos:pos+2] == '+=':
                            result += '+='
                            pos += 2
                            value_part, value_pos = self._collect_assignment_value(input_text, pos)
                            result += value_part
                            return result, value_pos
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

    def _collect_assignment_value(self, input_text: str, pos: int) -> Tuple[str, int]:
        """Collect the value part of an assignment until a terminator.

        This handles quoted values and continues until it hits whitespace or operators.
        """
        from ..pure_helpers import QuoteState

        result = ""
        state = QuoteState()

        while pos < len(input_text):
            char = input_text[pos]
            # Only an active (unquoted, non-quote/escape) char can terminate.
            if state.consume(char):
                if char in ' \t\n\r|&;(){}' or (char in '<>' and self.config and self.config.enable_redirections):
                    break
            result += char
            pos += 1

        return result, pos

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
