"""The single "is this command complete?" oracle.

Both line-gathering layers — the script/`-c`/stdin reader
(`scripting/source_processor.py`) and the interactive PS2 loop
(`interactive/multiline_handler.py`) — must answer the same question for
every line they read: *does the buffer now form a complete command, or is
more input needed?* Historically each layer answered it with its own
machinery (the interactive side with keyword pseudo-parsing and error-message
string-matching). This module is the one shared answer, and the decision
comes from the REAL lexer and parser:

- the lexer raises a structured ``UnclosedQuoteError`` when a quote spans
  the end of input;
- the parser raises ``ParseError`` with ``at_eof=True`` (and
  ``unclosed_expansion`` for ``$(``/``${``/``$((``/backtick) when the parse
  fails at end of input, i.e. more lines could complete it;
- the parser's ``ParserContext.open_constructs`` trail records which
  constructs were still open at that failure ('if', 'then', 'while', ...),
  which is exactly what the interactive continuation prompt wants to show;
- heredoc bodies are tracked by the shared detector in
  ``utils/heredoc_detection.py`` (a body line like ``)`` must never be
  shown to the parser as command text).

``feed(line)`` returns either ``NeedMore`` — carrying an honest ``Hint``
about WHY more input is needed — or ``Complete``, carrying the buffered
text and, when the trial parse succeeded with the recursive-descent parser,
the parsed AST and token stream so the execution path need not parse the
same text a second time.
"""

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from ..ast_nodes import ASTNode

from ..lexer import UnclosedQuoteError, tokenize
from ..parser import ParseError, Parser
from ..utils import contains_heredoc, open_heredoc_delimiters
from .input_preprocessing import process_line_continuations


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
    heredoc delimiter, or the unclosed expansion kind ('command',
    'parameter', 'arithmetic', 'backtick'). ``constructs`` is the parser's
    open-construct trail at the point of failure (('if',), ('for', 'then'),
    ...) — the interactive layer renders its contextual PS2 from it.
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
    echoes it verbatim). ``source`` is the preprocessed text the trial
    actually parsed (continuations joined, history silently expanded).
    ``ast``/``tokens`` are the trial-parse results when the recursive-descent
    parser is active — execution reuses them instead of re-parsing, provided
    its own (reporting) preprocessing reproduces ``source``. ``error`` is a
    REAL syntax error (not incomplete input): the command is complete but
    invalid, and the caller reports it.
    """

    text: str
    source: str = ''
    ast: Optional["ASTNode"] = None
    tokens: Optional[list] = None
    error: Optional[Exception] = None


class CommandAccumulator:
    """Accumulates physical lines into complete logical commands.

    One instance per gathering session; ``reset()`` (or a ``Complete``
    result, which resets implicitly) starts the next command.
    """

    def __init__(self, shell):
        self.shell = shell
        self.state = shell.state
        self._lines: List[str] = []
        # Pending heredoc bodies as (delimiter, strip_tabs) pairs. While
        # non-empty, fed lines are body text checked incrementally against
        # these delimiters — never re-scanning (or re-parsing) the whole
        # buffer per body line.
        self._open_heredocs: List[tuple] = []
        # The trial parser's live open-construct trail (see _trial_parse).
        self._open_constructs: List[str] = []

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

        End-of-input inside a heredoc body is the one EOF state the
        source processor does not execute (the command is discarded).
        """
        return bool(self._open_heredocs)

    def reset(self) -> None:
        """Drop the buffer and start the next command."""
        self._lines = []
        self._open_heredocs = []

    def flush(self) -> Complete:
        """End of input: hand back whatever is buffered, unparsed.

        The execution path parses it and reports the error a truncated
        construct produces (e.g. "Expected FI, got EOF"), exactly as it
        always did for an EOF-terminated buffer.
        """
        result = Complete(text=self.buffer_text.rstrip('\n'))
        self.reset()
        return result

    # === The oracle ===

    def feed(self, line: str) -> Union[Complete, NeedMore]:
        """Add one physical line; decide completeness with the real parser."""
        self._lines.append(line)

        # Inside heredoc bodies, the line is body text: check it against
        # the pending delimiters and nothing else (O(1) per body line).
        if self._open_heredocs:
            self._close_heredocs_matching(line)
            if self._open_heredocs:
                return self._need_more(
                    Hint(HintKind.HEREDOC, detail=self._open_heredocs[0][0]))
            # Every body delimited — fall through to the full trial.

        raw = self.buffer_text

        # Preprocess a PREVIEW for the trial: join backslash-newline
        # continuations, then (interactively) apply history expansion
        # silently — errors and the expansion echo are the execution
        # path's job.
        preview = process_line_continuations(raw)
        if not self.state.is_script_mode and hasattr(self.shell, 'history_expander'):
            expanded = self.shell.history_expander.expand_history(
                preview, print_expansion=False, report_errors=False)
            if expanded is not None:
                preview = expanded

        # 1. Trailing backslash: the next physical line continues this one.
        if _ends_with_line_continuation(preview):
            return self._need_more(Hint(HintKind.LINE_CONTINUATION))

        # 2. Open heredoc: following lines are body text for the pending
        #    delimiters, NOT command text — don't show them to the parser.
        if contains_heredoc(preview):
            self._open_heredocs = open_heredoc_delimiters(preview)
            if self._open_heredocs:
                return self._need_more(
                    Hint(HintKind.HEREDOC, detail=self._open_heredocs[0][0]))

        # 3. A failed/unexpanded history reference: complete, unparsed.
        #    Execution re-runs the expansion with reporting and either
        #    prints the "event not found" error or executes the result.
        from ..interactive.history_expansion import contains_history_reference
        if contains_history_reference(preview):
            return self._complete(raw, preview)

        # 4. The real oracle: tokenize and parse the preview.
        try:
            ast, tokens = self._trial_parse(preview)
        except UnclosedQuoteError as e:
            return self._need_more(
                Hint(HintKind.UNCLOSED_QUOTE, detail=e.quote_char))
        except ParseError as e:
            if e.at_eof:
                # Structurally incomplete: the parse failed at end of
                # input, so more lines could complete it. The hint carries
                # what the parser knows — which expansion is unclosed,
                # and which constructs are still open.
                if e.unclosed_expansion:
                    kind, detail = HintKind.UNCLOSED_EXPANSION, e.unclosed_expansion
                else:
                    kind, detail = HintKind.INCOMPLETE_STRUCTURE, None
                return self._need_more(
                    Hint(kind, detail=detail,
                         constructs=tuple(self._open_constructs)))
            # A real syntax error: the command is complete but invalid.
            return self._complete(raw, preview, error=e)
        except SyntaxError as e:
            # Lexer errors other than unclosed quotes are real errors too.
            return self._complete(raw, preview, error=e)

        return self._complete(raw, preview, ast=ast, tokens=tokens)

    # === Internals ===

    def _close_heredocs_matching(self, line: str) -> None:
        """Close the first pending heredoc whose delimiter is ``line``
        (tab-stripped for ``<<-``) — same matching as the shared detector."""
        for i, (word, strip_tabs) in enumerate(self._open_heredocs):
            check = line.lstrip('\t') if strip_tabs else line
            if check.rstrip() == word:
                del self._open_heredocs[i]
                return

    def _trial_parse(self, preview: str):
        """Tokenize and parse ``preview`` with the recursive-descent parser.

        Mirrors the execution path's lexing exactly: commands containing
        heredocs go through ``tokenize_with_heredocs`` so body lines stay
        out of the token stream (a body line like ``)`` must not be a
        parse error), and the collected bodies are populated into the AST.
        """
        self._open_constructs = []
        if contains_heredoc(preview):
            from ..lexer import tokenize_with_heredocs
            tokens, heredoc_map = tokenize_with_heredocs(
                preview,
                strict=self.state.options.get('posix', False),
                shell_options=self.state.options)
            # Expand aliases on the token stream (lex→parse boundary) so the
            # trial AST — which the execution path reuses — matches what the
            # execution seam produces.
            tokens = self.shell.alias_manager.expand_aliases(tokens)
            parser = Parser(tokens)
            self._open_constructs = parser.ctx.open_constructs
            ast = parser.parse()
            parser.utils.populate_heredoc_content(ast, heredoc_map)
        else:
            tokens = tokenize(preview, shell_options=self.state.options)
            tokens = self.shell.alias_manager.expand_aliases(tokens)
            parser = Parser(tokens, source_text=preview)
            self._open_constructs = parser.ctx.open_constructs
            ast = parser.parse()
        return ast, tokens

    def _need_more(self, hint: Hint) -> NeedMore:
        return NeedMore(hint)

    def _complete(self, raw: str, preview: str, ast=None, tokens=None,
                  error=None) -> Complete:
        # The AST is only reusable when execution would parse with the
        # same (recursive-descent) parser the trial used.
        if self.shell.active_parser != 'recursive_descent':
            ast = tokens = None
        # Trailing newlines are bare statement separators — strip them from
        # both views so the execution path's own preprocessing of ``text``
        # can be matched against ``source`` for AST reuse.
        result = Complete(text=raw.rstrip('\n'), source=preview.rstrip('\n'),
                          ast=ast, tokens=tokens, error=error)
        self.reset()
        return result


def _ends_with_line_continuation(text: str) -> bool:
    """True if the last line of ``text`` ends with an unescaped backslash.

    The backslash must be the FINAL character (like bash: ``echo \\ `` is
    an escaped space, not a continuation — the old interactive heuristic
    rstripped first and wrongly prompted for more input there).
    """
    if not text:
        return False
    last_line = text.splitlines()[-1]
    if not last_line.endswith('\\'):
        return False
    # An odd-length run of trailing backslashes means the final one is
    # unescaped — a line continuation.
    run = len(last_line) - len(last_line.rstrip('\\'))
    return run % 2 == 1
