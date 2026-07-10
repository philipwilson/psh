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


def _make_config(shell_options: Optional[Mapping[str, Any]] = None) -> LexerConfig:
    """Build the lexer config for an entry point (shell options like extglob
    and posix applied).

    ``posix_mode`` is taken from the active shell options (``set -o posix``) so
    the lexer's POSIX-aware identifier paths (variable-name extraction in
    ``$var``/``${var}``, assignment-name recognition, named-fd names) actually
    activate — previously ``config.posix_mode`` was never set and those paths
    were dead on the public path. With posix OFF (the default) this is
    byte-identical to before; with posix ON the lexer restricts identifiers to
    the ASCII portable set, consistent with the executor/state-layer name
    validation (`set -o posix` gating in function/read/declare/for/assignment).

    (The historical ``strict`` batch-vs-interactive flag was retired in the
    lexer R2 refactor: the two configs had been identical since the lexer lost
    its error-recovery mode, so the flag selected nothing.)
    """
    config = LexerConfig()
    if shell_options:
        if shell_options.get('extglob', False):
            config.enable_extglob = True
        if shell_options.get('posix', False):
            config.posix_mode = True
    return config


def _post_lex(tokens: List[Token], source: str,
              shell_options: Optional[Mapping[str, Any]] = None) -> List[Token]:
    """The shared post-lex pipeline: keyword normalization, then word fusion.

    Word fusion (``word_fusion.fuse_words``) runs AFTER keyword normalization:
    a maximal run of adjacent word-like tokens becomes ONE WORD token carrying
    the run's parts, so the parser sees one token per shell word and never
    re-assembles a composite. Running it after normalization means reserved
    words are already retyped (and excluded from the word-like set), so a
    keyword adjacent to an expansion (``then$x``) fuses or not exactly as the
    old parser-side ``peek_composite_sequence`` decided. ``source`` supplies the
    fused token's span-faithful lexeme.

    Brace expansion is NO LONGER a lexer pass — it moved to the Word stage
    (``ExpansionManager.brace_expand_word``, driven by
    ``psh.expansion.brace_expansion_words.WordBraceExpander``), where bash
    performs it, so the LIVE ``braceexpand`` option is read per command at
    execution time. That retired the token-stream expander and its
    same-stream ``set``/``shopt`` toggle scanner (a 6-class parse-time
    approximation). ``shell_options`` is retained on the signature for the
    lexer-config path (``_make_config``: extglob/posix) but is no longer read
    here.

    Note: misplaced case terminators (`;;` outside case, etc.) are rejected
    by the parser (see parsers/statements.py), not by a lexer pass.
    """
    from .word_fusion import fuse_words
    return fuse_words(KeywordNormalizer().normalize(tokens), source)


def tokenize(input_string: str, shell_options: Optional[Mapping[str, Any]] = None) -> List[Token]:
    """
    Tokenize a shell command string using the unified lexer implementation.

    This function provides the main entry point for shell tokenization with
    comprehensive Unicode support, metadata tracking, context awareness, and
    enhanced error handling - all features built into the standard Token class.

    Args:
        input_string: The shell command string to tokenize
        shell_options: Optional shell options dict to configure extglob/posix

    Returns:
        List of tokens representing the parsed command
    """
    lexer = ModularLexer(input_string, config=_make_config(shell_options))
    return _post_lex(lexer.tokenize(), input_string, shell_options)


def tokenize_with_heredocs(input_string: str,
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
        shell_options: Optional shell options dict to configure extglob/posix
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

    lexer = HeredocLexer(input_string, config=_make_config(shell_options),
                         source_name=source_name, base_line=base_line,
                         warn_unterminated=warn_unterminated)
    tokens, heredoc_map = lexer.tokenize_with_heredocs()
    return _post_lex(tokens, input_string, shell_options), heredoc_map


__all__ = [
    # Main lexer interface
    'ModularLexer', 'tokenize', 'tokenize_with_heredocs',
    # Configuration
    'LexerConfig',
    # Errors
    'LexerError', 'UnclosedQuoteError',
]
