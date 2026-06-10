"""Keyword normalization pass for lexer output."""

from typing import List, Optional

from ..token_types import Token, TokenType
from .command_position import (
    CASE_TERMINATORS,
    RESET_TO_COMMAND_POSITION,
)
from .command_position import (
    STATEMENT_SEPARATORS as _BASE_SEPARATORS,
)
from .constants import KEYWORDS
from .keyword_defs import KEYWORD_TYPE_MAP


class KeywordNormalizer:
    """Normalize WORD tokens to reserved keyword token types when appropriate."""

    CONTROL_KEYWORDS = {'if', 'for', 'select', 'while', 'until', 'case', 'function'}

    # Operators that return us to command position: the basic separators plus
    # case-item terminators (which the normalizer treats as separators).
    STATEMENT_SEPARATORS = _BASE_SEPARATORS | CASE_TERMINATORS

    RESET_TO_COMMAND_POSITION = RESET_TO_COMMAND_POSITION

    def normalize(self, tokens: List[Token]) -> List[Token]:
        """Normalize reserved keywords in token list."""
        if not tokens:
            return tokens

        command_position = True
        pending_in: Optional[str] = None
        pending_heredoc_delim = False
        heredoc_already_collected = False
        heredoc_delimiter: Optional[str] = None
        in_heredoc = False

        for token in tokens:
            token_lower = token.value if token.value is None else token.value.lower()
            converted_type: Optional[TokenType] = None

            # Track heredoc delimiters to avoid normalizing content lines.
            # When heredoc content has already been collected (heredoc_key present),
            # the content lines are NOT in the token stream, so we must NOT enter
            # in_heredoc mode — otherwise we'd skip real tokens looking for a
            # delimiter that has already been consumed.
            if token.type in {TokenType.HEREDOC, TokenType.HEREDOC_STRIP}:
                heredoc_already_collected = hasattr(token, 'heredoc_key')
                pending_heredoc_delim = True
                command_position = False
                continue

            if pending_heredoc_delim:
                # The token after HEREDOC should be the delimiter
                if token.type == TokenType.WORD:
                    if not heredoc_already_collected:
                        heredoc_delimiter = token.value
                        in_heredoc = True
                pending_heredoc_delim = False
                command_position = False
                continue

            if in_heredoc:
                if token.type == TokenType.WORD and heredoc_delimiter is not None and token.value == heredoc_delimiter:
                    # Delimiter terminates the heredoc
                    in_heredoc = False
                    heredoc_delimiter = None
                command_position = False
                continue

            if token.type == TokenType.WORD and token_lower:
                if pending_in and token_lower == 'in':
                    converted_type = TokenType.IN
                    pending_in = None
                elif command_position and token_lower in KEYWORDS:
                    if token_lower == 'in' and not pending_in:
                        converted_type = None
                    else:
                        converted_type = KEYWORD_TYPE_MAP.get(token_lower)
                        if token_lower in {'for', 'select', 'case'}:
                            pending_in = token_lower

            if converted_type:
                token.type = converted_type
                token.is_keyword = True
            elif token.type == TokenType.IN:
                # Already tagged as IN by lexer, clear pending state
                pending_in = None

            # Update command position based on (possibly converted) token
            command_position = self._next_command_position(
                token, command_position, pending_in
            )

            # Adjust pending_in when encountering explicit tokens
            if token.type in {TokenType.FOR, TokenType.SELECT, TokenType.CASE}:
                pending_in = token.type.name.lower()

        return tokens

    def _next_command_position(
        self,
        token: Token,
        _current_command_position: bool,
        pending_in: Optional[str],
    ) -> bool:
        """Determine whether the next token should be treated as command position."""
        token_type = token.type

        if token_type in self.STATEMENT_SEPARATORS:
            return True

        if token_type in self.RESET_TO_COMMAND_POSITION:
            return True

        if token_type in {TokenType.IF, TokenType.WHILE, TokenType.UNTIL}:
            # Conditions are parsed as command lists
            return True

        if token_type in {TokenType.FI, TokenType.DONE, TokenType.ESAC}:
            return True

        if token_type in {TokenType.LPAREN, TokenType.LBRACE}:
            return True

        # After closing a case pattern with ), we're in command position
        if token_type == TokenType.RPAREN:
            return True

        if token_type == TokenType.IN and pending_in:
            return False

        if token_type in {
            TokenType.FOR,
            TokenType.SELECT,
            TokenType.CASE,
            TokenType.FUNCTION,
        }:
            return False

        if token.type == TokenType.WORD and token.value:
            lowered = token.value.lower()
            if lowered in self.CONTROL_KEYWORDS:
                return lowered in {'if', 'while', 'until'}

        return False
