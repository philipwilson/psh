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

        # Find the matching ) with the same grammar-aware scanner used for
        # $(...) command substitutions: the content is a full shell command
        # list, so case patterns (`<(case x in x) echo hi;; esac)`), quotes,
        # comments, and heredocs must not break the extent.
        from ..cmdsub_scanner import find_command_substitution_end
        pos, found = find_command_substitution_end(input_text, pos)
        if not found:
            # Unclosed: take everything to end of input as one (incomplete)
            # process-substitution token — mirroring how $( marks
            # 'command_unclosed' rather than returning None. Degrading to a
            # bare '<' redirect here would let an inner `<<EOF` leak out as a
            # SEPARATE top-level heredoc, whose body the heredoc lexer would
            # then strip — breaking the later full-state tokenization once the
            # closing ')' arrives (`cat <(cat <<EOF ... EOF\n)`). Keeping the
            # whole span inside this token leaves the heredoc nested where it
            # belongs, exactly as it is inside $(...).
            pos = len(input_text)

        # Create token with the entire process substitution
        value = input_text[start_pos:pos]
        token = Token(
            token_type,
            value,
            start_pos,
            pos
        )

        return token, pos
