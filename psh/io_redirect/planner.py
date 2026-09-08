"""Shared redirection planning.

Planning is the common part of every redirection backend: dynamic fd-dup
resolution, target expansion, process-substitution creation, and target-fd
classification. Backends still own how the plan is applied.
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from ..ast_nodes import Redirect
from .process_sub import ProcessSubstitutionResource
from .redirect_program import RedirectOp, RedirectProgram, classify_redirect

if TYPE_CHECKING:
    from ..ast_nodes import ProcessSubstitution
    from .file_redirect import FileRedirector
    from .process_sub import ProcessSubstitutionHandler


def redirect_target_fd(redirect: Redirect) -> int:
    """Which file descriptor this redirection targets.

    The ONE classification of "what fd does `[n]<word` touch": an explicit
    ``redirect.fd`` wins, ``&>``/``&>>`` always start at 1, and an omitted
    ``n`` defaults to 0 for the input operators and 1 for the output ones.
    Both the plan below and the null-command status rule
    (``executor/null_command.py``) read it, so `$(exit 5) 0> f` -> 0 and
    `$(exit 5) > f` -> 1 can never disagree between them.
    """
    if redirect.combined:
        return 1
    if redirect.type in ('<<', '<<-', '<<<'):
        return redirect.fd if redirect.fd is not None else 0
    if redirect.fd is not None:
        return redirect.fd
    return 0 if redirect.type.startswith('<') else 1


@dataclass
class RedirectPlan:
    """A resolved redirect plus optional process-substitution resource.

    ``procsub_node`` records the structural fact the planner read from the
    Word AST: it is the ``ProcessSubstitution`` node when the target is a
    whole-word process substitution, else None. The resource in ``procsub`` is
    created FROM that node — nothing downstream re-sniffs the expanded string.
    """
    redirect: Redirect
    target: Optional[str]
    procsub: Optional[ProcessSubstitutionResource] = None
    procsub_node: Optional['ProcessSubstitution'] = None

    @property
    def target_fd(self) -> int:
        return redirect_target_fd(self.redirect)

    @property
    def open_target(self) -> str:
        """The resolved filename this plan OPENS.

        Only the file-opening forms reach it (``<`` ``<>`` ``>`` ``>>`` ``>|``
        ``&>`` ``&>>``), and for those the planner either produced exactly one
        expanded field or already raised bash's "ambiguous redirect" — so the
        target is a string, never None. Stating that here keeps the open sites
        free of bare casts and makes the impossible state fail loudly instead of
        reaching ``open()`` as None.
        """
        if self.target is None:
            raise ValueError(
                f"redirect {self.redirect.type!r} reached an open with no "
                f"resolved target")
        return self.target

    def close_procsub(self, *, applied: bool) -> None:
        """Close this redirect's process-substitution parent fd after applying
        it (unless the dup2 made that fd the redirect's own target). Used by
        the external/permanent redirect paths."""
        if self.procsub is not None:
            self.procsub.close_parent_fd_for_redirect(
                self.redirect, applied=applied)

    def hand_procsub_to_scope(self, handler: 'ProcessSubstitutionHandler') -> None:
        """Hand this redirect's process-substitution parent fd to the enclosing
        ``process_sub_scope()`` instead of closing it. Used by the in-process
        builtin redirect path, where the builtin reads ``/dev/fd/N`` and the fd
        must outlive the single redirect (the scope closes it on exit)."""
        if self.procsub is not None:
            self.procsub.hand_off_to_scope(handler)


class RedirectPlanner:
    """Build `RedirectPlan` objects for backend-specific application."""

    def __init__(self, file_redirector: 'FileRedirector'):
        self.file_redirector = file_redirector

    def plan_program(self, redirects: List[Redirect]) -> RedirectProgram:
        """Classify a command's redirects into ONE typed, source-ordered program.

        This is the sole producer of `RedirectProgram`: the operation KIND is
        computed once here, in exact source order.  Resolution (`plan`) and
        application stay per-operation, performed by the adapter at each
        operation's turn (`RedirectProgram.apply_in_order`), so source-order
        side effects (a substitution fork, a file open) are preserved.
        """
        return RedirectProgram(
            [RedirectOp(classify_redirect(r), r) for r in redirects])

    def plan(self, redirect: Redirect) -> RedirectPlan:
        redirect = self.file_redirector.resolve_dynamic_dup(redirect)
        procsub_node = self.file_redirector.redirect_procsub_node(redirect)
        if procsub_node is not None:
            # Whole-word process substitution: the AST already told us so.
            # Resolve it FROM the node (raw body text) — never re-sniff or
            # re-expand a string.
            target, procsub = (
                self.file_redirector.procsub_handler.resolve_procsub_resource(
                    procsub_node))
        else:
            # A non-procsub redirect is a filename, full stop.
            target = self.file_redirector.expand_redirect_target(redirect)
            procsub = None
        return RedirectPlan(redirect, target, procsub, procsub_node)
