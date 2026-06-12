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

from typing import Optional, Tuple

from .command_position import CMDPOS_KEEPING_WORDS as _CMDPOS_KEEPING_WORDS
from .pure_helpers import (
    find_balanced_double_parentheses,
    validate_brace_expansion,
)

# Per-`case` scanner states (one stack entry per enclosing case statement).
_CASE_SUBJECT = 'subject'              # `case` seen; subject word not started
_CASE_SUBJECT_SEEN = 'subject_seen'    # consuming the subject word
_CASE_EXPECT_IN = 'expect_in'          # subject done; the word `in` expected
_CASE_EXPECT_PATTERN = 'expect_pattern'  # after `in` / `;;` — pattern or esac
_CASE_PATTERN = 'pattern'              # in a pattern; `)` at depth 0 ends it
_CASE_BODY = 'body'                    # commands until `;;` / `;&` / `;;&` / esac

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
    """
    n = len(input_text)
    pos = start_pos
    depth = 0                # unmatched unquoted '(' group openers
    case_stack: list = []    # [state, pattern_paren_depth] per open `case`
    command_position = True
    at_word_start = True
    if pending_heredocs is None:
        pending_heredocs = []

    while pos < n:
        ch = input_text[pos]
        top = case_stack[-1] if case_stack else None

        # --- case-state transitions driven by the raw character ---
        if top is not None:
            blank = ch in ' \t\n' or (
                ch == '\\' and input_text.startswith('\\\n', pos))
            if top[0] == _CASE_SUBJECT and not blank:
                top[0] = _CASE_SUBJECT_SEEN
            elif top[0] == _CASE_SUBJECT_SEEN and blank:
                top[0] = _CASE_EXPECT_IN
            elif top[0] == _CASE_EXPECT_PATTERN and not blank and ch != '#':
                if ch == '(':
                    # The grammar's optional pattern-opening '(':
                    # `case x in (x) ...` — consume without counting.
                    top[0] = _CASE_PATTERN
                    pos += 1
                    at_word_start = True
                    continue
                if _peek_plain_word(input_text, pos) == 'esac':
                    case_stack.pop()
                    pos += 4
                    command_position = False
                    at_word_start = False
                    continue
                top[0] = _CASE_PATTERN

        # --- whitespace / newline ---
        if ch in ' \t':
            pos += 1
            at_word_start = True
            continue
        if ch == '\n':
            pos += 1
            if pending_heredocs:
                pos = _consume_heredoc_bodies(input_text, pos, pending_heredocs)
                if pending_heredocs:
                    return n, False  # input ended inside a heredoc body
            command_position = True
            at_word_start = True
            continue

        # --- backslash escapes (and line continuation) ---
        if ch == '\\':
            if input_text.startswith('\\\n', pos):
                pos += 2  # line continuation: vanishes entirely
                continue
            pos += 2
            command_position = False
            at_word_start = False
            continue

        # --- quotes ---
        if ch == "'":
            end = input_text.find("'", pos + 1)
            if end == -1:
                return n, False
            pos = end + 1
            command_position = False
            at_word_start = False
            continue
        if ch == '"':
            end = _skip_double_quotes(input_text, pos + 1, pending_heredocs)
            if end == -1:
                return n, False
            pos = end
            command_position = False
            at_word_start = False
            continue
        if ch == '`':
            end = _skip_until_unescaped(input_text, pos + 1, '`')
            if end == -1:
                return n, False
            pos = end
            command_position = False
            at_word_start = False
            continue

        # --- $-expansions ---
        if ch == '$':
            nxt = input_text[pos + 1] if pos + 1 < n else ''
            if nxt == "'":           # ANSI-C $'...'
                end = _skip_until_unescaped(input_text, pos + 2, "'")
                if end == -1:
                    return n, False
                pos = end
            elif nxt == '"':         # locale string $"..."
                end = _skip_double_quotes(input_text, pos + 2, pending_heredocs)
                if end == -1:
                    return n, False
                pos = end
            elif input_text.startswith('$((', pos):
                end, found = find_balanced_double_parentheses(
                    input_text, pos + 3)
                if not found:
                    return n, False
                pos = end
            elif nxt == '(':
                end, found = find_command_substitution_end(
                    input_text, pos + 2, pending_heredocs)
                if not found:
                    return n, False
                pos = end
            elif nxt == '{':
                _content, end, found = validate_brace_expansion(
                    input_text, pos + 2)
                if not found:
                    return n, False
                pos = end
            else:
                pos += 1
            command_position = False
            at_word_start = False
            continue

        # --- comments ---
        if ch == '#' and at_word_start:
            nl = input_text.find('\n', pos)
            if nl == -1:
                return n, False  # comment hides the rest of the input
            pos = nl
            continue  # the newline branch handles heredocs/command position

        # --- parentheses ---
        if ch == '(':
            if top is not None and top[0] == _CASE_PATTERN:
                top[1] += 1  # extglob/group paren inside a pattern
                pos += 1
                at_word_start = True
                continue
            if command_position and input_text.startswith('((', pos):
                end, found = find_balanced_double_parentheses(
                    input_text, pos + 2)
                if found:  # arithmetic command ((...))
                    pos = end
                    command_position = False
                    at_word_start = False
                    continue
                # no '))' — fall through: treat as a grouping paren
            depth += 1
            pos += 1
            command_position = True
            at_word_start = True
            continue
        if ch == ')':
            if top is not None and top[0] == _CASE_PATTERN:
                if top[1] > 0:
                    top[1] -= 1  # closes an extglob/group paren
                else:
                    top[0] = _CASE_BODY  # ends the pattern (case syntax)
                    command_position = True
                pos += 1
                at_word_start = True
                continue
            if depth > 0:
                depth -= 1
                pos += 1
                command_position = False
                at_word_start = True
                continue
            if case_stack:
                # A bare ')' while a `case` is still open (no `esac` yet,
                # e.g. `$(case x in x) echo hi)`) cannot close the
                # substitution — bash rejects this as a syntax error.
                # Report the substitution as unclosed: more input could
                # still complete the case (interactive PS2), and at EOF
                # the unclosed-substitution error rejects it like bash.
                return n, False
            return pos + 1, True  # the closer of this substitution

        # --- separators / operators ---
        if ch == ';':
            if top is not None and top[0] == _CASE_BODY:
                if input_text.startswith(';;&', pos):
                    top[0] = _CASE_EXPECT_PATTERN
                    pos += 3
                elif input_text.startswith(';;', pos) or \
                        input_text.startswith(';&', pos):
                    top[0] = _CASE_EXPECT_PATTERN
                    pos += 2
                else:
                    pos += 1
            else:
                pos += 1
            command_position = True
            at_word_start = True
            continue
        if ch in '&|':
            pos += 1
            command_position = True
            at_word_start = True
            continue
        if ch in '<>':
            if input_text.startswith('<<', pos) and \
                    not input_text.startswith('<<<', pos):
                strip_tabs = input_text.startswith('<<-', pos)
                j = pos + (3 if strip_tabs else 2)
                delimiter, j = _read_heredoc_delimiter(input_text, j)
                if delimiter is not None:
                    pending_heredocs.append((delimiter, strip_tabs))
                    pos = j
                    command_position = False
                    at_word_start = False
                    continue
                pos += 3 if strip_tabs else 2
            elif input_text.startswith('<<<', pos):
                pos += 3
            else:
                pos += 1
            # Reserved words are not recognized after redirections.
            command_position = False
            at_word_start = True
            continue

        # --- plain word ---
        start = pos
        while pos < n and input_text[pos] not in _WORD_TERMINATORS:
            pos += 1
        word = input_text[start:pos]
        pure = pos >= n or input_text[pos] not in '\'"`$\\'
        if top is not None and top[0] == _CASE_EXPECT_IN:
            if pure and word == 'in':
                top[0] = _CASE_EXPECT_PATTERN
            else:
                case_stack.pop()  # malformed `case` — degrade gracefully
            command_position = False
        elif command_position and pure and word == 'case' and (
                top is None or top[0] == _CASE_BODY):
            case_stack.append([_CASE_SUBJECT, 0])
            command_position = False
        elif command_position and pure and word == 'esac' and \
                top is not None and top[0] == _CASE_BODY:
            case_stack.pop()
            command_position = False
        elif not (pure and word in _CMDPOS_KEEPING_WORDS and command_position):
            command_position = False
        at_word_start = False

    return n, False
