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

from dataclasses import dataclass
from typing import List, Optional

from ....ast_nodes import ArrayAssignment, ArrayElementAssignment, ArrayInitialization, Word
from ....lexer.token_types import Token, TokenType
from ..helpers import TokenGroups


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


class ArrayParser:
    """Parser for array constructs."""

    def __init__(self, main_parser):
        """Initialize with reference to main parser."""
        self.parser = main_parser

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
        value = token.value

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
        tail = value[equals_pos + (2 if is_append else 1):]
        return AssignmentCandidate(
            name=value[:bracket_pos],
            operator='+=' if is_append else '=',
            is_initializer=False,
            is_element=True,
            subscript=subscript,
            inline_tail=tail,
            head_token_count=1,
        )

    def _candidate_split_element(self, value: str) -> Optional[AssignmentCandidate]:
        """``arr[i]`` (no ``=``) + a following ``=value``/``+=`` token."""
        if not self._peek_is_assignment_operator(1):
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
        """``name=(`` / ``name+=(`` (one token) or ``name`` + ``=``/``+=`` + ``(``."""
        token = self.parser.peek()
        value = token.value

        # Single token ending with '=' or '+=', then LPAREN.
        if (value.endswith('=') or value.endswith('+=')) and '=' in value:
            if self.parser.peek(1).type != TokenType.LPAREN:
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

        # Separate tokens: name + '=' / '+=' + LPAREN.
        op_token = self.parser.peek(1)
        if (op_token.type == TokenType.WORD and op_token.value in ('=', '+=')
                and self.parser.peek(2).type == TokenType.LPAREN):
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
        self.parser.advance()  # name (or name-with-subscript) token
        if candidate.head_token_count == 2 and not candidate.is_element:
            self.parser.advance()  # separate '=' / '+=' before '('

        if candidate.is_initializer:
            return self._parse_array_initialization(
                candidate.name, is_append=(candidate.operator == '+='))

        return self._parse_element(candidate)

    def _parse_element(self, candidate: AssignmentCandidate) -> ArrayElementAssignment:
        """Parse an element assignment from a normalized candidate.

        Covers the single-token (``a[i]=v``) and split (``a[i]`` + ``=v``)
        shapes; the name+subscript token has already been consumed.
        """
        is_append = candidate.operator == '+='

        if candidate.head_token_count == 2:
            # Split shape: the operator token follows. It may carry a tail
            # value (e.g. "=v") or be a bare "="/"+=" with the value in
            # adjacent continuation tokens.
            op_token = self.parser.advance()
            if op_token.value in ('=', '+='):
                if not self.parser.match_any(TokenGroups.WORD_LIKE):
                    raise self.parser.error("Expected value after '='")
                tail = ''
            else:
                tail = op_token.value[2:] if is_append else op_token.value[1:]
        else:
            tail = candidate.inline_tail

        value, value_word = self._parse_element_value(tail)
        subscript = candidate.subscript if candidate.subscript is not None else ''
        return ArrayElementAssignment(
            name=candidate.name,
            index=[Token(TokenType.WORD, subscript, 0)],
            value=value,
            is_append=is_append,
            value_word=value_word,
        )

    def _parse_element_value(self, tail: str) -> tuple:
        """Parse an element-assignment value into (value, word).

        ``tail`` is literal value text that followed ``=``/``+=`` inside the
        same token as the array name. The lexer splits expansions and quoted
        segments into *adjacent* tokens (``a[0]=pre$x"y"`` arrives as
        WORD ``a[0]=pre`` + VARIABLE ``x`` + STRING ``y``), which are merged
        here into a single value Word with per-part quote context.
        """
        from ....ast_nodes import LiteralPart, WordPart
        has_continuation = (
            self.parser.match_any(TokenGroups.WORD_LIKE)
            and (not tail or self.parser.peek().adjacent_to_previous))
        if tail:
            parts: List[WordPart] = [LiteralPart(tail)]
            if has_continuation:
                parts.extend(self.parser.commands.parse_argument_as_word().parts)
            word = Word(parts=parts)
        elif has_continuation:
            word = self.parser.commands.parse_argument_as_word()
        else:
            word = Word(parts=[])
        value = word.display_text()
        return value, word

    def _parse_array_initialization(self, name: str, is_append: bool = False) -> ArrayInitialization:
        """Parse array initialization: name=(elements)"""
        self.parser.expect(TokenType.LPAREN)

        elements = []
        words = []

        # Parse array elements (newlines between elements are allowed, as in bash)
        while not self.parser.match(TokenType.RPAREN) and not self.parser.at_end():
            if self.parser.match(TokenType.NEWLINE):
                self.parser.advance()
            elif self.parser.match_any(TokenGroups.WORD_LIKE):
                word = self.parser.commands.parse_argument_as_word()
                elements.append(word.display_text())
                words.append(word)
            else:
                break

        self.parser.expect(TokenType.RPAREN)

        return ArrayInitialization(
            name=name,
            elements=elements,
            is_append=is_append,
            words=words
        )
