"""Redirection node."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from .base import ASTNode

if TYPE_CHECKING:
    from .words import Word


@dataclass
class Redirect(ASTNode):
    type: str  # '<', '>', '>>', '<<', '<<-', '<>', '>|', '2>', '2>>', '2>&1', etc.
    target: Optional[str]  # None for fd-dup/close forms (e.g. '>&-', '2>&1')
    fd: Optional[int] = None  # File descriptor (None for stdin/stdout, 2 for stderr, etc.)
    dup_fd: Optional[int] = None  # For duplications like 2>&1
    heredoc_content: Optional[str] = None  # For here documents
    quote_type: Optional[str] = None  # Quote type used (' or " or None) for here strings
    heredoc_quoted: bool = False  # Whether heredoc delimiter was quoted (disables variable expansion)
    combined: bool = False  # True for &> and &>> (redirects both stdout and stderr)
    heredoc_key: Optional[str] = None  # Lexer-assigned key linking to collected heredoc content
    # The parsed Word for a filename-target redirect (`<`/`>`/`>>`/`<>`/`>|`/
    # `&>`/`&>>`). Carries per-part quote context so the executor can apply
    # bash's "ambiguous redirect" rule: an unquoted target that expands +
    # word-splits + globs to ≠1 word is an error. None for fd-dup/close,
    # heredoc, and here-string forms (their targets are handled differently).
    target_word: Optional['Word'] = None
