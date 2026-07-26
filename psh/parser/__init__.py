"""
Parser package for PSH shell.

This package provides a unified parser implementation with comprehensive features.
The parser converts tokens into an Abstract Syntax Tree (AST) with metadata support,
context-aware parsing, semantic analysis, and enhanced error recovery.
"""

from .config import ParserConfig
from .parse_inputs import ParseInputs, ParserState
from .parse_outcome import (
    Complete,
    ExpectedInput,
    Incomplete,
    Invalid,
    ParseOutcome,
    materialize,
)
from .recursive_descent.helpers import (
    ParseError,
    SubstitutionSyntaxError,
    is_substitution_origin,
)

# Import from final locations
from .recursive_descent.parser import Parser

# Public API
__all__ = [
    # Main parsing interface
    'parse', 'parse_with_inputs', 'parse_with_heredocs', 'create_parser',
    'Parser',
    # Configuration
    'ParserConfig',
    # Immutable inputs / mutable state (campaign S4)
    'ParseInputs', 'ParserState',
    # Total parse outcome (campaign S4)
    'ParseOutcome', 'Complete', 'Incomplete', 'Invalid', 'ExpectedInput',
    'materialize',
    # Errors
    'ParseError',
    'SubstitutionSyntaxError',
    'is_substitution_origin',
]


def parse(tokens, config=None):
    """Parse tokens into AST using the unified parser implementation.

    This function provides comprehensive parsing with metadata utilization,
    context-aware analysis, and enhanced error handling - all features built
    into the standard parser.

    Args:
        tokens: List of tokens to parse
        config: Optional ParserConfig for custom parsing behavior

    Returns:
        Parsed AST with full feature support
    """
    if config is None:
        config = ParserConfig()

    return Parser(tokens, config=config).parse()


# Accepted parser-selection names. The shell only ever passes the canonical
# 'recursive_descent'/'combinator' (validated by --parser / parser-select), but
# these factories are a public API, so they validate the name themselves rather
# than treating every non-'combinator' string as recursive descent.
_RECURSIVE_DESCENT_NAMES = frozenset({'rd', 'recursive_descent'})
_COMBINATOR_NAMES = frozenset({'combinator'})


def _use_combinator(active_parser: str) -> bool:
    """Return True for the combinator parser, False for recursive descent.

    Raises ``ValueError`` for any unrecognized name — an unknown parser must
    fail loudly instead of silently falling through to recursive descent.
    """
    if active_parser in _COMBINATOR_NAMES:
        return True
    if active_parser in _RECURSIVE_DESCENT_NAMES:
        return False
    raise ValueError(
        f"unknown parser {active_parser!r}: expected one of "
        "'recursive_descent'/'rd' or 'combinator'")


def parse_with_inputs(tokens, inputs: ParseInputs, active_parser='rd'):
    """THE one parse entry: dispatch *tokens* to the selected parser, threading
    the whole ``ParseInputs`` through BOTH implementations.

    ``inputs`` is the frozen caller context — ``source_text`` (error caret),
    ``line_offset`` (absolute nested-fragment line numbers), ``lexer_options``
    (so a nested substitution body re-lexes with the same option-sensitive
    lexing, notably extglob), ``heredocs`` (the collected ``<<``/``<<-`` bodies),
    and ``config``. Every field reaches whichever parser runs, so neither path
    loses context on the nested-substitution re-lex or the depth budget
    (remediation HIGH-5: the combinator no longer discards source/options).

    ``active_parser`` selects ``'recursive_descent'``/``'rd'`` (default) or
    ``'combinator'``; any other name raises ``ValueError``. Returns the
    canonical ``Program``.
    """
    if _use_combinator(active_parser):
        from .combinators.parser import ParserCombinatorShellParser

        return ParserCombinatorShellParser(inputs.config).parse(tokens, inputs)
    return Parser(tokens, config=inputs.config,
                  source_text=inputs.source_text,
                  line_offset=inputs.line_offset,
                  heredocs=inputs.heredocs,
                  lexer_options=inputs.lexer_options).parse()


def parse_with_heredocs(tokens, heredocs, active_parser='rd',
                        lexer_options=None):
    """Parse tokens with collected heredocs using the selected implementation.

    A thin adapter over :func:`parse_with_inputs`: the heredoc map and
    ``lexer_options`` become a ``ParseInputs`` threaded into whichever parser.

    Args:
        tokens: Token stream (heredoc bodies absent; operator tokens carry
            ``heredoc_id`` linking them to ``heredocs``).
        heredocs: The LexedUnit's id-keyed map of LexedHeredoc entries
            (delimiter spec + collected body).
        active_parser: ``'recursive_descent'``/``'rd'`` (default) or
            ``'combinator'``. Any other name raises ``ValueError``.
        lexer_options: Shell option dict in effect, threaded so a nested
            substitution body is re-lexed with the same option-sensitive
            lexing (extglob) as the outer command.
    """
    inputs = ParseInputs(lexer_options=lexer_options, heredocs=heredocs)
    return parse_with_inputs(tokens, inputs, active_parser)


class _DeferredParse:
    """A parser handle whose ``.parse()`` runs the selected parser once.

    :func:`create_parser` returns this so a caller can build a parser now and
    parse later (matching the recursive-descent ``Parser`` object shape). It is
    uniform for both implementations and defers to :func:`parse_with_inputs`, so
    the combinator path carries the SAME bound ``ParseInputs`` as recursive
    descent — no caller context is dropped (remediation HIGH-5, which the old
    combinator-only facade wrapper caused).
    """

    def __init__(self, tokens, inputs: ParseInputs, active_parser: str):
        self.tokens = tokens
        self._inputs = inputs
        self._active_parser = active_parser

    def parse(self):
        return parse_with_inputs(self.tokens, self._inputs, self._active_parser)


def create_parser(tokens, active_parser='rd', source_text=None, line_offset=0,
                  lexer_options=None):
    """Create a parser configured for the selected implementation.

    Chooses between the recursive descent parser and the combinator parser
    based on the ``active_parser`` argument. Returns a deferred handle whose
    ``.parse()`` threads the full caller context (``source_text`` /
    ``line_offset`` / ``lexer_options``) into whichever parser runs.

    Args:
        tokens: List of tokens to parse.
        active_parser: ``'recursive_descent'``/``'rd'`` (default) or
            ``'combinator'``. Any other name raises ``ValueError``.
        source_text: Optional source text for error reporting.
        line_offset: Number of source lines before this fragment in the
            enclosing input, so errors report absolute line numbers.
        lexer_options: Shell option dict in effect, threaded so a nested
            substitution body is re-lexed with the same option-sensitive
            lexing (extglob) as the outer command.

    Returns:
        Object with a ``.parse()`` method that returns an AST.
    """
    # Validate the parser name eagerly (create-time), matching the old
    # behavior where an unknown name raised before .parse() was called.
    _use_combinator(active_parser)
    inputs = ParseInputs(source_text=source_text, line_offset=line_offset,
                         lexer_options=lexer_options)
    return _DeferredParse(tokens, inputs, active_parser)
