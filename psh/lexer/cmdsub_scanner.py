"""Grammar-aware ``$(...)`` extent scanner.

The single hard problem of lexing command substitutions: where does
``$(`` end? Parentheses cannot simply be counted — case patterns contain
unmatched ``)``, and parens inside quotes, comments, and heredoc bodies are
not delimiters at all. :func:`find_command_substitution_end` (see its
Design / Maintenance-contract docstring) models exactly enough of the shell
grammar to answer that question; everything else in this module is its
private helpers.

Extracted from ``pure_helpers.py``: this scanner is a PARSER COMPONENT that
happens to live in the lexer package, not a char-level helper — keeping it
as its own module makes the maintenance contract (and its owner tests)
discoverable.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from .command_position import CMDPOS_KEEPING_WORDS as _CMDPOS_KEEPING_WORDS
from .pure_helpers import (
    find_balanced_double_parentheses,
    validate_brace_expansion,
)


class CasePhase(Enum):
    """Per-`case` scanner phases (one stack entry per enclosing case)."""

    SUBJECT = 'subject'              # `case` seen; subject word not started
    SUBJECT_SEEN = 'subject_seen'    # consuming the subject word
    EXPECT_IN = 'expect_in'          # subject done; the word `in` expected
    EXPECT_PATTERN = 'expect_pattern'  # after `in` / `;;` — pattern or esac
    PATTERN = 'pattern'              # in a pattern; `)` at depth 0 ends it
    BODY = 'body'                    # commands until `;;` / `;&` / `;;&` / esac


@dataclass
class CaseScanState:
    """Mutable scan state for one enclosing ``case`` statement."""

    phase: CasePhase
    pattern_paren_depth: int = 0

# Characters that end a plain word (quote/expansion starters are handled
# separately by the main scan loop before the word reader runs).
_WORD_TERMINATORS = frozenset(' \t\n;|&()<>\'"`$\\')


def _skip_until_unescaped(text: str, pos: int, end_char: str) -> int:
    """Index just past the first unescaped *end_char* at/after *pos*, or -1.

    Used for backtick substitutions and ANSI-C ``$'...'`` strings, where a
    backslash escapes the next character (so ``\\``` / ``\\'`` do not close).
    """
    n = len(text)
    while pos < n:
        if text[pos] == '\\' and pos + 1 < n:
            pos += 2
        elif text[pos] == end_char:
            return pos + 1
        else:
            pos += 1
    return -1


def _skip_double_quotes(text: str, pos: int, pending_heredocs: list) -> int:
    """Index just past the ``"`` closing a double quote opened before *pos*.

    Returns -1 when the quote (or a nested expansion inside it) never closes.
    Nested ``$(...)`` regions restart full shell context, so they are scanned
    with :func:`find_command_substitution_end` (sharing *pending_heredocs*).
    """
    n = len(text)
    while pos < n:
        c = text[pos]
        if c == '\\' and pos + 1 < n:
            pos += 2
        elif c == '"':
            return pos + 1
        elif text.startswith('$((', pos):
            end, found = find_balanced_double_parentheses(text, pos + 3)
            if not found:
                return -1
            pos = end
        elif text.startswith('$(', pos):
            end, found = find_command_substitution_end(
                text, pos + 2, pending_heredocs)
            if not found:
                return -1
            pos = end
        elif text.startswith('${', pos):
            _content, end, found = validate_brace_expansion(text, pos + 2)
            if not found:
                return -1
            pos = end
        elif c == '`':
            end = _skip_until_unescaped(text, pos + 1, '`')
            if end == -1:
                return -1
            pos = end
        else:
            pos += 1
    return -1


def _read_heredoc_delimiter(text: str, pos: int) -> Tuple[Optional[str], int]:
    """Read the delimiter word after ``<<`` / ``<<-``.

    Returns ``(delimiter, new_pos)`` with one level of quoting removed
    (``<<'EOF'``, ``<<"EOF"``, ``<<\\EOF`` all yield ``EOF``), or
    ``(None, pos)`` when no word follows on the line.
    """
    n = len(text)
    while pos < n and text[pos] in ' \t':
        pos += 1
    out = []
    while pos < n and text[pos] not in ' \t\n;|&()<>':
        c = text[pos]
        if c == "'":
            end = text.find("'", pos + 1)
            if end == -1:
                break
            out.append(text[pos + 1:end])
            pos = end + 1
        elif c == '"':
            pos += 1
            while pos < n and text[pos] != '"':
                if text[pos] == '\\' and pos + 1 < n:
                    out.append(text[pos + 1])
                    pos += 2
                else:
                    out.append(text[pos])
                    pos += 1
            pos += 1
        elif c == '\\' and pos + 1 < n:
            out.append(text[pos + 1])
            pos += 2
        else:
            out.append(c)
            pos += 1
    if not out:
        return None, pos
    return ''.join(out), pos


def _consume_heredoc_bodies(text: str, pos: int, pending: list) -> int:
    """Consume heredoc body lines starting at *pos* (just after a newline).

    Lines are matched against the pending delimiters in order (the body of
    the first ``<<WORD`` on a line comes first, as in bash). Entries are
    popped from *pending* as their delimiter lines are found; a non-empty
    *pending* on return means the input ended mid-body (caller reports the
    substitution as unclosed so more input can be gathered).
    """
    n = len(text)
    while pending:
        if pos >= n:
            return n
        nl = text.find('\n', pos)
        line_end = n if nl == -1 else nl
        line = text[pos:line_end]
        delimiter, strip_tabs = pending[0]
        check = line.lstrip('\t') if strip_tabs else line
        # rstrip() mirrors psh's heredoc line gatherer so the two layers
        # always agree on where a body ends.
        if check.rstrip() == delimiter:
            pending.pop(0)
        pos = n if nl == -1 else nl + 1
    return pos


def _peek_plain_word(text: str, pos: int) -> str:
    """The plain literal word starting at *pos*, or ``''``.

    A word is "plain" when it is delimited by whitespace/operators on both
    sides and contains no quoting or expansion characters — only such words
    can be reserved words (``esac$x`` is a pattern, not ``esac``).
    """
    n = len(text)
    end = pos
    while end < n and text[end] not in _WORD_TERMINATORS:
        end += 1
    if end == pos:
        return ''
    if end < n and text[end] in '\'"`$\\':
        return ''
    return text[pos:end]


def find_command_substitution_end(
    input_text: str,
    start_pos: int,
    pending_heredocs: Optional[list] = None,
) -> Tuple[int, bool]:
    """Find the ``)`` that closes a ``$(`` command substitution.

    Args:
        input_text: The input string.
        start_pos: Position just after the opening ``$(``.
        pending_heredocs: Internal — heredocs opened but not yet closed,
            shared across nested scans (see below).

    Returns:
        Tuple of ``(position_after_close_paren, found_closing)``. When the
        closing paren is not found, the position is ``len(input_text)`` and
        the caller should treat the substitution as unclosed (incomplete
        input — more lines may complete it).

    Design
    ------
    The extent of ``$(...)`` cannot be found by counting parentheses: shell
    grammar permits an *unmatched* ``)`` inside the substitution, most
    importantly in case patterns (``$(case x in x) echo hi;; esac)``), and
    parentheses inside quotes, comments, and heredoc bodies are not
    delimiters at all. Bash solves this by recursively invoking its parser
    (``xparse_dolparen``); psh uses this scanner — a deliberately small
    model of the shell grammar that tracks *just enough* state to know when
    a ``)`` is structural:

    * **Quotes**: ``'...'``, ``"..."`` (with nested ``$(...)``/``${...}``/
      backticks rescanned inside), ANSI-C ``$'...'``, and backslash escapes.
      A quoted or escaped ``)`` never closes anything.
    * **Nested expansions**: ``$(...)`` recurses into this scanner;
      ``$((...))`` is skipped as arithmetic (same greedy ``$((`` dispatch
      as the lexer itself); ``${...}`` is skipped brace-aware.
    * **Comments**: an unquoted ``#`` at the start of a word hides the rest
      of the line, so ``$(echo hi # not-a-paren )`` stays open until a
      later ``)``.
    * **Heredocs**: ``<<WORD`` / ``<<-WORD`` (but not ``<<<``) queue a
      delimiter; body lines after the next newline are skipped until the
      delimiter line. The queue is shared with nested scans because bash
      reads heredoc bodies at the next physical newline regardless of
      nesting depth (``$(echo $(cat <<A) x`` + body lines works). A
      substitution that closes on the same line as its ``<<WORD`` leaves
      the body to be read at top level — bash steals the following source
      lines for it (with a warning); psh does not, which is a documented
      divergence for that corner.
    * **Group parens**: an unquoted ``(`` in command context (subshell,
      function definition, process substitution, extglob) raises a depth
      counter that the matching ``)`` lowers; ``((...))`` at command
      position is skipped as arithmetic, falling back to a grouping paren
      when no ``))`` follows.
    * **Case statements**: the heart of the fix. A small state machine
      recognizes ``case`` *only at command position* (so ``echo case in x)``
      is not misparsed), skips the subject word, requires the word ``in``,
      and then alternates between pattern context — where exactly one
      unmatched ``)`` per pattern is consumed as case syntax, ``(`` opens
      the optional POSIX pattern paren or an extglob group, and ``|``
      separates alternatives — and body context, where ``;;`` / ``;&`` /
      ``;;&`` return to pattern context and ``esac`` pops the state. Case
      statements nest (stack), and ``$(case ...)`` inside a pattern or
      subject recurses normally.

    Command position is approximated: true at the start, after separators
    (``;``, ``&``, ``|``, newline, ``(``) and after reserved words such as
    ``then``/``do``/``{``, false after ordinary words and redirections.
    This is exactly the context the real lexer/parser use to decide whether
    ``case`` is a keyword, so the scanner and the later full parse of the
    substitution body agree on structure. Malformed input degrades
    gracefully: the scanner picks *a* plausible extent and the real parser
    of the substitution body reports the syntax error (as bash does).

    Maintenance contract
    --------------------
    This function is a PARSER COMPONENT that happens to live in the lexer:
    it models a parallel copy of the shell grammar for quoting (all four
    quote forms + backslash), comments, heredoc redirections, arithmetic
    ``$((...))``/``((...))``, ``${...}``, group/subshell parens, and the
    ``case``..``esac`` statement (keyword-at-command-position rules
    included). Any parser or lexer grammar change touching those areas —
    new quoting forms, heredoc operators, case/pattern syntax, arithmetic
    delimiters, command-position keyword rules — MUST consider whether this
    scanner needs the same change, or the extent it picks will drift from
    what the parser later accepts. Owner tests to extend when it changes:

    * tests/unit/lexer/test_cmdsub_extent.py        (unit: extent picking)
    * tests/integration/parsing/test_cmdsub_grammar.py  (lexer+parser agree)
    * tests/conformance/bash/test_cmdsub_case_conformance.py
      (bash 5.2 parity for tricky $(...) bodies — add a probe-verified
      case here for every new grammar feature this scanner models)

    Implementation
    --------------
    The scan state and per-construct handlers live in :class:`_CmdSubScanner`;
    this function is just the public entry point that drives it. Each handler
    returns ``None`` to continue scanning or a ``(pos, found)`` tuple to stop.
    """
    return _CmdSubScanner(input_text, start_pos, pending_heredocs).scan()


class _CmdSubScanner:
    """Mutable scan state + per-construct handlers for one ``$(`` extent.

    A fresh instance scans one substitution body (nested ``$(...)`` create
    their own instances via :func:`find_command_substitution_end`, sharing
    only the ``pending_heredocs`` list). The handlers form a flat dispatch
    over the construct at the cursor; each consumes its construct, updates the
    state fields below, and returns either ``None`` (keep scanning) or a final
    ``(pos, found)`` result tuple.

    State fields:
        text, n       -- the input and its length (immutable)
        pos           -- cursor; advances as constructs are consumed
        depth         -- unmatched unquoted ``(`` group/subshell openers
        case_stack    -- a :class:`CaseScanState` per open ``case``
        command_position -- True where a reserved word (``case``/``if``/...)
                         would be recognized (start, after separators, ...)
        at_word_start -- True at the first char of a word (so ``#`` is a
                         comment only there)
        pending_heredocs -- ``(delimiter, strip_tabs)`` queue, shared across
                         nested scans (bash reads bodies at the next physical
                         newline regardless of nesting depth)
    """

    def __init__(
        self,
        text: str,
        start_pos: int,
        pending_heredocs: Optional[list],
    ) -> None:
        self.text = text
        self.n = len(text)
        self.pos = start_pos
        self.depth = 0
        self.case_stack: List[CaseScanState] = []
        self.command_position = True
        self.at_word_start = True
        self.pending_heredocs: list = (
            [] if pending_heredocs is None else pending_heredocs)

    def scan(self) -> Tuple[int, bool]:
        """Drive the per-construct handlers until a result or end of input."""
        while self.pos < self.n:
            ch = self.text[self.pos]
            top = self.case_stack[-1] if self.case_stack else None

            result = self._advance_case_state(ch, top)
            if result is not None:
                continue  # handler consumed input; re-evaluate from new pos

            handler = self._dispatch(ch)
            outcome = handler(ch, top)
            if outcome is not None:
                return outcome
        return self.n, False

    def _dispatch(self, ch: str):
        """Pick the handler for the construct starting with *ch*."""
        if ch in ' \t':
            return self._handle_blank
        if ch == '\n':
            return self._handle_newline
        if ch == '\\':
            return self._handle_backslash
        if ch == "'":
            return self._handle_single_quote
        if ch == '"':
            return self._handle_double_quote
        if ch == '`':
            return self._handle_backtick
        if ch == '$':
            return self._handle_dollar
        if ch == '#':
            return self._handle_hash
        if ch == '(':
            return self._handle_open_paren
        if ch == ')':
            return self._handle_close_paren
        if ch == ';':
            return self._handle_semicolon
        if ch in '&|':
            return self._handle_pipe_amp
        if ch in '<>':
            return self._handle_redirection
        return self._handle_word

    # -- case-statement state machine ------------------------------------

    def _advance_case_state(self, ch: str, top) -> Optional[bool]:
        """Apply the raw-character ``case`` state transitions.

        Returns ``True`` when it consumed input itself (the optional pattern
        ``(`` or a closing ``esac`` at pattern-expect) so the caller restarts
        the loop; otherwise ``None`` after possibly mutating *top* in place.
        """
        if top is None:
            return None
        blank = ch in ' \t\n' or (
            ch == '\\' and self.text.startswith('\\\n', self.pos))
        if top.phase == CasePhase.SUBJECT and not blank:
            top.phase = CasePhase.SUBJECT_SEEN
        elif top.phase == CasePhase.SUBJECT_SEEN and blank:
            top.phase = CasePhase.EXPECT_IN
        elif top.phase == CasePhase.EXPECT_PATTERN and not blank and ch != '#':
            if ch == '(':
                # The grammar's optional pattern-opening '(':
                # `case x in (x) ...` — consume without counting.
                top.phase = CasePhase.PATTERN
                self.pos += 1
                self.at_word_start = True
                return True
            if _peek_plain_word(self.text, self.pos) == 'esac':
                self.case_stack.pop()
                self.pos += 4
                self.command_position = False
                self.at_word_start = False
                return True
            top.phase = CasePhase.PATTERN
        return None

    # -- whitespace / newline --------------------------------------------

    def _handle_blank(self, ch: str, top) -> None:
        self.pos += 1
        self.at_word_start = True
        return None

    def _handle_newline(self, ch: str, top) -> Optional[Tuple[int, bool]]:
        self.pos += 1
        if self.pending_heredocs:
            self.pos = _consume_heredoc_bodies(
                self.text, self.pos, self.pending_heredocs)
            if self.pending_heredocs:
                return self.n, False  # input ended inside a heredoc body
        self.command_position = True
        self.at_word_start = True
        return None

    # -- backslash escapes (and line continuation) -----------------------

    def _handle_backslash(self, ch: str, top) -> None:
        if self.text.startswith('\\\n', self.pos):
            self.pos += 2  # line continuation: vanishes entirely
            return None
        self.pos += 2
        self.command_position = False
        self.at_word_start = False
        return None

    # -- quotes -----------------------------------------------------------

    def _handle_single_quote(self, ch: str, top) -> Optional[Tuple[int, bool]]:
        end = self.text.find("'", self.pos + 1)
        if end == -1:
            return self.n, False
        self.pos = end + 1
        self.command_position = False
        self.at_word_start = False
        return None

    def _handle_double_quote(self, ch: str, top) -> Optional[Tuple[int, bool]]:
        end = _skip_double_quotes(
            self.text, self.pos + 1, self.pending_heredocs)
        if end == -1:
            return self.n, False
        self.pos = end
        self.command_position = False
        self.at_word_start = False
        return None

    def _handle_backtick(self, ch: str, top) -> Optional[Tuple[int, bool]]:
        end = _skip_until_unescaped(self.text, self.pos + 1, '`')
        if end == -1:
            return self.n, False
        self.pos = end
        self.command_position = False
        self.at_word_start = False
        return None

    # -- $-expansions -----------------------------------------------------

    def _handle_dollar(self, ch: str, top) -> Optional[Tuple[int, bool]]:
        text, pos, n = self.text, self.pos, self.n
        nxt = text[pos + 1] if pos + 1 < n else ''
        if nxt == "'":            # ANSI-C $'...'
            end = _skip_until_unescaped(text, pos + 2, "'")
            if end == -1:
                return self.n, False
            self.pos = end
        elif nxt == '"':          # locale string $"..."
            end = _skip_double_quotes(text, pos + 2, self.pending_heredocs)
            if end == -1:
                return self.n, False
            self.pos = end
        elif text.startswith('$((', pos):
            end, found = find_balanced_double_parentheses(text, pos + 3)
            if not found:
                return self.n, False
            self.pos = end
        elif nxt == '(':
            end, found = find_command_substitution_end(
                text, pos + 2, self.pending_heredocs)
            if not found:
                return self.n, False
            self.pos = end
        elif nxt == '{':
            _content, end, found = validate_brace_expansion(text, pos + 2)
            if not found:
                return self.n, False
            self.pos = end
        else:
            self.pos += 1
        self.command_position = False
        self.at_word_start = False
        return None

    # -- comments ---------------------------------------------------------

    def _handle_hash(self, ch: str, top) -> Optional[Tuple[int, bool]]:
        if not self.at_word_start:
            self._handle_word(ch, top)  # never matches a close; returns None
            return None
        nl = self.text.find('\n', self.pos)
        if nl == -1:
            return self.n, False  # comment hides the rest of the input
        self.pos = nl
        # the newline branch handles heredocs / command position
        return None

    # -- parentheses ------------------------------------------------------

    def _handle_open_paren(self, ch: str, top) -> None:
        if top is not None and top.phase == CasePhase.PATTERN:
            top.pattern_paren_depth += 1  # extglob/group paren in a pattern
            self.pos += 1
            self.at_word_start = True
            return None
        if self.command_position and self.text.startswith('((', self.pos):
            end, found = find_balanced_double_parentheses(
                self.text, self.pos + 2)
            if found:  # arithmetic command ((...))
                self.pos = end
                self.command_position = False
                self.at_word_start = False
                return None
            # no '))' — fall through: treat as a grouping paren
        self.depth += 1
        self.pos += 1
        self.command_position = True
        self.at_word_start = True
        return None

    def _handle_close_paren(self, ch: str, top) -> Optional[Tuple[int, bool]]:
        if top is not None and top.phase == CasePhase.PATTERN:
            if top.pattern_paren_depth > 0:
                top.pattern_paren_depth -= 1  # closes an extglob/group paren
            else:
                top.phase = CasePhase.BODY  # ends the pattern (case syntax)
                self.command_position = True
            self.pos += 1
            self.at_word_start = True
            return None
        if self.depth > 0:
            self.depth -= 1
            self.pos += 1
            self.command_position = False
            self.at_word_start = True
            return None
        if self.case_stack:
            # A bare ')' while a `case` is still open (no `esac` yet,
            # e.g. `$(case x in x) echo hi)`) cannot close the
            # substitution — bash rejects this as a syntax error.
            # Report the substitution as unclosed: more input could
            # still complete the case (interactive PS2), and at EOF
            # the unclosed-substitution error rejects it like bash.
            return self.n, False
        return self.pos + 1, True  # the closer of this substitution

    # -- separators / operators ------------------------------------------

    def _handle_semicolon(self, ch: str, top) -> None:
        if top is not None and top.phase == CasePhase.BODY:
            if self.text.startswith(';;&', self.pos):
                top.phase = CasePhase.EXPECT_PATTERN
                self.pos += 3
            elif self.text.startswith(';;', self.pos) or \
                    self.text.startswith(';&', self.pos):
                top.phase = CasePhase.EXPECT_PATTERN
                self.pos += 2
            else:
                self.pos += 1
        else:
            self.pos += 1
        self.command_position = True
        self.at_word_start = True
        return None

    def _handle_pipe_amp(self, ch: str, top) -> None:
        self.pos += 1
        self.command_position = True
        self.at_word_start = True
        return None

    def _handle_redirection(self, ch: str, top) -> None:
        text, pos = self.text, self.pos
        if text.startswith('<<', pos) and not text.startswith('<<<', pos):
            strip_tabs = text.startswith('<<-', pos)
            j = pos + (3 if strip_tabs else 2)
            delimiter, j = _read_heredoc_delimiter(text, j)
            if delimiter is not None:
                self.pending_heredocs.append((delimiter, strip_tabs))
                self.pos = j
                self.command_position = False
                self.at_word_start = False
                return None
            self.pos += 3 if strip_tabs else 2
        elif text.startswith('<<<', pos):
            self.pos += 3
        else:
            self.pos += 1
        # Reserved words are not recognized after redirections.
        self.command_position = False
        self.at_word_start = True
        return None

    # -- plain word -------------------------------------------------------

    def _handle_word(self, ch: str, top) -> None:
        text, n = self.text, self.n
        start = self.pos
        pos = start
        while pos < n and text[pos] not in _WORD_TERMINATORS:
            pos += 1
        self.pos = pos
        word = text[start:pos]
        pure = pos >= n or text[pos] not in '\'"`$\\'
        if top is not None and top.phase == CasePhase.EXPECT_IN:
            if pure and word == 'in':
                top.phase = CasePhase.EXPECT_PATTERN
            else:
                self.case_stack.pop()  # malformed `case` — degrade gracefully
            self.command_position = False
        elif self.command_position and pure and word == 'case' and (
                top is None or top.phase == CasePhase.BODY):
            self.case_stack.append(CaseScanState(CasePhase.SUBJECT))
            self.command_position = False
        elif self.command_position and pure and word == 'esac' and \
                top is not None and top.phase == CasePhase.BODY:
            self.case_stack.pop()
            self.command_position = False
        elif not (pure and word in _CMDPOS_KEEPING_WORDS
                  and self.command_position):
            self.command_position = False
        self.at_word_start = False
        return None
