"""
Lexer driver with heredoc support.

Separates heredoc BODY lines from command text, then tokenizes the joined
command text in ONE ModularLexer pass — so cross-line lexer state (open
quotes, case/bracket depth, command position) survives. Earlier versions
re-lexed each physical line with a fresh lexer, which broke any multi-line
construct sharing a command with a heredoc.

The lexer/parser boundary is the immutable :class:`LexedUnit`: the token
stream plus an id-keyed map of :class:`LexedHeredoc` entries (spec +
collected body). Operator tokens carry the spec's ordinal ``heredoc_id``;
there are no string-derived heredoc keys (campaign S2).
"""

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, List, Mapping, NamedTuple, Optional, Tuple

from ..utils.heredoc_detection import (
    CollectedHeredoc,
    HeredocSpec,
    HeredocTermination,
)
from .heredoc_collector import HeredocCollector
from .modular_lexer import ModularLexer
from .state_context import LexerContext
from .token_types import Token, TokenType

if TYPE_CHECKING:
    from .position import LexerConfig


@dataclass(frozen=True)
class LexedHeredoc:
    """One heredoc at the lexer/parser boundary: its delimiter spec and its
    collected body. Keyed by ``spec.id`` in :class:`LexedUnit.heredocs`."""

    spec: HeredocSpec
    collected: CollectedHeredoc


class LexedUnit(NamedTuple):
    """The immutable lexer/parser boundary for heredoc-aware lexing.

    ``tokens`` is the post-lex token stream (heredoc bodies lifted out;
    ``<<``/``<<-`` operator tokens carry their spec's ``heredoc_id``).
    ``heredocs`` maps spec id -> :class:`LexedHeredoc` — a read-only view.
    ``tokenize_with_heredocs`` always supplies the mapping (possibly empty);
    the scripting seam (``lex_and_expand``) uses ``None`` to mean "plain,
    non-heredoc-aware lexing was performed" (its parse dispatch keys on
    that). A NamedTuple, so ``tokens, heredocs = ...`` unpacking reads
    naturally at call sites.
    """

    tokens: Tuple[Token, ...]
    heredocs: Optional[Mapping[int, LexedHeredoc]]


# Token types that can be ADJACENT parts of one heredoc delimiter word
# (`<<E"O"F`, `<<E$X`, `<<E<(x)`). Operators (`;`, `|`, redirects) end the
# word even when they touch it (`<<EOF;`), so they are excluded.
# PROCESS_SUB_IN/OUT: bash accepts a process-substitution-SHAPED piece as
# literal delimiter text (`cat << <(x)` terminates at the line `<(x)`;
# `cat <<E<(x)` at `E<(x)` — bash 5.2), with NO paren nesting: the piece
# extends to the FIRST `)` and `<< <(a(b)c)` is a bash syntax error. The
# no-nesting rule is applied by _procsub_delimiter_ok, mirroring the
# text-level scanner's `[<>]\([^()]*\)` unit so the two layers agree.
_DELIMITER_PART_TYPES = frozenset({
    TokenType.WORD, TokenType.STRING, TokenType.VARIABLE,
    TokenType.COMMAND_SUB, TokenType.COMMAND_SUB_BACKTICK,
    TokenType.ARITH_EXPANSION,
    TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT,
})


def _procsub_delimiter_ok(token: Token) -> bool:
    """A procsub-shaped delimiter piece is accepted only without nested
    parens (bash's heredoc-word reader does not nest them)."""
    if token.type not in (TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT):
        return True
    return '(' not in token.value[2:]


def delimiter_token_acceptable(token: Token) -> bool:
    """Shared token-level delimiter-part rule for the heredoc scanners and
    both parsers: a word-like part type, with the procsub no-nesting rule."""
    return token.type in _DELIMITER_PART_TYPES and _procsub_delimiter_ok(token)


class HeredocLexer:
    """Lexer with heredoc collection support.

    ``source_name`` and ``base_line`` locate the source text within its
    input source, for the unterminated-heredoc warning: the name prefixes
    the message (a script path, or "psh" for -c/stdin/eval, like bash's
    "bash:" there) and ``base_line`` is the absolute line the source's
    first line sits on (source_processor passes the buffered command's
    start line). ``warn_unterminated=False`` suppresses the WARNING for
    EOF-delimited heredocs — for TRIAL parses (the command accumulator's
    completeness oracle), which must not print a warning the execution
    pass will print again. The typed ``HeredocTermination.EOF`` outcome is
    recorded on the CollectedHeredoc either way.
    """

    def __init__(self, source: str, config: "Optional[LexerConfig]" = None,
                 source_name: str | None = None, base_line: int = 1,
                 warn_unterminated: bool = True) -> None:
        self.source = source
        self.config = config
        self.source_name = source_name
        self.base_line = base_line
        self.warn_unterminated = warn_unterminated
        self.heredoc_collector = HeredocCollector()
        # The heredoc-stripped command text the final token stream indexes
        # into — set by tokenize_with_heredocs(). Post-lex passes (word
        # fusion's span-faithful lexemes) must slice THIS text, never the
        # body-bearing input source.
        self.command_text: str = ''

    @staticmethod
    def _split_physical_lines(source: str) -> List[str]:
        """Split *source* into physical lines: ``\\n`` boundaries only, one
        trailing CR dropped per line (the line-reading layer's CRLF
        handling, so a ``-c`` string with DOS line endings behaves like a
        CRLF script file). Unlike ``str.splitlines`` this keeps a lone CR,
        FF, or VT inside a line — they are ordinary word characters, not
        line boundaries (bash agrees)."""
        lines = source.split('\n')
        if lines and lines[-1] == '':
            lines.pop()  # trailing newline is a terminator, not a new line
        return [line[:-1] if line.endswith('\r') else line for line in lines]

    def tokenize_with_heredocs(self) -> LexedUnit:
        """Tokenize and return the immutable :class:`LexedUnit`.

        Algorithm:
        1. Classify each physical line as command text or heredoc body.
           Heredoc operators are found by tokenizing command text INCREMENTALLY
           (so quoted ``"<<EOF"`` is never a heredoc). Each logical command
           (one or more physical lines) is lexed ONCE, seeded with the lexer
           state (``LexerContext``) the previous command ended in, so the
           discovery pass is linear in source length rather than re-lexing the
           whole accumulated prefix per line (which was O(N^2)). While a
           command is mid-construct (e.g. an unclosed multi-line string), its
           accumulated lines don't tokenize yet and following lines are command
           continuation, like bash — bodies only start once the command
           tokenizes completely.
        2. Tokenize the joined command text once, with full cross-line state.

        End of input with a heredoc still pending does NOT drop it: like
        bash, the gathered lines become the body ("delimited by
        end-of-file", the typed EOF termination) and a warning is printed
        to stderr (suppressed for trial parses).
        """
        command_lines: List[str] = []

        # Incremental discovery state (replaces per-line whole-prefix re-lex):
        #   carry_context      - the lexer state the last COMPLETE command ended
        #                        in; seeds the next command's lexer (None for the
        #                        first command -> fresh context from config).
        #   committed_lines    - number of command_lines folded into
        #                        carry_context (i.e. up to the last complete
        #                        command).
        #   pending_lines      - command lines of the logical command being
        #                        tried now but not yet fully tokenized (grows
        #                        while an unclosed construct spans lines).
        carry_context: Optional[LexerContext] = None
        committed_lines = 0
        pending_lines: List[str] = []

        lines = self._split_physical_lines(self.source)
        lineno = 0
        for lineno, raw_line in enumerate(lines, start=1):
            if self.heredoc_collector.has_pending_heredocs():
                completed = self.heredoc_collector.collect_line(raw_line, lineno)
                if completed is not None:
                    # The next pending heredoc's body gathering begins here
                    # (bash reports this line in its EOF warning).
                    self.heredoc_collector.restamp_head_start(lineno)
                continue

            command_lines.append(raw_line)
            pending_lines.append(raw_line)
            # The suffix of the joined command text after the last complete
            # command, WITH the joining newline so the NEWLINE transition
            # between commands (which returns to command position) replays.
            # Token positions index into this `text`.
            text = ('\n' if committed_lines else '') + '\n'.join(pending_lines)
            try:
                lexer = ModularLexer(
                    text, config=self.config,
                    initial_context=(carry_context.copy()
                                     if carry_context is not None else None))
                toks = lexer.tokenize()
            except SyntaxError:
                # The command text is mid-construct (an unclosed
                # quote/expansion spans lines). Like bash, the next line is
                # command CONTINUATION — heredoc bodies only begin once the
                # command itself tokenizes completely. Keep pending_lines and
                # carry_context so the next line re-tries this command from the
                # same seed state (only this command's lines are re-lexed, not
                # the whole script).
                continue
            self._register_from_tokens(toks, text, lineno)
            # This logical command tokenized completely: carry its end state to
            # the next command and reset the pending accumulator.
            carry_context = lexer.context
            committed_lines += len(pending_lines)
            pending_lines = []

        if self.heredoc_collector.has_pending_heredocs():
            finalized = self.heredoc_collector.finalize_at_eof(max(lineno, 1))
            if self.warn_unterminated:
                self._warn_eof_delimited(finalized, max(lineno, 1))

        command_text = '\n'.join(command_lines)
        if self.source.endswith('\n'):
            command_text += '\n'
        self.command_text = command_text

        # The single full-state tokenization of the command text.
        tokens = ModularLexer(command_text, config=self.config).tokenize()
        self._mark_heredoc_tokens(tokens)

        heredocs = {
            spec_id: LexedHeredoc(spec=self.heredoc_collector.specs[spec_id],
                                  collected=collected)
            for spec_id, collected in self.heredoc_collector.collected.items()
        }
        return LexedUnit(tokens=tuple(tokens),
                         heredocs=MappingProxyType(heredocs))

    # === Heredoc operator discovery ===

    def _warn_eof_delimited(self, pending: List[Tuple[HeredocSpec, int]],
                            last_line: int) -> None:
        """Print bash's unterminated-heredoc warning for each EOF-delimited
        heredoc: ``NAME: line M: warning: here-document at line N delimited
        by end-of-file (wanted `DELIM')`` — M is the EOF line, N the line
        the heredoc's body gathering began (both absolute via base_line).
        The wanted delimiter is the spec's COOKED terminator (bash prints
        the quote-removed word).
        """
        import sys
        name = self.source_name or 'psh'
        eof_line = self.base_line + last_line - 1
        for spec, start_line in pending:
            at_line = self.base_line + start_line - 1
            print(f"{name}: line {eof_line}: warning: here-document at "
                  f"line {at_line} delimited by end-of-file "
                  f"(wanted `{spec.cooked}')", file=sys.stderr)

    def _register_from_tokens(self, toks: List[Token],
                              text: str, lineno: int) -> None:
        """Register a heredoc for every heredoc operator in ``toks``.

        ``toks`` are the tokens of ONE logical command (the incremental
        discovery pass lexes each command exactly once, when it completes), so
        every heredoc operator here is new — no skip counter is needed.
        ``text`` is the command text ``toks`` were tokenized from (heredoc
        bodies already stripped), so token positions index INTO ``text`` — NOT
        ``self.source`` (whose offsets include the removed body lines).
        ``lineno`` is the current physical source line — where the newly
        registered heredocs' body gathering begins.
        """
        for i, token in enumerate(toks):
            if token.type in (TokenType.HEREDOC, TokenType.HEREDOC_STRIP):
                if (i + 1 < len(toks)
                        and delimiter_token_acceptable(toks[i + 1])):
                    # (An operator with NO delimiter word after it — e.g.
                    # `cat << #comment`, `cat <<` at end of line — registers
                    # nothing; the parser reports the syntax error.)
                    # Recover the FULL delimiter word from the raw SOURCE span of
                    # its adjacent tokens. The delimiter is taken LITERALLY (no
                    # expansion), so a `$X`/`$(...)` in it (`<<E$X`) is part of
                    # the terminator, and a composite (`E"O"F`, `<<E$X`) spans
                    # several tokens. Reconstructing from individual token
                    # *values* drops a VARIABLE part's `$` or a STRING's quotes;
                    # the source slice preserves them. The spec (built by the
                    # sole constructor) derives the literal terminator and the
                    # body-is-quoted fact from that raw spelling.
                    delim_toks = [toks[i + 1]]
                    j = i + 2
                    while (j < len(toks) and toks[j].adjacent_to_previous
                           and delimiter_token_acceptable(toks[j])):
                        delim_toks.append(toks[j])
                        j += 1
                    span = (delim_toks[0].position, delim_toks[-1].end_position)
                    raw = text[span[0]:span[1]]
                    self.heredoc_collector.register_heredoc(
                        raw=raw,
                        strip_tabs=(token.type == TokenType.HEREDOC_STRIP),
                        line=lineno, span=span,
                    )

    def _mark_heredoc_tokens(self, tokens: List[Token]) -> None:
        """Attach spec ids to heredoc operator tokens, in order.

        A non-None ``heredoc_id`` (the declared Token field) is the signal, to
        KeywordNormalizer and the parser, that this heredoc's body lines are
        NOT in the token stream. Tokens are immutable, so each marked token is
        rebuilt in place with :func:`dataclasses.replace`. Registration and
        this pass both walk operators in source order, so the ordinal ids
        line up positionally.
        """
        ids = sorted(self.heredoc_collector.specs)
        idx = 0
        for i, token in enumerate(tokens):
            if token.type in (TokenType.HEREDOC, TokenType.HEREDOC_STRIP):
                if idx < len(ids):
                    tokens[i] = replace(token, heredoc_id=ids[idx])
                    idx += 1


__all__ = [
    'HeredocLexer', 'LexedHeredoc', 'LexedUnit', 'HeredocTermination',
    'delimiter_token_acceptable',
]
