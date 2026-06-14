"""Small shared traversal scaffolding for the analysis visitors.

The structured Word-AST inspection the analysis visitors share (variable
reference extraction, word classification) lives in :mod:`word_analysis`; this
module keeps only the redirect-traversal mixin, which is about tree shape rather
than word content.
"""

from ..ast_nodes import ASTNode


class RedirectTraversalMixin:
    """Shared redirect-traversal skeleton for analysis visitors.

    Compound commands (loops, conditionals, groups, function defs, ``[[ ]]``,
    ``(( ))``, ...) carry a ``redirects`` list just like ``SimpleCommand``. A
    visitor whose explicit handler for such a node visits only the
    condition/body but forgets the redirects silently skips analyzing
    ``while ...; done >/etc/passwd``. This mixin gives every analysis visitor
    one correct traversal so the hazard can't recur per handler.

    The per-redirect *action* stays each visitor's own: this method dispatches
    each redirect through ``self.visit(...)``, which lands in that visitor's
    ``visit_Redirect`` (security flags sensitive targets, metrics counts,
    validator warns on syntax, ...). Visitors that intentionally do not
    traverse redirects simply don't call this.
    """

    def _visit_redirects(self, node: ASTNode) -> None:
        """Dispatch every redirect carried by *node* through ``self.visit``."""
        for redirect in getattr(node, 'redirects', []):
            self.visit(redirect)  # type: ignore[attr-defined]
