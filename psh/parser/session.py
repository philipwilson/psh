"""The one incremental multiline-completeness engine (campaign I3, #20 H15).

Both line-gathering channels — the script/`-c`/stdin reader
(`scripting/source_processor.py`) and the interactive PS2 loop
(`interactive/multiline_handler.py`) — must answer the same question for every
physical line they read: *does the buffer now form a complete command, or is
more input needed?* This module is the single engine that answers it, and the
answer comes from the REAL lexer and parser (no regex, no whole-buffer keyword
oracle):

- the lexer raises a structured ``UnclosedQuoteError`` when a quote spans the
  end of input;
- an unclosed ``$(``/``${``/``$((``/`` ` ``/``<(`` is a token whose part carries
  an ``*_unclosed`` marker → the recursive-descent parser returns the typed
  ``Incomplete`` outcome (`parse_outcome()`, campaign S4) carrying the
  unclosed-expansion KIND and the open-construct trail;
- heredoc bodies are matched incrementally against the pending
  ``PendingHeredocQueue`` (S2) — a body line like ``)`` is never shown to the
  parser as command text, and a body line costs O(1) (no re-lex, no re-parse).

`ParserDriver.start_session(inputs)` returns a `ParseSession`; each
`feed(line)` returns the typed `Completeness` classification (mapping onto the
one-shot `Complete | Incomplete | Invalid` outcome sum) plus the gathering
payload (the buffered text, and — when the recursive-descent trial parse
succeeded — the reusable AST + tokens).

## Cost model (the H15 boundary — read `ParseSession.feed`)

The engine is genuinely incremental for the families that CAN be:

- a heredoc BODY line is O(1) (pending-queue match, no lex/parse) — LINEAR;
- a multi-command stream commits and drops each complete command (the buffer
  resets), so N complete commands cost O(N) — LINEAR.

A single OPEN logical command that is not a heredoc body (a growing `if…fi`, a
quoted string, an unclosed `$(…`) re-lexes and re-parses its own accumulated
text on every fed line → O(k²) for that one command (bounded by one command,
reset on completion). This residual is CAUSED by an oracle constraint, not
laziness: bash reports a mid-construct syntax error IMMEDIATELY (PTY-proven —
`if true; then echo )` errors on the offending line, not deferred to `fi`), so
the parse cannot be deferred to structural close; and psh's ModularLexer is
forward-only and cannot resume mid-construct (its `_post_lex` fusion/keyword
passes are whole-list), so the lex cannot be made incremental within one open
construct. Linearising it needs a resumable lexer+parser (bash's re-entrant
model) — a grammar rewrite outside the campaign's S1–S5 fences, recorded as the
post-campaign path to full H15 closure. The residual's shape is pinned by a
doubling-ratio characterization test so any accidental worsening (O(k³)) fails
and any future improvement flips it consciously.

The parser package stays scripting-free: history expansion and the
continuation-join preprocessing are injected as `SessionInputs.preprocess`
(the seam where campaign I4's typed history expansion will plug in), and the
heredoc-aware alias-expanding lex is injected as `SessionInputs.lex`.
"""

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from ..ast_nodes import Program

from ..lexer import UnclosedQuoteError
from ..utils import (
    PendingHeredocQueue,
    contains_heredoc,
    open_heredoc_specs,
)
from .parse_outcome import Incomplete as ParsedIncomplete
from .parse_outcome import Invalid as ParsedInvalid
from .recursive_descent.parser import Parser


class Completeness(enum.Enum):
    """The three completeness classes — the `Complete | Incomplete | Invalid`
    outcome sum, named for the gathering layer."""

    COMPLETE = 'complete'      # a complete, well-formed command (execute it)
    INCOMPLETE = 'incomplete'  # more input could complete it (keep reading)
    INVALID = 'invalid'        # complete but ill-formed (report the error)


class ContinuationReason(enum.Enum):
    """Why the engine needs another line (drives the interactive PS2 prompt)."""

    LINE_CONTINUATION = 'line_continuation'        # trailing backslash
    UNCLOSED_QUOTE = 'unclosed_quote'              # ', ", $' or $" still open
    HEREDOC = 'heredoc'                            # reading a heredoc body
    UNCLOSED_EXPANSION = 'unclosed_expansion'      # $( / ${ / $(( / ` still open
    INCOMPLETE_STRUCTURE = 'incomplete_structure'  # if/for/case/... still open


@dataclass(frozen=True)
class ContinuationHint:
    """What the lexer/parser knows about the missing input.

    ``detail`` depends on ``reason``: the open quote character, the pending
    heredoc delimiter, or the unclosed-expansion kind ('command', 'parameter',
    'arithmetic', 'backtick'). ``constructs`` is the parser's open-construct
    trail (('if',), ('for', 'then'), ...) — the contextual PS2 renders from it.
    """

    reason: ContinuationReason
    detail: Optional[str] = None
    constructs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionStep:
    """One ``ParseSession.feed`` result.

    ``completeness`` is the class. For ``INCOMPLETE``, ``hint`` carries the
    continuation facts. For ``COMPLETE``/``INVALID``, ``text`` is the raw
    buffered command (what execution receives — ``set -v`` echoes it verbatim)
    and ``source`` is the preprocessed text the trial actually parsed;
    ``program``/``tokens`` are the reusable recursive-descent trial parse (set
    only when the RD trial produced a program), and ``error`` is the real
    syntax error on ``INVALID``.
    """

    completeness: Completeness
    text: str = ''
    source: str = ''
    program: Optional["Program"] = None
    tokens: Optional[list] = None
    error: Optional[Exception] = None
    hint: Optional[ContinuationHint] = None


@dataclass
class SessionOps:
    """Deterministic operation counters for the linearity pins (campaign I3).

    Cumulative over the session lifetime (NOT reset per command), so a
    multi-command stream's total work is measurable. ``tokens_lexed`` and
    ``tokens_parsed`` are the two op-count proxies the doubling-ratio tests
    assert on; ``heredoc_body_lines`` proves heredoc bodies cost no lex/parse.
    """

    feeds: int = 0
    lex_calls: int = 0
    tokens_lexed: int = 0
    parse_calls: int = 0
    tokens_parsed: int = 0
    heredoc_body_lines: int = 0


# The heredoc-aware, alias-expanding lex seam: (preview, base_line) ->
# (tokens, heredocs). Injected so the parser package never imports scripting.
LexHook = Callable[[str, int], Tuple[Sequence[Any], Any]]


def _identity(text: str) -> str:
    return text


def _never(_text: str) -> bool:
    return False


@dataclass(frozen=True)
class SessionInputs:
    """Immutable per-session configuration (the `start_session(inputs)` arg).

    ``lex`` is the heredoc-aware alias-expanding lexer seam (scripting-owned;
    injected so the parser package stays scripting-free). ``preprocess`` joins
    backslash-newline continuations and — interactively — applies history
    expansion silently; it is the INJECTION POINT for campaign I4's typed
    history expansion (thread the existing hook; do not reshape its timing).
    ``detects_history_reference`` reports a still-unexpanded history reference
    (a completed-but-unparsed buffer). ``lexer_options`` mirrors the execution
    lexing (extglob/posix).
    """

    lex: LexHook
    preprocess: Callable[[str], str] = _identity
    detects_history_reference: Callable[[str], bool] = _never
    lexer_options: Any = None


class ParseSession:
    """The incremental completeness engine for ONE gathering session.

    Persistent state across feeds: the buffered physical lines, the pending
    heredoc queue (S2), and the cumulative op counters. ``feed(line)`` decides
    completeness with the real lexer+parser; ``reset()`` (or any terminal
    ``SessionStep``) starts the next command. One instance per gathering
    session — created via ``ParserDriver.start_session(inputs)``.
    """

    def __init__(self, inputs: SessionInputs):
        self.inputs = inputs
        # Absolute 1-based line where the buffered command starts in the
        # enclosing input (set by the caller as it reads); trial-parse errors
        # use it so a multi-line script reports absolute line numbers.
        self.start_line: int = 1
        self._lines: List[str] = []
        # Pending heredoc bodies (shared head-of-queue policy). While non-empty,
        # fed lines are body text routed to the queue HEAD only — never compared
        # with later pending delimiters (H1/G1), and never re-lexing/re-parsing
        # the whole buffer per body line (O(1) per body line).
        self._open_heredocs = PendingHeredocQueue()
        self.ops = SessionOps()

    # === Buffer state ===

    @property
    def is_empty(self) -> bool:
        """True when no command is being built."""
        return not self._lines

    @property
    def buffer_text(self) -> str:
        """The raw buffered text so far (for end-of-input handling)."""
        return '\n'.join(self._lines)

    @property
    def pending_heredoc(self) -> bool:
        """True when the last ``feed`` left us inside a heredoc body.

        End-of-input inside a heredoc body is the one EOF state the caller does
        not execute (the command is discarded).
        """
        return bool(self._open_heredocs)

    def reset(self) -> None:
        """Drop the buffer and start the next command (op counters persist)."""
        self._lines = []
        self._open_heredocs = PendingHeredocQueue()

    def flush(self) -> SessionStep:
        """End of input: hand back whatever is buffered, unparsed.

        The execution path parses it and reports the error a truncated construct
        produces, exactly as it always did for an EOF-terminated buffer. End of
        input INSIDE a heredoc body keeps the buffer verbatim: the heredoc is
        "delimited by end-of-file", so trailing empty lines and the final
        newline are body CONTENT (bash keeps them). Otherwise trailing newlines
        are bare separators, stripped (with the one-newline reprieve for a
        trailing continuation).
        """
        text = (self.buffer_text if self._open_heredocs
                else _strip_trailing_separators(self.buffer_text))
        self.reset()
        return SessionStep(Completeness.COMPLETE, text=text)

    # === The oracle ===

    def feed(self, line: str) -> SessionStep:
        """Add one physical line; decide completeness with the real parser.

        Cost note (the H15 boundary): a heredoc BODY line is O(1) (matched
        against the pending queue — no lex/parse); every other fed line
        re-preprocesses and RE-PARSES the accumulated command text. Gathering a
        single OPEN logical command of k physical lines is therefore O(k²) in
        the lexer+parser — bounded by ONE command, reset on completion. That
        residual is oracle-forced (bash reports mid-construct errors immediately
        so the parse cannot be deferred) and lexer-bound (ModularLexer is
        forward-only, cannot resume mid-construct); see the module docstring.
        Pushing below O(k²) needs a resumable lexer+parser (fenced).
        """
        self.ops.feeds += 1
        self._lines.append(line)

        # Inside heredoc bodies, the line is body text: the head-of-queue policy
        # decides whether it terminates the FIRST open heredoc — nothing else is
        # consulted (O(1) per body line; a line equal to a LATER pending
        # delimiter is body text of the head).
        if self._open_heredocs:
            self.ops.heredoc_body_lines += 1
            self._open_heredocs.feed_line(line)
            head = self._open_heredocs.head
            if head is not None:
                return SessionStep(
                    Completeness.INCOMPLETE,
                    hint=ContinuationHint(ContinuationReason.HEREDOC,
                                          detail=head.cooked))
            # Every body delimited — fall through to the full trial.

        raw = self.buffer_text

        # Preprocess a PREVIEW for the trial: join backslash-newline
        # continuations, then (interactively) apply history expansion silently —
        # errors and the expansion echo are the execution path's job. This is
        # the injected scripting hook (campaign I4's typed history expansion
        # plugs in here); do not reshape its timing.
        preview = self.inputs.preprocess(raw)

        # 1. Trailing backslash: the next physical line continues this one.
        if _ends_with_line_continuation(preview):
            return SessionStep(
                Completeness.INCOMPLETE,
                hint=ContinuationHint(ContinuationReason.LINE_CONTINUATION))

        # 2. Open heredoc: following lines are body text for the pending
        #    delimiters, NOT command text — don't show them to the parser.
        if contains_heredoc(preview):
            self._open_heredocs = PendingHeredocQueue()
            for spec in open_heredoc_specs(preview):
                self._open_heredocs.push(spec)
            head = self._open_heredocs.head
            if head is not None:
                return SessionStep(
                    Completeness.INCOMPLETE,
                    hint=ContinuationHint(ContinuationReason.HEREDOC,
                                          detail=head.cooked))

        # 3. A failed/unexpanded history reference: complete, unparsed.
        #    Execution re-runs the expansion with reporting.
        if self.inputs.detects_history_reference(preview):
            return self._complete(raw, preview)

        # 4. The real oracle: tokenize and parse the preview into the honest
        #    Complete | Incomplete | Invalid outcome sum (campaign S4). Only the
        #    LEXER layer still signals through exceptions (an unclosed quote /
        #    other lexer SyntaxError raised before parsing).
        try:
            outcome, tokens = self._trial_parse(preview)
        except UnclosedQuoteError as e:
            return SessionStep(
                Completeness.INCOMPLETE,
                hint=ContinuationHint(ContinuationReason.UNCLOSED_QUOTE,
                                      detail=e.quote_char))
        except SyntaxError as e:
            # Lexer errors other than unclosed quotes are real errors too.
            return self._complete(raw, preview, error=e)

        if isinstance(outcome, ParsedIncomplete):
            # Structurally incomplete: the parse failed at end of input, so more
            # lines could complete it. The typed ExpectedInput carries what the
            # parser knows — which expansion is unclosed, which constructs open.
            expected = outcome.expected
            if expected.unclosed_expansion:
                reason = ContinuationReason.UNCLOSED_EXPANSION
                detail = expected.unclosed_expansion
            else:
                reason = ContinuationReason.INCOMPLETE_STRUCTURE
                detail = None
            return SessionStep(
                Completeness.INCOMPLETE,
                hint=ContinuationHint(reason, detail=detail,
                                      constructs=expected.constructs))
        if isinstance(outcome, ParsedInvalid):
            # A real syntax error: the command is complete but invalid.
            return self._complete(raw, preview, error=outcome.error)

        # Complete: carry the parsed AST + tokens for execution reuse.
        return self._complete(raw, preview,
                              program=outcome.program, tokens=tokens)

    # === Internals ===

    def _trial_parse(self, preview: str):
        """Tokenize and parse ``preview``, returning ``(ParseOutcome, tokens)``.

        Uses the injected heredoc-aware lex→alias seam (shared with execution
        and analysis) but builds the recursive-descent ``Parser`` itself and
        asks it for the typed ``Complete | Incomplete | Invalid`` outcome
        (campaign S4): the completeness oracle relies on the ``Incomplete``
        variant's open-construct trail and ``unclosed_expansion`` kind, which
        the combinator parser does not compute — so the trial is recursive
        descent REGARDLESS of the active parser (its AST is reused for execution
        only when recursive descent is active too, decided by the caller). The
        lexer may still raise ``UnclosedQuoteError``/``SyntaxError`` here;
        ``feed`` catches those.
        """
        tokens, heredocs = self.inputs.lex(preview, self.start_line)
        self.ops.lex_calls += 1
        self.ops.tokens_lexed += len(tokens)
        parser = Parser(list(tokens), source_text=preview,
                        line_offset=max(0, self.start_line - 1),
                        heredocs=heredocs,
                        lexer_options=self.inputs.lexer_options)
        self.ops.parse_calls += 1
        self.ops.tokens_parsed += len(tokens)
        return parser.parse_outcome(), tokens

    def _complete(self, raw: str, preview: str, program=None, tokens=None,
                  error=None) -> SessionStep:
        # Trailing newlines are bare statement separators — strip them from both
        # views so the execution path's own preprocessing of ``text`` can be
        # matched against ``source`` for AST reuse (one exception in
        # _strip_trailing_separators: a newline consumed by a trailing
        # continuation is NOT a bare separator).
        step = SessionStep(
            Completeness.INVALID if error is not None else Completeness.COMPLETE,
            text=_strip_trailing_separators(raw),
            source=preview.rstrip('\n'),
            program=program, tokens=tokens, error=error)
        self.reset()
        return step


class ParserDriver:
    """The entry point to the incremental completeness engine (campaign I3).

    ``start_session(inputs)`` returns a fresh ``ParseSession`` — the single
    completeness engine both the scripting reader and the interactive PS2 loop
    drive. It is not a one-shot whole-buffer re-parse adapter: heredoc bodies
    are matched incrementally and complete commands commit and drop; the
    single-open-construct O(k²) residual is the fenced RD/lexer limit (module
    docstring).
    """

    @staticmethod
    def start_session(inputs: SessionInputs) -> ParseSession:
        """Begin an incremental completeness session over ``inputs``."""
        return ParseSession(inputs)


def _strip_trailing_separators(raw: str) -> str:
    """Strip trailing newlines from a gathered buffer — except the one a
    trailing continuation consumes.

    Trailing newlines are bare statement separators, EXCEPT when the text left
    after stripping ends with an unescaped backslash: that backslash and the
    following newline are a line-continuation PAIR (the buffer gathered
    ``echo hi \\`` plus an empty final line), and stripping the newline stranded
    the backslash as a literal word character — ``echo hi \\<newline>`` at end
    of input runs ``echo hi`` in bash (every input mode), not ``echo hi \\``.
    Keep exactly one newline back so ``process_line_continuations`` joins the
    pair away. (A backslash that is comment or single-quote content gets the
    newline back too — harmless, since joining is context-aware and leaves those
    literal.)
    """
    text = raw.rstrip('\n')
    if text != raw and _ends_with_line_continuation(text):
        text += '\n'
    return text


def _ends_with_line_continuation(text: str) -> bool:
    """True if the last line of ``text`` ends with an unescaped backslash.

    The backslash must be the FINAL character (like bash: ``echo \\ `` is an
    escaped space, not a continuation — the old interactive heuristic rstripped
    first and wrongly prompted for more input there).

    Splitting on ``\\n`` (not ``str.splitlines``, which also breaks on ``\\r``)
    keeps a trailing ``\\<CR>`` from looking like a bare trailing backslash:
    bash only honors ``\\<LF>`` as a continuation, so ``echo a\\<CR><LF>`` is a
    complete command (the backslash escapes the CR), not a request for more
    input.
    """
    if not text:
        return False
    last_line = text.split('\n')[-1]
    if not last_line.endswith('\\'):
        return False
    # An odd-length run of trailing backslashes means the final one is
    # unescaped — a line continuation.
    run = len(last_line) - len(last_line.rstrip('\\'))
    return run % 2 == 1
