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
    VAR_FD = "var_fd"          # {v}>  {v}<  {v}>&N  {v}>&-


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
