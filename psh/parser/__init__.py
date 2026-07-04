"""
Parser package for PSH shell.

This package provides a unified parser implementation with comprehensive features.
The parser converts tokens into an Abstract Syntax Tree (AST) with metadata support,
context-aware parsing, semantic analysis, and enhanced error recovery.
"""

from .config import ErrorHandlingMode, ParserConfig, ParsingMode
from .recursive_descent.context import ParserContext
from .recursive_descent.helpers import ErrorContext, ParseError

# Import from final locations
from .recursive_descent.parser import Parser
from .recursive_descent.support.context_factory import create_context
from .recursive_descent.support.utils import parse_with_heredocs as utils_parse_with_heredocs

# Public API
__all__ = [
    # Main parsing interface
    'parse', 'parse_with_heredocs', 'create_parser', 'Parser',
    # Configuration
    'ParserConfig',
    # Errors
    'ParseError',
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


def parse_with_heredocs(tokens, heredoc_map, active_parser='rd'):
    """Parse tokens with heredoc content using the selected implementation.

    Args:
        tokens: List of tokens (heredoc bodies absent; operator tokens carry
            ``heredoc_key`` attributes linking them to ``heredoc_map``).
        heredoc_map: Map of heredoc keys to ``{'content', 'quoted'}`` entries.
        active_parser: ``'rd'`` for recursive descent (default),
            ``'combinator'`` for the combinator parser.
    """
    if active_parser == 'combinator':
        from .combinators.parser import ParserCombinatorShellParser

        return ParserCombinatorShellParser(ParserConfig()).parse_with_heredocs(
            tokens, heredoc_map)
    return utils_parse_with_heredocs(tokens, heredoc_map)


def create_parser(tokens, active_parser='rd', source_text=None, line_offset=0):
    """Create a parser configured for the selected implementation.

    Chooses between the recursive descent parser and the combinator parser
    based on the ``active_parser`` argument.

    Args:
        tokens: List of tokens to parse.
        active_parser: ``'rd'`` for recursive descent (default),
            ``'combinator'`` for the combinator parser.
        source_text: Optional source text for error reporting.
        line_offset: Number of source lines before this fragment in the
            enclosing input, so errors report absolute line numbers.

    Returns:
        Object with a ``.parse()`` method that returns an AST.
    """
    config = ParserConfig()

    if active_parser == 'combinator':
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
                  line_offset=line_offset)
