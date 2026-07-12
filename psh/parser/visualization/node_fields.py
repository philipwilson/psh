"""The one structure-driven field walk shared by every AST renderer.

Historically ``ast_formatter``, ``ascii_tree``, ``sexp_renderer`` and
``dot_generator`` each carried their own ``dir(node)`` reflection loop to
discover a node's "significant fields". Those loops drifted apart and, worse,
read *derived properties* (``SimpleCommand.args``, ``Word.is_quoted``,
``BinaryTestExpression.left``) as if they were structural fields — phantom
reads that duplicated real fields and rendered noise.

``node_fields`` is the single answer to "what are this node's fields?": it
walks ``__dataclass_fields__`` in definition order, so it sees exactly the
stored dataclass fields — never a ``@property`` — and stays aligned with the
AST automatically (a new field on any node shows up with no renderer edit).
Per-node ``visit_*`` methods now exist only to customise labels/colours, not
to re-discover fields.
"""

from typing import Any, List, Tuple

from ...ast_nodes import ASTNode

# Source-location metadata carried as plain class/instance attributes rather
# than dataclass fields (``line``), plus two names some nodes might shadow
# defensively. Never rendered as a field — ``show_positions`` reads ``line``
# through the dedicated header path instead.
_SKIP_ATTRS = frozenset({"line", "column", "position"})


def node_fields(node: ASTNode, *, include_empty: bool = False
                ) -> List[Tuple[str, Any]]:
    """Significant ``(name, value)`` pairs for an AST node.

    Walks ``__dataclass_fields__`` in definition order (dispatch-agnostic; no
    per-node methods to fall out of sync). ``line``/``column``/``position``
    metadata is skipped. Derived ``@property`` values (``SimpleCommand.args``,
    ``Word.is_quoted``, ...) are not dataclass fields, so they are excluded —
    this is what removes the old phantom-field reads.

    Args:
        node: The AST node to introspect.
        include_empty: When False (the default), also drop ``None``, ``False``
            flags, and empty collections (noise). When True, keep every
            declared field — the ``show_empty_fields`` mode the renderers
            offer.
    """
    result: List[Tuple[str, Any]] = []
    # __dataclass_fields__ is an ordered dict (definition order); using it
    # keeps this dispatch-agnostic and avoids a typed dataclasses.fields()
    # call on the abstract ASTNode base.
    dc_fields = getattr(node, "__dataclass_fields__", None)
    if not dc_fields:
        return result  # not a dataclass (shouldn't happen for AST nodes)
    for name in dc_fields:
        if name in _SKIP_ATTRS:
            continue
        value = getattr(node, name, None)
        if not include_empty:
            if value is None or value is False:
                continue
            if isinstance(value, (list, tuple)) and len(value) == 0:
                continue
        result.append((name, value))
    return result
