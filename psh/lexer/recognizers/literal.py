"""Literal token recognizer for words, identifiers and assignments.

The recognizer has two halves:

* :meth:`LiteralRecognizer.can_recognize` — the word-START rules: which
  characters may begin a literal word in the current context (most
  operator characters may not; a handful of context exceptions apply).

* the collect loop (:meth:`LiteralRecognizer._collect_literal_value`) —
  consumes characters until a terminator ends the word, maintaining
  explicit forward state: a :class:`~.word_scanners.WordShapeTracker`
  (``NEUTRAL → ASSIGN_NAME → ASSIGN_VALUE``) updated as each character is
  consumed, and an :class:`~.word_scanners.UnmatchedBracketTracker` for
  open subscripts. Sub-grammar segments (glob bracket classes, extglob
  groups, array-assignment subscripts) are consumed whole by the pure
  mini-scanners in ``word_scanners.py``.

Because the shape state runs forward, the loop always KNOWS whether the
``=`` it just hit starts an assignment value or ends the word — there is
no retro-scanning of the accumulated value. A ``$'...'`` in a value or
concatenation (``v=$'a\\tb'``, ``pre$'x'post``) ends the literal like any
quote/expansion: it lexes as its own ``$'``-typed STRING token, and the
parser re-joins the adjacent tokens into one composite Word — so the
ANSI-C part keeps its quote metadata (mirroring ``"..."``; J6). It is not
decoded inline into a flat, quote-less literal.
"""

from typing import TYPE_CHECKING, Optional, Tuple

from ..state_context import LexerContext
from ..token_types import Token, TokenType
from ..unicode_support import is_whitespace
from .base import ContextualRecognizer
from .comment import is_comment_start
from .word_scanners import (
    UnmatchedBracketTracker,
    WordShapeTracker,
    cached_assignment_prefix_map,
    can_start_expansion,
    scan_assignment_prefix,
    scan_extglob_group,
    scan_glob_bracket,
)

if TYPE_CHECKING:
    from ..position import LexerConfig


def extglob_active(config: "Optional[LexerConfig]", context: LexerContext) -> bool:
    """Is extglob pattern recognition (``?*+@!(...)``) live at this point?

    True when the ``extglob`` shell option is on (``config.enable_extglob``)
    OR we are inside a ``[[ ]]`` conditional (``context.bracket_depth > 0``).
    Bash recognizes extended-glob patterns in a ``[[ ]]`` ``==``/``!=``
    pattern operand *unconditionally* — independent of the ``extglob`` shopt —
    so the lexer must accept the ``(`` of a pattern group there even with the
    option off. (This predicate is shared by the literal and operator
    recognizers so all the extglob gates agree.)
    """
    return bool(
        (config and config.enable_extglob) or context.bracket_depth > 0)


class LiteralRecognizer(ContextualRecognizer):
    """Recognizes literal tokens: words, identifiers, assignments."""

    def __init__(self) -> None:
        super().__init__()
        self.config: "Optional[LexerConfig]" = None  # Will be set by ModularLexer

    # Characters that can terminate a word. The whitespace row is the shell
    # token-separator set (space/tab/newline ONLY — see
    # unicode_support.SHELL_WHITESPACE): CR/FF/VT are ordinary word
    # characters in bash (`echo a<FF>b` is one word), and a CRLF line's
    # trailing CR is handled by the line-reading layer, never here.
    WORD_TERMINATORS = {
        ' ', '\t', '\n',                         # Whitespace (shell blanks + newline)
        '|', '&', ';', '(', ')', '{', '}',       # Operators
        '<', '>', '=', '+',                      # More operators
        '[', ']',                                # Bracket operators
        '$', '`', "'",  '"',                     # Special characters
    }

    @property
    def priority(self) -> int:
        """Medium priority for literals."""
        return 70

    @property
    def _posix_mode(self) -> bool:
        return self.config.posix_mode if self.config else False

    def can_recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> bool:
        """Check if current position might be a literal."""
        if pos >= len(input_text):
            return False

        char = input_text[pos]

        # Skip whitespace and operators (handled by other recognizers),
        # with a few exceptions that start words.
        if char in self.WORD_TERMINATORS:
            # A $ that cannot start a valid expansion is a literal word char
            if char == '$' and not can_start_expansion(
                    input_text, pos, self._posix_mode):
                return True  # Can be part of word (invalid expansion)
            # Inside [[ ]], < and > are comparison operators that should be tokenized as words
            if char in ['<', '>'] and context.bracket_depth > 0:
                return True  # Can be part of word
            # Inside (( )), < and > are arithmetic comparisons, not redirects.
            # The operator recognizer already rejects them, but the literal
            # recognizer must accept them as word-start characters — otherwise
            # they are silently dropped from the token stream.
            if char in ['<', '>'] and context.arithmetic_depth > 0:
                return True  # Can be part of word
            # Extglob: +( should be treated as word start, not operator.
            # ('!' is not in WORD_TERMINATORS; !( is handled below.)
            if char == '+' and extglob_active(self.config, context):
                if pos + 1 < len(input_text) and input_text[pos + 1] == '(':
                    return True  # Start of extglob pattern
            # { and } are operators only when standalone (followed by
            # whitespace/delimiter/EOF).  When adjacent to word chars
            # (e.g. {a..1}) they start a word.  {} is always a word.
            if char in ('{', '}'):
                next_pos = pos + 1
                # {} is a word, not operators
                if char == '{' and next_pos < len(input_text) and input_text[next_pos] == '}':
                    return True
                # } at non-command position is always a word character
                if char == '}' and not context.command_position:
                    return True
                # A brace is "standalone" (operator) only when followed by
                # whitespace, a command operator, or EOF. When followed by
                # another brace (e.g. {{1..3},...} nesting) or word chars, it is
                # part of a word — note '{'/'}' are NOT in this set.
                if next_pos >= len(input_text) or input_text[next_pos] in ' \t\n\r;|&()<>':
                    return False  # Standalone brace — let operator handle it
                return True  # Attached to word chars — part of word
            return False

        # Anything else (including '!', which the operator recognizer
        # declines when it isn't a standalone token) can start a literal.
        return True

    def recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Optional[Tuple[Token, int]]:
        """Recognize literal tokens."""
        start_pos = pos

        # Collect the literal value using helper method
        value, pos = self._collect_literal_value(input_text, pos, context)

        if not value:
            return None

        return Token(TokenType.WORD, value, start_pos, pos), pos

    def _collect_literal_value(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Tuple[str, int]:
        """Collect literal value characters until a terminator is reached.

        Returns:
            Tuple of (collected_value, new_position)
        """
        posix_mode = self._posix_mode
        value = ""
        # Forward word-shape state, updated as characters are consumed.
        shape = WordShapeTracker(posix_mode)
        # Forward "value ends inside an unmatched [" state (quote-aware).
        brackets = UnmatchedBracketTracker()

        def take(segment: str, new_pos: int) -> None:
            """Append a consumed segment to the word and advance."""
            nonlocal value, pos
            value += segment
            shape.feed(segment)
            brackets.feed(segment)
            pos = new_pos

        while pos < len(input_text):
            char = input_text[pos]

            # --- '[': assignment subscript or glob bracket class ---
            if char == '[':
                assignment = None
                if shape.is_identifier:
                    assignment = scan_assignment_prefix(
                        input_text, pos,
                        cached_assignment_prefix_map(
                            input_text, posix_mode, context))
                if assignment is not None:
                    if self._is_word_terminator(char, context):
                        # arr[key]= / arr[key]+= (possibly degraded to a
                        # bare '[' when the subscript scan is interrupted)
                        take(*assignment)
                    else:
                        # In arithmetic, '[' is a plain word character.
                        take('[', pos + 1)
                    continue
                # Glob bracket class: collect literally up to ']'. A quote
                # or expansion inside ends the literal here — it keeps its
                # normal meaning (bash: `echo x["ok"]` prints `x[ok]`) and
                # the parser re-joins adjacent parts into one composite
                # word. Only confirmed assignment subscripts collect their
                # quotes literally (scan_assignment_prefix above).
                segment, new_pos, ended_by_quote = scan_glob_bracket(
                    input_text, pos, posix_mode)
                take(segment, new_pos)
                if ended_by_quote:
                    break
                continue

            # --- '$' that cannot start an expansion is a literal char ---
            if char == '$' and not can_start_expansion(
                    input_text, pos, posix_mode):
                take(char, pos + 1)
                continue

            # --- extglob: prefix( opens a balanced pattern group ---
            if (char == '(' and extglob_active(self.config, context)
                    and value and value[-1] in '?*+@!'):
                group = scan_extglob_group(input_text, pos)
                if group is not None:
                    take(*group)
                    continue

            # Extglob: + and ! are in WORD_TERMINATORS but when extglob is
            # enabled and they are followed by (, they are part of the word
            if (char in ('+', '!') and extglob_active(self.config, context)
                    and pos + 1 < len(input_text) and input_text[pos + 1] == '('):
                take(char, pos + 1)
                continue

            # --- terminators, with the shape-driven continuations ---
            if self._is_word_terminator(char, context):
                # '~+' directory-stack tilde prefix: the '+' (a terminator)
                # right after a leading '~' continues the word so the whole
                # ~+, ~+N prefix lexes as one WORD (~- and ~N already do,
                # since '-'/digits are not terminators). Tilde expansion
                # interprets it; if it isn't a valid prefix it stays literal.
                if char == '+' and value == '~':
                    take(char, pos + 1)
                    continue
                # '=' continuing an assignment: NAME= / NAME[idx]= / NAME+=
                if char == '=' and (value.endswith('+')
                                    or shape.can_take_assignment):
                    take(char, pos + 1)
                    continue
                # Inside an open subscript these stay part of the word.
                if brackets.inside and char in (']', '$', '(', ')', '+'):
                    take(char, pos + 1)
                    continue
                # '+' opening '+=' after a subscripted name (arr[i][j]+=v).
                if (char == '+' and shape.plus_assign_ready
                        and input_text[pos + 1:pos + 2] == '='):
                    take(char, pos + 1)
                    continue
                break  # ordinary terminator: the word ends here

            # --- quotes inside an open subscript stay in the word ---
            if brackets.inside and char in ("'", '"', '$', '`'):
                take(char, pos + 1)
                continue

            # --- quotes/expansions end the word (only non-terminator
            #     contexts, e.g. arithmetic, reach these checks) ---
            if char in ('$', '`', "'", '"'):
                break

            # Check if # starts a comment (shared definition with
            # CommentRecognizer — see comment.is_comment_start)
            if char == '#' and is_comment_start(input_text, pos):
                break

            # Handle escape sequences
            if char == '\\' and pos + 1 < len(input_text):
                take(char + input_text[pos + 1], pos + 2)
                continue

            take(char, pos + 1)

        return value, pos

    def _is_word_terminator(self, char: str, context: LexerContext) -> bool:
        """Check if character terminates a word in current context."""
        # In arithmetic context, only semicolon and parentheses are terminators
        if context.arithmetic_depth > 0:
            return char in (';', '(', ')', '\n')

        # Check for Unicode whitespace (which should terminate words)
        if is_whitespace(char, posix_mode=context.posix_mode):
            return True

        # Basic word terminators
        if char in self.WORD_TERMINATORS:
            # Inside [[ ]], < and > are comparison operators that should be treated as word chars
            if char in ['<', '>'] and context.bracket_depth > 0:
                return False  # Treat as word character
            # { and } are operators only when standalone; inside words
            # (e.g. {a..1}) they are literal characters.  The operator
            # recognizer handles the standalone check, so here we just
            # need to check if we're already mid-word — if the literal
            # collector has accumulated any value, the brace is
            # continuation, not a terminator.  If we're at word start,
            # the operator recognizer already declined (otherwise we
            # wouldn't be here), so treat as literal.
            if char in ('{', '}'):
                return False
            return True

        # Context-specific terminators
        if context.bracket_depth > 0:
            # Inside [[ ]], some characters have special meaning
            if char in ['[', ']']:
                return True

        return False
