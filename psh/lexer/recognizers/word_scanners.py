"""Pure mini-scanners and forward word-shape state for the literal recognizer.

A shell "word" is not one flat thing: while the literal recognizer collects
characters it can pass through several sub-grammars — a glob bracket class
(``x[a-z]``), an extglob group (``@(a|b)``), an array-assignment subscript
(``arr["key"]=``), an inline ANSI-C string in an assignment value
(``v=$'a\\nb'``). Historically the recognizer answered "which sub-grammar am
I in?" by RE-SCANNING the value it had accumulated so far with four
hedge-worded heuristics ("likely", "probably"). This module replaces that
with two things:

* **Mini-scanners** — pure functions that, given the input text and a
  position, consume one complete sub-grammar segment and return it:
  :func:`scan_glob_bracket`, :func:`scan_extglob_group`,
  :func:`scan_assignment_prefix`, :func:`scan_inline_ansi_c`.

* **WordShapeTracker** — explicit forward state over the characters already
  appended to the word (``NEUTRAL → ASSIGN_NAME → ASSIGN_VALUE``), updated
  once per appended character, so the collect loop always KNOWS whether it
  is reading an assignment name, an assignment value, or a plain word —
  instead of guessing by retro-scanning.

Everything here is pure: no lexer state, no config objects — ``posix_mode``
is threaded as a plain argument. That makes each scanner's contract directly
unit-testable (see tests/unit/lexer/test_word_scanners.py).

Relationship to the lexer-level assignment map
----------------------------------------------
``build_assignment_prefix_map`` (moved here from ``ModularLexer``) is the
single O(n) forward pass that answers "is position *i* inside a confirmed
``NAME[...]=`` subscript?" for the whole input. ``ModularLexer`` caches it on
the shared ``LexerContext`` and consults it to keep quotes inside subscripts
literal; :func:`scan_assignment_prefix` consults the SAME map (threaded in
via the context) instead of re-deriving the shape. The map cannot be the
sole authority for the recognizer, though — two classes need the local
subscript scan as a documented supplement:

* **word-interior starts**: the map requires ``NAME[`` at a word boundary
  in the raw text, but the recognizer restarts mid-word after quotes and
  expansions (``"q"a[0]=v``, ``${v}a[0]=v`` — the ``a[0]=`` is an
  assignment shape from the recognizer's point of view);
* **escape-awareness**: the local scan honours backslash escapes
  (``a[\\[x]=v`` — the escaped ``[`` is not an opener), the map does not.

Both layers agree on the common cases by construction (same
quote tracking, same ``skip_expansion_region`` opacity for ``$(...)`` /
``${...}`` / backticks inside subscripts).
"""

from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple

from ..pure_helpers import QuoteState
from ..unicode_support import is_identifier_char, is_identifier_start

if TYPE_CHECKING:
    from ..state_context import LexerContext

__all__ = [
    'WordShape', 'WordShapeTracker', 'UnmatchedBracketTracker',
    'can_start_expansion',
    'scan_glob_bracket', 'scan_extglob_group',
    'scan_assignment_prefix', 'scan_inline_ansi_c',
    'build_assignment_prefix_map', 'cached_assignment_prefix_map',
    'skip_expansion_region',
]


def skip_expansion_region(text: str, pos: int) -> Optional[int]:
    """Skip a ``$(...)``, ``${...}`` or `` `...` `` region starting at ``pos``.

    Returns the index just past the closing delimiter, or ``None`` when
    ``pos`` does not start such a region or the region never closes.

    Used by the word-shape scanners (array-assignment detection) so that
    whitespace and delimiters inside an expansion do not end the shell
    word: ``a[$(echo 1 + 1)]=v`` is a single assignment word.
    """
    from ..cmdsub_scanner import find_command_substitution_end
    from ..pure_helpers import (
        ArithParenScan,
        find_closing_delimiter,
        scan_double_paren_arithmetic,
    )
    if pos >= len(text):
        return None
    ch = text[pos]
    if ch == '`':
        end = text.find('`', pos + 1)
        return end + 1 if end != -1 else None
    if ch == '$' and pos + 1 < len(text) and text[pos + 1] in '({':
        if text.startswith('$((', pos):
            end, status = scan_double_paren_arithmetic(text, pos + 3)
            if status is ArithParenScan.CLOSED:
                return end
            if status is ArithParenScan.UNCLOSED:
                return None
            # NOT_ARITHMETIC: re-read as a `$(` command substitution below
        if text[pos + 1] == '(':
            end, found = find_command_substitution_end(text, pos + 2)
            return end if found else None
        end, found = find_closing_delimiter(text, pos + 2, '{', '}')
        return end if found else None
    return None


# ---------------------------------------------------------------------------
# Forward word-shape state
# ---------------------------------------------------------------------------

class WordShape(Enum):
    """What kind of word the collected characters form so far.

    ``NEUTRAL``      — a plain word (``echo``, ``./path``, ``x[a-z]*`` …).
    ``ASSIGN_NAME``  — a possible assignment left-hand side: a valid
                       identifier (``var``) or an identifier followed by a
                       subscript (``arr[0]``, ``arr[0][1]``).
    ``ASSIGN_VALUE`` — past the ``=`` of an assignment (``var=…``,
                       ``arr[k]+=…``); the rest of the word is the value.
    """
    NEUTRAL = 'neutral'
    ASSIGN_NAME = 'assign_name'
    ASSIGN_VALUE = 'assign_value'


class WordShapeTracker:
    """Forward word-shape state, fed one appended character at a time.

    Replaces four retro-scanning heuristics that re-derived the same facts
    from the accumulated value string on every consult:

    ===========================  =====================================
    retired heuristic            forward property
    ===========================  =====================================
    _is_variable_assignment_start  :attr:`can_take_assignment`
    _is_potential_array_assignment_start (shape half)  :attr:`is_identifier`
    _looks_like_array_assignment_before_plus_equals  :attr:`plus_assign_ready`
    _is_in_variable_assignment_value  :attr:`in_assignment_value`
    _is_in_string_concatenation  :attr:`concat_safe`
    ===========================  =====================================

    The transition rules are intentionally EXACTLY the retired predicates'
    semantics, recast as incremental updates (the oracle test in
    test_word_scanners.py re-implements the old predicates and checks
    agreement over generated words). Notable inherited corners:

    * a word *ending* in ``=`` always counts as "in an assignment value"
      (the old ``value.endswith('=')`` fast path), even for shapes like
      ``v=x=`` whose last ``=`` has no valid name before it;
    * the bracket balance for :attr:`plus_assign_ready` counts raw
      brackets, ignoring quotes and escapes, exactly like the predicate
      it replaces.
    """

    __slots__ = ('_posix', '_empty', '_is_identifier', '_name_bracket',
                 '_concat_safe', '_in_value_sticky', '_bracket_balance',
                 '_last_char', '_prev_is_identifier', '_prev_name_bracket')

    def __init__(self, posix_mode: bool = False):
        self._posix = posix_mode
        self._empty = True
        self._is_identifier = False   # whole word is a valid identifier
        self._name_bracket = False    # word starts with identifier + '['
        self._concat_safe = False     # plain enough to concatenate $'..'
        self._in_value_sticky = False  # the LAST '=' had a valid name before it
        self._bracket_balance = 0     # raw [ minus ] count
        self._last_char = ''
        self._prev_is_identifier = False
        self._prev_name_bracket = False

    def feed(self, appended: str) -> None:
        """Advance the state over text just appended to the word."""
        for ch in appended:
            self._feed_one(ch)

    def _feed_one(self, ch: str) -> None:
        prev_ident, prev_bracket = self._is_identifier, self._name_bracket
        if self._empty:
            self._empty = False
            self._is_identifier = is_identifier_start(ch, self._posix)
            self._concat_safe = self._is_identifier or ch in '/.~'
        else:
            if self._is_identifier:
                if ch == '[':
                    self._is_identifier = False
                    self._name_bracket = True
                elif not is_identifier_char(ch, self._posix):
                    self._is_identifier = False
            if ch in '=[](){}|&;<>!':
                self._concat_safe = False
        if ch == '=':
            # The last '=' governs: a valid name (identifier, NAME[...],
            # or either with one trailing '+') directly before THIS '='
            # makes the rest of the word an assignment value.
            self._in_value_sticky = (
                prev_ident or prev_bracket
                or (self._last_char == '+'
                    and (self._prev_is_identifier or self._prev_name_bracket))
            )
        if ch == '[':
            self._bracket_balance += 1
        elif ch == ']':
            self._bracket_balance -= 1
        self._prev_is_identifier = prev_ident
        self._prev_name_bracket = prev_bracket
        self._last_char = ch

    @property
    def shape(self) -> WordShape:
        if self.in_assignment_value:
            return WordShape.ASSIGN_VALUE
        if self.can_take_assignment:
            return WordShape.ASSIGN_NAME
        return WordShape.NEUTRAL

    @property
    def is_identifier(self) -> bool:
        """The whole word so far is a non-empty valid identifier."""
        return self._is_identifier

    @property
    def can_take_assignment(self) -> bool:
        """An ``=`` here would start an assignment value (``NAME=`` or
        ``NAME[anything=``)."""
        return self._is_identifier or self._name_bracket

    @property
    def in_assignment_value(self) -> bool:
        """We are past the ``=`` of an assignment."""
        return self._last_char == '=' or self._in_value_sticky

    @property
    def concat_safe(self) -> bool:
        """The word is plain enough (identifier/path characters) that an
        inline ``$'...'`` concatenates onto it (``pre$'x'post``)."""
        return self._concat_safe and not self._empty

    @property
    def plus_assign_ready(self) -> bool:
        """A ``+`` here can start ``+=`` after a subscripted name: the word
        is ``NAME[...]`` with raw-balanced brackets ending in ``]``."""
        return (self._name_bracket and self._bracket_balance == 0
                and self._last_char == ']')


class UnmatchedBracketTracker:
    """Incrementally tracks whether the word collected so far ends inside
    an unmatched ``[`` (outside quotes).

    This is NOT the same predicate as the lexer-level assignment map
    (:func:`build_assignment_prefix_map`): that map requires a confirmed
    ``NAME[...]=`` assignment shape, while this tracker counts any
    unmatched bracket — which is what keeps glob character classes like
    ``*[[:upper:]]*`` intact (the second ``]`` must not terminate the
    word). Feeding each appended character exactly once runs the
    quote-aware bracket automaton in O(n) total.
    """

    __slots__ = ('_bracket_count', '_has_opening_bracket',
                 '_in_single', '_in_double')

    def __init__(self) -> None:
        self._bracket_count = 0
        self._has_opening_bracket = False
        self._in_single = False
        self._in_double = False

    def feed(self, appended: str) -> None:
        """Advance the state over text just appended to the word."""
        for char in appended:
            if char == "'" and not self._in_double:
                self._in_single = not self._in_single
            elif char == '"' and not self._in_single:
                self._in_double = not self._in_double
            elif not self._in_single and not self._in_double:
                if char == '[':
                    self._bracket_count += 1
                    self._has_opening_bracket = True
                elif char == ']':
                    self._bracket_count -= 1

    @property
    def inside(self) -> bool:
        return self._has_opening_bracket and self._bracket_count > 0


# ---------------------------------------------------------------------------
# Mini-scanners
# ---------------------------------------------------------------------------

def can_start_expansion(text: str, pos: int, posix_mode: bool = False) -> bool:
    """True when the ``$`` at ``pos`` can start a valid expansion
    (``$(...)``, ``${...}``, ``$[...]``, ``$'...'``, ``$"..."``, ``$VAR``, ``$?`` …).
    A ``$`` that cannot is a literal word character."""
    if pos >= len(text) or text[pos] != '$':
        return False
    if pos + 1 >= len(text):
        return False  # lone $ at end of input
    next_char = text[pos + 1]
    # '[' is the deprecated `$[expr]` arithmetic form (== `$((expr))`).
    if next_char in '([{\'"':
        return True
    from ..constants import SPECIAL_VARIABLES
    if next_char in SPECIAL_VARIABLES:
        return True
    return is_identifier_start(next_char, posix_mode)


def scan_glob_bracket(text: str, pos: int,
                      posix_mode: bool = False) -> Tuple[str, int, bool]:
    """Consume a glob bracket segment starting at the ``[`` at ``pos``.

    Inside a non-assignment ``[...]`` word, quotes and expansions keep
    their normal meaning (bash: ``echo x["ok"]`` prints ``x[ok]``,
    ``echo x[$USER]`` expands, and ``echo x["oops`` is an
    unterminated-quote error), so the segment ends — and with it the
    literal token — at any quote, backtick, or valid ``$`` expansion; the
    parser later re-joins adjacent parts into one composite word.
    Everything else, including whitespace and escaped pairs, is collected
    literally until the closing ``]`` (or end of input, leaving the
    bracket unclosed — the word simply ends there).

    Returns ``(segment, new_pos, ended_by_quote)``; *ended_by_quote* means
    the whole literal token must end here so the quote/expansion machinery
    takes over.
    """
    assert text[pos] == '['
    segment = '['
    pos += 1
    n = len(text)
    while pos < n:
        ch = text[pos]
        if ch == '\\' and pos + 1 < n:
            segment += ch + text[pos + 1]  # escaped char (e.g. x[\"]) stays
            pos += 2
            continue
        if ch in ('"', "'", '`') or (
                ch == '$' and can_start_expansion(text, pos, posix_mode)):
            return segment, pos, True
        segment += ch
        pos += 1
        if ch == ']':
            return segment, pos, False
    return segment, pos, False


def scan_extglob_group(text: str, pos: int) -> Optional[Tuple[str, int]]:
    """Consume a balanced ``(...)`` extglob group starting at ``pos``.

    Called when ``pos`` points at ``(`` and the preceding word character
    was an extglob prefix (``?*+@!``). Collects the entire group including
    nested extglob and regular parens; backslash escapes are honoured.

    Returns ``(segment, new_pos)``, or ``None`` when the parens never
    balance (the ``(`` then keeps its normal operator meaning).
    """
    if pos >= len(text) or text[pos] != '(':
        return None
    depth = 1
    segment = '('
    i = pos + 1
    n = len(text)
    while i < n and depth > 0:
        ch = text[i]
        if ch == '\\' and i + 1 < n:
            segment += ch + text[i + 1]
            i += 2
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        segment += ch
        i += 1
    if depth != 0:
        return None
    return segment, i


def _subscript_confirms_assignment(text: str, pos: int) -> bool:
    """Local lookahead: does the ``[`` at ``pos`` close as ``]=``/``]+=``?

    Quote-aware (``arr["key"]=v`` works), escape-aware (``a[\\[x]=v``),
    and expansion-opaque (the space in ``a[$(echo 1 + 1)]=v`` does not
    break the word). Unquoted whitespace breaks the pattern.
    """
    remaining = text[pos:]
    bracket_count = 0
    state = QuoteState()
    i = 0
    while i < len(remaining):
        char = remaining[i]
        if state.consume(char):  # active (outside quotes, not quote/escape)
            if char in ('$', '`'):
                # $(...), ${...}, `...`: opaque — their contents
                # (including whitespace) are part of the subscript.
                skip = skip_expansion_region(remaining, i)
                if skip is not None:
                    i = skip
                    continue
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    # Found the closing bracket: assignment iff = or +=
                    if remaining[i + 1:i + 2] == '=':
                        return True
                    return remaining[i + 1:i + 3] == '+='
            elif char in (' ', '\t', '\n', '\r'):
                return False  # whitespace outside quotes breaks the pattern
        i += 1
    return False


def _collect_assignment_subscript(text: str, pos: int) -> Tuple[str, int]:
    """Collect ``[index]=`` / ``[index]+=`` starting at the ``[`` at ``pos``.

    Quote-aware: quoted keys are collected literally (the lexer-level
    assignment map keeps the quote machinery away from confirmed
    subscripts, so the quotes stay part of this word). Collection stops
    right after the ``=`` so the VALUE tokenizes exactly like a scalar
    assignment value (``a[0]=$x`` becomes WORD ``a[0]=`` + VARIABLE ``x``,
    mirroring ``v=$x``).

    Returns ``(segment, new_pos)``. The segment may lack the trailing
    ``=`` when the raw bracket count closes without one (an expansion
    containing ``]`` can make this scan disagree with the lookahead —
    the collected prefix is still returned and the word continues), or be
    ``("", pos)`` when a terminator interrupts the subscript.
    """
    if pos >= len(text) or text[pos] != '[':
        return "", pos

    start_pos = pos
    result = ""
    bracket_count = 0
    state = QuoteState()

    while pos < len(text):
        char = text[pos]

        # Non-active chars (quote toggles, escapes, anything inside quotes)
        # are simply collected.
        if not state.consume(char):
            result += char
            pos += 1
            continue

        # Active (outside quotes): track brackets and look for assignment.
        if char == '[':
            bracket_count += 1
            result += char
            pos += 1
        elif char == ']':
            bracket_count -= 1
            result += char
            pos += 1
            if bracket_count == 0:
                # Look for = or += and stop right after it: the value
                # part is tokenized by the normal lexer machinery so
                # expansions/quotes become proper adjacent tokens.
                if text.startswith('=', pos):
                    return result + '=', pos + 1
                if text.startswith('+=', pos):
                    return result + '+=', pos + 2
                return result, pos  # not an assignment after all
        elif char in ' \t\n\r|&;(){}' and bracket_count == 0:
            return "", start_pos  # terminator outside brackets
        else:
            result += char
            pos += 1

    return "", start_pos  # end of input without finding the assignment


def scan_assignment_prefix(
    text: str,
    pos: int,
    assignment_map: Optional[bytearray] = None,
) -> Optional[Tuple[str, int]]:
    """Consume an array-assignment subscript prefix at the ``[`` at ``pos``.

    The caller has already established (via :class:`WordShapeTracker`)
    that the word so far is a valid identifier — this function decides
    whether the bracket is an assignment subscript (``arr[key]=``,
    ``arr[key]+=``) rather than a glob class, and collects it.

    Confirmation consults the lexer-level *assignment_map* first (built
    once per input by :func:`build_assignment_prefix_map` — no shape
    re-derivation), falling back to the local subscript lookahead for the
    word-interior and escape-sensitive classes the map cannot see (see
    the module docstring).

    Returns ``None`` when the bracket is not an assignment subscript
    (glob-class handling applies), otherwise ``(segment, new_pos)`` —
    where the segment degrades to just ``"["`` when the subscript scan
    is interrupted (the word then continues character by character,
    exactly like the legacy path).
    """
    confirmed = (
        (assignment_map is not None and pos + 1 < len(assignment_map)
         and assignment_map[pos + 1])
        or _subscript_confirms_assignment(text, pos)
    )
    if not confirmed:
        return None
    segment, new_pos = _collect_assignment_subscript(text, pos)
    if not segment:
        return '[', pos + 1
    return segment, new_pos


def scan_inline_ansi_c(text: str, pos: int) -> Optional[Tuple[str, int]]:
    """Parse an inline ANSI-C quote ``$'...'`` at ``pos`` into its decoded
    content.

    Used when ``$'...'`` appears inside an assignment value or a plain
    concatenation (``v=$'a\\nb'``, ``pre$'x'post``) — the decoded content
    joins the current word instead of starting a new STRING token.
    Delegates to UnifiedQuoteParser so escape semantics live in exactly
    one place.

    Returns ``(decoded_content, new_pos)``, or ``None`` when ``pos`` does
    not start ``$'`` or the quote never closes.
    """
    if pos + 1 >= len(text) or text[pos:pos + 2] != "$'":
        return None

    from ..quote_parser import QUOTE_RULES, UnifiedQuoteParser
    parts, new_pos, closed = UnifiedQuoteParser().parse_quoted_string(
        text, pos + 2, QUOTE_RULES["$'"], None, quote_type="$'")
    if not closed:
        return None
    return ''.join(part.value for part in parts), new_pos


# ---------------------------------------------------------------------------
# Lexer-level assignment-prefix map
# ---------------------------------------------------------------------------

def build_assignment_prefix_map(text: str,
                                posix_mode: bool = False) -> bytearray:
    """map[i] == 1 iff position i is inside a confirmed ``NAME[...]=``.

    Forward scan tracking quote state and a stack of open brackets;
    each ``[`` records whether it directly follows a valid identifier
    at a word boundary (the array-assignment shape). When the
    outermost bracket closes with ``]=`` or ``]+=`` and its ``[`` had
    that shape, the whole subscript span is marked. Unconfirmed
    bracket words (``x["ok"]``, ``x[$v]``, glob classes) are never
    marked, so quotes/expansions inside them lex normally. Span
    marking is amortized O(n): spans never overlap.

    Built once per input (ModularLexer caches it on the LexerContext) and
    consulted by both the quote/expansion dispatch and
    :func:`scan_assignment_prefix`.
    """
    n = len(text)
    result = bytearray(n)

    def is_array_open(i: int) -> bool:
        # `[` must directly follow an identifier that starts at a word
        # boundary: arr[index], not arr [index] or +x[.
        if i == 0 or text[i - 1] in ' \t\n':
            return False
        if not is_identifier_char(text[i - 1], posix_mode):
            return False
        id_start = i - 1
        while id_start > 0 and is_identifier_char(text[id_start - 1],
                                                  posix_mode):
            id_start -= 1
        if not is_identifier_start(text[id_start], posix_mode):
            return False
        return id_start == 0 or text[id_start - 1] in ' \t\n;|&(){}'

    in_single = False
    in_double = False
    open_stack: list = []  # (index, is_array_shape) per unmatched '['

    i = 0
    while i < n:
        ch = text[i]
        if not in_single and ch in ('$', '`'):
            # $(...), ${...}, `...`: opaque — whitespace/brackets inside
            # are part of the subscript (a[$(echo 1 + 1)]=v).
            skip = skip_expansion_region(text, i)
            if skip is not None:
                i = skip
                continue
        if ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "'" and not in_double:
            in_single = not in_single
        elif not in_single and not in_double:
            if ch == '[':
                open_stack.append((i, is_array_open(i)))
            elif ch == ']':
                if open_stack:
                    start, shaped = open_stack.pop()
                    if not open_stack and shaped and (
                            text[i + 1:i + 2] == '=' or
                            text[i + 1:i + 3] == '+='):
                        # Confirmed assignment subscript: mark the span
                        # between (and including) the brackets' interior
                        # so quotes/expansions inside stay literal.
                        for j in range(start + 1, i + 1):
                            result[j] = 1
            elif ch in ' \t\n;|&(){}':
                # Unquoted word/command boundary: an assignment
                # subscript cannot span it (`h[a b]=v` is two words).
                open_stack.clear()
        i += 1

    return result


def cached_assignment_prefix_map(text: str, posix_mode: bool,
                                 context: "LexerContext") -> bytearray:
    """The assignment-prefix map for *text*, cached on the LexerContext.

    Both consumers — ModularLexer's quote/expansion dispatch and the
    literal recognizer's :func:`scan_assignment_prefix` — share one build
    per input. The cache is keyed by string identity: a lexer run passes
    the same input object throughout, while direct recognizer tests that
    reuse a context across different inputs get a correct rebuild.
    """
    cache = context.assignment_map_cache
    if cache is None or cache[0] is not text:
        cache = (text, build_assignment_prefix_map(text, posix_mode))
        context.assignment_map_cache = cache
    return cache[1]
