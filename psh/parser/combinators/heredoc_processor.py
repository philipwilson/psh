"""Heredoc content processor for the shell parser combinator.

After the main parsing phase the redirect nodes that opened a here-document
(``<<``/``<<-``) carry only a ``heredoc_key``; their bodies were collected
separately during lexing. This module copies each collected body into the
redirect it belongs to, in a second pass over the AST.

That second pass is a textbook use of the **visitor pattern**: rather than
re-implement a bespoke walk of every node shape, :class:`HeredocProcessor`
subclasses the shared :class:`~psh.visitor.base.ASTVisitor` and reuses the
common child-traversal (:func:`~psh.visitor.traversal.visit_children`, the same
dataclass-field walk the metrics/security/linter visitors use). It overrides
only what the generic walk cannot do on its own:

* **every node** must populate its *own* heredoc redirects (``generic_visit``);
* **``if``** must additionally reach the ``(condition, body)`` pairs inside
  ``elif_parts`` — those live in *tuples*, and the shared walk yields ASTNode
  children and ASTNode-list elements only, so it steps over tuple-nested nodes
  (``visit_IfConditional``).
"""

from typing import Any, Dict

from ...ast_nodes import ASTNode, IfConditional
from ...visitor.base import ASTVisitor
from ...visitor.traversal import visit_children


class HeredocProcessor(ASTVisitor[None]):
    """Populate heredoc bodies into their Redirect nodes via an AST walk.

    A thin :class:`~psh.visitor.base.ASTVisitor` subclass: ``visit()`` dispatches
    by node type (and caches the lookup); ``generic_visit`` is the default
    action for every node — fill its heredoc redirects, then descend into its
    children. The only per-type override is ``if`` (for its ``elif`` tuples).
    """

    def __init__(self) -> None:
        """Initialize the heredoc processor."""
        super().__init__()
        self._heredoc_contents: Dict[str, Any] = {}

    def populate_heredocs(self, ast: ASTNode,
                          heredoc_contents: Dict[str, Any]) -> None:
        """Copy collected heredoc bodies into the AST's Redirect nodes.

        Walks the AST and, for every redirect that opened a heredoc, copies the
        matching body from ``heredoc_contents`` into its ``heredoc_content``
        (and ``heredoc_quoted``) field.

        Args:
            ast: The root AST node to process.
            heredoc_contents: Map of heredoc key to its body — either a bare
                string, or the heredoc lexer's ``{'content': ..., 'quoted':
                ...}`` entry (the live ``tokenize_with_heredocs`` format).
        """
        if not heredoc_contents:
            return
        self._heredoc_contents = heredoc_contents
        self.visit(ast)

    def generic_visit(self, node: ASTNode) -> None:
        """Populate a node's own heredoc redirects, then descend into children.

        This is the one chokepoint for redirect population, so a trailing
        redirect on a compound (``done <<EOF``, ``fi <<EOF``) is handled exactly
        like a simple command's. ``visit_children`` then recurses into every
        ASTNode child using the shared dataclass-field walk.
        """
        self._populate_redirects(node)
        visit_children(self, node)

    def visit_IfConditional(self, node: IfConditional) -> None:
        """Descend normally, then into the ``elif`` (condition, body) tuples.

        ``elif_parts`` is a list of *tuples*, which the shared child walk does
        not enter (it yields ASTNodes and ASTNode-list elements only), so the
        elif clauses are visited explicitly here.
        """
        self.generic_visit(node)
        for elif_condition, elif_body in node.elif_parts:
            self.visit(elif_condition)
            self.visit(elif_body)

    def _populate_redirects(self, node: ASTNode) -> None:
        """Fill heredoc content on any heredoc redirects this node owns.

        Nodes without a ``redirects`` attribute (words, expansions, patterns …)
        are a no-op. A redirect whose ``heredoc_key`` is absent from the map is
        left untouched (an as-yet-unpopulated or non-heredoc redirect).
        """
        for redirect in getattr(node, 'redirects', None) or ():
            key = getattr(redirect, 'heredoc_key', None)
            if key and key in self._heredoc_contents:
                info = self._heredoc_contents[key]
                if isinstance(info, dict):
                    redirect.heredoc_content = info['content']
                    redirect.heredoc_quoted = info.get('quoted', False)
                else:
                    redirect.heredoc_content = info


# Convenience functions

def create_heredoc_processor() -> HeredocProcessor:
    """Create and return a HeredocProcessor instance.

    Returns:
        Initialized HeredocProcessor object
    """
    return HeredocProcessor()


def populate_heredocs(ast: ASTNode, heredoc_contents: Dict[str, Any]) -> None:
    """Convenience function to populate heredoc content in an AST.

    Args:
        ast: The root AST node to process
        heredoc_contents: Map of heredoc keys to their content
    """
    HeredocProcessor().populate_heredocs(ast, heredoc_contents)
