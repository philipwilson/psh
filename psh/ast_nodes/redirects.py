"""Redirection nodes.

Two types, and the split IS the invariant (remediation 2.5, #22 MEDIUM-10):

* :class:`Redirect` — every redirection kind. A ``Redirect`` whose ``type`` is
  a heredoc operator (``<<``/``<<-``) is **structurally a heredoc but NOT
  executable**: it is the incomplete PARSE STATE a bare token-level parse
  produces when no bodies were collected (bodies are still in the token
  stream). It carries no body and never will.
* :class:`HeredocRedirect` — the **only executable** here-document form. Its
  body is non-optional, so "an executable heredoc with no collected body" is
  unrepresentable rather than discovered late at execution.

Execution dispatches on the TYPE, not on the operator string — see
``io_redirect/file_redirect.py#FileRedirector.apply_fd_plan``; a
structurally-heredoc plain ``Redirect`` that reaches execution raises the typed
``io_redirect/file_redirect.py#NonExecutableRedirectError``.

Here-strings (``<<<``) are NOT part of this split: their content has always
lived in ``target``/``target_word``, never in a heredoc body field, so ``<<<``
stays a plain :class:`Redirect` (see
``io_redirect/file_redirect.py#FileRedirector.redirect_herestring``).
"""

from dataclasses import dataclass, field
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


@dataclass
class HeredocRedirect(Redirect):
    """The EXECUTABLE here-document redirect: its body is NON-OPTIONAL.

    Only this class can carry a here-document body, and ``heredoc_content`` is
    a required keyword with no default — ``HeredocRedirect(type='<<',
    target='EOF')`` raises ``TypeError`` at construction. The invalid
    executable state (#22 MEDIUM-10: an executable heredoc with
    ``heredoc_content=None``) is therefore unrepresentable rather than
    discovered at execution.

    Every heredoc-aware parse path that COLLECTED the bodies constructs this
    class, attaching the body from the ``LexedUnit``'s collected entry as the
    node is built (an empty body is ``''``, never ``None``). A parse whose
    bodies were NOT collected constructs a plain :class:`Redirect` instead —
    structurally a heredoc, honestly not executable. Two such routes exist: a
    bare token-level parse (bodies still in the token stream), and ALIAS
    SUBSTITUTION, which happens after the lex, so an alias expanding to
    ``cat <<EOF`` yields a heredoc operator whose body was never gathered.
    The alias route is LIVE USER INPUT (``alias foo='cat <<EOF'; foo``), not a
    theoretical case; execution reports it through
    ``io_redirect/file_redirect.py#NonExecutableRedirectError``.

    Visitor dispatch is EXACT-CLASS (``visitor/base.py#ASTVisitor.visit``
    resolves ``visit_{class name}`` with no MRO walk), so every visitor that
    handles ``Redirect`` declares ``visit_HeredocRedirect`` too; a visitor that
    forgets fails ``tests/unit/visitor/test_ast_coverage_matrix.py``. The class
    is likewise registered in ``visitor/traversal.py#AstChildSchema``.
    """

    # Required keyword: no default, so it cannot be omitted, and `kw_only`
    # because the base class's fields already carry defaults.
    heredoc_content: str = field(kw_only=True)
