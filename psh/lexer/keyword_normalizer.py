"""Keyword normalization pass for lexer output."""

from dataclasses import dataclass, replace
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


@dataclass
class _HeredocSkip:
    """The heredoc-skip mini-FSM used by :meth:`KeywordNormalizer.normalize`.

    When a ``<<``/``<<-`` operator's body lines are STILL in the token stream —
    ``heredoc_key is None``, i.e. plain ``tokenize()`` rather than
    ``tokenize_with_heredocs`` (which lifts bodies out) — the delimiter word and
    every body line must pass through UN-normalized (a body line ``done`` is not
    a keyword). This tracks that skip window; a collected body
    (``heredoc_key`` set) is never entered, so real tokens after it are still
    normalized.
    """
    pending_delim: bool = False
    already_collected: bool = False
    delimiter: Optional[str] = None
    in_body: bool = False

    def handle(self, token: Token) -> bool:
        """Advance the FSM for *token*; return True when the token is part of a
        heredoc (operator, delimiter word, or body line) and must be emitted
        verbatim — the caller then drops out of command position and continues.
        Returns False for ordinary command text the keyword FSM should classify.
        """
        if token.type in {TokenType.HEREDOC, TokenType.HEREDOC_STRIP}:
            # Absent heredoc_key => body lines are still in the stream and we
            # must scan for the delimiter; present => body was collected.
            self.already_collected = token.heredoc_key is not None
            self.pending_delim = True
            return True
        if self.pending_delim:
            # The token right after HEREDOC is the delimiter word.
            if token.type == TokenType.WORD and not self.already_collected:
                self.delimiter = token.value
                self.in_body = True
            self.pending_delim = False
            return True
        if self.in_body:
            if (token.type == TokenType.WORD and self.delimiter is not None
                    and token.value == self.delimiter):
                self.in_body = False
                self.delimiter = None
            return True
        return False


@dataclass
class _KeywordState:
    """The keyword FSM's command-position axis and one-shot look-ahead flags,
    grouped so :meth:`KeywordNormalizer.normalize` reads as one machine.

    * ``command_position`` — a reserved word is only promoted here.
    * ``pending_in`` — the opener (``'for'``/``'select'``/``'case'``) awaiting
      its ``in`` (or, for the loops, a no-``in`` ``do``).
    * ``function_name_pending`` — set by ``function``; the token after the name
      starts the body at command position.
    * ``subject_pending`` — the loop variable / case subject right after
      ``for``/``select``/``case`` stays a WORD even when spelled ``in``.
    * ``case_pattern_start`` — the token right after a case's ``in`` where a
      bare ``esac`` closes an empty case.
    """
    command_position: bool = True
    pending_in: Optional[str] = None
    function_name_pending: bool = False
    subject_pending: bool = False
    case_pattern_start: bool = False


class KeywordNormalizer:
    """Normalize WORD tokens to reserved keyword token types when appropriate."""

    # Operators that return us to command position: the basic separators plus
    # case-item terminators (which the normalizer treats as separators).
    STATEMENT_SEPARATORS = _BASE_SEPARATORS | CASE_TERMINATORS

    RESET_TO_COMMAND_POSITION = RESET_TO_COMMAND_POSITION

    def normalize(self, tokens: List[Token]) -> List[Token]:
        """Normalize reserved keywords, returning a NEW list.

        Classification does not mutate: a WORD promoted to a reserved keyword
        is replaced by a fresh token (``dataclasses.replace``) in the returned
        list; the caller's tokens are left untouched. Every input token appears
        in the output, in order.
        """
        if not tokens:
            return tokens

        result: List[Token] = []
        st = _KeywordState()
        heredoc = _HeredocSkip()

        for token in tokens:
            # Heredoc delimiter/body tokens (when bodies are still in the stream)
            # pass through un-normalized and drop us out of command position.
            if heredoc.handle(token):
                st.command_position = False
                result.append(token)
                continue

            # Keyword recognition is case-sensitive, matching bash: `IF` is an
            # ordinary word, only the exact lowercase spelling is a keyword.
            token_value = token.value
            converted_type: Optional[TokenType] = None
            next_pattern_start = False

            if token.type == TokenType.WORD and token_value:
                if st.subject_pending:
                    # Loop variable / case subject: stays a WORD even when
                    # spelled `in` (or any other keyword).
                    converted_type = None
                elif st.pending_in and token_value == 'in':
                    converted_type = TokenType.IN
                    if st.pending_in == 'case':
                        next_pattern_start = True
                    st.pending_in = None
                elif st.pending_in in ('for', 'select') and token_value == 'do':
                    # POSIX no-`in` loop form: `for name do ...` /
                    # `for name; do ...` iterates the positional parameters.
                    # `do` here ends the implicit word list and opens the body,
                    # so it is the DO keyword even though it is not at command
                    # position (`for x do`, no separator). Clearing pending_in
                    # also stops a later `in` in the body (`for x; do echo in`)
                    # being mis-read as the loop's `in`.
                    converted_type = TokenType.DO
                    st.pending_in = None
                elif st.case_pattern_start and token_value == 'esac':
                    # `case a in esac` — esac right after `in` closes the case.
                    converted_type = TokenType.ESAC
                elif st.command_position and token_value in KEYWORDS:
                    if token_value == 'in' and not st.pending_in:
                        converted_type = None
                    else:
                        converted_type = KEYWORD_TYPE_MAP.get(token_value)

            if converted_type:
                token = replace(token, type=converted_type, is_keyword=True)
            elif token.type == TokenType.IN:
                # Already tagged as IN by lexer, clear pending state
                if st.pending_in == 'case':
                    next_pattern_start = True
                st.pending_in = None
            elif token.type == TokenType.DO and st.pending_in in ('for', 'select'):
                # A pre-typed `do` (this normalizer runs again over already-
                # normalized tokens via create_context) closes a no-`in` loop
                # header. Clear pending_in so this pass stays idempotent and a
                # later `in` in the body is not mis-read as the loop keyword.
                st.pending_in = None

            # Update command position based on (possibly converted) token
            st.command_position = self._next_command_position(token, st.pending_in)

            # The token just processed was the `function NAME` name — its body
            # (a compound command) starts at command position.
            if st.function_name_pending:
                st.command_position = True
                st.function_name_pending = False

            # Both flags are one-shot: consumed by this token.
            st.subject_pending = False
            st.case_pattern_start = next_pattern_start

            # Adjust pending_in when encountering explicit tokens
            if token.type in {TokenType.FOR, TokenType.SELECT, TokenType.CASE}:
                st.pending_in = token.type.name.lower()
                st.subject_pending = True
            elif token.type == TokenType.FUNCTION:
                st.function_name_pending = True

            result.append(token)

        return result

    def _next_command_position(
        self,
        token: Token,
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
