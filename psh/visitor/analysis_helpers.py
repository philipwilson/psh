"""Small shared predicates and traversal for the analysis visitors.

These name checks that more than one analysis visitor (security, validator,
linter) would otherwise spell out inline. The visitors keep their own policy —
which contexts they flag, at what severity, with what message — but share the
underlying classification here.
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


def has_unquoted_expansion(word, arg: str) -> bool:
    """True if *arg* carries an unquoted ``$`` expansion (word-split risk).

    *word* is the Word AST node for *arg*; *arg* is its expanded-source text.
    A wholly-quoted word is safe; otherwise a ``$`` in the text indicates an
    unquoted expansion subject to word splitting / globbing.
    """
    return not word.is_quoted and '$' in arg
