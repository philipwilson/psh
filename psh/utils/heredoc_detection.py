"""Heredoc detection heuristics.

Distinguishes a real ``<<EOF`` heredoc from a ``<<`` bit-shift (arithmetic) or
a ``<<<`` here-string, and tracks whether a heredoc's delimiter has appeared
yet. This is the single source of truth for heredoc line-gathering, consumed
by the shared completeness oracle (`scripting/command_accumulator.py`) that
both the script/`-c`/stdin path and the interactive multiline path drive.
"""

import re

# A heredoc start: ``<<WORD``, ``<<-WORD``, ``<< WORD``, plus every quoted /
# escaped / composite delimiter spelling bash accepts — ``<<'EOF'``,
# ``<<"E F"``, ``<<\EOF``, ``<<EO\F``, ``<<E"O"F``, ``<<E$X``. The look-around
# rejects a third ``<`` so a here-string (``<<<WORD``) is not mistaken for a
# heredoc.
#   group(1): '-' for <<- (strip leading tabs)
#   group(2): the RAW delimiter — a run of word chars (``$`` included, taken
#             LITERALLY like bash), backslash-escaped chars, and single/double-
#             quoted segments (quotes/escapes still present).
# Use heredoc_delimiter_word(match) for the literal terminator text. ``$`` is a
# plain delimiter character here (``<<E$X`` → terminator ``E$X``); this MUST
# agree with HeredocLexer._delimiter_from_source and the parser's _parse_heredoc.
HEREDOC_MARKER_RE = re.compile(
    r'(?<!<)<<(?!<)(-?)\s*((?:\\.|"[^"]*"|\'[^\']*\'|[A-Za-z0-9_$])+)')


def heredoc_delimiter_word(match: 're.Match') -> str:
    """The literal terminator text for a HEREDOC_MARKER_RE match.

    Normalizes the raw delimiter (group 2) the way the body terminator is
    written: each ``\\x`` becomes ``x`` and quoted segments contribute their
    contents — so ``\\EOF``/``EO\\F``/``E"O"F`` all yield ``EOF`` and ``"E F"``
    yields ``E F`` (mirrors the lexer's normalize_heredoc_delimiter).
    """
    raw = match.group(2)
    out: list = []
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == '\\' and i + 1 < n:
            out.append(raw[i + 1])
            i += 2
        elif c in ('"', "'"):
            j = raw.find(c, i + 1)
            if j < 0:
                j = n
            out.append(raw[i + 1:j])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def _scan_arith_or_cmdsub(line: str, position: int, opener: str, open_len: int) -> bool:
    """True if *position* falls within a ``opener … )`` region on *line*.

    ``opener`` is ``'$(('`` / ``'$('`` / ``'(('``; ``open_len`` is how many
    parens it contributes to the nesting depth (2 for the arithmetic forms,
    1 for command substitution).
    """
    start = -1
    depth = 0
    i = 0
    while i < len(line):
        if line[i:i + len(opener)] == opener and start < 0:
            # For bare '((' don't re-trigger on the '((' inside a '$(('.
            if opener == '((' and i > 0 and line[i - 1] == '$':
                i += 1
                continue
            if i <= position:
                start = i
                depth = open_len
                i += len(opener)
                continue
            break
        if start >= 0:
            if line[i] == '(':
                depth += 1
            elif line[i] == ')':
                depth -= 1
                if depth == 0:
                    if start <= position <= i:
                        return True
                    start = -1
        i += 1
    return False


def _inside_closed_cmdsub(line: str, position: int) -> bool:
    """True if *position* falls within a ``$( … )`` region that CLOSES on
    *line*, using the grammar-aware extent scanner (so a case pattern's bare
    ``)`` inside the substitution does not end the region early). An
    unclosed ``$(`` returns False: a ``<<`` inside it is then treated as a
    pending heredoc so the line gatherer keeps reading — matching how the
    full lexer will see it once the substitution is complete.
    """
    from ..lexer.cmdsub_scanner import find_command_substitution_end
    i = 0
    n = len(line)
    while i < n and i <= position:
        if line.startswith('$((', i):
            i += 3  # arithmetic; handled by _scan_arith_or_cmdsub
            continue
        if line.startswith('$(', i):
            end, found = find_command_substitution_end(line, i + 2)
            if found:
                if i <= position < end:
                    return True
                i = end
                continue
            return False
        i += 1
    return False


def _inside_param_expansion(line: str, position: int) -> bool:
    """True if *position* is inside a ``${…}`` parameter expansion (where a
    ``<<`` is an arithmetic left-shift in a subscript, e.g. ``${arr[1<<1]}``,
    not a heredoc). Tracks brace nesting (``${a${b}}``). An unclosed ``${``
    returns False so the line gatherer keeps reading, mirroring the cmdsub case.
    """
    i, n = 0, len(line)
    while i < n and i <= position:
        if line.startswith('${', i):
            depth, j = 0, i + 1
            while j < n:
                if line[j] == '{':
                    depth += 1
                elif line[j] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j < n:  # found the matching close brace
                if i <= position <= j:
                    return True
                i = j + 1
                continue
            return False  # unclosed ${ — let the gatherer keep reading
        i += 1
    return False


def is_inside_expansion(line: str, position: int) -> bool:
    """True if *position* on *line* is inside an expansion where ``<<`` is not
    a heredoc: ``$((…))`` / bare ``((…))`` arithmetic, ``$(…)`` command
    substitution, ``${…}`` parameter expansion, or ``` `…` ``` backticks.
    """
    if _scan_arith_or_cmdsub(line, position, '$((', 2):
        return True
    if _inside_closed_cmdsub(line, position):
        return True
    if _scan_arith_or_cmdsub(line, position, '((', 2):
        return True
    if _inside_param_expansion(line, position):
        return True

    # Backtick command substitution
    backtick_start = -1
    i = 0
    while i < len(line):
        if line[i] == '`':
            if backtick_start == -1:
                if i <= position:
                    backtick_start = i
            else:
                if backtick_start <= position <= i:
                    return True
                backtick_start = -1
        i += 1
    return False


def _quote_flags(line: str, quote):
    """Per-character "protected" flags for `line`, starting in `quote` state.

    Returns (flags, final_quote). A char is flagged True when it is shielded
    from TOP-LEVEL comment/heredoc recognition: inside single/double quotes,
    or inside an unquoted ``` `...` ``` backtick command substitution.

    Backtick interiors are flagged but do NOT contribute to the returned
    quote state. Unlike ``$(...)`` — where bash re-parses the body as a
    command list, so a ``#`` there starts a comment and a trailing backslash
    is a continuation — a backtick word is raw-scanned: bash splices
    backslash-newline and never treats ``#`` or ``'`` specially while looking
    for the closing backtick (comment/quote handling inside the body is the
    lexer's job AFTER the splice). So a backtick interior must never suppress
    a continuation join or open a command-level quote. (A backtick inside
    double quotes needs no special handling: the double-quote path already
    joins and shields ``#``.) The carried quote state lets the caller track
    strings that span multiple command lines.
    """
    flags = []
    backtick = False  # inside an unquoted `...` command substitution
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == '\\' and quote != "'" and i + 1 < n:
            inside = quote is not None or backtick
            flags.append(inside)
            flags.append(inside)
            i += 2
            continue
        if backtick:
            flags.append(True)
            if c == '`':  # only an unescaped ` closes the backtick word
                backtick = False
        elif quote:
            flags.append(True)
            if c == quote:
                quote = None
        elif c == '`':
            backtick = True
            flags.append(True)
        elif c in ('"', "'"):
            quote = c
            flags.append(True)
        else:
            flags.append(False)
        i += 1
    return flags, quote


def _comment_start(line: str, flags) -> int:
    """Position where a comment starts on *line*, or ``len(line)`` if none.

    Uses the lexer's shared comment-start predicate on the first unquoted
    ``#`` (*flags* are the per-char in-quote flags from ``_quote_flags``).
    One raw-text refinement: the ``#`` of ``${#...}`` is rejected here —
    the lexer never consults the predicate there because the expansion
    parser consumes ``${...}`` whole.
    """
    from ..lexer.recognizers.comment import is_comment_start
    for pos, char in enumerate(line):
        if char != '#' or (pos < len(flags) and flags[pos]):
            continue
        if pos >= 2 and line[pos - 1] == '{' and line[pos - 2] == '$':
            continue
        if is_comment_start(line, pos):
            return pos
    return len(line)


def scan_line_heredoc_markers(line: str, quote=None):
    """The heredocs one COMMAND line opens, in order, with the carried
    quote state.

    Returns ``(markers, quote_after)`` where each marker is a
    ``(delimiter, strip_tabs, quoted)`` triple — ``quoted`` True when any
    part of the raw delimiter is quoted or escaped (the body is then
    literal, like bash) — and ``quote_after`` is the quote state at end
    of line for multi-line strings. Markers inside quotes, expansions, or
    a comment are not heredocs; comment text is also excluded from the
    carried quote state (an apostrophe in ``# don't`` is not a quote).
    """
    flags, _ = _quote_flags(line, quote)
    comment_at = _comment_start(line, flags)
    _, quote_after = _quote_flags(line[:comment_at], quote)
    markers = []
    for match in HEREDOC_MARKER_RE.finditer(line, 0, comment_at):
        if is_inside_expansion(line, match.start()):
            continue
        if match.start() < len(flags) and flags[match.start()]:
            continue  # quoted "<<WORD" is not a heredoc
        raw = match.group(2)
        markers.append((heredoc_delimiter_word(match), bool(match.group(1)),
                        any(c in raw for c in '\'"\\')))
    return markers, quote_after


def eol_backslash_is_literal(line: str, quote=None) -> bool:
    """True when a backslash ending command line *line* is literal text —
    single-quoted or comment content — rather than a line continuation.
    *quote* is the carried-in quote state (see ``_quote_flags``). A ``'`` or
    ``#`` inside an unquoted backtick does NOT count (bash splices
    backslash-newline while scanning a backtick regardless), so such a
    trailing backslash is still a continuation. The line-continuation
    preprocessing consults this before joining."""
    flags, quote_after = _quote_flags(line, quote)
    return quote_after == "'" or _comment_start(line, flags) < len(line)


def has_unclosed_heredoc(command: str) -> bool:
    """True if *command* opens a heredoc whose delimiter has not yet appeared.

    Ignores ``<<`` that is bit-shift (arithmetic) or a ``<<<`` here-string, and
    ``<<`` inside command substitutions/backticks. Used to decide whether more
    input lines are still needed to complete the command.
    """
    return bool(open_heredoc_delimiters(command))


def open_heredoc_delimiters(command: str) -> list:
    """The heredocs *command* opens but never closes, in order, as
    ``(delimiter, strip_tabs)`` pairs.

    Empty list means every heredoc (if any) already has its body. The same
    scan backs ``has_unclosed_heredoc``; the CommandAccumulator seeds its
    incremental body tracking from this (checking each subsequent line
    against the pending delimiters, without re-scanning the whole buffer).
    """
    # Fast path / arithmetic-only exclusion: if every '<<' is bit-shift inside
    # arithmetic, there is no heredoc at all.
    if not contains_heredoc(command):
        return []

    delimiters: list[dict[str, object]] = []
    quote_state = None  # quote carried across COMMAND lines (multi-line strings)
    for line in command.split('\n'):
        if any(not d['closed'] for d in delimiters):
            # Inside an open heredoc: does this line close one?
            for d in delimiters:
                if not d['closed']:
                    # Exact match (bash); only <<- strips leading tabs. A line
                    # with trailing whitespace is body, not the terminator.
                    check = line.lstrip('\t') if d['strip_tabs'] else line
                    if check == d['word']:
                        d['closed'] = True
                        break
        else:
            markers, quote_state = scan_line_heredoc_markers(line, quote_state)
            for word, strip_tabs, _quoted in markers:
                delimiters.append({
                    'word': word,
                    'strip_tabs': strip_tabs,
                    'closed': False,
                })
    return [(d['word'], d['strip_tabs']) for d in delimiters if not d['closed']]


def contains_heredoc(command_string: str) -> bool:
    """Check if command contains heredoc operators (not bit-shift in arithmetic).

    Returns True if the command contains << that's likely a heredoc,
    False if << only appears inside arithmetic expressions.
    """
    if '<<' not in command_string:
        return False

    # Quick check: if we have arithmetic expressions, check if << is inside them
    # This is a simple heuristic that handles the common case
    if '((' in command_string:
        # Find all arithmetic expression boundaries
        arith_start = []
        arith_end = []
        i = 0
        while i < len(command_string) - 1:
            if command_string[i:i+2] == '((':
                arith_start.append(i)
                i += 2
            elif command_string[i:i+2] == '))':
                arith_end.append(i + 2)
                i += 2
            else:
                i += 1

        # Find all << positions
        heredoc_positions = []
        i = 0
        while i < len(command_string) - 1:
            if command_string[i:i+2] == '<<':
                heredoc_positions.append(i)
                i += 2
            else:
                i += 1

        # Check if all << are inside arithmetic expressions
        if heredoc_positions and arith_start and arith_end:
            all_inside_arithmetic = True
            for pos in heredoc_positions:
                inside = False
                # Check if this << is inside any arithmetic expression
                for j in range(min(len(arith_start), len(arith_end))):
                    if arith_start[j] < pos < arith_end[j]:
                        inside = True
                        break
                if not inside:
                    all_inside_arithmetic = False
                    break

            # If all << are inside arithmetic expressions, no heredoc
            if all_inside_arithmetic:
                return False

    # Default: assume << is a heredoc
    return True
