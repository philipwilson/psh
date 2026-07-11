"""Operator-debris word recognizer.

The literal recognizer's word-START rules reject most operator characters,
but the shell grammar still makes words out of them mid-command. An
instrumented census (2026-06-12, B6: 15k-input characterization corpus +
the full test suite + ~71k fuzz inputs) found exactly FOUR word-start
character classes that the literal recognizer rejects yet which still
begin legitimate, bash-verified words. This recognizer collects them.

Census-verified live word-start set (the only chars ``can_recognize``
accepts):

* ``]`` — closing-bracket words: ``[ x = y ]`` test commands,
  ``a=([1]=x z)`` sparse-array element prefixes (``]=x``), and composite
  continuations like ``a]b``;
* ``+`` — ``vars+=(x)`` append assignments (WORD ``+=`` re-joined by the
  parser), ``set +x`` option words, regex ``([a-z]+)``;
* ``=`` — bare ``=`` in test commands, assignment continuations like the
  ``=c`` of ``a=b=c`` (re-joined by the parser);
* ``[`` — case-pattern glob classes (``[0-9]*)``) and bracket words in
  array-init contexts.

These words deliberately use a LOOSER terminator set than the literal
recognizer (``= + [ ]`` do NOT terminate here): folding them into the
literal collect loop would split ``]=x`` and ``+=`` differently. The
collection rule: read until whitespace, a hard operator (``<>&|;(){}!``),
or a quote/expansion starter (``$ ` " '``).

The recognizer carries the LOWEST priority of any recognizer (literal=70,
comment=60, whitespace=30, debris=10) so it is tried strictly LAST —
preserving the historical "fallback step" ordering in which this collector
ran only after every other recognizer declined. Because it runs last, a
plain ``[`` or ``[[`` handled by the operator/literal recognizers is never
stolen by this recognizer.
"""

from typing import Optional, Tuple

from ..state_context import LexerContext
from ..token_types import Token, TokenType
from ..unicode_support import is_whitespace
from .base import TokenRecognizer

# The four word-start characters the census proved reach this recognizer.
# Making the domain explicit documents that this is a grammar-recognized
# word form, not a catch-all for arbitrary stray characters.
_DEBRIS_WORD_STARTS = frozenset(']+=[')

# Characters that end an operator-debris word: whitespace (checked
# separately for Unicode awareness), the hard operators, and the
# quote/expansion starters. Deliberately EXCLUDES ``= + [ ]``.
_HARD_OPERATORS = '<>&|;(){}!'
_QUOTE_EXPANSION_STARTERS = frozenset('$`"\'')


class OperatorDebrisWordRecognizer(TokenRecognizer):
    """Recognizes operator-debris words (``]``, ``+``, ``=``, ``[`` starts)."""

    def can_recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> bool:
        """True iff the character at ``pos`` is one of ``] + = [``."""
        if pos >= len(input_text):
            return False
        return input_text[pos] in _DEBRIS_WORD_STARTS

    def recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Optional[Tuple[Token, int]]:
        """Collect an operator-debris word.

        Reads from ``pos`` until (a) whitespace, (b) a hard operator
        (``<>&|;(){}!``), or (c) a quote/expansion starter (``$ ` " '``).
        Note that ``= + [ ]`` do NOT terminate — the looser terminator set
        that distinguishes this recognizer from the literal recognizer.
        """
        start_pos = pos
        value = ""

        while pos < len(input_text):
            char = input_text[pos]

            # A backslash escapes the next character: consume the pair AS-IS
            # (keeping the backslash, exactly like the literal recognizer — the
            # backslash is removed later, at expansion). This keeps an escaped
            # quote/expansion starter from ending the word: an explicit-index
            # array element value ``[k]=a\$b`` reaches this recognizer as the
            # ``]=a\$b`` piece, and without honouring the ``\`` the ``$`` would
            # split off ``$b`` as an expansion, stranding the backslash (bash:
            # ``[k]=a\$b`` -> value ``a$b``). A trailing lone backslash is an
            # ordinary character.
            if char == '\\' and pos + 1 < len(input_text):
                value += char + input_text[pos + 1]
                pos += 2
                continue

            # Stop at whitespace
            if is_whitespace(char, posix_mode=context.posix_mode):
                break

            # Stop at operators (but not brackets - they might be part of
            # glob patterns)
            if char in _HARD_OPERATORS:
                # A `!` immediately after a bracket-glob `[` is the negation
                # marker of a `[!...]` character class (bash's `[!chars]`),
                # not a terminator. Without this the debris word splits
                # `[!x]` into `[` `!x`, which the recursive-descent parser
                # re-joins but the combinator's case-pattern path does not —
                # so a case arm like `[![:space:]])` diverged between parsers.
                if char == '!' and value.endswith('['):
                    value += char
                    pos += 1
                    continue
                break

            # Stop at quotes and expansions
            if char in _QUOTE_EXPANSION_STARTERS:
                break

            value += char
            pos += 1

        if not value:
            return None

        return Token(TokenType.WORD, value, start_pos, pos), pos
