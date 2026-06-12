"""Pure helper functions for lexer operations.

This module contains stateless, pure functions that can be used by the lexer
without coupling to the lexer's internal state. These functions are easier to
test, reuse, and reason about.
"""

from typing import Optional, Set, Tuple


class QuoteState:
    """Tracks single/double-quote and backslash-escape state during a forward
    left-to-right scan of shell text.

    Feed each character in order to ``consume()``; it updates the state and
    reports whether that character is "active" — i.e. outside quotes and not
    itself a quote toggle or an escape (lead or escaped) character — so the
    caller can apply its own structural logic (delimiters, terminators, bracket
    counting) only to active characters while still copying every character.

    By default a backslash inside single quotes is a literal (shell semantics);
    pass ``backslash_literal_in_single=False`` to treat ``\\`` as an escape
    everywhere.
    """

    __slots__ = ('in_single', 'in_double', '_escaped', '_bsl_literal_single')

    def __init__(self, backslash_literal_in_single: bool = True):
        self.in_single = False
        self.in_double = False
        self._escaped = False
        self._bsl_literal_single = backslash_literal_in_single

    @property
    def in_quotes(self) -> bool:
        return self.in_single or self.in_double

    def consume(self, char: str) -> bool:
        """Advance the state by one character; return True if it is active."""
        if self._escaped:
            self._escaped = False
            return False
        if char == '\\' and not (self._bsl_literal_single and self.in_single):
            self._escaped = True
            return False
        if char == "'" and not self.in_double:
            self.in_single = not self.in_single
            return False
        if char == '"' and not self.in_single:
            self.in_double = not self.in_double
            return False
        return not self.in_quotes


def skip_expansion_region(text: str, pos: int) -> Optional[int]:
    """Skip a ``$(...)``, ``${...}`` or `` `...` `` region starting at ``pos``.

    Returns the index just past the closing delimiter, or ``None`` when
    ``pos`` does not start such a region or the region never closes.

    Used by word-shape scanners (array-assignment detection) so that
    whitespace and delimiters inside an expansion do not end the shell
    word: ``a[$(echo 1 + 1)]=v`` is a single assignment word.
    """
    if pos >= len(text):
        return None
    ch = text[pos]
    if ch == '`':
        end = text.find('`', pos + 1)
        return end + 1 if end != -1 else None
    if ch == '$' and pos + 1 < len(text) and text[pos + 1] in '({':
        if text.startswith('$((', pos):
            end, found = find_balanced_double_parentheses(text, pos + 3)
            return end if found else None
        if text[pos + 1] == '(':
            end, found = find_command_substitution_end(text, pos + 2)
            return end if found else None
        end, found = find_closing_delimiter(text, pos + 2, '{', '}')
        return end if found else None
    return None


def find_closing_delimiter(
    input_text: str,
    start_pos: int,
    open_delim: str,
    close_delim: str,
    track_quotes: bool = True,
    track_escapes: bool = True
) -> Tuple[int, bool]:
    """
    Find matching closing delimiter, handling nesting and quotes.

    Args:
        input_text: The input string to search in
        start_pos: Starting position (after opening delimiter)
        open_delim: Opening delimiter string
        close_delim: Closing delimiter string
        track_quotes: Whether to track quote contexts
        track_escapes: Whether to handle escape sequences

    Returns:
        Tuple of (position_after_close, found_closing)
    """
    depth = 1
    pos = start_pos
    in_single_quote = False
    in_double_quote = False

    while pos < len(input_text) and depth > 0:
        char = input_text[pos]

        # Handle escape sequences if enabled
        if track_escapes and char == '\\' and pos + 1 < len(input_text):
            # Skip the escaped character
            pos += 2
            continue

        # Handle quotes if tracking is enabled
        if track_quotes:
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                pos += 1
                continue
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                pos += 1
                continue

        # Track delimiter depth when not in quotes
        if not (in_single_quote or in_double_quote):
            # Check for opening delimiter
            if (pos + len(open_delim) <= len(input_text) and
                input_text[pos:pos+len(open_delim)] == open_delim):
                depth += 1
                pos += len(open_delim)
                continue

            # Check for closing delimiter
            if (pos + len(close_delim) <= len(input_text) and
                input_text[pos:pos+len(close_delim)] == close_delim):
                depth -= 1
                if depth == 0:
                    return pos + len(close_delim), True
                pos += len(close_delim)
                continue

        pos += 1

    return pos, False


def find_balanced_parentheses(
    input_text: str,
    start_pos: int,
    track_quotes: bool = True
) -> Tuple[int, bool]:
    """
    Find balanced parentheses starting from given position.

    Args:
        input_text: The input string
        start_pos: Starting position (after opening paren)
        track_quotes: Whether to ignore parens inside quotes

    Returns:
        Tuple of (position_after_close_paren, found_closing)
    """
    return find_closing_delimiter(
        input_text, start_pos, '(', ')', track_quotes, True
    )


# --------------------------------------------------------------------------
# Grammar-aware command-substitution extent scanning
# --------------------------------------------------------------------------

# Reserved words that keep the scanner "at command position", so a `case`
# directly after them is recognized (`if case ...`, `do case ...`, `{ case ...`).
_CMDPOS_KEEPING_WORDS = frozenset({
    'if', 'then', 'else', 'elif', 'fi', 'while', 'until', 'do', 'done',
    '{', '}', '!', 'time', 'coproc',
})

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


def find_balanced_double_parentheses(
    input_text: str,
    start_pos: int,
    track_quotes: bool = False
) -> Tuple[int, bool]:
    """
    Find balanced double parentheses for arithmetic expressions.

    Args:
        input_text: The input string
        start_pos: Starting position (after opening $(()
        track_quotes: Whether to ignore parens inside quotes.
            Default False to preserve existing lexer behaviour;
            expansion callers pass True.

    Returns:
        Tuple of (position_after_close_parens, found_closing)
    """
    # For arithmetic expressions, we need to find ))
    # but track individual ( and ) for internal balance
    depth = 0
    pos = start_pos
    in_single_quote = False
    in_double_quote = False

    while pos < len(input_text):
        char = input_text[pos]

        # Handle backslash escapes
        if char == '\\' and pos + 1 < len(input_text):
            pos += 2
            continue

        # A nested command substitution may contain unmatched parens (case
        # patterns); skip its full grammar-aware extent. Nested $((...))
        # still balances and is handled by the plain counting below.
        if (input_text.startswith('$(', pos) and
                not input_text.startswith('$((', pos)):
            end, found = find_command_substitution_end(input_text, pos + 2)
            if found:
                pos = end
                continue

        # Handle quotes if tracking is enabled
        if track_quotes:
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                pos += 1
                continue
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                pos += 1
                continue

        # Skip parentheses inside quotes
        if in_single_quote or in_double_quote:
            pos += 1
            continue

        # Check for )) first
        if pos + 1 < len(input_text) and input_text[pos:pos+2] == '))':
            if depth == 0:
                # Found the closing )) at the right depth
                return pos + 2, True
            else:
                # This )) but we have unmatched ( so treat as regular )
                depth -= 1
                pos += 1  # Only advance by 1 to check the second ) again
                continue

        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1

        pos += 1

    return pos, False


def handle_escape_sequence(
    input_text: str,
    pos: int,
    quote_context: Optional[str] = None
) -> Tuple[str, int]:
    """
    Handle escape sequences based on context.

    Args:
        input_text: The input string
        pos: Position of the backslash
        quote_context: Current quote context ('"', "'", "$'", or None)

    Returns:
        Tuple of (escaped_string, new_position)
    """
    if pos >= len(input_text) or input_text[pos] != '\\':
        return '\\', pos + 1

    if pos + 1 >= len(input_text):
        return '\\', pos + 1

    next_char = input_text[pos + 1]

    if quote_context == "$'":
        # ANSI-C quoting - handle extended escape sequences
        return handle_ansi_c_escape(input_text, pos)
    elif quote_context == '"':
        # In double quotes, bash only processes: \", \\, \$, \` and
        # \newline. Other sequences like \n, \t, \r are NOT escape
        # sequences here — the backslash is preserved literally.
        if next_char == '\n':
            # Escaped newline is a line continuation - remove it
            return '', pos + 2
        elif next_char in '"\\`':
            return next_char, pos + 2
        elif next_char == '$':
            # Special case: \$ preserves the backslash in double quotes
            return '\\$', pos + 2
        else:
            # Other characters keep the backslash
            return '\\' + next_char, pos + 2
    elif quote_context is None:
        # Outside quotes - backslash escapes everything
        if next_char == '\n':
            # Escaped newline is a line continuation - remove it
            return '', pos + 2
        elif next_char == '$':
            return '$', pos + 2  # Escaped dollar is literal $
        else:
            return next_char, pos + 2
    else:
        # Single quotes - no escaping (except for the quote itself in some contexts)
        return '\\' + next_char, pos + 2


def handle_ansi_c_escape(input_text: str, pos: int) -> Tuple[str, int]:
    """
    Handle ANSI-C escape sequences in $'...' strings.

    Args:
        input_text: The input string
        pos: Position of the backslash

    Returns:
        Tuple of (escaped_string, new_position)
    """
    if pos + 1 >= len(input_text):
        return '\\', pos + 1

    next_char = input_text[pos + 1]

    # Simple single-character escapes
    simple_escapes = {
        'n': '\n', 't': '\t', 'r': '\r', 'b': '\b',
        'f': '\f', 'v': '\v', 'a': '\a', '\\': '\\',
        "'": "'", '"': '"', '?': '?',
        'e': '\x1b', 'E': '\x1b'  # ANSI escape
    }

    if next_char in simple_escapes:
        return simple_escapes[next_char], pos + 2

    # Hex escape: \xHH
    if next_char == 'x':
        hex_str = ""
        new_pos = pos + 2
        # Read up to 2 hex digits
        for i in range(2):
            if new_pos < len(input_text) and input_text[new_pos] in '0123456789ABCDEFabcdef':
                hex_str += input_text[new_pos]
                new_pos += 1
            else:
                break

        if hex_str:
            try:
                return chr(int(hex_str, 16)), new_pos
            except ValueError:
                return '\\x' + hex_str, new_pos
        else:
            return '\\x', pos + 2

    # Octal escape: \NNN — 1 to 3 octal digits (bash style; a leading 0 is
    # just the first digit, so \101 -> 'A' and \0101 -> octal 010 + '1').
    if next_char in '01234567':
        octal_str = ""
        new_pos = pos + 1  # start at the first octal digit (next_char)
        for i in range(3):
            if new_pos < len(input_text) and input_text[new_pos] in '01234567':
                octal_str += input_text[new_pos]
                new_pos += 1
            else:
                break
        return chr(int(octal_str, 8) & 0xFF), new_pos

    # Unicode escape: \uHHHH
    if next_char == 'u':
        hex_str = ""
        new_pos = pos + 2
        # Read exactly 4 hex digits
        for i in range(4):
            if new_pos < len(input_text) and input_text[new_pos] in '0123456789ABCDEFabcdef':
                hex_str += input_text[new_pos]
                new_pos += 1
            else:
                break

        # bash accepts 1 to 4 hex digits after \u.
        if hex_str:
            try:
                return chr(int(hex_str, 16)), new_pos
            except ValueError:
                return '\\u' + hex_str, new_pos
        else:
            return '\\u', new_pos

    # Unicode escape: \UHHHHHHHH (8 digits)
    if next_char == 'U':
        hex_str = ""
        new_pos = pos + 2
        # Read exactly 8 hex digits
        for i in range(8):
            if new_pos < len(input_text) and input_text[new_pos] in '0123456789ABCDEFabcdef':
                hex_str += input_text[new_pos]
                new_pos += 1
            else:
                break

        # bash accepts 1 to 8 hex digits after \U.
        if hex_str:
            try:
                return chr(int(hex_str, 16)), new_pos
            except ValueError:
                return '\\U' + hex_str, new_pos
        else:
            return '\\U', new_pos

    # For other characters, keep the backslash
    return '\\' + next_char, pos + 2


def extract_variable_name(
    input_text: str,
    start_pos: int,
    special_vars: Set[str],
    posix_mode: bool = False
) -> Tuple[str, int]:
    """
    Extract a variable name starting from the given position.

    Args:
        input_text: The input string
        start_pos: Starting position (after $)
        special_vars: Set of special single-character variables
        posix_mode: Whether to use POSIX-compliant identifier rules

    Returns:
        Tuple of (variable_name, new_position)
    """
    from .unicode_support import is_identifier_char, is_identifier_start

    if start_pos >= len(input_text):
        return "", start_pos

    char = input_text[start_pos]

    # Special single-character variables
    if char in special_vars:
        return char, start_pos + 1

    # Regular variable names
    var_name = ""
    pos = start_pos

    # First character must be letter or underscore (not digit)
    if pos < len(input_text) and is_identifier_start(char, posix_mode):
        var_name += char
        pos += 1

        # Subsequent characters can be letters, numbers, marks, or underscore
        while pos < len(input_text):
            char = input_text[pos]
            if is_identifier_char(char, posix_mode):
                var_name += char
                pos += 1
            else:
                break

    # Don't return anything for invalid start (like digits)
    return var_name, pos


def validate_brace_expansion(
    input_text: str,
    start_pos: int
) -> Tuple[str, int, bool]:
    """
    Validate and extract a brace expansion ${...}.

    Args:
        input_text: The input string
        start_pos: Starting position (after ${)

    Returns:
        Tuple of (content, position_after_close_brace, found_closing_brace)
    """
    pos = start_pos
    n = len(input_text)
    brace_depth = 1

    while pos < n:
        char = input_text[pos]

        if char == '\\' and pos + 1 < n:
            pos += 2
            continue
        if char == "'":
            # Single-quoted segment: a } inside it does not close (POSIX)
            end = input_text.find("'", pos + 1)
            if end == -1:
                break
            pos = end + 1
            continue
        if char == '"':
            # Double-quoted segment (with escape handling)
            pos += 1
            while pos < n and input_text[pos] != '"':
                if input_text[pos] == '\\' and pos + 1 < n:
                    pos += 2
                else:
                    pos += 1
            pos += 1
            continue
        if input_text.startswith('$((', pos):
            # Arithmetic expansion: skip to the matching ))
            end, found = find_balanced_double_parentheses(input_text, pos + 3)
            if not found:
                break
            pos = end
            continue
        if input_text.startswith('$(', pos):
            # Command substitution: skip its full grammar-aware extent (a
            # case pattern inside may contain an unmatched ')' and a '}').
            end, found = find_command_substitution_end(input_text, pos + 2)
            if not found:
                break
            pos = end
            continue
        if char == '{':
            brace_depth += 1
        elif char == '}':
            brace_depth -= 1
            if brace_depth == 0:
                return input_text[start_pos:pos], pos + 1, True

        pos += 1

    return input_text[start_pos:min(pos, n)], min(pos, n), False


def is_inside_expansion(
    input_text: str,
    position: int
) -> bool:
    """
    Check if the position is inside an arithmetic expression or command substitution.

    Args:
        input_text: The input string
        position: Position to check

    Returns:
        True if position is inside an expansion
    """
    if position >= len(input_text):
        return False

    # Simple approach: scan from beginning and track expansion boundaries
    i = 0
    while i <= position and i < len(input_text):
        # Check for arithmetic expansion $((
        if i + 2 < len(input_text) and input_text[i:i+3] == '$((':
            # Find the closing ))
            end_pos, found = find_balanced_double_parentheses(input_text, i + 3)
            if found and i <= position < end_pos:
                return True
            i = end_pos if found else i + 3
            continue

        # Check for command substitution $(
        if i + 1 < len(input_text) and input_text[i:i+2] == '$(':
            # Find the closing )
            end_pos, found = find_balanced_parentheses(input_text, i + 2)
            if found and i <= position < end_pos:
                return True
            i = end_pos if found else i + 2
            continue

        # Check for backtick command substitution
        if input_text[i] == '`':
            # Find the closing backtick
            j = i + 1
            while j < len(input_text) and input_text[j] != '`':
                j += 1
            if j < len(input_text):  # Found closing backtick
                if i < position < j:  # Position is inside backticks
                    return True
                i = j + 1
            else:
                i += 1
            continue

        i += 1

    return False
