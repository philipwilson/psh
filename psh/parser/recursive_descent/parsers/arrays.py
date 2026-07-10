"""
Array parsing for PSH shell.

This module handles parsing of array assignments and initializations.

Design note (Tier C-B2, review "Ugly 5")
-----------------------------------------
The ModularLexer can split ``arr[i]=v`` / ``name=(...)`` across several
token shapes. Rather than re-inspecting those shapes inline in both the
detector and the parser, ALL token-shape variance is absorbed once by
``_normalize_assignment_head()``, which returns a small structured
``AssignmentCandidate``. ``is_array_assignment()`` and
``parse_array_assignment()`` then consume the candidate instead of
peeking at raw tokens.

The LIVE token shapes the current lexer actually produces (verified by a
3,240-input fuzz census; see
``tests/unit/parser/test_array_assignment_characterization.py``) are:

* Initialization, single-token name -- WORD ``a=`` (or ``a+=``... but
  ``+=`` always splits, see below) then ``LPAREN``.
* Initialization, separate operator -- WORD ``a`` + WORD ``=``/``+=`` +
  ``LPAREN`` (covers ``a+=(...)`` and the spaced ``a = (...)``).
* Element, single token -- WORD ``a[i]=v`` / ``a[i]+=v`` / ``a[i]=``
  (subscript and operator inside one token, plus adjacent expansion /
  quoted continuation tokens).
* Element, split -- WORD ``a[i]`` (no ``=``) + a separate WORD starting
  with ``=``/``+=`` (only reachable via the space-separated ``a[0] =v``,
  a pre-existing divergence from bash where bash treats ``a[0]`` as a
  command).

The space-separated ``a [ 0 ] = v`` form (a space BEFORE the bracket) is
NOT an array assignment: bash parses it as a simple command (``a`` plus
the words ``[``, ``0``, ``]``, ``=``, ``v``) and reports
``a: command not found``. psh used to special-case it into a bespoke
parse error; that machinery was removed so the words fall through to
normal simple-command execution, matching bash.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

from ....ast_nodes import ArrayAssignment, ArrayElementAssignment, ArrayInitialization, Word
from ....lexer.token_types import Token, TokenType
from .base import ParserSubcomponent

# A valid assignment name is a portable identifier at the very start of the
# word's UNQUOTED LEADING LITERAL.
_NAME_START_RE = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')


def _unquoted_leading_literal(token: Token) -> str:
    """The word's unquoted leading LITERAL text — the only place an array
    assignment head may live.

    Returns '' when the leading part is quoted or an expansion. Word fusion
    merges a quoted/expansion prefix (``"q"a[0]=v``, ``${v}a[0]=v``, ``$x[0]=v``)
    into ONE WORD whose raw value (``qa[0]=v``) looks like an assignment though
    bash runs it as a command; keying the array-assignment classifier off the
    UNQUOTED leading literal keeps psh in step (also handles ``a[0]$x=y``, where
    the ``=`` sits past the leading literal in an expansion-split part).
    """
    parts = token.parts
    if not parts:
        return token.value
    # Concatenate the maximal run of leading UNQUOTED LITERAL parts (stop at the
    # first quoted / expansion part). `a+=` fuses to literal parts 'a'+'+=';
    # `a[0]$x=y` stops the head at 'a[0]' (before the `$x` expansion part).
    out = []
    for p in parts:
        if p.quote_type is None and not p.is_expansion and not p.is_variable:
            out.append(p.value)
        else:
            break
    return ''.join(out)


@dataclass
class AssignmentCandidate:
    """Structured view of an ``arr[i]=v`` / ``name=(...)`` head.

    Built once by ``_normalize_assignment_head()`` so the detector and the
    parser share a single interpretation of the token shape.
    """

    name: str
    #: "=" or "+=".
    operator: str
    #: True when the value begins with ``(`` -- an array initialization.
    is_initializer: bool
    #: True when a ``[subscript]`` is present -- an element assignment.
    is_element: bool
    #: Subscript text for the single-token / split element shapes.
    subscript: Optional[str] = None
    #: Literal value text carried in the same token after the operator
    #: (e.g. ``v`` in WORD ``a[0]=v``, ``pre`` in WORD ``a[0]=pre``).
    inline_tail: str = ""
    #: How many leading tokens the head occupies (name [+ operator]).
    head_token_count: int = 1
    #: Char length of the ``name[subscript]operator`` prefix within the head
    #: token's leading literal part — where the value begins. Word fusion now
    #: merges an element's ``name[i]=`` head and its ``$x``/``"q"`` value into
    #: ONE WORD, so the value is recovered by dropping this many chars from the
    #: fused word's first (literal) part; see ``_element_value_from_head``.
    head_len: int = 0


class ArrayParser(ParserSubcomponent):
    """Parser for array constructs."""


    # ------------------------------------------------------------------ #
    # Normalization: one place that absorbs tokenization-shape variance.
    # ------------------------------------------------------------------ #

    def _normalize_assignment_head(self) -> Optional[AssignmentCandidate]:
        """Classify the tokens at the current position as an array head.

        Returns an ``AssignmentCandidate`` if the position starts an array
        assignment (initialization or element), else ``None``. Peek-only:
        does not advance the parser.
        """
        if not self.parser.match(TokenType.WORD):
            return None

        token = self.parser.peek()
        # An array assignment head (NAME[subscript]op / NAME=() must be a valid
        # identifier at the START of the word's UNQUOTED LEADING LITERAL. A fused
        # quoted/expansion prefix (`"q"a[0]=v`, `${v}a[0]=v`, `a[0]$x=y`) yields
        # an empty/invalid leading literal and is NOT an assignment (bash runs it
        # as a command / syntax-errors) — classify off `value` (the leading
        # literal), never the raw fused lexeme.
        value = _unquoted_leading_literal(token)
        m = _NAME_START_RE.match(value)
        if not m:
            return None

        # --- Element assignment with subscript inside the name token ---
        if '[' in value and ']' in value:
            # Single token: arr[i]=value / arr[i]+=value
            cand = self._candidate_single_token_element(value)
            if cand is not None:
                return cand
            # Split: WORD "arr[i]" (no '=') + separate WORD "=value"/"+="
            cand = self._candidate_split_element(value)
            if cand is not None:
                return cand

        # --- Array initialization: name=( / name+=( / name + =/+= + ( ---
        cand = self._candidate_initializer()
        if cand is not None:
            return cand

        return None

    def _candidate_single_token_element(self, value: str) -> Optional[AssignmentCandidate]:
        """``arr[i]=v`` / ``arr[i]+=v`` carried in a single WORD token."""
        if '=' not in value:
            return None
        is_append = '+=' in value
        equals_pos = value.index('+=') if is_append else value.index('=')
        bracket_pos = value.index('[')
        # The '=' must come after the '[' (otherwise it's not a subscript).
        if bracket_pos >= equals_pos:
            return None
        close_bracket_pos = value.index(']')
        subscript = value[bracket_pos + 1:close_bracket_pos]
        head_len = equals_pos + (2 if is_append else 1)
        tail = value[head_len:]
        return AssignmentCandidate(
            name=value[:bracket_pos],
            operator='+=' if is_append else '=',
            is_initializer=False,
            is_element=True,
            subscript=subscript,
            inline_tail=tail,
            head_token_count=1,
            head_len=head_len,
        )

    def _candidate_split_element(self, value: str) -> Optional[AssignmentCandidate]:
        """``arr[i]`` (no ``=``) + a following ``=value``/``+=`` token."""
        if not self._peek_is_assignment_operator(1):
            return None
        # The operator token must be lexically ADJACENT to the ``arr[i]`` token.
        # A space before it (`a[0] =v`) means `a[0]` is a command word and `=v`
        # an argument, not an element assignment — matching bash (finding 5c).
        if not self.parser.peek(1).adjacent_to_previous:
            return None
        bracket_pos = value.index('[')
        close_bracket_pos = value.index(']')
        op_token = self.parser.peek(1)
        is_append = op_token.value == '+=' or op_token.value.startswith('+=')
        return AssignmentCandidate(
            name=value[:bracket_pos],
            operator='+=' if is_append else '=',
            is_initializer=False,
            is_element=True,
            subscript=value[bracket_pos + 1:close_bracket_pos],
            inline_tail='',  # resolved from the operator token at parse time
            head_token_count=2,
        )

    def _candidate_initializer(self) -> Optional[AssignmentCandidate]:
        """``name=(`` / ``name+=(`` (one token) or ``name`` + ``=``/``+=`` + ``(``.

        Classifies off the head token's UNQUOTED LEADING LITERAL (self-contained
        so BOTH the statement-position and argument-position callers guard
        identically), so a fused quoted/expansion prefix (`"q"a=(1 2)`) never
        reaches the ``(`` init classifier as a valid ``name=`` head.
        """
        value = _unquoted_leading_literal(self.parser.peek())
        if not _NAME_START_RE.match(value):
            return None

        # Single token ending with '=' or '+=', then an ADJACENT LPAREN.
        # bash only treats `(` as an array initializer when it is glued to the
        # assignment head; `a= (x)` is a syntax error, not an init (finding 5b).
        if (value.endswith('=') or value.endswith('+=')) and '=' in value:
            if (self.parser.peek(1).type != TokenType.LPAREN
                    or not self.parser.peek(1).adjacent_to_previous):
                return None
            is_append = value.endswith('+=')
            name = value[:-2] if is_append else value[:-1]
            return AssignmentCandidate(
                name=name,
                operator='+=' if is_append else '=',
                is_initializer=True,
                is_element=False,
                head_token_count=1,
            )

        # Separate tokens: name + '=' / '+=' + LPAREN, all lexically ADJACENT.
        # `a+=(x)` (glued) is an init; `a += (x)`, `a =(x)`, `a = (x)` (any gap)
        # are syntax errors in bash, not inits (finding 5b).
        op_token = self.parser.peek(1)
        if (op_token.type == TokenType.WORD and op_token.value in ('=', '+=')
                and op_token.adjacent_to_previous
                and self.parser.peek(2).type == TokenType.LPAREN
                and self.parser.peek(2).adjacent_to_previous):
            return AssignmentCandidate(
                name=value,
                operator=op_token.value,
                is_initializer=True,
                is_element=False,
                head_token_count=2,
            )

        return None

    def _peek_is_assignment_operator(self, offset: int) -> bool:
        """Check if token at offset is '=…' or '+='."""
        t = self.parser.peek(offset)
        return (t.type == TokenType.WORD and
                (t.value.startswith('=') or t.value == '+='))

    # ------------------------------------------------------------------ #
    # Detection (thin wrapper over the normalizer).
    # ------------------------------------------------------------------ #

    def is_array_assignment(self) -> bool:
        """Check if current position starts an array assignment."""
        return self._normalize_assignment_head() is not None

    # ------------------------------------------------------------------ #
    # Parsing.
    # ------------------------------------------------------------------ #

    def parse_array_assignment(self) -> ArrayAssignment:
        """Parse an array assignment (initialization or element)."""
        candidate = self._normalize_assignment_head()
        if candidate is None:  # pragma: no cover - guarded by is_array_assignment
            raise self.parser.error("Expected array assignment")

        # Consume the head tokens (name [+ separate operator]).
        head_token = self.parser.peek()
        self.parser.advance()  # name (or name-with-subscript) token
        if candidate.head_token_count == 2 and not candidate.is_element:
            self.parser.advance()  # separate '=' / '+=' before '('

        if candidate.is_initializer:
            return self._parse_array_initialization(
                candidate.name, is_append=(candidate.operator == '+='))

        return self._parse_element(candidate, head_token)

    def _parse_element(self, candidate: AssignmentCandidate,
                       head_token: Token) -> ArrayElementAssignment:
        """Parse an element assignment from a normalized candidate.

        The element's ``name[subscript]operator`` head and its value are one
        (possibly word-fused) WORD; the value is recovered from that token's
        parts, dropping the head prefix (``candidate.head_len`` chars).
        """
        is_append = candidate.operator == '+='

        value, value_word = self._element_value_from_head(
            head_token, candidate.head_len)
        subscript = candidate.subscript if candidate.subscript is not None else ''
        return ArrayElementAssignment(
            name=candidate.name,
            index=[Token(TokenType.WORD, subscript, 0)],
            value=value,
            is_append=is_append,
            value_word=value_word,
        )

    def _element_value_from_head(self, head_token: Token,
                                 head_len: int) -> tuple:
        """Extract an element assignment's (value_string, value_Word).

        Word fusion merges the element's ``name[i]=`` head and its value (a
        literal ``v``, an expansion ``$x``, a quoted ``"q"``, or any
        concatenation) into ONE WORD. The value is the whole word MINUS the
        ``name[subscript]operator`` prefix: drop ``head_len`` chars from the
        leading literal part, keep any remainder plus the following parts. This
        works for a plain literal head (``a[i]=v`` — one literal part, the value
        is its tail) and a fused head (``a[0]=pre$x"y"`` — the head prefix and
        ``pre`` share the first literal part; ``$x`` and ``"y"`` follow). A
        space before the value (``a[i]= v``) is a separate command, never fused,
        so the value is correctly empty here.
        """
        from ....ast_nodes import LiteralPart
        from ..support.word_builder import WordBuilder
        full = WordBuilder.build_word_from_token(head_token, ctx=self.parser.ctx)
        parts = list(full.parts)
        value_parts: List = []
        if parts:
            first = parts[0]
            # name[subscript]operator lives in the leading literal part.
            remainder = getattr(first, 'text', '')[head_len:]
            if remainder:
                value_parts.append(LiteralPart(
                    remainder, quoted=getattr(first, 'quoted', False),
                    quote_char=getattr(first, 'quote_char', None)))
            value_parts.extend(parts[1:])
        word = Word(parts=value_parts)
        return word.display_text(), word

    def _parse_array_initialization(self, name: str, is_append: bool = False) -> ArrayInitialization:
        """Parse array initialization: name=(elements)

        Uses the shared element-collection loop on the command parser (the same
        one the argument-position ``declare a=(...)`` path uses); the
        token-faithful element strings it also returns aren't needed here.
        """
        self.parser.expect(TokenType.LPAREN)
        words, _ = self.parser.commands.parse_array_init_elements()
        return ArrayInitialization(
            name=name,
            elements=[w.display_text() for w in words],
            is_append=is_append,
            words=words
        )
