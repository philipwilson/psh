"""Keyword normalization pass for lexer output."""

from typing import List, Optional

from .command_position import (
    CASE_TERMINATORS,
    PIPELINE_PREFIX_TOKENS,
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
        # One-shot: set when a `function` keyword is seen, consumed by the very
        # next token (the function name). bash allows ANY compound command as a
        # `function NAME` body (`function f for ...; do ...; done`), so the
        # token after the name is at command position — this flag forces that so
        # the body's leading reserved word (`for`/`if`/`while`/`case`/...) is
        # recognized. (The `NAME()` form already reaches command position via
        # the closing `)`.)
        function_name_pending = False
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
                elif pending_in in ('for', 'select') and token_value == 'do':
                    # POSIX no-`in` loop form: `for name do ...` /
                    # `for name; do ...` iterates the positional parameters.
                    # `do` here ends the implicit word list and opens the body,
                    # so it is the DO keyword even though it is not at command
                    # position (`for x do`, no separator). Clearing pending_in
                    # also stops a later `in` in the body (`for x; do echo in`)
                    # being mis-read as the loop's `in`.
                    converted_type = TokenType.DO
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
            elif token.type == TokenType.DO and pending_in in ('for', 'select'):
                # A pre-typed `do` (this normalizer runs again over already-
                # normalized tokens via create_context) closes a no-`in` loop
                # header. Clear pending_in so this pass stays idempotent and a
                # later `in` in the body is not mis-read as the loop keyword.
                pending_in = None

            # Update command position based on (possibly converted) token
            command_position = self._next_command_position(
                token, command_position, pending_in
            )

            # The token just processed was the `function NAME` name — its body
            # (a compound command) starts at command position.
            if function_name_pending:
                command_position = True
                function_name_pending = False

            # Both flags are one-shot: consumed by this token.
            subject_pending = False
            case_pattern_start = next_pattern_start

            # Adjust pending_in when encountering explicit tokens
            if token.type in {TokenType.FOR, TokenType.SELECT, TokenType.CASE}:
                pending_in = token.type.name.lower()
                subject_pending = True
            elif token.type == TokenType.FUNCTION:
                function_name_pending = True

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

        # A pipeline-prefix operator (`!`) keeps the next token at command
        # position, so `! while ...`, `! if ...`, `! [[ ... ]]` recognize their
        # reserved word / test operator.
        if token_type in PIPELINE_PREFIX_TOKENS:
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

        # NOTE: a WORD whose *value* merely looks like a keyword (`if`, `while`,
        # …) does NOT keep command position. By the time we reach here a real
        # control-flow keyword carries its own token type (handled above); a
        # WORD that still spells `if` is an ordinary argument (`echo if then`),
        # so the token AFTER it must NOT be promoted to a keyword.
        return False
