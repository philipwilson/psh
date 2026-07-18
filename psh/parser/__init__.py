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
from .recursive_descent.support.utils import parse_with_heredocs as utils_parse_with_heredocs

# Public API
__all__ = [
    # Main parsing interface
    'parse', 'parse_with_heredocs', 'create_parser', 'Parser',
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


def parse_with_heredocs(tokens, heredocs, active_parser='rd',
                        lexer_options=None):
    """Parse tokens with collected heredocs using the selected implementation.

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
    if _use_combinator(active_parser):
        from .combinators.parser import ParserCombinatorShellParser

        # Thread lexer_options into the combinator too (campaign S4 handoff 3):
        # its syntax templates build with the same option-sensitive budget as
        # the recursive-descent path, rather than being dropped here.
        return ParserCombinatorShellParser(ParserConfig()).parse_with_heredocs(
            tokens, heredocs, lexer_options=lexer_options)
    return utils_parse_with_heredocs(tokens, heredocs,
                                     lexer_options=lexer_options)


def create_parser(tokens, active_parser='rd', source_text=None, line_offset=0,
                  lexer_options=None):
    """Create a parser configured for the selected implementation.

    Chooses between the recursive descent parser and the combinator parser
    based on the ``active_parser`` argument.

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
    config = ParserConfig()

    if _use_combinator(active_parser):
        from .combinators.parser import ParserCombinatorShellParser

        pc = ParserCombinatorShellParser(config)

        class _ParserWrapper:
            def __init__(self, parser, tokens):
                self._parser = parser
                self.tokens = tokens

            def parse(self):
                return self._parser.parse(self.tokens)

        return _ParserWrapper(pc, tokens)

    return Parser(tokens, config=config, source_text=source_text,
                  line_offset=line_offset, lexer_options=lexer_options)
