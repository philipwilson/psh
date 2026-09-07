"""One typed, source-ordered redirect program (campaign R1).

`RedirectProgram` is the single ordered representation every redirect-dispatch
site consumes.  A command's redirects are classified ONCE — by
``RedirectPlanner.plan_program`` — into typed ``RedirectOp`` operations
(``OPEN_FILE``, ``DUP_FD``, ``CLOSE_FD``, ``HERE_INPUT``, ``COMBINED``,
``VAR_FD``) in exact source order.  ``apply_in_order`` is the one semantic
applicator: it walks the operations left-to-right and applies each
IMMEDIATELY.  There is no representation for a deferred operation — the
fd-and-Python-stream adapters differ only in the per-op callback they supply,
never in the order (#20 H4: builtin fd closes used to be postponed, so a later
``n>&m`` duplicated a descriptor source order had already closed).

Resolution (``RedirectPlanner.plan``: target expansion, process-substitution
creation) stays a per-operation step performed by the adapter AT the operation's
turn, so a substitution fork and a file open keep bash's source-order side
effects.  The operation carries the resolved ``RedirectPlan`` back for the
adapter's cleanup (``plan.close_procsub``).
"""
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Iterator, List, Optional

if TYPE_CHECKING:
    from ..ast_nodes import Redirect
    from .planner import RedirectPlan


class RedirectOpKind(Enum):
    """The typed operation category a redirect performs (computed once)."""

    OPEN_FILE = "open_file"    # <  <>  >  >>  >|
    DUP_FD = "dup_fd"          # >&  <&  (incl. move [n]>&m- : dup then close m)
    CLOSE_FD = "close_fd"      # >&-  <&-
    HERE_INPUT = "here_input"  # <<  <<-  <<<
    COMBINED = "combined"      # &>  &>>
    # var_fd is tested FIRST in classify_redirect, so it claims the named-fd
    # spelling of every operator it supports -- including the here-document and
    # here-string forms added in remediation 2.5, whose content is materialized
    # on a fresh fd >= 10 instead of on stdin (file_redirect.py#apply_var_fd_redirect).
    VAR_FD = "var_fd"          # {v}>  {v}<  {v}>&N  {v}>&-  {v}<<  {v}<<-  {v}<<<


def classify_redirect(redirect: 'Redirect') -> RedirectOpKind:
    """Classify one ``Redirect`` node into its typed operation kind.

    The SOLE place a redirect's operation category is derived — consumers read
    ``op.kind`` rather than re-inspecting ``redirect.type`` strings.  ``var_fd``
    is orthogonal to the operator (a ``{v}>&-`` is both a named-fd allocation
    and a close) but is dispatched as one self-contained VAR_FD operation, so it
    is checked first, exactly as every dispatch site did.
    """
    if redirect.var_fd:
        return RedirectOpKind.VAR_FD
    if redirect.combined:
        return RedirectOpKind.COMBINED
    if redirect.type in ('<<', '<<-', '<<<'):
        return RedirectOpKind.HERE_INPUT
    if redirect.type in ('>&-', '<&-'):
        return RedirectOpKind.CLOSE_FD
    if redirect.type in ('>&', '<&'):
        return RedirectOpKind.DUP_FD
    # '<', '<>', '>', '>>', '>|'
    return RedirectOpKind.OPEN_FILE


def target_fd_of(redirect: 'Redirect') -> int:
    """The fd this redirect RE-POINTS (its left-hand side).

    The one place the default-fd rule lives: ``&>``/``&>>`` name fd 1, an
    explicit ``[n]`` names n, and a bare operator takes 0 for the input
    spellings and 1 for the output ones — the operator DIRECTION only picks the
    default (bash closes fd n for ``n<&-`` and ``n>&-`` alike).
    ``RedirectPlan.target_fd`` delegates here.
    """
    if redirect.combined:
        return 1
    if redirect.type in ('<<', '<<-', '<<<'):
        return redirect.fd if redirect.fd is not None else 0
    if redirect.fd is not None:
        return redirect.fd
    return 0 if redirect.type.startswith('<') else 1


def supplies_frame_stdin(redirect: 'Redirect') -> bool:
    """True when this redirect gives fd 0 an INPUT for the frame that carries it.

    BOTH halves are load-bearing, and each was a live defect on its own:

    * DIRECTION — an OUTPUT redirect that happens to land on fd 0
      (``0> out``, ``0>&1``, ``0>> out``) supplies no input, so the POSIX async
      ``/dev/null`` must still apply. Counting it made
      ``{ cat & wait; } 0>&1`` hand the background reader a write-only fd 0:
      ``cat`` then blocks forever on a terminal (and reports
      ``Bad file descriptor`` elsewhere) where bash returns at once.
    * FD — an input redirect on another descriptor (``3< file``, ``{v}< file``)
      supplies fd 3 / a fd >= 10, not fd 0.

    A CLOSE (``<&-``/``0>&-``) counts when it closes fd 0: bash treats it as a
    stdin redirection too, and the async child inherits the closed descriptor.

    Read by ``manager.py#IOManager.apply_compound_redirections`` — the one
    producer of the fd-0 fact ``core/stdin_binding.py#StdinBinding`` holds.
    """
    kind = classify_redirect(redirect)
    if kind in (RedirectOpKind.VAR_FD, RedirectOpKind.COMBINED):
        return False           # a named fd (>= 10); `&>` is output
    if kind is RedirectOpKind.CLOSE_FD:
        return target_fd_of(redirect) == 0
    if kind is RedirectOpKind.HERE_INPUT:
        return target_fd_of(redirect) == 0
    if kind is RedirectOpKind.DUP_FD:
        return redirect.type == '<&' and target_fd_of(redirect) == 0
    # OPEN_FILE: '<' and '<>' read; '>', '>>', '>|' do not.
    return redirect.type in ('<', '<>') and target_fd_of(redirect) == 0


def list_supplies_frame_stdin(redirects: List['Redirect']) -> bool:
    """True when a redirect LIST gives its frame's fd 0 an input."""
    return any(supplies_frame_stdin(r) for r in redirects)


@dataclass
class RedirectOp:
    """One typed redirect operation with its source location.

    ``plan`` is None until the adapter resolves the operation at its turn (a
    VAR_FD operation never carries a plan — it is self-contained).  The adapter
    stores the resolved plan back so the ordered walk's per-op cleanup
    (``close_procsub``) can find it.
    """

    kind: RedirectOpKind
    redirect: 'Redirect'
    plan: Optional['RedirectPlan'] = None


def is_self_dup(redirect: 'Redirect') -> bool:
    """bash's ``n>&n`` rule: a dup whose source and target fd coincide is an
    unconditional SUCCESS NO-OP — no validation, no syscall, no fd change —
    even when fd n is closed or was never opened (probe-verified vs bash 5.2:
    every universe, both directions, the move spelling ``n>&n-``, and a
    DYNAMICALLY resolved source ``n>&$x`` with x == n).

    POST-RESOLUTION predicate: a dynamic dup carries ``dup_fd=None`` until
    ``resolve_dynamic_dup`` runs, so callers apply this to the plan's resolved
    redirect, never the raw AST node.  The one place the rule is written; every
    dup path (validation, fd apply, save planning, builtin stream half, exec
    stream rebind) consults it.
    """
    return (redirect.type in ('>&', '<&') and not redirect.combined
            and redirect.fd is not None
            and redirect.dup_fd is not None
            and redirect.dup_fd == redirect.fd)


@dataclass
class RedirectProgram:
    """A command's redirects as one typed, source-ordered operation sequence."""

    ops: List[RedirectOp]

    def apply_in_order(self, apply_one: Callable[[RedirectOp], None]) -> None:
        """The one semantic applicator: apply every operation, in source order.

        No deferral is representable — ``apply_one`` runs for each operation
        before the next, so an fd a close operation frees is closed before a
        later dup can read it (#20 H4).  ``apply_one`` is the mechanical
        adapter (fd universe / Python-stream universe).
        """
        for op in self.ops:
            apply_one(op)

    def __iter__(self) -> Iterator[RedirectOp]:
        return iter(self.ops)

    def __len__(self) -> int:
        return len(self.ops)

    def __bool__(self) -> bool:
        return bool(self.ops)
