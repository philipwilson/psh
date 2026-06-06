"""Shared AST child traversal for analysis visitors.

Several analysis visitors (metrics, security, linter) need a ``generic_visit``
that simply descends into a node's children when there is no specific handler.
They previously carried three separate implementations — two that walked only
one of ``items``/``statements``/``body`` (so they missed children of any other
shape) and one dataclass-field walk. This module is the single source of truth:
the dataclass-field walk, which visits every ``ASTNode`` child regardless of the
attribute name.

Visitors whose ``generic_visit`` is intentionally non-traversing (the
validators' ``pass``) or that build output strings (formatter, debug) are not
affected — they keep their own ``generic_visit``.
"""

import dataclasses

from ..ast_nodes import ASTNode


def iter_child_nodes(node: ASTNode):
    """Yield each direct ``ASTNode`` child of *node*.

    Walks the node's dataclass fields, yielding any value that is an
    ``ASTNode`` and any ``ASTNode`` element of a list-valued field. Non-AST
    values (strings, ints, dicts, …) are ignored.
    """
    if not dataclasses.is_dataclass(node):
        return
    for field in dataclasses.fields(node):
        attr = getattr(node, field.name, None)
        if isinstance(attr, ASTNode):
            yield attr
        elif isinstance(attr, list):
            for item in attr:
                if isinstance(item, ASTNode):
                    yield item


def visit_children(visitor, node: ASTNode) -> None:
    """Visit every direct ``ASTNode`` child of *node* with *visitor*."""
    for child in iter_child_nodes(node):
        visitor.visit(child)
