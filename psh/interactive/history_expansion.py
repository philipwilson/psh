"""History expansion implementation for PSH.

This module implements bash-compatible history expansion, processing history
references like !!, !n, !-n, and !string before commands are tokenized.

The public entry point :meth:`HistoryExpander.expand_history` returns a typed
:class:`HistoryExpansionResult` (campaign I4): the four distinct outcomes
(NONE / EXPANDED / PRINT_ONLY / ERROR) are the ``kind`` field, not overloaded
sentinels or a regex. The producer is PURE — it never prints and never records;
consumers echo/print/record from the result.
"""

from typing import List, Tuple, Union

from ..utils.heredoc_detection import (
    HEREDOC_MARKER_RE,
    HeredocSpec,
    PendingHeredocQueue,
    _comment_start,
    contains_heredoc,
    is_inside_expansion,
    make_heredoc_spec,
)
from .history_result import (
    HistoryExpansionKind,
    HistoryExpansionResult,
    HistoryExpansionSpan,
)

# A context frame for _context_flags: "'" / '"' for quote spans, or a mutable
# ['cs', paren_depth] list for a $( … ) command substitution reopened INSIDE
# double quotes (the one construct the shared _quote_flags is blind to).
_CtxFrame = Union[str, List]


def _shell_single_quote(text: str) -> str:
    """Quote *text* as a single shell word (``:q`` / ``:x`` modifiers).

    Wrap in single quotes, rendering an embedded ``'`` as ``'\\''`` — the
    bash-faithful escaping the history ``:q`` modifier produces (``echo a'b'c``
    -> ``'echo a'\\''b'\\''c'``)."""
    return "'" + text.replace("'", "'\\''") + "'"


def _context_flags(line: str, stack: List[_CtxFrame]):
    """Per-char suppressed flags for *line* plus the carried context stack.

    A local variant of ``heredoc_detection._quote_flags`` with ONE delta: a
    ``$(`` opened INSIDE double quotes pushes an effectively-UNQUOTED command-
    substitution frame (bash re-parses the substitution body as a fresh command
    context), popping back to the double quote on its balancing ``)`` — so a
    heredoc opener inside ``"$( … "`` is detected where the shared scanner's
    flat quote flags see only "quoted". ``$((`` inside quotes stays suppressed
    (arithmetic — its ``<<`` is a shift). Everything else mirrors the shared
    conventions: backslash pairs, per-line backtick interiors (flagged but not
    carried), quote chars flagged True. The shared oracle itself is untouched
    (S2 fence); this feeds only the history-expansion span scan below.

    *stack* frames: ``"'"``/``'"'`` quote spans (carried across command lines
    for multi-line strings) and ``['cs', depth]`` command-substitution frames.
    Returns ``(flags, stack_after)``; the input stack is not mutated.
    """
    stack = [f.copy() if isinstance(f, list) else f for f in stack]
    flags: List[bool] = []
    backtick = False  # per-line, like the shared _quote_flags
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        top = stack[-1] if stack else None
        quote = top if isinstance(top, str) else None
        if c == '\\' and quote != "'" and i + 1 < n:
            inside = quote is not None or backtick
            flags.append(inside)
            flags.append(inside)
            i += 2
            continue
        if backtick:
            flags.append(True)
            if c == '`':
                backtick = False
            i += 1
            continue
        if quote == "'":
            flags.append(True)
            if c == "'":
                stack.pop()
            i += 1
            continue
        if quote == '"':
            # THE delta: $( (but not $(( arithmetic) reopens command context.
            if (c == '$' and i + 1 < n and line[i + 1] == '('
                    and line[i + 2:i + 3] != '('):
                flags.append(False)
                flags.append(False)
                stack.append(['cs', 0])
                i += 2
                continue
            flags.append(True)
            if c == '"':
                stack.pop()
            i += 1
            continue
        # Top level or inside a $( … ) frame: effectively unquoted.
        if c == '`':
            backtick = True
            flags.append(True)
        elif c in ('"', "'"):
            stack.append(c)
            flags.append(True)
        elif (c == '$' and i + 1 < n and line[i + 1] == '('
                and line[i + 2:i + 3] != '('):
            flags.append(False)
            flags.append(False)
            stack.append(['cs', 0])
            i += 2
            continue
        else:
            flags.append(False)
            if isinstance(top, list):
                if c == '(':
                    top[1] += 1
                elif c == ')':
                    if top[1] == 0:
                        stack.pop()
                    else:
                        top[1] -= 1
        i += 1
    return flags, stack


def _scan_line_markers_ctx(line: str, stack: List[_CtxFrame],
                           first_ordinal: int):
    """The heredocs one command line opens, with dq-cmdsub-aware context.

    Mirrors ``heredoc_detection.scan_line_heredoc_markers`` (comment exclusion,
    quoted-marker exclusion, ``is_inside_expansion`` for closed cmdsub/arith/
    param regions) but computes flags with :func:`_context_flags` so a marker
    inside a ``"$( …`` reopened context is live. Returns ``(specs, stack_after)``.
    """
    flags, stack_after = _context_flags(line, stack)
    comment_at = _comment_start(line, flags)
    if comment_at < len(line):
        # Recompute the carried context up to the comment so comment text
        # (e.g. an apostrophe in `# don't`) is excluded (shared convention).
        _, stack_after = _context_flags(line[:comment_at], stack)
    specs: List[HeredocSpec] = []
    for match in HEREDOC_MARKER_RE.finditer(line, 0, comment_at):
        if is_inside_expansion(line, match.start(), flags):
            continue
        if match.start() < len(flags) and flags[match.start()]:
            continue  # quoted "<<WORD" is not a heredoc
        specs.append(make_heredoc_spec(
            ordinal=first_ordinal + len(specs),
            raw=match.group(2),
            strip_tabs=bool(match.group(1)),
            span=(match.start(2), match.end(2))))
    return specs, stack_after


def heredoc_body_spans(command: str) -> List[Tuple[int, int]]:
    """The ``[start, end)`` char spans of *command* that are heredoc BODY text.

    bash never history-expands heredoc body lines (they are passed to the
    command verbatim). psh joins the whole logical command — opener plus body —
    into one string before expanding, so the flat scanner would otherwise
    expand a ``!!`` sitting in a heredoc body. This walks the command line by
    line with the completeness oracle's close policy
    (:class:`PendingHeredocQueue`) and a context-aware opener scan
    (:func:`_scan_line_markers_ctx` — the shared scanner plus the
    ``$(``-inside-double-quotes reopen bash performs, which the flat quote
    flags are blind to): while a heredoc is open, each line is
    body/terminator text — never command text — so its char range is marked
    suppressed. Non-overlapping, source-ordered.
    """
    if not contains_heredoc(command):
        return []
    spans: List[Tuple[int, int]] = []
    queue = PendingHeredocQueue()
    ordinal = 0
    ctx_stack: List[_CtxFrame] = []  # quote/cmdsub context across command lines
    pos = 0
    for line in command.split('\n'):
        line_start = pos
        line_end = pos + len(line)  # excludes the '\n'
        if queue:
            # Inside open heredoc bodies: the line either terminates the HEAD or
            # is its body text — never command text, never history-expanded.
            spans.append((line_start, line_end))
            queue.feed_line(line)
        else:
            specs, ctx_stack = _scan_line_markers_ctx(line, ctx_stack, ordinal)
            ordinal += len(specs)
            for spec in specs:
                queue.push(spec)
        pos = line_end + 1  # skip the '\n'
    return spans


# Sentinels used by the event/word-designator resolvers below to distinguish
# "no such event" and "malformed word designator" from a normal string result.
_EVENT_NOT_FOUND = object()
_BAD_WORD_SPECIFIER = object()
# A :s/old/new/ (or :&) modifier that parsed correctly but whose `old` was not
# present in the selected line: bash reports this as "substitution failed", a
# distinct error class from a malformed/out-of-range "bad word specifier".
_SUBSTITUTION_FAILED = object()
_NOT_QUICK_SUB = object()  # leading text is not a ^old^new quick substitution


class _SuppressionContext:
    """Forward tracker for the three contexts that suppress a history ``!``.

    The original scanner answered "is this ``!`` inside ``[...]`` / ``${...}`` /
    ``$((...))``?" with three per-``!`` *backward* rescans over the raw prefix
    (an O(n) rewind at every ``!``). This tracks the same three depths
    incrementally in a single forward pass. ``feed`` is called for every
    consumed character, in order — including characters inside quotes and after
    a backslash, because the backward scans read the raw prefix regardless of
    quoting and the refactor must reproduce that (quote-blind) behavior byte for
    byte. ``suppressed`` reports whether the character position just reached
    lies inside any of the three constructs.

    Openers/closers match the original scans exactly: ``[`` / ``]`` for
    brackets; ``${`` (a ``{`` immediately preceded by ``$``) opens a brace and
    a bare ``{`` does not, while any ``}`` closes one; ``$((`` opens arithmetic
    and ``))`` closes it, both consumed as non-overlapping pairs. Closers floor
    at zero (a stray ``]`` / ``}`` / ``))`` with no open construct is inert),
    which is the forward equivalent of the backward scans' "nearest unmatched
    opener to the left" search.
    """

    __slots__ = ("bracket", "brace", "arith", "_skip_pair")

    def __init__(self):
        self.bracket = 0
        self.brace = 0
        self.arith = 0
        # True when the previous fed character opened/closed a two-char
        # arithmetic token ($(( or )) ); its partner char is consumed here so
        # the pair is counted once (matching the backward scan's paired skip).
        self._skip_pair = False

    def suppressed(self) -> bool:
        """True if the last-fed position is inside [...], ${...} or $((...))."""
        return self.bracket > 0 or self.brace > 0 or self.arith > 0

    def feed(self, command: str, p: int) -> None:
        """Advance the depths past ``command[p]``."""
        if self._skip_pair:
            self._skip_pair = False
            return
        c = command[p]
        if c == '[':
            self.bracket += 1
        elif c == ']':
            if self.bracket > 0:
                self.bracket -= 1
        elif c == '{':
            if p > 0 and command[p - 1] == '$':
                self.brace += 1
        elif c == '}':
            if self.brace > 0:
                self.brace -= 1
        elif c == '(':
            # '$((' arithmetic opener: this '(' follows '$' and precedes '('.
            if (p > 0 and command[p - 1] == '$'
                    and p + 1 < len(command) and command[p + 1] == '('):
                self.arith += 1
                self._skip_pair = True   # consume the paired second '('
        elif c == ')':
            # '))' arithmetic closer (paired, non-overlapping).
            if p + 1 < len(command) and command[p + 1] == ')':
                if self.arith > 0:
                    self.arith -= 1
                self._skip_pair = True   # consume the paired second ')'

    def feed_range(self, command: str, start: int, stop: int) -> None:
        """Advance the depths past ``command[start:stop]`` in order."""
        for p in range(start, stop):
            self.feed(command, p)


class HistoryExpander:
    """Handles history expansion for the shell."""

    def __init__(self, shell):
        self.shell = shell
        self.state = shell.state
        # Last :s/old/new/ substitution, for the :& (repeat) modifier.
        self._last_sub = None
        # Set by a :p modifier during one expand_history call: print, don't run.
        self._print_only = False

    def expand_history(self, command: str,
                       force: bool = False) -> HistoryExpansionResult:
        """Expand history references in *command*, returning a typed outcome.

        PURE: never prints, never records. The :class:`HistoryExpansionResult`
        ``kind`` is the authority (NONE / EXPANDED / PRINT_ONLY / ERROR); the
        reporting consumer echoes/prints/records from it and the silent
        completeness trial reads only ``kind``.

        ``force`` bypasses the ``histexpand`` option gate — the explicit
        ``history -p`` builtin expands regardless of ``set +H`` (bash).

        Supports:
        - !! : Previous command; !n / !-n : by number; !string / !?string? ;
          !# : the current line so far; ^old^new : quick substitution.
        - word designators (:0 :^ :$ :* :n-m) and modifiers
          (:h :t :r :e :s :gs :& :p :q :x).
        """
        # Skip expansion if history expansion is disabled: a NONE outcome whose
        # text is the input verbatim (bash still RECORDS such a line — a literal
        # `!!` with `set +H` is a recordable command, not a dropped reference).
        if not force and not self.state.options.get('histexpand', True):
            return HistoryExpansionResult(HistoryExpansionKind.NONE, command)

        # Get history from the shell
        history = self.state.history

        # ^old^new[^] quick substitution: only when it is the FIRST char of the
        # line (bash). Equivalent to !!:s/old/new/. Handled before the scanner.
        if command.startswith('^'):
            quick = self._expand_quick_substitution(command, history)
            if quick is not _NOT_QUICK_SUB:
                return quick

        # Per-call print-only flag (set by a :p modifier).
        self._print_only = False

        # Heredoc BODY spans: bash never history-expands heredoc body text, so
        # those char ranges are emitted verbatim (like a single-quoted span).
        body_spans = heredoc_body_spans(command)
        body_i = 0

        # Track whether any reference fired, and each resolved reference's span.
        expanded = False
        spans: List[HistoryExpansionSpan] = []
        result = []
        n = len(command)
        i = 0
        # Emit/quote state. History IS expanded inside double quotes (bash);
        # only single quotes and a preceding backslash suppress it. `in_squote`
        # consumes a single-quoted span verbatim; a ' inside "..." is literal
        # text (so it does not open a span).
        in_squote = False
        in_dquote = False
        # Suppression context: a single forward pass replacing the three
        # per-`!` backward rescans. `ctx` is fed EVERY consumed character in
        # order (see _SuppressionContext), so at each candidate `!` it reflects
        # exactly the raw prefix the old scans examined.
        ctx = _SuppressionContext()

        # Process the command character by character to handle quotes properly.
        while i < n:
            char = command[i]

            # Inside a heredoc BODY span: emit verbatim, NO expansion and NO
            # context feed (the body is invisible to the command's `!`/quote/
            # bracket logic — bash reads it as literal data).
            while body_i < len(body_spans) and i >= body_spans[body_i][1]:
                body_i += 1
            if (body_i < len(body_spans)
                    and body_spans[body_i][0] <= i < body_spans[body_i][1]):
                result.append(char)
                i += 1
                continue

            # Inside a single-quoted span: everything is literal until the
            # closing ' (or end of line for an unterminated quote).
            if in_squote:
                result.append(char)
                ctx.feed(command, i)
                i += 1
                if char == "'":
                    in_squote = False
                continue

            # Single quotes suppress history expansion — but NOT when already
            # inside double quotes (a ' inside "..." is literal text, bash).
            if char == "'" and not in_dquote:
                in_squote = True
                result.append(char)
                ctx.feed(command, i)
                i += 1
                continue

            # Double quotes do NOT suppress history expansion (bash) — just
            # toggle the state and keep scanning for ! references inside.
            if char == '"':
                in_dquote = not in_dquote
                result.append(char)
                ctx.feed(command, i)
                i += 1
                continue

            # A backslash quotes the next character for history expansion: \!
            # is a literal ! (no expansion). The backslash is KEPT verbatim
            # (bash's history -p keeps it; the lexer removes it later); keeping
            # \" intact also stops that " from toggling the double-quote state.
            # The escaped char still advances the context (the old scans, being
            # quote-blind, counted a \[ etc. too).
            if char == '\\' and i + 1 < n:
                result.append(char)
                ctx.feed(command, i)
                i += 1
                result.append(command[i])
                ctx.feed(command, i)
                i += 1
                continue

            # Candidate history reference: a `!` not immediately before `=` and
            # not inside [...] / ${...} / $((...)). The three constructs are the
            # forward-tracked ctx depths (was three backward rescans).
            if (char == '!' and i + 1 < n and command[i + 1] != '='
                    and not ctx.suppressed()):
                # A history reference is an EVENT designator (!!, !n, !-n,
                # !string, !?string?, !#) optionally followed by a WORD
                # designator (:n, :^, :$, :*, :n-m, ...). The shorthands !^, !$
                # and !* are an implicit !! event plus a word designator.
                # Resolve the event first, then any word designator/modifiers.
                # !# is the current line so far — the text already emitted.
                resolved = self._resolve_event(command, i, history,
                                               ''.join(result))
                if resolved is not None:
                    event_text, event_label, j = resolved
                    if event_text is _EVENT_NOT_FOUND:
                        return HistoryExpansionResult(
                            HistoryExpansionKind.ERROR, '',
                            error=f"{event_label}: event not found",
                            spans=(HistoryExpansionSpan(i, j),))

                    # Apply an optional word designator, then any :modifiers
                    # (:h/:t/:r/:e, :s/:gs/:&, :p, :q, :x) to the event text.
                    selected = self._apply_word_designator(command, j, event_text)
                    if selected is not _BAD_WORD_SPECIFIER:
                        text, j = selected
                        selected = self.apply_modifiers(text, command, j)
                    if selected is _BAD_WORD_SPECIFIER:
                        spec = command[j:self._word_designator_end(command, j)]
                        return HistoryExpansionResult(
                            HistoryExpansionKind.ERROR, '',
                            error=f"{spec}: bad word specifier",
                            spans=(HistoryExpansionSpan(i, j),))
                    if selected[0] is _SUBSTITUTION_FAILED:
                        # A :s/old/new/ whose `old` was not found: bash's
                        # distinct "substitution failed" error class.
                        return HistoryExpansionResult(
                            HistoryExpansionKind.ERROR, '',
                            error=f"{selected[1]}: substitution failed",
                            spans=(HistoryExpansionSpan(i, j),))

                    text, j = selected
                    expanded = True
                    result.append(text)
                    spans.append(HistoryExpansionSpan(i, j))
                    # The consumed reference (command[i:j], the raw !... text —
                    # NOT the expansion) still advances the context for a later
                    # `!`, matching the old backward scans.
                    ctx.feed_range(command, i, j)
                    i = j
                    continue
                # resolved is None: `!` is not a recognized event pattern
                # (e.g. [[ ! ... ]], a trailing !). Fall through to emit it
                # as a literal character.

            # Regular character (also a suppressed or unrecognized `!`).
            result.append(char)
            ctx.feed(command, i)
            i += 1

        final_result = ''.join(result)
        span_tuple = tuple(spans)

        # A :p modifier means "print, don't execute" (bash): a distinct
        # PRINT_ONLY outcome carrying the expansion text — the reporting
        # consumer prints it and records it, but nothing runs.
        if self._print_only:
            return HistoryExpansionResult(
                HistoryExpansionKind.PRINT_ONLY, final_result, spans=span_tuple)

        if expanded:
            return HistoryExpansionResult(
                HistoryExpansionKind.EXPANDED, final_result, spans=span_tuple)

        # No reference fired: the input is unchanged (a literal command).
        return HistoryExpansionResult(HistoryExpansionKind.NONE, final_result)

    def _expand_quick_substitution(self, command: str, history):
        """Expand a ``^old^new[^]`` quick substitution on the previous command.

        Returns a :class:`HistoryExpansionResult` (EXPANDED, or ERROR on no
        history / no match), or the ``_NOT_QUICK_SUB`` sentinel if this is not
        actually a quick sub (so the normal scanner runs — e.g. a bare ``^``
        with no second ``^``).
        """
        # ^old^new^   (the final ^ is optional; old must be non-empty)
        rest = command[1:]
        sep = rest.find('^')
        if sep < 0:
            return _NOT_QUICK_SUB
        old = rest[:sep]
        tail = rest[sep + 1:]
        end = tail.find('^')
        new = tail if end < 0 else tail[:end]
        suffix = '' if end < 0 else tail[end + 1:]
        if not old:
            return _NOT_QUICK_SUB
        if not history:
            return HistoryExpansionResult(
                HistoryExpansionKind.ERROR, '', error=":s: substitution failed")
        last = history[-1]
        if old not in last:
            return HistoryExpansionResult(
                HistoryExpansionKind.ERROR, '',
                error=f"{command}: substitution failed")
        self._last_sub = (old, new)
        return HistoryExpansionResult(
            HistoryExpansionKind.EXPANDED, last.replace(old, new, 1) + suffix,
            spans=(HistoryExpansionSpan(0, len(command)),))

    def _resolve_event(self, command: str, i: int, history, current_line: str):
        """Resolve the event designator beginning at ``command[i]`` (a ``!``).

        Returns a ``(event_text, event_label, end_index)`` tuple where
        ``end_index`` is the index just past the event token (positioned at any
        following word designator), or ``None`` if ``!`` does not begin a
        recognized event pattern (so the caller treats it as a literal).

        ``event_text`` is the matched command line, or the ``_EVENT_NOT_FOUND``
        sentinel if the event reference matched no history entry. ``current_line``
        is the text expanded so far on this line — the ``!#`` designator.
        """
        n = len(command)
        c1 = command[i + 1] if i + 1 < n else ''

        # !! - previous command
        if c1 == '!':
            if history:
                return history[-1], '!!', i + 2
            return _EVENT_NOT_FOUND, '!!', i + 2

        # !# - the current command line typed so far (bash). Never fails; when
        # nothing precedes it the expansion is the empty string.
        if c1 == '#':
            return current_line, '!#', i + 2

        # !$, !^, !*, !:n - implicit !! event plus a word designator. The word
        # designator itself is handled by _apply_word_designator, which is
        # invoked at the same end index, so we leave the cursor on the sigil
        # (or on the ':' introducing a numeric designator).
        if c1 in '$^*:':
            if history:
                return history[-1], '!!', i + 1
            return _EVENT_NOT_FOUND, '!' + c1, i + 1

        # !n / !-n - numeric event reference
        if c1 == '-' or c1.isdigit():
            j = i + 1
            if command[j] == '-':
                j += 1
            while j < n and command[j].isdigit():
                j += 1
            if j == i + 1 or (command[i + 1] == '-' and j == i + 2):
                return None  # bare !- with no digits
            num = int(command[i + 1:j])
            label = f'!{command[i + 1:j]}'
            if num == 0:
                # Event numbers are 1-based; !0 / !-0 is not an event (bash:
                # "event not found"), NOT history[0].
                return _EVENT_NOT_FOUND, label, j
            if num > 0:
                if num <= len(history):
                    return history[num - 1], label, j
                return _EVENT_NOT_FOUND, label, j
            else:
                if abs(num) <= len(history):
                    return history[num], label, j
                return _EVENT_NOT_FOUND, label, j

        # !?string? - most recent command containing string
        if c1 == '?':
            j = i + 2
            while j < n and command[j] != '?':
                j += 1
            search_str = command[i + 2:j]
            end = j + 1 if j < n else j  # skip closing '?'
            for k in range(len(history) - 1, -1, -1):
                if search_str in history[k]:
                    return history[k], f'!?{search_str}?', end
            return _EVENT_NOT_FOUND, f'!?{search_str}?', end

        # !string - most recent command starting with string
        j = i + 1
        while j < n and not command[j].isspace() and command[j] not in '!?;|&(){}[]<>:':
            j += 1
        if j > i + 1:
            prefix = command[i + 1:j]
            for k in range(len(history) - 1, -1, -1):
                if history[k].startswith(prefix):
                    return history[k], f'!{prefix}', j
            return _EVENT_NOT_FOUND, f'!{prefix}', j

        # ! not followed by a recognized pattern (e.g. trailing !, "! ").
        return None

    @staticmethod
    def _split_words(line: str):
        """Split a history line into words for word designators.

        Like bash, splitting respects quoting: a single- or double-quoted
        span is one word and the quote characters are kept as part of the word
        (history stores the literal typed line). Whitespace otherwise
        separates words.
        """
        words = []
        cur = []
        in_word = False
        quote = None
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            if quote:
                cur.append(ch)
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in '\'"':
                quote = ch
                cur.append(ch)
                in_word = True
            elif ch.isspace():
                if in_word:
                    words.append(''.join(cur))
                    cur = []
                    in_word = False
            else:
                cur.append(ch)
                in_word = True
            i += 1
        if in_word:
            words.append(''.join(cur))
        return words

    def _word_designator_end(self, command: str, j: int) -> int:
        """Return the index just past the word designator starting at ``j``.

        Used only to build the "bad word specifier" error string. ``j`` points
        at the sigil (``$``/``^``/``*``) or at the ``:`` introducing a numeric
        designator.
        """
        n = len(command)
        if j < n and command[j] in '$^*':
            return j + 1
        k = j
        if k < n and command[k] == ':':
            k += 1
        while k < n and (command[k].isdigit() or command[k] in '-*$^'):
            k += 1
        return k

    def _apply_word_designator(self, command: str, j: int, event_text: str):
        """Apply an optional word designator at ``command[j]`` to ``event_text``.

        Returns a ``(selected_text, end_index)`` tuple, or the
        ``_BAD_WORD_SPECIFIER`` sentinel on a malformed/out-of-range designator.

        Supported designators (words are 0-indexed; word 0 is the command):
        ``:0`` ``:n`` ``:^`` ``:$`` ``:*`` ``:n-m`` ``:n-`` ``:n*``, and the
        bare sigils ``^`` ``$`` ``*`` (shorthand for ``:1`` ``:$`` ``:1-$``).
        With no designator the whole event line is returned unchanged.
        """
        n = len(command)
        words = self._split_words(event_text)
        # last index of an *argument* word ($ in bash = last word overall).
        last = len(words) - 1

        # Determine the designator text and its end index.
        spec = None
        end = j
        if j < n and command[j] in '$^*':
            # Bare sigil shorthand: !$ !^ !*
            spec = command[j]
            end = j + 1
        elif (j < n and command[j] == ':' and j + 1 < n
              and (command[j + 1].isdigit() or command[j + 1] in '-*$^')):
            k = j + 1
            while k < n and (command[k].isdigit() or command[k] in '-*$^'):
                k += 1
            spec = command[j + 1:k]
            end = k
        else:
            # No word designator (a ':' here introduces a :modifier, applied by
            # the caller via _apply_modifiers): the whole event line.
            return event_text, j

        # Resolve the designator to a (start, stop) inclusive word range.
        def resolve_index(token):
            if token == '$':
                return last
            if token == '^':
                return 1
            if token.isdigit():
                return int(token)
            return None

        if spec == '^':
            start = stop = 1
        elif spec == '$':
            start = stop = last
        elif spec in ('*',):
            # All arguments: words 1..last. Empty (not an error) if no args.
            if last < 1:
                return '', end
            start, stop = 1, last
        elif spec.startswith('-') and len(spec) > 1:
            # -n (the 0-n abbreviation): words 0 through n (bash). So
            # :-2 == :0-2, :-$ == :0-$, :-0 == :0 (just word 0).
            start = 0
            stop = resolve_index(spec[1:])
            if stop is None:
                return _BAD_WORD_SPECIFIER
        elif '-' in spec:
            # n-m or n-  (range)
            lo, _, hi = spec.partition('-')
            start = resolve_index(lo)
            if hi == '':
                # n- : word n through the second-to-last word
                stop = last - 1
            else:
                stop = resolve_index(hi)
            if start is None or stop is None:
                return _BAD_WORD_SPECIFIER
        elif spec.endswith('*') and spec[:-1].isdigit():
            # n* : word n through last
            start = int(spec[:-1])
            stop = last
        elif spec == '' or spec is None:
            return _BAD_WORD_SPECIFIER
        else:
            idx = resolve_index(spec)
            if idx is None:
                return _BAD_WORD_SPECIFIER
            start = stop = idx

        # Validate the range against the available words. Bash is strict:
        # an out-of-range single index or range end is a bad word specifier,
        # EXCEPT that :* / n* / n- yielding nothing is allowed when there are
        # simply no further words.
        if start < 0 or stop < 0 or start > last or stop > last or start > stop:
            # An empty :* (no args) was already handled above. A "n-" or "n*"
            # that lands past the end with start<=last+... follows bash: out of
            # range is a bad specifier.
            return _BAD_WORD_SPECIFIER

        return ' '.join(words[start:stop + 1]), end

    # --- :modifiers (h/t/r/e/s/g&/p) applied after an event[:word] selection ---

    def apply_modifiers(self, text: str, command: str, k: int):
        """Apply a chain of ``:`` modifiers at ``command[k]`` to ``text``.

        Returns ``(new_text, end_index)``, ``_BAD_WORD_SPECIFIER`` on a
        malformed modifier (e.g. ``:&`` with no previous substitution, or an
        unknown modifier letter), or ``(_SUBSTITUTION_FAILED, spec)`` when a
        ``:s`` old-text is absent (``spec`` is the exact modifier text for the
        "substitution failed" diagnostic). Supported: ``:h`` ``:t`` ``:r`` ``:e``
        (pathname head/tail/root/ext on the whole selection), ``:s/old/new/``
        and ``:gs//`` global, ``:&`` (repeat last sub, ``:g&`` global),
        ``:p`` (print, don't execute — sets a flag the caller honors),
        ``:q`` (quote the whole selection as one shell word) and ``:x`` (quote
        each word separately).
        """
        n = len(command)
        while k < n and command[k] == ':':
            m = k + 1
            glob = False
            if m < n and command[m] in 'ga':  # global prefix for s / &
                glob = True
                m += 1
            mod = command[m] if m < n else ''
            if mod == 'h':
                text = self._mod_head(text); k = m + 1
            elif mod == 't':
                text = self._mod_tail(text); k = m + 1
            elif mod == 'r':
                text = self._mod_root(text); k = m + 1
            elif mod == 'e':
                text = self._mod_ext(text); k = m + 1
            elif mod == 'p':
                self._print_only = True; k = m + 1
            elif mod == 'q':
                # :q — quote the selection so it is one word, immune to further
                # expansion (bash). The whole text becomes a single quoted word.
                text = _shell_single_quote(text); k = m + 1
            elif mod == 'x':
                # :x — like :q but break the selection into words at blanks and
                # quote each separately (bash).
                text = ' '.join(_shell_single_quote(w) for w in text.split())
                k = m + 1
            elif mod in ('s', '&'):
                result = self._mod_subst(text, command, m, glob)
                if result is _BAD_WORD_SPECIFIER:
                    return _BAD_WORD_SPECIFIER
                if result[0] is _SUBSTITUTION_FAILED:
                    # Carry the exact modifier spec (this ':' through the end
                    # index) up for the "substitution failed" diagnostic.
                    return _SUBSTITUTION_FAILED, command[k:result[1]]
                text, k = result
            else:
                return _BAD_WORD_SPECIFIER
        return text, k

    @staticmethod
    def _mod_head(text: str) -> str:
        """``:h`` — strip a trailing pathname component (head/dirname)."""
        idx = text.rfind('/')
        return text[:idx] if idx > 0 else (text if idx < 0 else text[:idx])

    @staticmethod
    def _mod_tail(text: str) -> str:
        """``:t`` — the trailing pathname component (tail/basename)."""
        idx = text.rfind('/')
        return text[idx + 1:] if idx >= 0 else text

    @staticmethod
    def _mod_root(text: str) -> str:
        """``:r`` — remove a trailing ``.suffix`` (in the basename)."""
        dot = text.rfind('.')
        slash = text.rfind('/')
        return text[:dot] if dot > slash else text

    @staticmethod
    def _mod_ext(text: str) -> str:
        """``:e`` — keep only a trailing ``.suffix`` (in the basename)."""
        dot = text.rfind('.')
        slash = text.rfind('/')
        return text[dot:] if dot > slash else text

    def _mod_subst(self, text: str, command: str, m: int, glob: bool):
        """Apply ``s<delim>old<delim>new<delim>`` (at ``command[m]=='s'``) or
        ``&`` (repeat the last substitution). Returns ``(text, end)`` on
        success, ``(_SUBSTITUTION_FAILED, end)`` when ``old`` parsed but is
        absent from ``text``, or ``_BAD_WORD_SPECIFIER`` on a malformed
        modifier / missing previous substitution."""
        n = len(command)
        if command[m] == '&':
            if self._last_sub is None:
                return _BAD_WORD_SPECIFIER
            old, new = self._last_sub
            k = m + 1
        else:
            # s<delim>old<delim>new[<delim>]
            d = m + 1
            if d >= n:
                return _BAD_WORD_SPECIFIER
            delim = command[d]
            # old<delim>new[<delim>] — _scan_until returns the index PAST the
            # delimiter, so `new` resumes exactly where `old` left off.
            old, p = self._scan_until(command, d + 1, delim)
            new, k = self._scan_until(command, p, delim)
            if not old:
                return _BAD_WORD_SPECIFIER
            self._last_sub = (old, new)
        if old not in text:
            # bash reports this as "substitution failed" (not "bad word
            # specifier"); return the end index so the caller can quote the
            # exact modifier spec in the message.
            return _SUBSTITUTION_FAILED, k
        replaced = text.replace(old, new) if glob else text.replace(old, new, 1)
        return replaced, k

    @staticmethod
    def _scan_until(command: str, i: int, delim: str):
        """Scan from ``i`` to the next unescaped ``delim`` (or end). Returns
        ``(text, index_past_delim)``; a ``\\<delim>`` contributes a literal delim."""
        out = []
        n = len(command)
        while i < n and command[i] != delim:
            if command[i] == '\\' and i + 1 < n and command[i + 1] == delim:
                out.append(delim)
                i += 2
                continue
            out.append(command[i])
            i += 1
        # i is at delim (consume it) or at end
        return ''.join(out), (i + 1 if i < n else i)
