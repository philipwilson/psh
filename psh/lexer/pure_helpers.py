"""Pure helper functions for lexer operations.

This module contains stateless, pure functions that can be used by the lexer
without coupling to the lexer's internal state. These functions are easier to
test, reuse, and reason about.
"""

from typing import Dict, Optional, Set, Tuple

from .constants import DOUBLE_QUOTE_ESCAPES


class QuoteState:
    """Tracks single/double-quote and backslash-escape state during a forward
    left-to-right scan of shell text.

    Feed each character in order to ``consume()``; it updates the state and
    reports whether that character is "active" — i.e. outside quotes and not
    itself a quote toggle or an escape (lead or escaped) character — so the
    caller can apply its own structural logic (delimiters, terminators, bracket
    counting) only to active characters while still copying every character.

    By default a backslash inside single quotes is a literal (shell semantics);
    pass ``backslash_literal_in_single=False`` to treat ``\\`` as an escape
    everywhere.
    """

    __slots__ = ('in_single', 'in_double', '_escaped', '_bsl_literal_single')

    def __init__(self, backslash_literal_in_single: bool = True):
        self.in_single = False
        self.in_double = False
        self._escaped = False
        self._bsl_literal_single = backslash_literal_in_single

    @property
    def in_quotes(self) -> bool:
        return self.in_single or self.in_double

    def consume(self, char: str) -> bool:
        """Advance the state by one character; return True if it is active."""
        if self._escaped:
            self._escaped = False
            return False
        if char == '\\' and not (self._bsl_literal_single and self.in_single):
            self._escaped = True
            return False
        if char == "'" and not self.in_double:
            self.in_single = not self.in_single
            return False
        if char == '"' and not self.in_single:
            self.in_double = not self.in_double
            return False
        return not self.in_quotes


def find_closing_delimiter(
    input_text: str,
    start_pos: int,
    open_delim: str,
    close_delim: str,
    track_quotes: bool = True,
    track_escapes: bool = True
) -> Tuple[int, bool]:
    """
    Find matching closing delimiter, handling nesting and quotes.

    Args:
        input_text: The input string to search in
        start_pos: Starting position (after opening delimiter)
        open_delim: Opening delimiter string
        close_delim: Closing delimiter string
        track_quotes: Whether to track quote contexts
        track_escapes: Whether to handle escape sequences

    Returns:
        Tuple of (position_after_close, found_closing)
    """
    depth = 1
    pos = start_pos
    in_single_quote = False
    in_double_quote = False

    while pos < len(input_text) and depth > 0:
        char = input_text[pos]

        # Handle escape sequences if enabled
        if track_escapes and char == '\\' and pos + 1 < len(input_text):
            # Skip the escaped character
            pos += 2
            continue

        # Handle quotes if tracking is enabled
        if track_quotes:
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                pos += 1
                continue
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                pos += 1
                continue

        # Track delimiter depth when not in quotes
        if not (in_single_quote or in_double_quote):
            # Check for opening delimiter
            if (pos + len(open_delim) <= len(input_text) and
                input_text[pos:pos+len(open_delim)] == open_delim):
                depth += 1
                pos += len(open_delim)
                continue

            # Check for closing delimiter
            if (pos + len(close_delim) <= len(input_text) and
                input_text[pos:pos+len(close_delim)] == close_delim):
                depth -= 1
                if depth == 0:
                    return pos + len(close_delim), True
                pos += len(close_delim)
                continue

        pos += 1

    return pos, False


def find_balanced_parentheses(
    input_text: str,
    start_pos: int,
    track_quotes: bool = True
) -> Tuple[int, bool]:
    """
    Find balanced parentheses starting from given position.

    Args:
        input_text: The input string
        start_pos: Starting position (after opening paren)
        track_quotes: Whether to ignore parens inside quotes

    Returns:
        Tuple of (position_after_close_paren, found_closing)
    """
    return find_closing_delimiter(
        input_text, start_pos, '(', ')', track_quotes, True
    )


def find_balanced_double_parentheses(
    input_text: str,
    start_pos: int,
    track_quotes: bool = False
) -> Tuple[int, bool]:
    """
    Find balanced double parentheses for arithmetic expressions.

    Args:
        input_text: The input string
        start_pos: Starting position (after opening $(()
        track_quotes: Whether to ignore parens inside quotes.
            Default False to preserve existing lexer behaviour;
            expansion callers pass True.

    Returns:
        Tuple of (position_after_close_parens, found_closing)
    """
    # For arithmetic expressions, we need to find ))
    # but track individual ( and ) for internal balance
    depth = 0
    pos = start_pos
    in_single_quote = False
    in_double_quote = False

    while pos < len(input_text):
        char = input_text[pos]

        # Handle backslash escapes
        if char == '\\' and pos + 1 < len(input_text):
            pos += 2
            continue

        # Handle quotes if tracking is enabled
        if track_quotes:
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                pos += 1
                continue
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                pos += 1
                continue

        # Skip parentheses inside quotes
        if in_single_quote or in_double_quote:
            pos += 1
            continue

        # Check for )) first
        if pos + 1 < len(input_text) and input_text[pos:pos+2] == '))':
            if depth == 0:
                # Found the closing )) at the right depth
                return pos + 2, True
            else:
                # This )) but we have unmatched ( so treat as regular )
                depth -= 1
                pos += 1  # Only advance by 1 to check the second ) again
                continue

        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1

        pos += 1

    return pos, False


def handle_escape_sequence(
    input_text: str,
    pos: int,
    quote_context: Optional[str] = None
) -> Tuple[str, int]:
    """
    Handle escape sequences based on context.

    Args:
        input_text: The input string
        pos: Position of the backslash
        quote_context: Current quote context ('"', "'", "$'", or None)

    Returns:
        Tuple of (escaped_string, new_position)
    """
    if pos >= len(input_text) or input_text[pos] != '\\':
        return '\\', pos + 1

    if pos + 1 >= len(input_text):
        return '\\', pos + 1

    next_char = input_text[pos + 1]

    if quote_context == "$'":
        # ANSI-C quoting - handle extended escape sequences
        return handle_ansi_c_escape(input_text, pos)
    elif quote_context == '"':
        # In double quotes
        if next_char == '\n':
            # Escaped newline is a line continuation - remove it
            return '', pos + 2
        elif next_char in '"\\`':
            return next_char, pos + 2
        elif next_char == '$':
            # Special case: \$ preserves the backslash in double quotes
            return '\\$', pos + 2
        elif next_char in DOUBLE_QUOTE_ESCAPES:
            return DOUBLE_QUOTE_ESCAPES[next_char], pos + 2
        else:
            # Other characters keep the backslash
            return '\\' + next_char, pos + 2
    elif quote_context is None:
        # Outside quotes - backslash escapes everything
        if next_char == '\n':
            # Escaped newline is a line continuation - remove it
            return '', pos + 2
        elif next_char == '$':
            return '$', pos + 2  # Escaped dollar is literal $
        else:
            return next_char, pos + 2
    else:
        # Single quotes - no escaping (except for the quote itself in some contexts)
        return '\\' + next_char, pos + 2


def handle_ansi_c_escape(input_text: str, pos: int) -> Tuple[str, int]:
    """
    Handle ANSI-C escape sequences in $'...' strings.

    Args:
        input_text: The input string
        pos: Position of the backslash

    Returns:
        Tuple of (escaped_string, new_position)
    """
    if pos + 1 >= len(input_text):
        return '\\', pos + 1

    next_char = input_text[pos + 1]

    # Simple single-character escapes
    simple_escapes = {
        'n': '\n', 't': '\t', 'r': '\r', 'b': '\b',
        'f': '\f', 'v': '\v', 'a': '\a', '\\': '\\',
        "'": "'", '"': '"', '?': '?',
        'e': '\x1b', 'E': '\x1b'  # ANSI escape
    }

    if next_char in simple_escapes:
        return simple_escapes[next_char], pos + 2

    # Hex escape: \xHH
    if next_char == 'x':
        hex_str = ""
        new_pos = pos + 2
        # Read up to 2 hex digits
        for i in range(2):
            if new_pos < len(input_text) and input_text[new_pos] in '0123456789ABCDEFabcdef':
                hex_str += input_text[new_pos]
                new_pos += 1
            else:
                break

        if hex_str:
            try:
                return chr(int(hex_str, 16)), new_pos
            except ValueError:
                return '\\x' + hex_str, new_pos
        else:
            return '\\x', pos + 2

    # Octal escape: \NNN — 1 to 3 octal digits (bash style; a leading 0 is
    # just the first digit, so \101 -> 'A' and \0101 -> octal 010 + '1').
    if next_char in '01234567':
        octal_str = ""
        new_pos = pos + 1  # start at the first octal digit (next_char)
        for i in range(3):
            if new_pos < len(input_text) and input_text[new_pos] in '01234567':
                octal_str += input_text[new_pos]
                new_pos += 1
            else:
                break
        return chr(int(octal_str, 8) & 0xFF), new_pos

    # Unicode escape: \uHHHH
    if next_char == 'u':
        hex_str = ""
        new_pos = pos + 2
        # Read exactly 4 hex digits
        for i in range(4):
            if new_pos < len(input_text) and input_text[new_pos] in '0123456789ABCDEFabcdef':
                hex_str += input_text[new_pos]
                new_pos += 1
            else:
                break

        # bash accepts 1 to 4 hex digits after \u.
        if hex_str:
            try:
                return chr(int(hex_str, 16)), new_pos
            except ValueError:
                return '\\u' + hex_str, new_pos
        else:
            return '\\u', new_pos

    # Unicode escape: \UHHHHHHHH (8 digits)
    if next_char == 'U':
        hex_str = ""
        new_pos = pos + 2
        # Read exactly 8 hex digits
        for i in range(8):
            if new_pos < len(input_text) and input_text[new_pos] in '0123456789ABCDEFabcdef':
                hex_str += input_text[new_pos]
                new_pos += 1
            else:
                break

        # bash accepts 1 to 8 hex digits after \U.
        if hex_str:
            try:
                return chr(int(hex_str, 16)), new_pos
            except ValueError:
                return '\\U' + hex_str, new_pos
        else:
            return '\\U', new_pos

    # For other characters, keep the backslash
    return '\\' + next_char, pos + 2


def extract_variable_name(
    input_text: str,
    start_pos: int,
    special_vars: Set[str],
    posix_mode: bool = False
) -> Tuple[str, int]:
    """
    Extract a variable name starting from the given position.

    Args:
        input_text: The input string
        start_pos: Starting position (after $)
        special_vars: Set of special single-character variables
        posix_mode: Whether to use POSIX-compliant identifier rules

    Returns:
        Tuple of (variable_name, new_position)
    """
    from .unicode_support import is_identifier_char, is_identifier_start

    if start_pos >= len(input_text):
        return "", start_pos

    char = input_text[start_pos]

    # Special single-character variables
    if char in special_vars:
        return char, start_pos + 1

    # Regular variable names
    var_name = ""
    pos = start_pos

    # First character must be letter or underscore (not digit)
    if pos < len(input_text) and is_identifier_start(char, posix_mode):
        var_name += char
        pos += 1

        # Subsequent characters can be letters, numbers, marks, or underscore
        while pos < len(input_text):
            char = input_text[pos]
            if is_identifier_char(char, posix_mode):
                var_name += char
                pos += 1
            else:
                break

    # Don't return anything for invalid start (like digits)
    return var_name, pos


def is_comment_start(
    input_text: str,
    pos: int
) -> bool:
    """
    Check if # at given position starts a comment.

    Args:
        input_text: The input string
        pos: Position to check

    Returns:
        True if this starts a comment
    """
    if pos >= len(input_text) or input_text[pos] != '#':
        return False

    # Comments start at beginning of input or after whitespace/operators
    if pos == 0:
        return True

    prev_char = input_text[pos - 1]
    return prev_char in ' \t\n;|&<>(){}[]'


def extract_quoted_content(
    input_text: str,
    start_pos: int,
    quote_char: str,
    allow_escapes: bool = True
) -> Tuple[str, int, bool]:
    """
    Extract content from a quoted string.

    Args:
        input_text: The input string
        start_pos: Starting position (after opening quote)
        quote_char: The quote character ('"' or "'")
        allow_escapes: Whether to process escape sequences

    Returns:
        Tuple of (content, position_after_close_quote, found_closing_quote)
    """
    content = ""
    pos = start_pos

    while pos < len(input_text):
        char = input_text[pos]

        # Check for closing quote
        if char == quote_char:
            return content, pos + 1, True

        # Handle escape sequences if allowed
        if allow_escapes and char == '\\' and pos + 1 < len(input_text):
            escaped_str, new_pos = handle_escape_sequence(
                input_text, pos, quote_char
            )
            content += escaped_str
            pos = new_pos
        else:
            content += char
            pos += 1

    # Reached end without finding closing quote
    return content, pos, False


def validate_brace_expansion(
    input_text: str,
    start_pos: int
) -> Tuple[str, int, bool]:
    """
    Validate and extract a brace expansion ${...}.

    Args:
        input_text: The input string
        start_pos: Starting position (after ${)

    Returns:
        Tuple of (content, position_after_close_brace, found_closing_brace)
    """
    pos = start_pos
    n = len(input_text)
    brace_depth = 1

    while pos < n:
        char = input_text[pos]

        if char == '\\' and pos + 1 < n:
            pos += 2
            continue
        if char == "'":
            # Single-quoted segment: a } inside it does not close (POSIX)
            end = input_text.find("'", pos + 1)
            if end == -1:
                break
            pos = end + 1
            continue
        if char == '"':
            # Double-quoted segment (with escape handling)
            pos += 1
            while pos < n and input_text[pos] != '"':
                if input_text[pos] == '\\' and pos + 1 < n:
                    pos += 2
                else:
                    pos += 1
            pos += 1
            continue
        if input_text.startswith('$(', pos):
            # Command/arithmetic substitution: skip balanced parens
            paren_depth = 0
            while pos < n:
                if input_text[pos] == '(':
                    paren_depth += 1
                elif input_text[pos] == ')':
                    paren_depth -= 1
                    if paren_depth == 0:
                        pos += 1
                        break
                pos += 1
            continue
        if char == '{':
            brace_depth += 1
        elif char == '}':
            brace_depth -= 1
            if brace_depth == 0:
                return input_text[start_pos:pos], pos + 1, True

        pos += 1

    return input_text[start_pos:min(pos, n)], min(pos, n), False


def is_inside_expansion(
    input_text: str,
    position: int
) -> bool:
    """
    Check if the position is inside an arithmetic expression or command substitution.

    Args:
        input_text: The input string
        position: Position to check

    Returns:
        True if position is inside an expansion
    """
    if position >= len(input_text):
        return False

    # Simple approach: scan from beginning and track expansion boundaries
    i = 0
    while i <= position and i < len(input_text):
        # Check for arithmetic expansion $((
        if i + 2 < len(input_text) and input_text[i:i+3] == '$((':
            # Find the closing ))
            end_pos, found = find_balanced_double_parentheses(input_text, i + 3)
            if found and i <= position < end_pos:
                return True
            i = end_pos if found else i + 3
            continue

        # Check for command substitution $(
        if i + 1 < len(input_text) and input_text[i:i+2] == '$(':
            # Find the closing )
            end_pos, found = find_balanced_parentheses(input_text, i + 2)
            if found and i <= position < end_pos:
                return True
            i = end_pos if found else i + 2
            continue

        # Check for backtick command substitution
        if input_text[i] == '`':
            # Find the closing backtick
            j = i + 1
            while j < len(input_text) and input_text[j] != '`':
                j += 1
            if j < len(input_text):  # Found closing backtick
                if i < position < j:  # Position is inside backticks
                    return True
                i = j + 1
            else:
                i += 1
            continue

        i += 1

    return False
