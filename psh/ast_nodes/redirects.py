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
    # Move form `[n]>&m-` / `[n]<&m-`: duplicate fd `dup_fd` onto `fd`, then
    # close the source `dup_fd` (bash keeps it open when dup_fd == fd).
    move: bool = False
    heredoc_key: Optional[str] = None  # Lexer-assigned key linking to collected heredoc content
    # Named file descriptor: the variable from a `{varname}>file` prefix. The
    # shell allocates a free fd >= 10, opens onto it, and stores the number in
    # this variable (bash). The allocation is PERMANENT (not auto-closed after
    # the command) and parent-side; `{varname}>&-` closes the fd in the var.
    var_fd: Optional[str] = None
    # The parsed Word for a filename-target redirect (`<`/`>`/`>>`/`<>`/`>|`/
    # `&>`/`&>>`) — and for a here-string (`<<<`), which both parsers also set
    # and `redirect_herestring` consumes. Carries per-part quote context so the
    # executor can apply bash's "ambiguous redirect" rule: an unquoted target
    # that expands + word-splits + globs to ≠1 word is an error. None for
    # fd-dup/close and heredoc forms (their targets are handled differently).
    target_word: Optional['Word'] = None
