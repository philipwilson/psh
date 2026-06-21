"""Shared redirection planning.

Planning is the common part of every redirection backend: dynamic fd-dup
resolution, target expansion, process-substitution creation, and target-fd
classification. Backends still own how the plan is applied.
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ..ast_nodes import Redirect
from .process_sub import ProcessSubstitutionResource

if TYPE_CHECKING:
    from .file_redirect import FileRedirector
    from .process_sub import ProcessSubstitutionHandler


@dataclass
class RedirectPlan:
    """A resolved redirect plus optional process-substitution resource."""
    redirect: Redirect
    target: Optional[str]
    procsub: Optional[ProcessSubstitutionResource] = None

    @property
    def target_fd(self) -> int:
        if self.redirect.combined:
            return 1
        if self.redirect.type in ('<<', '<<-', '<<<'):
            return self.redirect.fd if self.redirect.fd is not None else 0
        if self.redirect.fd is not None:
            return self.redirect.fd
        return 0 if self.redirect.type.startswith('<') else 1

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

    def plan(self, redirect: Redirect) -> RedirectPlan:
        redirect = self.file_redirector.resolve_dynamic_dup(redirect)
        target = self.file_redirector.expand_redirect_target(redirect)
        target, procsub = (
            self.file_redirector.procsub_handler.resolve_procsub_resource(
                target))
        return RedirectPlan(redirect, target, procsub)
