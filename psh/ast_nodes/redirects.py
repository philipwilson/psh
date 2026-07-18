"""Redirection node."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from .base import ASTNode

if TYPE_CHECKING:
    from .words import Word


@dataclass
class Redirect(ASTNode):
    type: str  # '<', '>', '>>', '<<', '<<-', '<>', '>|', '2>', '2>>', '2>&1', etc.
    # For a heredoc ('<<'/'<<-') this is the RAW delimiter word exactly as
    # spelled in the source (`$X`, `'EOF'`, `$'EOF'`, `E"O"F`) — what the
    # formatter re-emits; the literal terminator derives from it through the
    # one quote-removal rule (utils.heredoc_detection). None for fd-dup/close
    # forms (e.g. '>&-', '2>&1').
    target: Optional[str]
    fd: Optional[int] = None  # File descriptor (None for stdin/stdout, 2 for stderr, etc.)
    dup_fd: Optional[int] = None  # For duplications like 2>&1
    # The collected here-document body. On every live (heredoc-aware) parse
    # path this is attached AS THE NODE IS CONSTRUCTED and is never None for
    # a heredoc redirect ('' for an empty body); the executor treats a None
    # body at execution as an internal defect. None only on bare token-level
    # parses with no collected bodies (unit-test paths) and for non-heredoc
    # redirect kinds.
    heredoc_content: Optional[str] = None
    quote_type: Optional[str] = None  # Quote type used (' or " or None) for here strings
    heredoc_quoted: bool = False  # Whether heredoc delimiter was quoted (disables variable expansion)
    combined: bool = False  # True for &> and &>> (redirects both stdout and stderr)
    # Move form `[n]>&m-` / `[n]<&m-`: duplicate fd `dup_fd` onto `fd`, then
    # close the source `dup_fd` (bash keeps it open when dup_fd == fd).
    move: bool = False
    # The heredoc's stable spec id (its ORDINAL within the lexed unit —
    # identity is positional, never delimiter text), linking this redirect
    # to the LexedUnit's collected-heredoc entry. None for non-heredoc
    # redirects and bare parses.
    heredoc_id: Optional[int] = None
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
