"""Unified quote parsing with configurable rules and expansion support."""

from typing import Dict, List, Optional, Tuple

from . import pure_helpers
from .position import Position
from .token_parts import TokenPart


class QuoteRules:
    """Defines parsing rules for different quote types."""

    def __init__(
        self,
        quote_char: str,
        allow_expansions: bool,
        escape_sequences: Dict[str, str],
        allows_newlines: bool = True,
        allows_nested_quotes: bool = False
    ):
        """
        Initialize quote rules.

        Args:
            quote_char: The quote character ('"', "'", '`')
            allow_expansions: Whether to process variable/command expansions
            escape_sequences: Map of escape sequences to their replacements
            allows_newlines: Whether newlines are allowed in quoted strings
            allows_nested_quotes: Whether the same quote can be nested (with escaping)
        """
        self.quote_char = quote_char
        self.allow_expansions = allow_expansions
        self.escape_sequences = escape_sequences
        self.allows_newlines = allows_newlines
        self.allows_nested_quotes = allows_nested_quotes


# Predefined quote rules for shell contexts
QUOTE_RULES = {
    '"': QuoteRules(
        quote_char='"',
        allow_expansions=True,
        escape_sequences={
            'n': '\n', 't': '\t', 'r': '\r', 'b': '\b',
            'f': '\f', 'v': '\v', '\\': '\\', '"': '"',
            '`': '`', '$': '\\$'  # Special handling for $
        },
        allows_newlines=True,
        allows_nested_quotes=True
    ),
    "'": QuoteRules(
        quote_char="'",
        allow_expansions=False,
        escape_sequences={},  # No escapes in single quotes
        allows_newlines=True,
        allows_nested_quotes=False
    ),
    '`': QuoteRules(
        quote_char='`',
        allow_expansions=False,  # Backticks are command substitution, not string quotes
        escape_sequences={
            '\\': '\\',
            '`': '`',
            '$': '$'
        },
        allows_newlines=True,
        allows_nested_quotes=True
    ),
    "$'": QuoteRules(
        quote_char="'",  # Closing quote is just '
        allow_expansions=False,  # No variable expansion in ANSI-C quotes
        escape_sequences={
            # Standard C escapes
            'n': '\n', 't': '\t', 'r': '\r', 'b': '\b',
            'f': '\f', 'v': '\v', 'a': '\a', '\\': '\\',
            "'": "'", '"': '"', '?': '?',
            # ANSI escape
            'e': '\x1b', 'E': '\x1b',
            # Special sequences handled separately: \xHH, \0NNN, \uHHHH, \UHHHHHHHH
        },
        allows_newlines=True,
        allows_nested_quotes=False
    )
}


class UnifiedQuoteParser:
    """Handles all quote parsing with unified logic."""

    def __init__(self, expansion_parser: Optional['ExpansionParser'] = None):
        """
        Initialize the unified quote parser.

        Args:
            expansion_parser: Parser for handling expansions within quotes
        """
        self.expansion_parser = expansion_parser

    def parse_quoted_string(
        self,
        input_text: str,
        start_pos: int,
        rules: QuoteRules,
        position_tracker: Optional['PositionTracker'] = None,
        quote_type: str = None
    ) -> Tuple[List[TokenPart], int, bool]:
        """
        Parse a quoted string according to the given rules.

        Args:
            input_text: The input string
            start_pos: Starting position (after opening quote)
            rules: Quote parsing rules
            position_tracker: Optional position tracker for rich position info
            quote_type: Optional quote type override (e.g., "$'" for ANSI-C)

        Returns:
            Tuple of (token_parts, position_after_closing_quote, found_closing_quote)
        """
        parts: List[TokenPart] = []
        pos = start_pos
        current_value = ""
        part_start = start_pos

        while pos < len(input_text):
            char = input_text[pos]

            # Check for closing quote
            if char == rules.quote_char:
                # Save final part if any
                if current_value:
                    parts.append(self._create_literal_part(
                        current_value, part_start, pos, rules.quote_char
                    ))
                return parts, pos + 1, True

            # Handle newlines if not allowed
            if char == '\n' and not rules.allows_newlines:
                # Unclosed quote error - save what we have
                if current_value:
                    parts.append(self._create_literal_part(
                        current_value, part_start, pos, rules.quote_char
                    ))
                return parts, pos, False

            # Handle expansions if allowed
            if rules.allow_expansions and char == '$' and self.expansion_parser:
                # Save current part
                if current_value:
                    parts.append(self._create_literal_part(
                        current_value, part_start, pos, rules.quote_char
                    ))
                    current_value = ""

                # Parse expansion
                expansion_part, new_pos = self.expansion_parser.parse_expansion(
                    input_text, pos, rules.quote_char
                )
                parts.append(expansion_part)
                pos = new_pos
                part_start = pos
                continue

            # Handle backtick command substitution in double quotes
            if rules.allow_expansions and char == '`' and rules.quote_char == '"':
                # Save current part
                if current_value:
                    parts.append(self._create_literal_part(
                        current_value, part_start, pos, rules.quote_char
                    ))
                    current_value = ""

                # Parse backtick substitution
                backtick_part, new_pos = self._parse_backtick_substitution(
                    input_text, pos, rules.quote_char
                )
                parts.append(backtick_part)
                pos = new_pos
                part_start = pos
                continue

            # Handle escape sequences (only if allowed by the quote rules)
            if char == '\\' and pos + 1 < len(input_text) and rules.escape_sequences:
                # Use the quote_type parameter if provided (for ANSI-C quotes)
                context = quote_type if quote_type else rules.quote_char
                escaped_str, new_pos = pure_helpers.handle_escape_sequence(
                    input_text, pos, context
                )
                current_value += escaped_str
                pos = new_pos
                continue

            # Regular character
            current_value += char
            pos += 1

        # Unclosed quote - add what we have
        if current_value:
            parts.append(self._create_literal_part(
                current_value, part_start, pos, rules.quote_char
            ))

        return parts, pos, False

    def parse_simple_quoted_string(
        self,
        input_text: str,
        start_pos: int,
        quote_char: str
    ) -> Tuple[str, int, bool]:
        """
        Parse a simple quoted string without expansion support.

        This is an optimized version for single quotes and contexts
        where we just need the literal content.

        Args:
            input_text: The input string
            start_pos: Starting position (after opening quote)
            quote_char: The quote character

        Returns:
            Tuple of (content, position_after_closing_quote, found_closing_quote)
        """
        rules = QUOTE_RULES.get(quote_char)
        if not rules or rules.allow_expansions:
            # Fall back to full parsing for complex cases
            parts, pos, found = self.parse_quoted_string(
                input_text, start_pos, rules or QUOTE_RULES["'"]
            )
            content = ''.join(part.value for part in parts)
            return content, pos, found

        # Use pure function for simple case
        return pure_helpers.extract_quoted_content(
            input_text, start_pos, quote_char, allow_escapes=False
        )

    def _create_literal_part(
        self,
        value: str,
        start_pos: int,
        end_pos: int,
        quote_type: str
    ) -> TokenPart:
        """Create a literal token part."""
        return TokenPart(
            value=value,
            quote_type=quote_type,
            is_variable=False,
            is_expansion=False,
            start_pos=Position(start_pos, 0, 0),  # Line/col will be filled by tracker
            end_pos=Position(end_pos, 0, 0)
        )

    def _parse_backtick_substitution(
        self,
        input_text: str,
        start_pos: int,
        quote_context: str
    ) -> Tuple[TokenPart, int]:
        """Parse backtick command substitution."""
        # Find closing backtick
        pos = start_pos + 1  # Skip opening backtick
        content = ""

        while pos < len(input_text) and input_text[pos] != '`':
            if input_text[pos] == '\\' and pos + 1 < len(input_text):
                next_char = input_text[pos + 1]
                if next_char in '`$\\':
                    pos += 1  # Skip backslash
                    content += input_text[pos] if pos < len(input_text) else ''
                else:
                    content += input_text[pos]
            else:
                content += input_text[pos]
            pos += 1

        # Include closing backtick
        if pos < len(input_text) and input_text[pos] == '`':
            pos += 1
            full_value = '`' + content + '`'
        else:
            full_value = '`' + content  # Unclosed

        return TokenPart(
            value=full_value,
            quote_type=quote_context,
            is_expansion=True,
            expansion_type='backtick',
            start_pos=Position(start_pos, 0, 0),
            end_pos=Position(pos, 0, 0)
        ), pos


class QuoteParsingContext:
    """Context for quote parsing operations."""

    def __init__(
        self,
        input_text: str,
        position_tracker: Optional['PositionTracker'] = None,
        config: Optional['LexerConfig'] = None
    ):
        """
        Initialize parsing context.

        Args:
            input_text: The input string being parsed
            position_tracker: Optional position tracker for rich position info
            config: Optional lexer configuration
        """
        self.input_text = input_text
        self.position_tracker = position_tracker
        self.config = config
        self.parser = UnifiedQuoteParser()

    def is_quote_character(self, char: str) -> bool:
        """Check if character is a supported quote character."""
        if not self.config:
            return char in QUOTE_RULES

        # Check configuration
        if char == '"':
            return self.config.enable_double_quotes
        elif char == "'":
            return self.config.enable_single_quotes
        elif char == '`':
            return self.config.enable_backtick_quotes

        return False


