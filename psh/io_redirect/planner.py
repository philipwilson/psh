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
        if self.procsub is not None:
            self.procsub.close_parent_fd_for_redirect(
                self.redirect, applied=applied)


class RedirectPlanner:
    """Build `RedirectPlan` objects for backend-specific application."""

    def __init__(self, file_redirector: 'FileRedirector'):
        self.file_redirector = file_redirector

    def plan(self, redirect: Redirect) -> RedirectPlan:
        redirect = self.file_redirector._resolved(redirect)
        target = self.file_redirector._expand_redirect_target(redirect)
        target, procsub = (
            self.file_redirector._procsub_handler.resolve_procsub_resource(
                target))
        return RedirectPlan(redirect, target, procsub)
