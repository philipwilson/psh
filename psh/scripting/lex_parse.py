"""The one heredoc-aware lex→alias→parse pipeline for the scripting layer.

Three script-entry callers must turn buffered text into an AST the same way:
the completeness-trial parser (``parser/session.py#ParseSession._trial_parse``), the
execution parser (``source_processor._parse_command``), and the analysis
parser (``visitor_modes._parse_for_analysis``). Historically each wrote the
sequence out by hand and the analysis copy had DRIFTED — it ignored
``--parser``, dropped ``lexer_options``, and skipped alias expansion
(reappraisal #19 H11). The pipeline now lives here:

- :func:`lex_and_expand` — heredoc gate → ``tokenize`` / ``tokenize_with_heredocs``
  → alias expansion, returning the immutable ``LexedUnit``. THE shared
  lex→alias seam, called by all THREE callers, so the sequence that drifted
  can no longer drift.
- :func:`parse_tokens` — dispatch a token stream to the shell's ACTIVE parser
  (recursive-descent or combinator), heredoc-aware. THE shared parse-dispatch,
  called by the two active-parser callers.
- :func:`lex_and_parse` — ``lex_and_expand`` + ``parse_tokens``: the convenience
  chokepoint for a caller that needs neither the intermediate token stream nor a
  parser pinned to recursive descent.

The completeness trial (``command_accumulator``) shares :func:`lex_and_expand`
but keeps its OWN recursive-descent ``Parser`` construction: the interactive
continuation oracle needs the recursive-descent parser's open-construct trail
and its ``at_eof`` / ``unclosed_expansion`` signals, which the combinator parser
does not provide — so the trial parses with recursive descent REGARDLESS of the
active parser (its AST is reused for execution only when recursive descent is
active too). ``_parse_command`` likewise uses the two building blocks directly
so it can print the token stream under ``--debug-tokens`` between lexing and
parsing.

Lex/parse errors (``ParseError`` / ``UnclosedQuoteError``) pass through
untouched — each caller interprets them (the trial as ``NeedMore``, the others
as reportable syntax errors).
"""
from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence

from ..lexer import tokenize, tokenize_with_heredocs
from ..lexer.heredoc_lexer import LexedUnit
from ..parser import create_parser, parse_with_heredocs
from ..utils import contains_heredoc

if TYPE_CHECKING:
    from ..ast_nodes import Program
    from ..lexer.heredoc_lexer import LexedHeredoc
    from ..lexer.token_types import Token
    from ..shell import Shell


def render_syntax_error_detail(exc: BaseException,
                               source_text: Optional[str] = None) -> str:
    """The detail half of a syntax-error diagnostic (no location prefix).

    A ``ParseError`` renders as its rich caret form (source line, ``^`` marker,
    suggestions, token context); any other lex/parse error (an
    ``UnclosedQuoteError``) renders as ``syntax error: <reason>``. Shared by the
    execution renderer (``source_processor._report_syntax_error``) and the
    analysis renderer (``visitor_modes._report_syntax_error``) so the
    ParseError-vs-lexer-error decision cannot drift between them; each caller
    supplies its own ``psh: <location>: `` prefix.

    ``source_text`` back-fills the caret's source line when the parser was not
    given the source (the combinator parser leaves ``error_context.source_line``
    unset) — the token's line is fragment-relative, so it indexes ``source_text``
    directly.
    """
    from ..parser import ParseError
    if isinstance(exc, ParseError) and exc.error_context:
        ctx = exc.error_context
        if ctx.source_line is None and source_text is not None:
            token = ctx.token
            token_line = getattr(token, 'line', None)
            lines = source_text.splitlines()
            if token_line and 0 < token_line <= len(lines):
                ctx.source_line = lines[token_line - 1]
        return ctx.format_error()
    return f"syntax error: {exc}"


def lex_and_expand(
    text: str,
    shell: 'Shell',
    *,
    source_name: Optional[str] = None,
    base_line: int = 1,
    expand_aliases: bool = True,
    lexer_options: Optional[Any] = None,
    warn_unterminated: bool = True,
) -> LexedUnit:
    """Tokenize *text* (heredoc-aware) and alias-expand the token stream.

    The shared front half of every script-entry parse. ``contains_heredoc``
    picks ``tokenize_with_heredocs`` (bodies collected into the LexedUnit's
    id-keyed ``heredocs`` map, so a body line like ``)`` is not tokenized as
    command text) or the plain ``tokenize``. Aliases are expanded at the
    lex→parse seam when ``expand_aliases`` is set — ``Shell.expand_aliases``
    itself honours the ``expand_aliases`` shopt, so this is the on/off switch
    for whether analysis / trial parses consult the alias table at all.

    ``lexer_options`` is the shell option dict (``extglob`` / ``posix``) applied
    to tokenization. ``source_name`` / ``base_line`` locate the
    unterminated-heredoc warning; ``warn_unterminated=False`` suppresses it for
    a completeness trial (the execution pass warns; the typed EOF termination
    is recorded either way).

    Returns a :class:`LexedUnit` — ``heredocs`` is ``None`` when *text*
    contains no heredoc (plain lexing was performed).
    """
    heredocs: Optional[Mapping[int, 'LexedHeredoc']]
    if contains_heredoc(text):
        tokens, heredocs = tokenize_with_heredocs(
            text,
            shell_options=lexer_options,
            source_name=source_name,
            base_line=base_line,
            warn_unterminated=warn_unterminated,
        )
    else:
        tokens = tuple(tokenize(text, shell_options=lexer_options))
        heredocs = None
    if expand_aliases:
        tokens = tuple(shell.expand_aliases(list(tokens)))
    return LexedUnit(tokens=tuple(tokens), heredocs=heredocs)


def parse_tokens(
    tokens: Sequence['Token'],
    heredocs: Optional[Mapping[int, 'LexedHeredoc']],
    shell: 'Shell',
    *,
    source_text: Optional[str] = None,
    line_offset: int = 0,
    lexer_options: Optional[Any] = None,
) -> 'Program':
    """Parse a token stream with the shell's ACTIVE parser, heredoc-aware.

    When ``heredocs`` is present the ``<<``/``<<-`` bodies are attached as the
    redirects are constructed (``parse_with_heredocs``); otherwise a plain parser
    is built. Either way the recursive-descent or combinator implementation is
    chosen by ``shell.active_parser``. ``source_text`` / ``line_offset`` improve
    error reporting (source-line caret; absolute line numbers) on the plain path;
    ``lexer_options`` threads the shell option set so a nested substitution body
    re-lexes with the same option-sensitive lexing (extglob) as the outer
    command. Raises ``ParseError`` / ``UnclosedQuoteError`` unchanged.
    """
    if heredocs is not None:
        return parse_with_heredocs(
            tokens, heredocs,
            active_parser=shell.active_parser,
            lexer_options=lexer_options)
    parser = create_parser(
        tokens,
        active_parser=shell.active_parser,
        source_text=source_text,
        line_offset=line_offset,
        lexer_options=lexer_options)
    return parser.parse()


def lex_and_parse(
    text: str,
    shell: 'Shell',
    *,
    source_name: Optional[str] = None,
    base_line: int = 1,
    expand_aliases: bool = True,
    lexer_options: Optional[Any] = None,
) -> 'Program':
    """Lex, alias-expand, and parse *text* into a ``Program`` in one call.

    The full pipeline chokepoint = :func:`lex_and_expand` then
    :func:`parse_tokens` against ``shell.active_parser``. ``base_line`` maps to
    the parser's ``line_offset`` (``base_line - 1``) and *text* is passed as the
    error-reporting ``source_text``. Errors pass through untouched.
    """
    tokens, heredocs = lex_and_expand(
        text, shell,
        source_name=source_name,
        base_line=base_line,
        expand_aliases=expand_aliases,
        lexer_options=lexer_options)
    return parse_tokens(
        tokens, heredocs, shell,
        source_text=text,
        line_offset=max(0, base_line - 1),
        lexer_options=lexer_options)
