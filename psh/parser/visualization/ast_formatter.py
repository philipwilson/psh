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

from typing import Any

from ...ast_nodes import ASTNode
from ...visitor import ASTVisitor
from .node_fields import node_fields


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

    def _format_node(self, node: ASTNode, indent: int) -> str:
        pad = self._pad(indent)
        header = node.__class__.__name__
        if self.show_positions and getattr(node, "line", None) is not None:
            header += f" @line{node.line}"

        fields = node_fields(node)
        if not fields:
            return f"{pad}{header}"

        if self.compact_mode and all(_is_scalar(v) for _, v in fields):
            inline = ", ".join(f"{n}={v!r}" for n, v in fields)
            line = f"{pad}{header}({inline})"
            if len(line) <= self.max_width:
                return line

        lines = [f"{pad}{header}:"]
        for name, value in fields:
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
