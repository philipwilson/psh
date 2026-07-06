"""AST Pretty Printer for human-readable output.

This is a GENERIC, structure-driven renderer: it walks each node's dataclass
fields and recurses into child ``ASTNode`` values. It has no per-node methods
to fall out of sync with the AST — every concrete node (and every future one)
renders correctly and exhaustively. The previous hand-written per-node
implementation drifted from the AST (it read obsolete attributes such as
``AndOrList.left``/``operator`` and ``ForLoop.iterable``, had no
``visit_Program``, and dumped raw ``repr`` for lists of child nodes because it
probed a nonexistent ``accept`` method).

For a summarized tree view see ``AsciiTreeRenderer``; this printer is the
exhaustive field-by-field structural dump.
"""

from typing import Any, List, Tuple

from ...ast_nodes import ASTNode
from ...visitor import ASTVisitor

# Node metadata that is not a dataclass field but may shadow one defensively.
_SKIP_ATTRS = frozenset({"line", "column", "position"})


class ASTPrettyPrinter(ASTVisitor[str]):
    """Pretty print an AST with indentation, driven purely by node structure."""

    def __init__(self, indent_size: int = 2, show_positions: bool = False,
                 max_width: int = 80, compact_mode: bool = False):
        """Initialize the pretty printer.

        Args:
            indent_size: Number of spaces per indentation level.
            show_positions: Append ``@line{N}`` when a node carries a source line.
            max_width: Maximum width for a compact single-line node.
            compact_mode: Render all-scalar nodes on one line when they fit.
        """
        super().__init__()
        self.indent_size = indent_size
        self.show_positions = show_positions
        self.max_width = max_width
        self.compact_mode = compact_mode

    # ASTVisitor dispatches every node here (no per-node methods exist), which
    # is exactly what keeps this renderer aligned with the AST.
    def generic_visit(self, node: ASTNode) -> str:
        return self._format_node(node, 0)

    def _pad(self, indent: int) -> str:
        return " " * (indent * self.indent_size)

    def _node_fields(self, node: ASTNode) -> List[Tuple[str, Any]]:
        """Significant (name, value) pairs: dataclass fields that are set.

        Skips ``None``, ``False`` flags, and empty collections (noise), plus
        the ``line`` source metadata (a class attribute, not a field). Derived
        properties such as ``SimpleCommand.args`` are not dataclass fields, so
        they are naturally excluded — the canonical ``words`` are shown instead.
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
            if value is None or value is False:
                continue
            if isinstance(value, (list, tuple)) and len(value) == 0:
                continue
            result.append((name, value))
        return result

    def _format_node(self, node: ASTNode, indent: int) -> str:
        pad = self._pad(indent)
        header = node.__class__.__name__
        if self.show_positions and getattr(node, "line", None) is not None:
            header += f" @line{node.line}"

        node_fields = self._node_fields(node)
        if not node_fields:
            return f"{pad}{header}"

        if self.compact_mode and all(_is_scalar(v) for _, v in node_fields):
            inline = ", ".join(f"{n}={v!r}" for n, v in node_fields)
            line = f"{pad}{header}({inline})"
            if len(line) <= self.max_width:
                return line

        lines = [f"{pad}{header}:"]
        for name, value in node_fields:
            lines.append(self._format_field(name, value, indent + 1))
        return "\n".join(lines)

    def _format_field(self, name: str, value: Any, indent: int) -> str:
        pad = self._pad(indent)
        if isinstance(value, ASTNode):
            return f"{pad}{name}:\n{self._format_node(value, indent + 1)}"
        if isinstance(value, (list, tuple)):
            return self._format_sequence(name, value, indent)
        return f"{pad}{name}: {value!r}"

    def _format_sequence(self, name: str, seq: Any, indent: int) -> str:
        pad = self._pad(indent)
        if len(seq) == 0:
            return f"{pad}{name}: []"
        lines = [f"{pad}{name}: ["]
        for item in seq:
            lines.append(self._format_item(item, indent + 1))
        lines.append(f"{pad}]")
        return "\n".join(lines)

    def _format_item(self, item: Any, indent: int) -> str:
        pad = self._pad(indent)
        if isinstance(item, ASTNode):
            return self._format_node(item, indent)
        if isinstance(item, (list, tuple)):
            # e.g. IfConditional.elif_parts is a list of (condition, then) tuples.
            inner = "\n".join(self._format_item(sub, indent + 1) for sub in item)
            return f"{pad}(\n{inner}\n{pad})"
        return f"{pad}{item!r}"


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def format_ast(ast: ASTNode, **kwargs) -> str:
    """Convenience function to format an AST.

    Args:
        ast: The AST node to format.
        **kwargs: Arguments passed to ``ASTPrettyPrinter``.

    Returns:
        Formatted string representation of the AST.
    """
    formatter = ASTPrettyPrinter(**kwargs)
    return formatter.visit(ast)
