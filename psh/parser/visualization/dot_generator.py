"""Graphviz DOT generator for AST visualization."""

import html
from typing import Any, Dict, List, Optional

from ...ast_nodes import ASTNode
from ...visitor import ASTVisitor


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
        self.node_ids: Dict[int, str] = {}  # Use id() instead of object as key

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

    def _make_node_id(self, node: Optional[ASTNode] = None) -> str:
        """Generate unique node ID."""
        self.node_counter += 1
        node_id = f"node{self.node_counter}"
        if node:
            self.node_ids[id(node)] = node_id
        return node_id

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

        # Add position info if requested
        if self.show_positions and hasattr(node, 'position'):
            label_parts.append(f"@{node.position}")

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
        node_id = self._make_node_id(node)
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

    def visit_SimpleCommand(self, node) -> str:
        """Generate DOT for simple command."""
        fields = {}
        if hasattr(node, 'args') and node.args:
            cmd = node.args[0] if node.args else "?"
            args = node.args[1:] if len(node.args) > 1 else []
            fields['cmd'] = cmd
            if args and self.compact_nodes:
                fields['args'] = f"({len(args)} args)"

        label = self._format_node_label(node, 'SimpleCommand', fields)
        node_id = self._add_node(node, label)

        # Add connections for complex fields
        if hasattr(node, 'args') and len(node.args) > 1:
            self._process_field(node_id, 'args', node.args[1:])
        if hasattr(node, 'redirects') and node.redirects:
            self._process_field(node_id, 'redirects', node.redirects)
        if hasattr(node, 'variable_assignments') and node.variable_assignments:
            self._process_field(node_id, 'assignments', node.variable_assignments)

        return node_id

    def visit_Pipeline(self, node) -> str:
        """Generate DOT for pipeline."""
        negated = ""
        if hasattr(node, 'negated') and node.negated:
            negated = " (negated)"

        label = self._format_node_label(node, f'Pipeline{negated}')
        node_id = self._add_node(node, label)

        if hasattr(node, 'commands'):
            self._process_field(node_id, 'commands', node.commands)

        return node_id

    def visit_AndOrList(self, node) -> str:
        """Generate DOT for and/or list."""
        ops = getattr(node, 'operators', [])
        op_str = ','.join(ops) if ops else '|'
        label = self._format_node_label(node, f'AndOrList\\n({op_str})')
        node_id = self._add_node(node, label)

        if hasattr(node, 'pipelines') and node.pipelines:
            self._process_field(node_id, 'pipelines', node.pipelines)

        return node_id

    def visit_IfConditional(self, node) -> str:
        """Generate DOT for if conditional."""
        label = self._format_node_label(node, 'IfConditional')
        node_id = self._add_node(node, label)

        if hasattr(node, 'condition'):
            self._process_field(node_id, 'condition', node.condition)
        if hasattr(node, 'then_part'):
            self._process_field(node_id, 'then', node.then_part)
        if hasattr(node, 'elif_parts') and node.elif_parts:
            self._process_field(node_id, 'elif', node.elif_parts)
        if hasattr(node, 'else_part') and node.else_part:
            self._process_field(node_id, 'else', node.else_part)

        return node_id

    def visit_WhileLoop(self, node) -> str:
        """Generate DOT for while loop."""
        label = self._format_node_label(node, 'WhileLoop')
        node_id = self._add_node(node, label)

        if hasattr(node, 'condition'):
            self._process_field(node_id, 'condition', node.condition)
        if hasattr(node, 'body'):
            self._process_field(node_id, 'body', node.body)

        return node_id

    def visit_ForLoop(self, node) -> str:
        """Generate DOT for for loop."""
        fields = {}
        if hasattr(node, 'variable'):
            fields['var'] = node.variable

        label = self._format_node_label(node, 'ForLoop', fields)
        node_id = self._add_node(node, label)

        if hasattr(node, 'iterable'):
            self._process_field(node_id, 'iterable', node.iterable)
        if hasattr(node, 'body'):
            self._process_field(node_id, 'body', node.body)

        return node_id

    def visit_CStyleForLoop(self, node) -> str:
        """Generate DOT for C-style for loop."""
        label = self._format_node_label(node, 'CStyleForLoop')
        node_id = self._add_node(node, label)

        if hasattr(node, 'init') and node.init:
            self._process_field(node_id, 'init', node.init)
        if hasattr(node, 'condition') and node.condition:
            self._process_field(node_id, 'condition', node.condition)
        if hasattr(node, 'update') and node.update:
            self._process_field(node_id, 'update', node.update)
        if hasattr(node, 'body'):
            self._process_field(node_id, 'body', node.body)

        return node_id

    def visit_FunctionDef(self, node) -> str:
        """Generate DOT for function definition."""
        fields = {}
        if hasattr(node, 'name'):
            fields['name'] = node.name

        label = self._format_node_label(node, 'FunctionDef', fields)
        node_id = self._add_node(node, label)

        if hasattr(node, 'body'):
            self._process_field(node_id, 'body', node.body)

        return node_id

    def visit_StatementList(self, node) -> str:
        """Generate DOT for a statement list."""
        count = len(node.statements) if hasattr(node, 'statements') else 0
        label = self._format_node_label(node, f'StatementList\\n({count} stmts)')
        node_id = self._add_node(node, label)

        if hasattr(node, 'statements') and node.statements:
            self._process_field(node_id, 'statements', node.statements)

        return node_id

    def generic_visit(self, node: ASTNode) -> str:
        """Generic visitor for unknown node types."""
        node_name = node.__class__.__name__
        label = self._format_node_label(node, node_name)
        node_id = self._add_node(node, label)

        # Add edges for all significant attributes
        for attr_name in dir(node):
            if (not attr_name.startswith('_') and
                not callable(getattr(node, attr_name)) and
                attr_name not in ['position', 'line', 'column']):
                try:
                    value = getattr(node, attr_name)
                    if value is not None:
                        self._process_field(node_id, attr_name, value)
                except (AttributeError, TypeError):
                    continue

        return node_id

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
        self.node_ids.clear()

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
