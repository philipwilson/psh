"""Unified quote parsing with configurable rules and expansion support."""

from typing import TYPE_CHECKING, List, Optional, Tuple

from . import pure_helpers
from .position import Position
from .token_parts import TokenPart

if TYPE_CHECKING:
    from .expansion_parser import ExpansionParser
    from .position import PositionTracker


class QuoteRules:
    """Defines parsing rules for different quote types."""

    def __init__(
        self,
        quote_char: str,
        allow_expansions: bool,
        processes_escapes: bool,
        allows_newlines: bool = True,
        allows_nested_quotes: bool = False
    ):
        """
        Initialize quote rules.

        Args:
            quote_char: The quote character ('"', "'", '`')
            allow_expansions: Whether to process variable/command expansions
            processes_escapes: Whether backslash escapes are processed at all.
                The actual escape semantics per context live in
                pure_helpers.handle_escape_sequence; this flag only gates it.
            allows_newlines: Whether newlines are allowed in quoted strings
            allows_nested_quotes: Whether the same quote can be nested (with escaping)
        """
        self.quote_char = quote_char
        self.allow_expansions = allow_expansions
        self.processes_escapes = processes_escapes
        self.allows_newlines = allows_newlines
        self.allows_nested_quotes = allows_nested_quotes


# Predefined quote rules for shell contexts
QUOTE_RULES = {
    '"': QuoteRules(
        quote_char='"',
        allow_expansions=True,
        processes_escapes=True,   # \$ \\ \" \` (handle_escape_sequence)
        allows_newlines=True,
        allows_nested_quotes=True
    ),
    "'": QuoteRules(
        quote_char="'",
        allow_expansions=False,
        processes_escapes=False,  # No escapes in single quotes
        allows_newlines=True,
        allows_nested_quotes=False
    ),
    '`': QuoteRules(
        quote_char='`',
        allow_expansions=False,  # Backticks are command substitution, not string quotes
        processes_escapes=True,
        allows_newlines=True,
        allows_nested_quotes=True
    ),
    "$'": QuoteRules(
        quote_char="'",  # Closing quote is just '
        allow_expansions=False,  # No variable expansion in ANSI-C quotes
        processes_escapes=True,  # C escapes, \xHH, \0NNN, \uHHHH, \UHHHHHHHH
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
        quote_type: Optional[str] = None
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
            if (rules.allow_expansions and char == '`' and rules.quote_char == '"'
                    and self.expansion_parser):
                # Save current part
                if current_value:
                    parts.append(self._create_literal_part(
                        current_value, part_start, pos, rules.quote_char
                    ))
                    current_value = ""

                # Parse backtick substitution (single implementation lives in
                # ExpansionParser). NOTE: an unclosed backtick here always
                # coincides with an unclosed double quote, so the lexer raises
                # before the 'backtick_unclosed' part type can be observed.
                backtick_part, new_pos = self.expansion_parser.parse_backtick_substitution(
                    input_text, pos, rules.quote_char
                )
                parts.append(backtick_part)
                pos = new_pos
                part_start = pos
                continue

            # Handle escape sequences (only if allowed by the quote rules)
            if char == '\\' and pos + 1 < len(input_text) and rules.processes_escapes:
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



