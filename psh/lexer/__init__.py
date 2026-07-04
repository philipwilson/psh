"""Advanced lexer package for PSH shell tokenization.

This package provides a unified lexer for shell tokenization with comprehensive
Unicode support, metadata tracking, and context-aware parsing. Enhanced
functionality is now built into the standard Token class and ModularLexer.

The main entry point is the tokenize() function which uses the ModularLexer
as the single lexer implementation.
"""

from typing import Any, Dict, List, Mapping, Optional, Tuple

from .constants import KEYWORDS, SPECIAL_VARIABLES
from .keyword_normalizer import KeywordNormalizer

# Core lexer components
from .modular_lexer import ModularLexer
from .position import (
    LexerConfig,
    LexerError,
    UnclosedQuoteError,
)
from .state_context import LexerContext
from .token_parts import RichToken, TokenPart
from .token_types import Token
from .unicode_support import (
    is_identifier_char,
    is_identifier_start,
    is_valid_name,
    is_whitespace,
    normalize_identifier,
    validate_identifier,
)


def _make_config(strict: bool, shell_options: Optional[Mapping[str, Any]] = None) -> LexerConfig:
    """Build the lexer config for an entry point (batch vs interactive,
    shell options like extglob applied)."""
    if strict:
        config = LexerConfig.create_batch_config()
    else:
        config = LexerConfig.create_interactive_config()
    if shell_options and shell_options.get('extglob', False):
        config.enable_extglob = True
    return config


def _post_lex(tokens: List[Token]) -> List[Token]:
    """The shared post-lex pipeline: keyword normalization, then brace
    expansion over the token stream.

    Keywords are normalized first so the brace expander can see
    command-prefix boundaries (separators, do/then, etc.) when deciding
    assignment words. Brace expansion happens AFTER tokenization (on the
    token stream), so generated characters are never re-lexed and quote/
    command-position context is available.

    Note: misplaced case terminators (`;;` outside case, etc.) are rejected
    by the parser (see parsers/statements.py), not by a lexer pass.
    """
    from ..expansion.brace_expansion_tokens import TokenBraceExpander

    tokens = KeywordNormalizer().normalize(tokens)
    return TokenBraceExpander().expand(tokens)


def tokenize(input_string: str, strict: bool = True, shell_options: Optional[Mapping[str, Any]] = None) -> List[Token]:
    """
    Tokenize a shell command string using the unified lexer implementation.

    This function provides the main entry point for shell tokenization with
    comprehensive Unicode support, metadata tracking, context awareness, and
    enhanced error handling - all features built into the standard Token class.

    Args:
        input_string: The shell command string to tokenize
        strict: If True, use strict mode (batch); if False, use interactive mode
        shell_options: Optional shell options dict to configure extglob etc.

    Returns:
        List of tokens representing the parsed command
    """
    lexer = ModularLexer(input_string, config=_make_config(strict, shell_options))
    return _post_lex(lexer.tokenize())


def tokenize_with_heredocs(input_string: str, strict: bool = True,
                           shell_options: Optional[Mapping[str, Any]] = None,
                           source_name: Optional[str] = None,
                           base_line: int = 1,
                           warn_unterminated: bool = True) -> Tuple[List[Token], Dict[str, Dict[str, Any]]]:
    """
    Tokenize a shell command string with heredoc support.

    This function tokenizes shell commands that may contain heredocs,
    collecting the heredoc content for later processing. The post-lex
    pipeline is the same as tokenize() — omitting brace expansion here once
    silently disabled it on any command line containing a heredoc.

    Args:
        input_string: The shell command string to tokenize
        strict: If True, use strict mode (batch); if False, use interactive mode
        shell_options: Optional shell options dict to configure extglob etc.
        source_name: Name prefixing the unterminated-heredoc warning (script
            path; None → "psh", matching bash's "bash:" for -c/stdin)
        base_line: Absolute source line of input_string's first line, so the
            warning's line numbers match the enclosing file
        warn_unterminated: False silences the unterminated-heredoc warning
            (trial parses; the execution pass prints it)

    Returns:
        Tuple of (tokens, heredoc_map) where heredoc_map contains collected heredoc content
    """
    from .heredoc_lexer import HeredocLexer

    lexer = HeredocLexer(input_string, config=_make_config(strict, shell_options),
                         source_name=source_name, base_line=base_line,
                         warn_unterminated=warn_unterminated)
    tokens, heredoc_map = lexer.tokenize_with_heredocs()
    return _post_lex(tokens), heredoc_map


__all__ = [
    # Main lexer interface
    'ModularLexer', 'tokenize', 'tokenize_with_heredocs',
    # Configuration
    'LexerConfig',
    # Errors
    'LexerError', 'UnclosedQuoteError',
]
