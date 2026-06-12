"""Keyword normalization pass for lexer output."""

from typing import List, Optional

from .command_position import (
    CASE_TERMINATORS,
    RESET_TO_COMMAND_POSITION,
)
from .command_position import (
    STATEMENT_SEPARATORS as _BASE_SEPARATORS,
)
from .constants import KEYWORDS
from .keyword_defs import KEYWORD_TYPE_MAP
from .token_types import Token, TokenType


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
        # One-shot: the token right after `for`/`select`/`case` is the loop
        # variable / case subject — bash never reads it as the `in` keyword
        # (`for in in 1 2` and `case in in in) ...` are valid bash).
        subject_pending = False
        # One-shot: the token right after a case's `in` keyword. bash
        # recognizes `esac` there (`case a in esac` is a valid empty case);
        # any other word is an ordinary pattern word.
        case_pattern_start = False
        pending_heredoc_delim = False
        heredoc_already_collected = False
        heredoc_delimiter: Optional[str] = None
        in_heredoc = False

        for token in tokens:
            # Keyword recognition is case-sensitive, matching bash: `IF` is an
            # ordinary word, only the exact lowercase spelling is a keyword.
            token_value = token.value
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

            next_pattern_start = False

            if token.type == TokenType.WORD and token_value:
                if subject_pending:
                    # Loop variable / case subject: stays a WORD even when
                    # spelled `in` (or any other keyword).
                    converted_type = None
                elif pending_in and token_value == 'in':
                    converted_type = TokenType.IN
                    if pending_in == 'case':
                        next_pattern_start = True
                    pending_in = None
                elif case_pattern_start and token_value == 'esac':
                    # `case a in esac` — esac right after `in` closes the case.
                    converted_type = TokenType.ESAC
                elif command_position and token_value in KEYWORDS:
                    if token_value == 'in' and not pending_in:
                        converted_type = None
                    else:
                        converted_type = KEYWORD_TYPE_MAP.get(token_value)

            if converted_type:
                token.type = converted_type
                token.is_keyword = True
            elif token.type == TokenType.IN:
                # Already tagged as IN by lexer, clear pending state
                if pending_in == 'case':
                    next_pattern_start = True
                pending_in = None

            # Update command position based on (possibly converted) token
            command_position = self._next_command_position(
                token, command_position, pending_in
            )

            # Both flags are one-shot: consumed by this token.
            subject_pending = False
            case_pattern_start = next_pattern_start

            # Adjust pending_in when encountering explicit tokens
            if token.type in {TokenType.FOR, TokenType.SELECT, TokenType.CASE}:
                pending_in = token.type.name.lower()
                subject_pending = True

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
            # Exact (case-sensitive) match, as in bash.
            if token.value in self.CONTROL_KEYWORDS:
                return token.value in {'if', 'while', 'until'}

        return False
