"""S-expression renderer for Lisp-style AST visualization."""

from typing import Any, List, Optional

from ...ast_nodes import ASTNode


class SExpressionRenderer:
    """Render AST as S-expressions (Lisp-style syntax)."""

    def __init__(self, compact_mode: bool = False, max_width: int = 80,
                 show_empty_fields: bool = False, show_positions: bool = False):
        """Initialize the S-expression renderer.

        Args:
            compact_mode: Whether to use compact single-line format when possible
            max_width: Maximum width before breaking to multiple lines
            show_empty_fields: Whether to show fields with None/empty values
            show_positions: Whether to show token positions
        """
        self.compact_mode = compact_mode
        self.max_width = max_width
        self.show_empty_fields = show_empty_fields
        self.show_positions = show_positions

    @staticmethod
    def render(node: ASTNode, **kwargs) -> str:
        """Render AST node as S-expression.

        Args:
            node: Root AST node to render
            **kwargs: Arguments passed to SExpressionRenderer

        Returns:
            S-expression representation
        """
        renderer = SExpressionRenderer(**kwargs)
        return renderer._render_node(node)

    def _render_node(self, node: ASTNode, indent: int = 0) -> str:
        """Render a single node as S-expression."""
        if node is None:
            return "nil"

        node_name = node.__class__.__name__
        fields = self._get_node_fields(node)

        if not fields:
            return f"({node_name})"

        # Try compact format first
        compact_repr = self._try_compact_format(node_name, fields)
        if self.compact_mode and compact_repr and len(compact_repr) <= self.max_width:
            return compact_repr

        # Multi-line format
        indent_str = "  " * indent
        next_indent = indent + 1

        parts = [f"({node_name}"]

        for field_name, field_value in fields:
            field_repr = self._render_field(field_name, field_value, next_indent)
            parts.append(f"\n{indent_str}  {field_repr}")

        return "".join(parts) + ")"

    def _try_compact_format(self, node_name: str, fields: List[tuple]) -> Optional[str]:
        """Try to render as compact single-line format."""
        if not fields:
            return f"({node_name})"

        # Special compact formats for common nodes
        if node_name == "SimpleCommand" and len(fields) == 1 and fields[0][0] == "arguments":
            args = fields[0][1]
            if isinstance(args, list) and all(isinstance(arg, str) for arg in args):
                args_str = " ".join(f'"{arg}"' if " " in arg else arg for arg in args)
                return f"(SimpleCommand {args_str})"

        # General compact format - only for small simple values
        if len(fields) <= 2 and all(self._is_simple_value(f[1]) for f in fields):
            field_strs = []
            for name, value in fields:
                field_strs.append(f":{name} {self._format_simple_value(value)}")

            result = f"({node_name} {' '.join(field_strs)})"
            if len(result) <= self.max_width:
                return result

        return None

    def _get_node_fields(self, node: ASTNode) -> List[tuple]:
        """Get significant fields from a node."""
        fields = []

        # Special handling for different node types
        if node.__class__.__name__ == 'SimpleCommand':
            return self._get_simple_command_fields(node)
        elif node.__class__.__name__ == 'StatementList':
            return self._get_statement_list_fields(node)
        elif node.__class__.__name__ == 'AndOrList':
            return self._get_and_or_list_fields(node)

        # Get all non-private attributes
        for attr_name in dir(node):
            if (not attr_name.startswith('_') and
                not callable(getattr(node, attr_name)) and
                attr_name not in ['position', 'line', 'column']):
                try:
                    value = getattr(node, attr_name)
                    if value is not None or self.show_empty_fields:
                        # Skip empty lists unless show_empty_fields is True
                        if isinstance(value, list) and not value and not self.show_empty_fields:
                            continue
                        # Skip false boolean values to reduce noise
                        if isinstance(value, bool) and value is False:
                            continue
                        fields.append((attr_name, value))
                except (AttributeError, TypeError):
                    continue

        return fields

    def _get_simple_command_fields(self, node) -> List[tuple]:
        """Get fields for SimpleCommand with compact argument representation."""
        fields = []

        # Show arguments simply
        args = getattr(node, 'args', [])
        if args:
            fields.append(('arguments', args))

        # Add other significant fields
        redirects = getattr(node, 'redirects', [])
        if redirects:
            fields.append(('redirects', redirects))

        background = getattr(node, 'background', False)
        if background:
            fields.append(('background', background))

        array_assignments = getattr(node, 'array_assignments', [])
        if array_assignments:
            fields.append(('array_assignments', array_assignments))

        return fields

    def _get_statement_list_fields(self, node) -> List[tuple]:
        """Get fields for StatementList without duplication."""
        fields = []
        statements = getattr(node, 'statements', [])
        if statements or self.show_empty_fields:
            fields.append(('statements', statements))
        return fields

    def _get_and_or_list_fields(self, node) -> List[tuple]:
        """Get fields for AndOrList in S-expression format."""
        fields: List[tuple] = []

        pipelines = getattr(node, 'pipelines', [])
        operators = getattr(node, 'operators', [])

        if not pipelines:
            return fields

        # For S-expressions, represent as a structured expression
        if operators:
            # Build a nested structure: (|| (& cmd1 cmd2) cmd3)
            expr = self._build_sexp_operator_tree(pipelines, operators)
            fields.append(('expression', expr))
        else:
            fields.append(('pipelines', pipelines))

        return fields

    def _build_sexp_operator_tree(self, pipelines, operators):
        """Build S-expression operator tree."""
        if not operators:
            return pipelines[0] if pipelines else None

        # Build left-associative tree
        result = pipelines[0]

        for i, operator in enumerate(operators):
            right_pipeline = pipelines[i + 1] if i + 1 < len(pipelines) else None
            if right_pipeline is not None:
                # Create operator list: (operator left right)
                op_symbol = "&&" if operator == "&&" else "||"
                result = [op_symbol, result, right_pipeline]

        return result

    def _render_field(self, field_name: str, field_value: Any, indent: int) -> str:
        """Render a field as S-expression."""
        if field_value is None:
            return f":{field_name} nil"
        elif isinstance(field_value, bool):
            return f":{field_name} {str(field_value).lower()}"
        elif isinstance(field_value, (str, int, float)):
            return f":{field_name} {self._format_simple_value(field_value)}"
        elif isinstance(field_value, list):
            if not field_value:
                return f":{field_name} ()"
            elif len(field_value) == 1 and isinstance(field_value[0], ASTNode):
                # Single node - render inline
                node_repr = self._render_node(field_value[0], indent + 1)
                return f":{field_name} {node_repr}"
            elif all(self._is_simple_value(item) for item in field_value):
                # All simple values - render as list
                items = " ".join(self._format_simple_value(item) for item in field_value)
                return f":{field_name} ({items})"
            else:
                # Mixed or complex values - multi-line
                item_strs = []
                for item in field_value:
                    if isinstance(item, ASTNode):
                        item_strs.append(self._render_node(item, indent + 1))
                    elif isinstance(item, list):
                        item_strs.append(self._render_sexp_list(item, indent + 1))
                    else:
                        item_strs.append(self._format_simple_value(item))

                if len(field_value) <= 3 and all(len(str(item)) < 40 for item in item_strs):
                    # Compact list format
                    items_str = " ".join(str(item) for item in item_strs)
                    return f":{field_name} ({items_str})"
                else:
                    # Multi-line list format
                    indent_str = "  " * indent
                    items_str = f"\n{indent_str}  ".join(str(item) for item in item_strs)
                    return f":{field_name} ({items_str})"
        elif isinstance(field_value, ASTNode):
            node_repr = self._render_node(field_value, indent + 1)
            return f":{field_name} {node_repr}"
        else:
            return f":{field_name} {self._format_simple_value(field_value)}"

    def _render_sexp_list(self, items: List[Any], indent: int) -> str:
        """Render a list in S-expression format."""
        if not items:
            return "()"

        # Special handling for operator expressions
        if (len(items) == 3 and isinstance(items[0], str) and
            items[0] in ["&&", "||"]):
            # Operator expression: (op left right)
            op, left, right = items
            left_repr = (self._render_node(left, 0) if isinstance(left, ASTNode)
                        else self._render_sexp_list(left, 0) if isinstance(left, list)
                        else self._format_simple_value(left))
            right_repr = (self._render_node(right, 0) if isinstance(right, ASTNode)
                         else self._render_sexp_list(right, 0) if isinstance(right, list)
                         else self._format_simple_value(right))
            return f"({op} {left_repr} {right_repr})"

        # Regular list
        if all(self._is_simple_value(item) for item in items):
            items_str = " ".join(self._format_simple_value(item) for item in items)
            return f"({items_str})"
        else:
            rendered_items = []
            for item in items:
                if isinstance(item, ASTNode):
                    rendered_items.append(self._render_node(item, 0))
                elif isinstance(item, list):
                    rendered_items.append(self._render_sexp_list(item, 0))
                else:
                    rendered_items.append(self._format_simple_value(item))

            items_str = " ".join(rendered_items)
            return f"({items_str})"

    def _is_simple_value(self, value: Any) -> bool:
        """Check if a value is simple (string, number, boolean)."""
        return isinstance(value, (str, int, float, bool)) or value is None

    def _format_simple_value(self, value: Any) -> str:
        """Format a simple value for S-expression output."""
        if value is None:
            return "nil"
        elif isinstance(value, bool):
            return str(value).lower()
        elif isinstance(value, str):
            # Quote strings that contain spaces or special characters
            if " " in value or any(c in value for c in "()[]{}\"'\\"):
                return f'"{value}"'
            else:
                return value
        else:
            return str(value)
