"""
PSH Utils Package

Utility modules supporting shell infrastructure:
- signal_utils: Signal handling with self-pipe pattern and registry
- heredoc_detection: Distinguish heredocs from bit-shift operators
- ast_debug: AST visualization for debugging
- file_tests: File comparison utilities for test expressions
- token_formatter: Token list formatting for debug output
"""

from .ast_debug import print_ast_debug
from .file_tests import file_newer_than, file_older_than, files_same
from .heredoc_detection import (
    HEREDOC_MARKER_RE,
    contains_heredoc,
    has_unclosed_heredoc,
    is_inside_expansion,
    open_heredoc_delimiters,
)
from .signal_utils import SignalNotifier, get_signal_registry
from .token_formatter import TokenFormatter

__all__ = [
    'SignalNotifier',
    'get_signal_registry',
    'contains_heredoc',
    'has_unclosed_heredoc',
    'open_heredoc_delimiters',
    'is_inside_expansion',
    'HEREDOC_MARKER_RE',
    'print_ast_debug',
    'TokenFormatter',
    'file_newer_than',
    'file_older_than',
    'files_same',
]
