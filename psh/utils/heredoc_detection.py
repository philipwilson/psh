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
#   group(2): the RAW delimiter — one shell WORD (quotes/escapes still
#             present). Bash accepts almost ANY non-blank run as the
#             delimiter (``E*F``, ``A?B``, ``AB[cd]``, ``E.F``, ``E-F``,
#             ``@X``, ``{abc}``, ``!``, digits, ``$`` taken LITERALLY —
#             verified against bash 5.2), so the character class is
#             NEGATED: the word ends at blanks (space/tab), the line
#             terminators newline/CR (a CRLF line's trailing CR is line
#             ending, not delimiter text), the shell metacharacters
#             ``| & ; ( ) < >``, and quote/escape characters (which the
#             leading alternatives consume as units). One extra rule: a
#             ``#`` cannot START the word — after the ``<<`` operator it
#             begins a comment (``cat << #foo`` and ``cat <<#foo`` are both
#             syntax errors in bash) — but is an ordinary character
#             mid-word (``<<E#F``).
# Call unquote_heredoc_delimiter(group(2)) for the literal terminator text.
# That is THE delimiter-word rule; every layer that recovers a heredoc
# terminator (this scanner, HeredocLexer._delimiter_from_source, the $(...)
# extent scanner's _read_heredoc_delimiter) routes through it so they cannot
# drift. (The parser computes body-is-quoted from token TYPES instead, keyed
# by heredoc_key — a separate, token-level concern.)
HEREDOC_MARKER_RE = re.compile(
    r'(?<!<)<<(?!<)(-?)[ \t]*'
    r'((?:\\.|"[^"]*"|\'[^\']*\'|[^ \t\n\r"\'\\|&;()<>#])'
    r'(?:\\.|"[^"]*"|\'[^\']*\'|[^ \t\n\r"\'\\|&;()<>])*)')


def unquote_heredoc_delimiter(raw: str) -> tuple[str, bool]:
    """Remove one level of quoting from a raw heredoc delimiter WORD.

    Returns ``(literal_terminator, quoted)``. The body terminator line must
    equal ``literal_terminator`` EXACTLY (see ``heredoc_terminator_matches``,
    the body-side twin of this rule). ANY quote or backslash anywhere in the
    delimiter makes the body literal — no expansion — which is what ``quoted``
    reports; an unquoted ``$`` is an ordinary terminator character
    (``<<E$X`` terminates at ``E$X`` and the body still expands).

    This is THE delimiter-word rule. It replaces three drifted copies (the M2
    finding): the copies disagreed on backslash-inside-double-quotes, and bash
    sided against two of them. Do not fork it.

    Bash 5.2 rules (pinned by ``TestUnquoteHeredocDelimiter`` in
    tests/unit/utils/test_heredoc_detection.py and the
    ``heredoc_delimiter_*`` goldens in tests/behavioral/golden_cases.yaml):
      * unquoted ``\\X`` -> ``X`` for ANY X (``\\EOF``->``EOF``,
        ``EO\\ F``->``EO F``);
      * single quotes: contents VERBATIM (``'A\\B'``->``A\\B``);
      * double quotes: backslash escapes ONLY the double-quote specials
        ``$``, `` ` ``, ``"``, ``\\`` (``"A\\"B"``->``A"B``, ``"A\\\\B"``->``A\\B``,
        ``"A\\$B"``->``A$B``) and is LITERAL before anything else
        (``"A\\B"``->``A\\B`` — the case the retired copies got wrong).
    """
    literal: list[str] = []
    quoted = False
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == '\\' and i + 1 < n:
            quoted = True
            literal.append(raw[i + 1])
            i += 2
        elif c == "'":
            quoted = True
            i += 1
            while i < n and raw[i] != "'":
                literal.append(raw[i])
                i += 1
            i += 1  # skip the closing quote
        elif c == '"':
            quoted = True
            i += 1
            while i < n and raw[i] != '"':
                if (raw[i] == '\\' and i + 1 < n
                        and raw[i + 1] in '$`"\\'):
                    literal.append(raw[i + 1])
                    i += 2
                else:
                    literal.append(raw[i])
                    i += 1
            i += 1  # skip the closing quote
        else:
            literal.append(c)
            i += 1
    return ''.join(literal), quoted


def heredoc_terminator_matches(line: str, delimiter: str, strip_tabs: bool) -> bool:
    """True when physical *line* terminates a heredoc with *delimiter*.

    This is the ONE terminator rule shared by every layer that gathers heredoc
    bodies (the completeness oracle, the line-continuation preprocessor, the
    lexer's body collector, and the ``$(...)`` extent scanner) so they never
    disagree about where a body ends.

    Bash requires the terminator to equal the delimiter EXACTLY — only ``<<-``
    strips leading tabs, and a line with trailing whitespace (``EOF ``) is body,
    not the terminator. The one concession is a CRLF line ending: bash keeps the
    raw CR as an ordinary byte, so its delimiter word captured from ``<<EOF\\r``
    is ``EOF\\r`` and a terminator line ``EOF\\r`` matches. psh instead strips
    the line-ending CR at the line-reading layer (FileInput per physical line;
    HeredocLexer's line splitter), so its delimiter word is ``EOF`` — but lines
    that reach this rule WITHOUT passing those layers (a ``-c`` string with
    embedded CRLF, fed line-by-line to the completeness oracle) still carry the
    CR. Dropping the single line-ending CR before the exact compare reproduces
    bash's "CRLF heredoc terminates" behavior everywhere while still treating
    trailing spaces/tabs as body (they are NOT stripped).
    """
    check = line.lstrip('\t') if strip_tabs else line
    if check.endswith('\r'):
        check = check[:-1]
    return check == delimiter


def _scan_arith_or_cmdsub(line: str, position: int, opener: str, open_len: int,
                          flags: list) -> bool:
    """True if *position* falls within a ``opener … )`` region on *line*.

    ``opener`` is ``'$(('`` / ``'(('``; ``open_len`` is how many parens it
    contributes to the nesting depth (2 for the arithmetic forms). *flags* are
    the per-char in-quote flags from ``_quote_flags`` — a QUOTED ``opener`` (or
    a quoted paren) is text, so it can neither open a region nor change its
    depth (H2: ``echo '((' ; cat <<EOF`` must not read the ``<<`` as a shift).
    """
    start = -1
    depth = 0
    i = 0
    n = len(line)
    while i < n:
        if i < len(flags) and flags[i]:
            i += 1  # quoted char: not an opener, and does not affect depth
            continue
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


def _inside_closed_cmdsub(line: str, position: int, flags: list) -> bool:
    """True if *position* falls within a ``$( … )`` region that CLOSES on
    *line*, using the grammar-aware extent scanner (so a case pattern's bare
    ``)`` inside the substitution does not end the region early). An
    unclosed ``$(`` returns False: a ``<<`` inside it is then treated as a
    pending heredoc so the line gatherer keeps reading — matching how the
    full lexer will see it once the substitution is complete. A QUOTED ``$(``
    (*flags*) is text, not a substitution opener.
    """
    from ..lexer.cmdsub_scanner import find_command_substitution_end
    i = 0
    n = len(line)
    while i < n and i <= position:
        if i < len(flags) and flags[i]:
            i += 1  # quoted char: not a substitution opener
            continue
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


def _inside_param_expansion(line: str, position: int, flags: list) -> bool:
    """True if *position* is inside a ``${…}`` parameter expansion (where a
    ``<<`` is an arithmetic left-shift in a subscript, e.g. ``${arr[1<<1]}``,
    not a heredoc). Tracks brace nesting (``${a${b}}``). An unclosed ``${``
    returns False so the line gatherer keeps reading, mirroring the cmdsub case.
    A QUOTED ``${`` (*flags*) is text, not an expansion opener.
    """
    i, n = 0, len(line)
    while i < n and i <= position:
        if i < len(flags) and flags[i]:
            i += 1  # quoted char: not an expansion opener
            continue
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


def is_inside_expansion(line: str, position: int,
                        flags: "list | None" = None) -> bool:
    """True if *position* on *line* is inside an expansion where ``<<`` is not
    a heredoc: ``$((…))`` / bare ``((…))`` arithmetic, ``$(…)`` command
    substitution, ``${…}`` parameter expansion, or ``` `…` ``` backticks.

    *flags* are the per-char in-quote flags from ``_quote_flags`` (computed
    here when omitted). Quote-awareness is the H2 fix: a QUOTED opener
    (``'(('``, ``"$("``, a quoted backtick) is ordinary text and can never open
    a region — so a following bare ``<<WORD`` is still recognised as a heredoc.
    """
    if flags is None:
        flags, _ = _quote_flags(line, None)
    if _scan_arith_or_cmdsub(line, position, '$((', 2, flags):
        return True
    if _inside_closed_cmdsub(line, position, flags):
        return True
    if _scan_arith_or_cmdsub(line, position, '((', 2, flags):
        return True
    if _inside_param_expansion(line, position, flags):
        return True

    # Backtick command substitution. This stays quote-BLIND: `_quote_flags`
    # marks a bare `...` interior as protected too, so a flags-guard here would
    # hide real backtick regions. A `<<` inside a QUOTED backtick is already
    # dropped by the `flags[match.start()]` guard in scan_line_heredoc_markers.
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
    flags, quote_after = _quote_flags(line, quote)
    comment_at = _comment_start(line, flags)
    if comment_at < len(line):
        # A comment: recompute the carried quote state up to it so comment
        # text (e.g. an apostrophe in `# don't`) is excluded. With no comment
        # the full-line scan above already gives quote_after (runs once).
        _, quote_after = _quote_flags(line[:comment_at], quote)
    markers = []
    for match in HEREDOC_MARKER_RE.finditer(line, 0, comment_at):
        # `flags` (computed once) makes both the quoted-`<<` check and the
        # quote-aware expansion scan share one pass — a quoted `((`/`$(`/backtick
        # cannot open a region and swallow this marker (H2).
        if is_inside_expansion(line, match.start(), flags):
            continue
        if match.start() < len(flags) and flags[match.start()]:
            continue  # quoted "<<WORD" is not a heredoc
        literal, quoted = unquote_heredoc_delimiter(match.group(2))
        markers.append((literal, bool(match.group(1)), quoted))
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
    # Cheap gate: no '<<' anywhere means no heredoc. Everything else (quotes,
    # arithmetic '<<', backticks) is decided accurately below, per line.
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
                    # with trailing whitespace is body, not the terminator — but
                    # a CRLF line-ending CR is dropped (see the shared rule).
                    if heredoc_terminator_matches(
                            line, str(d['word']), bool(d['strip_tabs'])):
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
    """A cheap OVER-APPROXIMATION: does the command contain a ``<<`` at all?

    This is only a gate that decides whether to run the accurate, quote- and
    grammar-aware scanner (``open_heredoc_delimiters`` /
    ``scan_line_heredoc_markers``) — never the final answer. It must NEVER
    return False for a real heredoc, so it deliberately does no arithmetic /
    quote analysis here: a false True just runs the accurate path (which
    returns no markers for ``echo $((1<<2))`` or ``echo '<<EOF'``); a false
    False would silently drop a heredoc.

    The previous version tried to exclude arithmetic ``<<`` by pairing ``((``
    with ``))`` by index, quote-blind — so ``echo '((' ; cat <<EOF … echo '))'``
    (quoted parens flanking a real heredoc) wrongly short-circuited to False and
    the body ran as commands (H2). Deferring the decision to the accurate path
    removes that whole class of bug.
    """
    return '<<' in command_string
