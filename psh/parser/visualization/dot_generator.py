"""Graphviz DOT generator for AST visualization."""

import html
from typing import Any, Dict, List, Optional

from ...ast_nodes import ASTNode
from ...visitor import ASTVisitor
from .node_fields import node_fields


class ASTDotGenerator(ASTVisitor[str]):
    """Generate Graphviz DOT format from AST for visual diagrams."""

    def __init__(self, graph_name: str = "AST", show_positions: bool = False,
                 compact_nodes: bool = True, color_by_type: bool = True):
        """Initialize the DOT generator.

        Args:
            graph_name: Name of the generated graph
            show_positions: Whether to include token positions in labels
            compact_nodes: Whether to use compact node representations
            color_by_type: Whether to color nodes by their type
        """
        super().__init__()
        self.graph_name = graph_name
        self.show_positions = show_positions
        self.compact_nodes = compact_nodes
        self.color_by_type = color_by_type

        self.node_counter = 0
        self.nodes: List[str] = []
        self.edges: List[str] = []

        # Color scheme for different node types
        self.type_colors = {
            'SimpleCommand': '#E3F2FD',      # Light blue
            'Pipeline': '#E8F5E8',           # Light green
            'IfConditional': '#FFF3E0',      # Light orange
            'WhileLoop': '#F3E5F5',          # Light purple
            'ForLoop': '#F3E5F5',            # Light purple
            'CStyleForLoop': '#F3E5F5',      # Light purple
            'FunctionDef': '#FFEBEE',        # Light red
            'CaseConditional': '#E0F2F1',    # Light teal
            'StatementList': '#F5F5F5',      # Light gray
            'Program': '#F5F5F5',            # Light gray
            'AndOrList': '#E1F5FE',          # Light cyan
            'Redirect': '#FFF8E1',           # Light yellow
        }

    def _make_node_id(self) -> str:
        """Generate unique node ID."""
        self.node_counter += 1
        return f"node{self.node_counter}"

    def _escape_label(self, text: str) -> str:
        """Escape text for DOT labels."""
        return html.escape(str(text), quote=True)

    def _get_node_color(self, node_type: str) -> str:
        """Get color for node type."""
        if not self.color_by_type:
            return '#FFFFFF'
        return self.type_colors.get(node_type, '#F0F0F0')

    def _format_node_label(self, node: ASTNode, base_label: str,
                          fields: Optional[Dict[str, Any]] = None) -> str:
        """Format a node label with optional fields."""
        label_parts = [base_label]

        # Add position info if requested. Reads the parser-stamped ``line``
        # (matching the other renderers); AST nodes carry no ``position``, so
        # the old hasattr check made show_positions a silent no-op.
        if self.show_positions and getattr(node, 'line', None) is not None:
            label_parts.append(f"@line{node.line}")

        # Add compact field info if requested
        if self.compact_nodes and fields:
            for name, value in fields.items():
                if value is not None and not isinstance(value, (list, ASTNode)):
                    if isinstance(value, str) and len(value) < 20:
                        label_parts.append(f"{name}: {value}")
                    elif isinstance(value, (int, bool)):
                        label_parts.append(f"{name}: {value}")

        return "\\n".join(label_parts)

    def _add_node(self, node: ASTNode, label: str, shape: str = "box",
                  style: str = "filled") -> str:
        """Add a node to the graph."""
        node_id = self._make_node_id()
        color = self._get_node_color(node.__class__.__name__)

        escaped_label = self._escape_label(label)
        node_def = (f'{node_id} [label="{escaped_label}", shape={shape}, '
                   f'style={style}, fillcolor="{color}"];')
        self.nodes.append(node_def)

        return node_id

    def _add_edge(self, from_id: str, to_id: str, label: str = "",
                  style: str = "solid") -> None:
        """Add an edge to the graph."""
        edge_attrs = []
        if label:
            edge_attrs.append(f'label="{self._escape_label(label)}"')
        if style != "solid":
            edge_attrs.append(f'style={style}')

        attrs_str = f' [{", ".join(edge_attrs)}]' if edge_attrs else ""
        self.edges.append(f'{from_id} -> {to_id}{attrs_str};')

    def _process_field(self, parent_id: str, field_name: str, value: Any) -> None:
        """Process a field and add appropriate nodes/edges."""
        if value is None:
            return
        elif isinstance(value, ASTNode):
            child_id = self.visit(value)
            self._add_edge(parent_id, child_id, field_name)
        elif isinstance(value, list):
            if not value:
                return

            # Create a collection node for lists with multiple items
            if len(value) > 1:
                list_id = self._make_node_id()
                list_label = f"{field_name}\\n[{len(value)} items]"
                self.nodes.append(f'{list_id} [label="{list_label}", shape=ellipse, '
                                f'style=filled, fillcolor="#F5F5F5"];')
                self._add_edge(parent_id, list_id, field_name)

                for i, item in enumerate(value):
                    if isinstance(item, ASTNode):
                        item_id = self.visit(item)
                        self._add_edge(list_id, item_id, str(i))
                    else:
                        item_id = self._make_node_id()
                        item_label = str(item)[:30] + ("..." if len(str(item)) > 30 else "")
                        self.nodes.append(f'{item_id} [label="{self._escape_label(item_label)}", '
                                        f'shape=ellipse, style=filled, fillcolor="#EEEEEE"];')
                        self._add_edge(list_id, item_id, str(i))
            else:
                # Single item - connect directly
                item = value[0]
                if isinstance(item, ASTNode):
                    item_id = self.visit(item)
                    self._add_edge(parent_id, item_id, field_name)
                else:
                    item_id = self._make_node_id()
                    item_label = str(item)[:30] + ("..." if len(str(item)) > 30 else "")
                    self.nodes.append(f'{item_id} [label="{self._escape_label(item_label)}", '
                                    f'shape=ellipse, style=filled, fillcolor="#EEEEEE"];')
                    self._add_edge(parent_id, item_id, field_name)

    def _emit(self, node: ASTNode, label: str) -> str:
        """Add ``node`` with ``label``, then wire every structural child edge.

        Field edges are driven by the shared ``node_fields`` walk (labelled
        with the field name), so a for-loop's ``items``/``item_words`` or a
        C-style loop's ``*_expr`` fields can never silently drop out again —
        the per-node methods below customise only the label, never the wiring.
        """
        node_id = self._add_node(node, label)
        for name, value in node_fields(node):
            self._process_field(node_id, name, value)
        return node_id

    def visit_SimpleCommand(self, node) -> str:
        """Generate DOT for simple command (label carries cmd + arg count)."""
        fields = {}
        if node.args:
            fields['cmd'] = node.args[0]
            if len(node.args) > 1 and self.compact_nodes:
                fields['args'] = f"({len(node.args) - 1} args)"
        return self._emit(node, self._format_node_label(node, 'SimpleCommand', fields))

    def visit_Pipeline(self, node) -> str:
        """Generate DOT for pipeline (label notes negation)."""
        negated = " (negated)" if getattr(node, 'negated', False) else ""
        return self._emit(node, self._format_node_label(node, f'Pipeline{negated}'))

    def visit_AndOrList(self, node) -> str:
        """Generate DOT for and/or list.

        The label shows the &&/|| operators between the pipelines. A list with
        a single pipeline has NO operator, so it gets a bare ``AndOrList``
        label — the old ``(|)`` fallback mislabelled it with the pipe operator.
        """
        ops = getattr(node, 'operators', [])
        base = f'AndOrList\\n({",".join(ops)})' if ops else 'AndOrList'
        return self._emit(node, self._format_node_label(node, base))

    def visit_ForLoop(self, node) -> str:
        """Generate DOT for for loop (label carries the loop variable)."""
        fields = {'var': node.variable} if getattr(node, 'variable', None) else {}
        return self._emit(node, self._format_node_label(node, 'ForLoop', fields))

    def visit_FunctionDef(self, node) -> str:
        """Generate DOT for function definition (label carries the name)."""
        fields = {'name': node.name} if getattr(node, 'name', None) else {}
        return self._emit(node, self._format_node_label(node, 'FunctionDef', fields))

    def visit_StatementList(self, node) -> str:
        """Generate DOT for a statement list (label carries the count)."""
        count = len(node.statements) if hasattr(node, 'statements') else 0
        return self._emit(node, self._format_node_label(node, f'StatementList\\n({count} stmts)'))

    def generic_visit(self, node: ASTNode) -> str:
        """Generic visitor: class-name label + structural field edges.

        Nodes with no label customisation (IfConditional, WhileLoop,
        CStyleForLoop, test expressions, ...) land here and now render every
        real field via ``_emit`` — no per-node method to drift.
        """
        return self._emit(node, self._format_node_label(node, node.__class__.__name__))

    def to_dot(self, ast: ASTNode) -> str:
        """Convert AST to DOT format.

        Args:
            ast: Root AST node to convert

        Returns:
            DOT format string
        """
        # Reset state
        self.node_counter = 0
        self.nodes.clear()
        self.edges.clear()

        # Visit the AST
        self.visit(ast)

        # Generate DOT output
        dot_lines = [
            f'digraph {self.graph_name} {{',
            '    rankdir=TB;',
            '    node [fontname="Helvetica", fontsize=10];',
            '    edge [fontname="Helvetica", fontsize=8];',
            ''
        ]

        # Add nodes
        if self.nodes:
            dot_lines.append('    // Nodes')
            for node in self.nodes:
                dot_lines.append(f'    {node}')
            dot_lines.append('')

        # Add edges
        if self.edges:
            dot_lines.append('    // Edges')
            for edge in self.edges:
                dot_lines.append(f'    {edge}')

        dot_lines.append('}')

        return '\n'.join(dot_lines)


def generate_dot(ast: ASTNode, **kwargs) -> str:
    """Convenience function to generate DOT from AST.

    Args:
        ast: The AST node to convert
        **kwargs: Arguments passed to ASTDotGenerator

    Returns:
        DOT format string
    """
    generator = ASTDotGenerator(**kwargs)
    return generator.to_dot(ast)
