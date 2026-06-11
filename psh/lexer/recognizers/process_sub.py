"""Process substitution token recognizer."""

from typing import Optional, Tuple

from ..state_context import LexerContext
from ..token_types import Token, TokenType
from .base import TokenRecognizer


class ProcessSubstitutionRecognizer(TokenRecognizer):
    """Recognizes process substitution tokens <(...) and >(...)."""

    @property
    def priority(self) -> int:
        """Higher priority than redirect/operator recognizers."""
        return 160

    def can_recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> bool:
        """Check if current position starts a process substitution."""
        if pos >= len(input_text) - 1:  # Need at least 2 chars
            return False

        # Check for <( or >(
        if pos + 1 < len(input_text):
            two_chars = input_text[pos:pos+2]
            return two_chars in ['<(', '>(']

        return False

    def recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Optional[Tuple[Token, int]]:
        """Recognize process substitution tokens."""
        start_pos = pos

        # Determine type
        if input_text[pos] == '<':
            token_type = TokenType.PROCESS_SUB_IN
        else:  # '>'
            token_type = TokenType.PROCESS_SUB_OUT

        # Skip the < or >
        pos += 1

        # Now we need to read the balanced parentheses
        # Skip the opening (
        if pos < len(input_text) and input_text[pos] == '(':
            pos += 1
        else:
            return None  # Not a process substitution

        # Read until we find the matching )
        paren_count = 1

        while pos < len(input_text) and paren_count > 0:
            char = input_text[pos]

            # Handle quotes to avoid counting parens inside strings
            if char in ['"', "'"]:
                # Skip quoted section
                quote_char = char
                pos += 1
                while pos < len(input_text):
                    if input_text[pos] == quote_char:
                        # Check if escaped
                        if pos > 0 and input_text[pos-1] == '\\':
                            # Count consecutive backslashes
                            backslash_count = 0
                            check_pos = pos - 1
                            while check_pos >= 0 and input_text[check_pos] == '\\':
                                backslash_count += 1
                                check_pos -= 1
                            # If odd number of backslashes, quote is escaped
                            if backslash_count % 2 == 1:
                                pos += 1
                                continue
                        # Quote is not escaped, we're done with quoted section
                        pos += 1
                        break
                    pos += 1
            elif char == '(':
                paren_count += 1
                pos += 1
            elif char == ')':
                paren_count -= 1
                pos += 1
            elif char == '\\' and pos + 1 < len(input_text):
                # Skip escaped character
                pos += 2
            else:
                pos += 1

        if paren_count != 0:
            # Unclosed parentheses
            return None

        # Create token with the entire process substitution
        value = input_text[start_pos:pos]
        token = Token(
            token_type,
            value,
            start_pos,
            pos
        )

        return token, pos
