"""Heredoc detection heuristics and the canonical heredoc types.

Distinguishes a real ``<<EOF`` heredoc from a ``<<`` bit-shift (arithmetic) or
a ``<<<`` here-string, and tracks whether a heredoc's delimiter has appeared
yet. This is the single source of truth for heredoc line-gathering, consumed
by the shared completeness oracle (`scripting/command_accumulator.py`) that
both the script/`-c`/stdin path and the interactive multiline path drive.

This module also owns the campaign-S2 heredoc transaction contracts:

* :class:`HeredocSpec` — one heredoc's delimiter facts (raw spelling, literal
  terminator, quote/tab policy, source span) with ORDINAL identity: duplicate
  textual delimiters are distinct specs. The sole constructor is
  :func:`make_heredoc_spec`; ``cooked``/``quoted`` are only ever derived
  through :func:`unquote_heredoc_delimiter`.
* :class:`CollectedHeredoc` — one heredoc's gathered body plus its typed
  :class:`HeredocTermination` (terminator line seen, or delimited by EOF).
* :class:`PendingHeredocQueue` — THE head-of-queue close policy. Bash reads
  heredoc bodies strictly in source order, so an input line is only ever
  compared with the FIRST open heredoc (a line equal to a LATER pending
  delimiter is plain body text — reappraisal #20 H1 / #21 G1). Every layer
  that tracks open bodies (the lexer's HeredocCollector, the completeness
  oracle here (:func:`open_heredoc_specs`) and in the CommandAccumulator,
  and the line-continuation preprocessor) delegates its close decision to
  :meth:`PendingHeredocQueue.feed_line` — the ONE production caller of
  :func:`heredoc_terminator_matches` (guarded by
  ``tests/unit/tooling/test_heredoc_transaction_guards.py``).
"""

import enum
import re
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

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
# The delimiter word is a sequence of UNITS. Beyond bare characters, the
# unit alternatives (tried in order) consume as one piece:
#   * ``\X``            — an escaped character;
#   * ``$'...'``        — an ANSI-C quoted piece (its own ``\X`` pairs kept
#                         whole so ``$'E\'F'`` scans to the real closing
#                         quote — bash decodes the escapes; see the ANSI-C
#                         arm of unquote_heredoc_delimiter);
#   * ``$"..."``        — a locale-quoted piece (double-quote rules);
#   * ``"..."``         — a double-quoted piece, ``\X`` pairs kept whole so
#                         ``"E\"F"`` scans to the real closing quote;
#   * ``'...'``         — a single-quoted piece (verbatim, no escapes);
#   * ``<(...)``/``>(...)`` — a process-substitution-SHAPED piece taken as
#                         literal delimiter text (``cat << <(x)`` terminates
#                         at the line ``<(x)`` — bash 5.2). The extent runs
#                         to the FIRST ``)``: bash does not nest parens here
#                         (``<< <(a(b)c)`` is a bash syntax error), and the
#                         token-level scanner applies the same no-nesting
#                         rule so the two layers agree.
# Call unquote_heredoc_delimiter(group(2)) for the literal terminator text.
# That is THE delimiter-word rule; every layer that recovers a heredoc
# terminator (this scanner, the lexer's HeredocCollector registration, the
# $(...) extent scanner's _read_heredoc_delimiter) routes through it — via
# make_heredoc_spec — so they cannot drift.
_DELIM_UNIT = (r'\\.'
               r"|\$'(?:\\.|[^'\\])*'"
               r'|\$"(?:\\.|[^"\\])*"'
               r'|"(?:\\.|[^"\\])*"'
               r"|'[^']*'"
               r'|[<>]\([^()]*\)')
HEREDOC_MARKER_RE = re.compile(
    r'(?<!<)<<(?!<)(-?)[ \t]*'
    r'((?:' + _DELIM_UNIT + r'|[^ \t\n\r"\'\\|&;()<>#])'
    r'(?:' + _DELIM_UNIT + r'|[^ \t\n\r"\'\\|&;()<>])*)')


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
        (``"A\\B"``->``A\\B`` — the case the retired copies got wrong);
      * ANSI-C ``$'...'``: contents with the escape sequences DECODED
        (``$'EOF'``->``EOF``, ``$'E\\tF'``->``E<TAB>F``, ``$'E\\'F'``->``E'F``)
        via the lexer's one ANSI-C escape decoder;
      * locale ``$\"...\"``: double-quote rules (the translation is the
        identity — ``$\"EOF\"``->``EOF``).
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
        elif c == '"' or (c == '$' and i + 1 < n and raw[i + 1] == '"'):
            quoted = True
            i += 2 if c == '$' else 1  # skip $" or "
            while i < n and raw[i] != '"':
                if (raw[i] == '\\' and i + 1 < n
                        and raw[i + 1] in '$`"\\'):
                    literal.append(raw[i + 1])
                    i += 2
                else:
                    literal.append(raw[i])
                    i += 1
            i += 1  # skip the closing quote
        elif c == '$' and i + 1 < n and raw[i + 1] == "'":
            # ANSI-C $'...': decode escapes with the ONE escape machinery.
            # cycle-break: utils.heredoc_detection is module-level-imported
            # by lexer modules; importing psh.lexer back here at module
            # level would be a genuine import cycle.
            from ..lexer.pure_helpers import handle_ansi_c_escape
            quoted = True
            i += 2  # skip $'
            while i < n and raw[i] != "'":
                if raw[i] == '\\':
                    decoded, i = handle_ansi_c_escape(raw, i, "'")
                    literal.append(decoded)
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


# === The canonical heredoc transaction types (campaign S2) ===


class HeredocTermination(enum.Enum):
    """How a heredoc body ended: its terminator line, or end of input."""

    DELIMITER = 'delimiter'
    EOF = 'eof'


@dataclass(frozen=True)
class HeredocSpec:
    """One heredoc's delimiter facts, with ordinal identity.

    ``id`` is the heredoc's ORDINAL within one lexed unit / one scan, in
    source order — identity is positional, never textual, so duplicate
    delimiters (``cat <<A <<A``) are distinct specs. ``raw`` is the exact
    source spelling of the delimiter word (what the formatter re-emits);
    ``cooked`` is the literal terminator after the one quote-removal rule;
    ``quoted`` reports whether ANY part was quoted/escaped (the body is then
    literal, no expansion); ``strip_tabs`` is the ``<<-`` policy. ``span``
    is the (start, end) offset pair of ``raw`` within the text handed to the
    scanner that produced this spec (the heredoc-stripped command text for
    the token-level scanner; the scanned line for the text-level scanner).
    """

    id: int
    raw: str
    cooked: str
    quoted: bool
    strip_tabs: bool
    span: Tuple[int, int]


def make_heredoc_spec(ordinal: int, raw: str, strip_tabs: bool,
                      span: Tuple[int, int] = (0, 0)) -> HeredocSpec:
    """THE HeredocSpec constructor: derive ``cooked``/``quoted`` from ``raw``
    through :func:`unquote_heredoc_delimiter` (the one quote-removal rule).
    Both delimiter scanners (the token-level HeredocCollector registration and
    the text-level :func:`scan_line_heredoc_markers`) construct specs only
    through this function."""
    cooked, quoted = unquote_heredoc_delimiter(raw)
    return HeredocSpec(id=ordinal, raw=raw, cooked=cooked, quoted=quoted,
                       strip_tabs=strip_tabs, span=span)


@dataclass(frozen=True)
class CollectedHeredoc:
    """One heredoc's gathered body and how it terminated.

    ``spec_id`` references the :class:`HeredocSpec` this body belongs to.
    ``body`` is the complete body text (``<<-`` tab-stripping applied; final
    newline present when the body is non-empty). ``termination`` is the typed
    outcome — a trial parse suppresses the EOF *warning*, never the typed
    fact. ``span`` is the (first_line, last_line) pair (1-based, within the
    lexed source) of the gathered body; ``(line, line - 1)`` for an empty
    body starting at ``line``.
    """

    spec_id: int
    body: str
    termination: HeredocTermination
    span: Tuple[int, int]


class PendingHeredocQueue:
    """THE head-of-queue close policy for pending heredoc bodies.

    Bash consumes heredoc bodies strictly in source order: an input line can
    only terminate the FIRST open heredoc; a line equal to a later pending
    delimiter is body text of the head (H1/G1). This queue is the single
    place that decision is made — :meth:`feed_line` is the one production
    caller of :func:`heredoc_terminator_matches`.
    """

    def __init__(self) -> None:
        self._pending: Deque[HeredocSpec] = deque()
        self._pushed = 0

    def push(self, spec: HeredocSpec) -> None:
        """Append a newly opened heredoc (source order)."""
        self._pending.append(spec)
        self._pushed += 1

    @property
    def pushed(self) -> int:
        """How many heredocs were EVER pushed — the next free ordinal for a
        caller that keys spec identity to this queue's lifetime (the
        ``$(...)`` extent scanner shares one queue across nested scans)."""
        return self._pushed

    @property
    def head(self) -> Optional[HeredocSpec]:
        """The first open heredoc — the only one input can terminate."""
        return self._pending[0] if self._pending else None

    @property
    def specs(self) -> Tuple[HeredocSpec, ...]:
        """The still-open heredocs, in order."""
        return tuple(self._pending)

    def __bool__(self) -> bool:
        return bool(self._pending)

    def __len__(self) -> int:
        return len(self._pending)

    def drain(self) -> Tuple[HeredocSpec, ...]:
        """End of input: pop and return every still-open heredoc, in order.

        This is the EOF-termination path (no terminator line will come), not
        a close decision — the specs come back so the caller can finalize
        them as ``HeredocTermination.EOF``.
        """
        remaining = tuple(self._pending)
        self._pending.clear()
        return remaining

    def feed_line(self, line: str) -> Optional[HeredocSpec]:
        """The close decision: does *line* terminate the HEAD heredoc?

        Compares *line* ONLY with the head's delimiter (exact match; ``<<-``
        strips leading tabs — the head's own policy). On a match the head is
        popped and returned (the line was its terminator); otherwise returns
        None (the line is body text of the head). Never consults any later
        pending delimiter.
        """
        if not self._pending:
            return None
        head = self._pending[0]
        if heredoc_terminator_matches(line, head.cooked, head.strip_tabs):
            return self._pending.popleft()
        return None


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


def scan_line_heredoc_markers(line: str, quote=None, first_ordinal: int = 0):
    """The heredocs one COMMAND line opens, in order, with the carried
    quote state.

    This is the TEXT-level delimiter scanner: it returns
    ``(specs, quote_after)`` where each spec is a :class:`HeredocSpec`
    (constructed only through :func:`make_heredoc_spec`, ids assigned
    sequentially from ``first_ordinal``, spans line-relative) and
    ``quote_after`` is the quote state at end of line for multi-line
    strings. Markers inside quotes, expansions, or a comment are not
    heredocs; comment text is also excluded from the carried quote state
    (an apostrophe in ``# don't`` is not a quote).
    """
    flags, quote_after = _quote_flags(line, quote)
    comment_at = _comment_start(line, flags)
    if comment_at < len(line):
        # A comment: recompute the carried quote state up to it so comment
        # text (e.g. an apostrophe in `# don't`) is excluded. With no comment
        # the full-line scan above already gives quote_after (runs once).
        _, quote_after = _quote_flags(line[:comment_at], quote)
    specs: List[HeredocSpec] = []
    for match in HEREDOC_MARKER_RE.finditer(line, 0, comment_at):
        # `flags` (computed once) makes both the quoted-`<<` check and the
        # quote-aware expansion scan share one pass — a quoted `((`/`$(`/backtick
        # cannot open a region and swallow this marker (H2).
        if is_inside_expansion(line, match.start(), flags):
            continue
        if match.start() < len(flags) and flags[match.start()]:
            continue  # quoted "<<WORD" is not a heredoc
        specs.append(make_heredoc_spec(
            ordinal=first_ordinal + len(specs),
            raw=match.group(2),
            strip_tabs=bool(match.group(1)),
            span=(match.start(2), match.end(2))))
    return specs, quote_after


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
    return bool(open_heredoc_specs(command))


def open_heredoc_specs(command: str) -> "Tuple[HeredocSpec, ...]":
    """The heredocs *command* opens but never closes, in source order.

    Empty means every heredoc (if any) already has its body. This is the
    completeness oracle's scan: the CommandAccumulator seeds its incremental
    :class:`PendingHeredocQueue` from it (checking each subsequent line
    against the queue HEAD, without re-scanning the whole buffer). Body/
    terminator routing delegates to the queue's head-of-queue policy — a
    line equal to a LATER pending delimiter is body text (H1/G1).
    """
    # Cheap gate: no '<<' anywhere means no heredoc. Everything else (quotes,
    # arithmetic '<<', backticks) is decided accurately below, per line.
    if not contains_heredoc(command):
        return ()

    queue = PendingHeredocQueue()
    ordinal = 0
    quote_state = None  # quote carried across COMMAND lines (multi-line strings)
    for line in command.split('\n'):
        if queue:
            # Inside open heredoc bodies: the line either terminates the
            # HEAD or is its body text — never command text either way.
            queue.feed_line(line)
        else:
            specs, quote_state = scan_line_heredoc_markers(
                line, quote_state, ordinal)
            ordinal += len(specs)
            for spec in specs:
                queue.push(spec)
    return queue.specs


def contains_heredoc(command_string: str) -> bool:
    """A cheap OVER-APPROXIMATION: does the command contain a ``<<`` at all?

    This is only a gate that decides whether to run the accurate, quote- and
    grammar-aware scanner (``open_heredoc_specs`` /
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
