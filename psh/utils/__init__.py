"""
PSH Utils Package

Utility modules supporting shell infrastructure:
- signal_utils: Signal handling with self-pipe pattern and registry
- heredoc_detection: Distinguish heredocs from bit-shift operators
- ast_debug: AST visualization for debugging
- file_tests: File comparison utilities for test expressions
"""

from .ast_debug import print_ast_debug
from .file_tests import file_newer_than, file_older_than, files_same
from .heredoc_detection import (
    HEREDOC_MARKER_RE,
    CollectedHeredoc,
    HeredocSpec,
    HeredocTermination,
    PendingHeredocQueue,
    contains_heredoc,
    has_unclosed_heredoc,
    heredoc_terminator_matches,
    is_inside_expansion,
    make_heredoc_spec,
    open_heredoc_specs,
)
from .signal_utils import SignalNotifier, get_signal_registry

__all__ = [
    'SignalNotifier',
    'get_signal_registry',
    'CollectedHeredoc',
    'HeredocSpec',
    'HeredocTermination',
    'PendingHeredocQueue',
    'contains_heredoc',
    'has_unclosed_heredoc',
    'heredoc_terminator_matches',
    'make_heredoc_spec',
    'open_heredoc_specs',
    'is_inside_expansion',
    'HEREDOC_MARKER_RE',
    'print_ast_debug',
    'file_newer_than',
    'file_older_than',
    'files_same',
]
