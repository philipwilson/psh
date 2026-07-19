"""The scripting adapter over the ONE completeness engine.

Both line-gathering layers — the script/`-c`/stdin reader
(`scripting/source_processor.py`) and the interactive PS2 loop
(`interactive/multiline_handler.py`) — must answer the same question for every
line they read: *does the buffer now form a complete command, or is more input
needed?* The answer comes from the single engine, `parser.session.ParseSession`
(campaign I3): the REAL lexer and parser decide completeness (no keyword
pseudo-parsing, no error-message string-matching). This module is the SCRIPTING
face of that engine — it injects the scripting-only preprocessing (backslash
continuation join + history expansion) and the heredoc-aware alias-expanding
lex seam (so the parser package stays scripting-free), holds a per-session
``ParseSession``, and maps its typed ``SessionStep`` onto the gathering
result types (`NeedMore` / `Complete`) that the two readers consume.

``feed(line)`` returns either ``NeedMore`` — carrying an honest ``Hint`` about
WHY more input is needed — or ``Complete``, carrying the buffered text and,
when the recursive-descent trial parse succeeded, the parsed AST and token
stream so the execution path need not parse the same text a second time.
"""

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Tuple, Union

if TYPE_CHECKING:
    from ..ast_nodes import ASTNode
    from ..interactive.history_result import HistoryExpansionResult

from ..parser.session import (
    Completeness,
    ContinuationReason,
    ParserDriver,
    SessionInputs,
    SessionStep,
)
from .input_preprocessing import process_line_continuations
from .lex_parse import lex_and_expand


class HintKind(enum.Enum):
    """Why the accumulator needs another line."""

    LINE_CONTINUATION = 'line_continuation'    # trailing backslash
    UNCLOSED_QUOTE = 'unclosed_quote'          # ', ", $' or $" still open
    HEREDOC = 'heredoc'                        # reading a heredoc body
    UNCLOSED_EXPANSION = 'unclosed_expansion'  # $( / ${ / $(( / ` still open
    INCOMPLETE_STRUCTURE = 'incomplete_structure'  # if/for/case/... still open


@dataclass(frozen=True)
class Hint:
    """What the lexer/parser actually knows about the missing input.

    ``detail`` depends on the kind: the open quote character, the pending
    heredoc delimiter, or the unclosed expansion kind ('command', 'parameter',
    'arithmetic', 'backtick'). ``constructs`` is the parser's open-construct
    trail at the point of failure (('if',), ('for', 'then'), ...) — the
    interactive layer renders its contextual PS2 from it.
    """

    kind: HintKind
    detail: Optional[str] = None
    constructs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class NeedMore:
    """The buffer is not a complete command yet; feed another line."""

    hint: Hint


@dataclass(frozen=True)
class Complete:
    """The buffer is a complete command (possibly an INVALID one).

    ``text`` is the raw buffered command (what execution receives — set -v
    echoes it verbatim). ``source`` is the preprocessed text the trial actually
    parsed (continuations joined, history silently expanded). ``ast``/``tokens``
    are the trial-parse results when the recursive-descent parser is active —
    execution reuses them instead of re-parsing, provided its own (reporting)
    preprocessing reproduces ``source``. ``error`` is a REAL syntax error (not
    incomplete input): the command is complete but invalid, and the caller
    reports it.
    """

    text: str
    source: str = ''
    ast: Optional["ASTNode"] = None
    tokens: Optional[list] = None
    error: Optional[Exception] = None


# ContinuationReason (the engine's continuation vocabulary) and HintKind (the
# gathering layer's) share member values, so the engine→gathering map is a
# value lookup rather than a hand-maintained branch table.
_REASON_TO_HINTKIND = {
    reason: HintKind(reason.value) for reason in ContinuationReason
}


class CommandAccumulator:
    """Accumulates physical lines into complete logical commands.

    One instance per gathering session; ``reset()`` (or a ``Complete`` result,
    which resets implicitly) starts the next command. The completeness decision
    is delegated to a single ``parser.session.ParseSession`` (campaign I3): this
    class only supplies the scripting-specific preprocessing/lex seams and maps
    the engine's typed ``SessionStep`` onto ``NeedMore``/``Complete``.
    """

    def __init__(self, shell):
        self.shell = shell
        self.state = shell.state
        # Whether history expansion may apply to this input (mirrors
        # InputSource.history_expansion_eligible; the source processor copies
        # the source's flag in). False for a -c command string and the rc file —
        # bash never bang-expands those, so the silent completeness-trial
        # expansion must not either. Read dynamically by the injected preprocess
        # hook, so a caller may set it after construction.
        self.history_expansion_eligible: bool = True
        # The typed HistoryExpansionResult from the most recent _preprocess call,
        # read by _detects_history_reference in the SAME feed cycle (campaign I4).
        self._last_history_result: "Optional[HistoryExpansionResult]" = None
        self._session = ParserDriver.start_session(SessionInputs(
            lex=self._lex,
            preprocess=self._preprocess,
            detects_history_reference=self._detects_history_reference,
            lexer_options=self.state.options,
        ))

    # === Buffer state (delegated to the engine) ===

    @property
    def is_empty(self) -> bool:
        """True when no command is being built."""
        return self._session.is_empty

    @property
    def buffer_text(self) -> str:
        """The raw buffered text so far (for end-of-input handling)."""
        return self._session.buffer_text

    @property
    def pending_heredoc(self) -> bool:
        """True when the last ``feed`` left us inside a heredoc body.

        End-of-input inside a heredoc body is the one EOF state the source
        processor does not execute (the command is discarded).
        """
        return self._session.pending_heredoc

    @property
    def start_line(self) -> int:
        """Absolute 1-based line where the buffered command starts (the source
        processor sets it as it reads; the engine uses it for absolute
        error line numbers)."""
        return self._session.start_line

    @start_line.setter
    def start_line(self, value: int) -> None:
        self._session.start_line = value

    def reset(self) -> None:
        """Drop the buffer and start the next command."""
        self._session.reset()

    def flush(self) -> Complete:
        """End of input: hand back whatever is buffered, unparsed."""
        # flush() always yields a COMPLETE step (no error, no continuation hint).
        result = self._to_result(self._session.flush())
        assert isinstance(result, Complete)
        return result

    # === The oracle ===

    def feed(self, line: str) -> Union[Complete, NeedMore]:
        """Add one physical line; decide completeness with the real parser."""
        return self._to_result(self._session.feed(line))

    # === Injected scripting seams ===

    def _lex(self, preview: str, base_line: int):
        """The heredoc-aware alias-expanding lex seam (shared with execution and
        analysis via ``lex_and_expand``). ``warn_unterminated=False``: a trial
        must never print the unterminated-heredoc warning — the execution pass
        warns. ``lexer_options`` mirrors the execution lexing so a nested
        substitution body re-lexes with the same options (extglob)."""
        return lex_and_expand(
            preview, self.shell,
            base_line=base_line,
            lexer_options=self.state.options,
            warn_unterminated=False)

    def _preprocess(self, raw: str) -> str:
        """Join backslash-newline continuations, then (interactively) apply
        history expansion silently for the completeness trial. This is the I3
        injection point for campaign I4's TYPED history expansion. ACTIVATION
        consumes the F1 interactive-FAMILY flag (`options['interactive']`) plus
        source eligibility — NOT is_script_mode. The producer is pure (no print,
        no record); the typed `HistoryExpansionResult` is CACHED so
        _detects_history_reference reads its `kind` rather than re-scanning with
        a regex. On a NONE/EXPANDED outcome the trial parses the resulting text;
        an ERROR keeps the raw preview (routed complete-but-unparsed below)."""
        preview = process_line_continuations(raw)
        self._last_history_result = None
        if (self.state.options.get('interactive', False)
                and self.history_expansion_eligible
                and hasattr(self.shell, 'history_expander')):
            result = self.shell.history_expander.expand_history(preview)
            self._last_history_result = result
            if not result.is_error:
                preview = result.text
        return preview

    def _detects_history_reference(self, preview: str) -> bool:
        """A history reference that FAILED (ERROR) or is PRINT-ONLY makes the
        buffer complete but unparsed; execution re-runs the expansion with
        reporting and either prints the diagnostic, prints the ``:p`` expansion
        (executing nothing), or would have executed the result. Reads the TYPED
        result cached by :meth:`_preprocess` (campaign I4) — not a regex."""
        result = self._last_history_result
        return result is not None and (result.is_error or result.is_print_only)

    # === Engine → gathering-result mapping ===

    def _to_result(self, step: SessionStep) -> Union[Complete, NeedMore]:
        if step.completeness is Completeness.INCOMPLETE:
            assert step.hint is not None
            return NeedMore(Hint(
                kind=_REASON_TO_HINTKIND[step.hint.reason],
                detail=step.hint.detail,
                constructs=step.hint.constructs))
        # COMPLETE / INVALID: the AST is only reusable when execution would
        # parse with the same (recursive-descent) parser the trial used.
        ast = step.program
        tokens = step.tokens
        if self.shell.active_parser != 'recursive_descent':
            ast = tokens = None
        return Complete(text=step.text, source=step.source,
                        ast=ast, tokens=tokens, error=step.error)
