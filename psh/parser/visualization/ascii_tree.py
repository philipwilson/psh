"""ASCII tree renderer for terminal-friendly AST visualization."""

from typing import Any, List, Tuple

from ...ast_nodes import ASTNode


class AsciiTreeRenderer:
    """Render AST as ASCII art tree structure."""

    def __init__(self, show_positions: bool = False, max_width: int = 80,
                 compact_mode: bool = False, show_empty_fields: bool = False):
        """Initialize the ASCII tree renderer.

        Args:
            show_positions: Whether to show token positions
            max_width: Maximum width before truncating labels
            compact_mode: Whether to use compact representations
            show_empty_fields: Whether to show fields with None/empty values
        """
        self.show_positions = show_positions
        self.max_width = max_width
        self.compact_mode = compact_mode
        self.show_empty_fields = show_empty_fields

        # Tree drawing characters
        self.chars = {
            'branch': '├── ',
            'last_branch': '└── ',
            'vertical': '│   ',
            'space': '    ',
            'leaf': '◦ ',
            'list_item': '• ',
        }

    @staticmethod
    def render(node: ASTNode, **kwargs) -> str:
        """Render AST node as ASCII tree.

        Args:
            node: Root AST node to render
            **kwargs: Arguments passed to AsciiTreeRenderer

        Returns:
            ASCII tree representation
        """
        renderer = AsciiTreeRenderer(**kwargs)
        return renderer._render_node(node, "", True)

    def _truncate_text(self, text: str) -> str:
        """Truncate text if it exceeds max width."""
        if len(text) <= self.max_width:
            return text
        return text[:self.max_width-3] + "..."

    def _format_node_label(self, node: ASTNode) -> str:
        """Format the main label for a node."""
        label = node.__class__.__name__

        if self.show_positions and hasattr(node, 'position'):
            label += f" @{node.position}"

        return self._truncate_text(label)

    def _format_simple_value(self, value: Any) -> str:
        """Format a simple value for display."""
        if isinstance(value, str):
            if len(value) > 30:
                return f'"{value[:27]}..."'
            return f'"{value}"'
        elif isinstance(value, bool):
            return str(value).lower()
        else:
            return str(value)

    def _get_node_fields(self, node: ASTNode) -> List[Tuple[str, Any]]:
        """Get significant fields from a node."""
        fields = []

        # Special handling for SimpleCommand to combine arguments compactly
        if node.__class__.__name__ == 'SimpleCommand':
            return self._get_simple_command_fields(node)

        # Special handling for StatementList to avoid duplication
        if node.__class__.__name__ == 'StatementList':
            return self._get_statement_list_fields(node)

        # Special handling for AndOrList to show pipeline/operator relationships
        if node.__class__.__name__ == 'AndOrList':
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

    def _get_statement_list_fields(self, node) -> List[Tuple[str, Any]]:
        """Get fields for StatementList without duplication from compatibility properties."""
        fields = []

        # Only show the main 'statements' field, skip the backward compatibility properties
        # that are derived from it (and_or_lists, pipelines)
        statements = getattr(node, 'statements', [])
        if statements or self.show_empty_fields:
            fields.append(('statements', statements))

        return fields

    def _get_and_or_list_fields(self, node) -> List[Tuple[str, Any]]:
        """Get fields for AndOrList showing pipeline/operator relationships."""
        fields: List[Tuple[str, Any]] = []

        pipelines = getattr(node, 'pipelines', [])
        operators = getattr(node, 'operators', [])

        if not pipelines:
            return fields

        # If no operators, just show pipelines normally
        if not operators:
            fields.append(('pipelines', pipelines))
            return fields

        # Create a tree structure where operators have pipelines as children
        # For "cmd1 && cmd2 || cmd3", we want to show:
        # expression_tree:
        #   └── ||
        #       ├── &&
        #       │   ├── Pipeline: cmd1
        #       │   └── Pipeline: cmd2
        #       └── Pipeline: cmd3

        expression_tree = self._build_operator_tree(pipelines, operators)
        fields.append(('expression_tree', expression_tree))
        return fields

    def _build_operator_tree(self, pipelines, operators):
        """Build a tree structure showing operator precedence and pipeline relationships."""
        if not operators:
            return pipelines[0] if pipelines else None

        # For now, build a simple left-associative tree
        # Start with the first pipeline
        result = pipelines[0]

        # Process each operator and its right operand
        for i, operator in enumerate(operators):
            right_pipeline = pipelines[i + 1] if i + 1 < len(pipelines) else None
            if right_pipeline is not None:
                # Create an operator node with left and right children
                result = ('OperatorExpression', {
                    'operator': operator,
                    'left': result,
                    'right': right_pipeline
                })

        return result

    def _render_expression_operand(self, operand, prefix: str, is_last: bool) -> List[str]:
        """Render an operand in an operator expression."""
        lines = []
        connector = self.chars['last_branch'] if is_last else self.chars['branch']

        if isinstance(operand, tuple) and len(operand) == 2 and operand[0] == 'OperatorExpression':
            # Nested operator expression
            operator_info = operand[1]
            operator = operator_info.get('operator', '?')
            left = operator_info.get('left')
            right = operator_info.get('right')

            lines.append(f"{prefix}{connector}{operator}")
            nested_prefix = prefix + (self.chars['space'] if is_last else self.chars['vertical'])

            # Render nested operands
            if left is not None:
                left_lines = self._render_expression_operand(left, nested_prefix, False)
                lines.extend(left_lines)

            if right is not None:
                right_lines = self._render_expression_operand(right, nested_prefix, True)
                lines.extend(right_lines)

        elif hasattr(operand, '__class__'):
            # AST Node
            node_lines = self._render_node(operand, prefix, is_last)
            lines.append(node_lines)
        else:
            # Simple value
            lines.append(f"{prefix}{connector}{self._format_simple_value(operand)}")

        return lines

    def _get_simple_command_fields(self, node) -> List[Tuple[str, Any]]:
        """Get fields for SimpleCommand with compact argument representation."""
        fields = []

        # Create compact argument representation using Word AST
        args = getattr(node, 'args', [])
        words = getattr(node, 'words', None) or []

        if args:
            compact_args = []
            for i, arg in enumerate(args):
                word = words[i] if i < len(words) else None
                if word and word.is_quoted:
                    qc = word.effective_quote_char or '?'
                    compact_args.append(f'"{arg}" (quoted, {qc})')
                elif word and word.has_expansion_parts:
                    compact_args.append(f'{arg} (expansion)')
                else:
                    compact_args.append(f'{arg} (literal)')

            fields.append(('arguments', compact_args))

        # Add other fields (skip raw args/words and removed fields)
        skip_fields = {'args', 'arg_types', 'quote_types', 'words'}
        for attr_name in dir(node):
            if (not attr_name.startswith('_') and
                not callable(getattr(node, attr_name)) and
                attr_name not in ['position', 'line', 'column'] and
                attr_name not in skip_fields):
                try:
                    value = getattr(node, attr_name)
                    if value is not None or self.show_empty_fields:
                        if isinstance(value, list) and not value and not self.show_empty_fields:
                            continue
                        if isinstance(value, bool) and value is False:
                            continue
                        fields.append((attr_name, value))
                except (AttributeError, TypeError):
                    continue

        return fields

    def _render_node(self, node: ASTNode, prefix: str, is_last: bool) -> str:
        """Render a single node and its children."""
        lines = []

        # Determine connector
        connector = self.chars['last_branch'] if is_last else self.chars['branch']

        # Main node label
        node_label = self._format_node_label(node)
        lines.append(f"{prefix}{connector}{node_label}")

        # Prepare prefix for children
        child_prefix = prefix + (self.chars['space'] if is_last else self.chars['vertical'])

        # Get and process fields
        fields = self._get_node_fields(node)

        if not fields:
            return '\n'.join(lines)

        # Separate simple and complex fields
        simple_fields: List[Tuple[str, Any]] = []
        complex_fields: List[Tuple[str, Any]] = []

        for name, value in fields:
            if value is None:
                if self.show_empty_fields:
                    simple_fields.append((name, None))
            elif isinstance(value, (str, int, float, bool)):
                simple_fields.append((name, value))
            elif isinstance(value, list):
                if not value:
                    if self.show_empty_fields:
                        simple_fields.append((name, "[]"))
                else:
                    complex_fields.append((name, value))
            elif isinstance(value, ASTNode):
                complex_fields.append((name, value))
            elif isinstance(value, tuple) and len(value) == 2 and value[0] == 'OperatorExpression':
                # Special handling for operator expressions
                complex_fields.append((name, [value]))  # Wrap in list for list renderer
            else:
                simple_fields.append((name, value))

        # Render simple fields compactly if in compact mode
        if simple_fields and self.compact_mode:
            simple_parts = []
            for name, value in simple_fields:
                if value is None:
                    simple_parts.append(f"{name}: None")
                else:
                    simple_parts.append(f"{name}: {self._format_simple_value(value)}")

            if simple_parts:
                simple_line = ", ".join(simple_parts)
                simple_line = self._truncate_text(simple_line)
                lines.append(f"{child_prefix}{self.chars['leaf']}{simple_line}")
        elif simple_fields:
            # Render simple fields individually
            for i, (name, value) in enumerate(simple_fields):
                is_last_simple = (i == len(simple_fields) - 1) and not complex_fields
                simple_connector = self.chars['last_branch'] if is_last_simple else self.chars['branch']

                if value is None:
                    formatted_value = "None"
                else:
                    formatted_value = self._format_simple_value(value)

                field_line = f"{name}: {formatted_value}"
                field_line = self._truncate_text(field_line)
                lines.append(f"{child_prefix}{simple_connector}{field_line}")

        # Render complex fields
        for i, (name, value) in enumerate(complex_fields):
            is_last_field = (i == len(complex_fields) - 1)

            if isinstance(value, list):
                lines.extend(self._render_list_field(name, value, child_prefix, is_last_field))
            elif isinstance(value, ASTNode):
                lines.extend(self._render_node_field(name, value, child_prefix, is_last_field))

        return '\n'.join(lines)

    def _render_list_field(self, field_name: str, items: List[Any],
                          prefix: str, is_last: bool) -> List[str]:
        """Render a list field."""
        lines = []

        # Special compact handling for SimpleCommand arguments
        if field_name == "arguments":
            connector = self.chars['last_branch'] if is_last else self.chars['branch']

            # Show all arguments on a single line if they fit (be more generous with the limit)
            args_line = ", ".join(str(item) for item in items)
            total_line = f"{prefix}{connector}{field_name}: {args_line}"

            # Use 120 as a reasonable limit for most terminals, or use max_width if it's higher
            line_limit = max(120, self.max_width)

            if len(total_line) <= line_limit:
                # Single line format
                lines.append(total_line)
                return lines
            else:
                # Fall back to multi-line if too long
                lines.append(f"{prefix}{connector}{field_name}:")
                list_prefix = prefix + (self.chars['space'] if is_last else self.chars['vertical'])
                for i, item in enumerate(items):
                    is_last_item = (i == len(items) - 1)
                    item_connector = self.chars['last_branch'] if is_last_item else self.chars['branch']
                    lines.append(f"{list_prefix}{item_connector}{self.chars['list_item']}{item}")
                return lines

        # Standard list rendering for other fields
        # List header
        connector = self.chars['last_branch'] if is_last else self.chars['branch']
        list_header = f"{field_name}: [{len(items)} items]"
        lines.append(f"{prefix}{connector}{list_header}")

        # List prefix
        list_prefix = prefix + (self.chars['space'] if is_last else self.chars['vertical'])

        # Render items
        for i, item in enumerate(items):
            is_last_item = (i == len(items) - 1)

            # Special handling for operator expressions and other tuples
            if isinstance(item, tuple) and len(item) == 2:
                item_type, item_value = item
                item_connector = self.chars['last_branch'] if is_last_item else self.chars['branch']

                if item_type == 'OperatorExpression' and isinstance(item_value, dict):
                    # Render operator expression as a tree
                    operator = item_value.get('operator', '?')
                    left = item_value.get('left')
                    right = item_value.get('right')

                    lines.append(f"{list_prefix}{item_connector}{operator}")
                    op_prefix = list_prefix + (self.chars['space'] if is_last_item else self.chars['vertical'])

                    # Render left operand
                    if left is not None:
                        left_lines = self._render_expression_operand(left, op_prefix, False)
                        lines.extend(left_lines)

                    # Render right operand
                    if right is not None:
                        right_lines = self._render_expression_operand(right, op_prefix, True)
                        lines.extend(right_lines)

                elif isinstance(item_value, ASTNode):
                    # For Pipeline nodes, show the type label then render the node
                    lines.append(f"{list_prefix}{item_connector}{item_type}:")
                    node_prefix = list_prefix + (self.chars['space'] if is_last_item else self.chars['vertical'])
                    item_lines = self._render_node(item_value, node_prefix, True)
                    lines.append(item_lines)
                else:
                    # For simple values, show as key: value
                    lines.append(f"{list_prefix}{item_connector}{item_type}: {item_value}")
            elif isinstance(item, ASTNode):
                item_lines = self._render_node(item, list_prefix, is_last_item)
                lines.append(item_lines)
            else:
                item_connector = self.chars['last_branch'] if is_last_item else self.chars['branch']
                item_str = self._format_simple_value(item)
                item_str = self._truncate_text(item_str)
                lines.append(f"{list_prefix}{item_connector}{self.chars['list_item']}{item_str}")

        return lines

    def _render_node_field(self, field_name: str, node: ASTNode,
                          prefix: str, is_last: bool) -> List[str]:
        """Render a single node field."""
        lines = []

        # Field header
        connector = self.chars['last_branch'] if is_last else self.chars['branch']
        lines.append(f"{prefix}{connector}{field_name}:")

        # Node content with increased indentation
        node_prefix = prefix + (self.chars['space'] if is_last else self.chars['vertical'])
        node_lines = self._render_node(node, node_prefix, True)
        lines.append(node_lines)

        return lines


# Specialized renderers for common use cases
class CompactAsciiTreeRenderer(AsciiTreeRenderer):
    """Compact ASCII tree renderer for dense output."""

    def __init__(self, **kwargs):
        super().__init__(
            compact_mode=True,
            show_empty_fields=False,
            max_width=60,
            **kwargs
        )


class DetailedAsciiTreeRenderer(AsciiTreeRenderer):
    """Detailed ASCII tree renderer showing all information."""

    def __init__(self, **kwargs):
        super().__init__(
            compact_mode=False,
            show_empty_fields=True,
            show_positions=True,
            max_width=100,
            **kwargs
        )


# Convenience functions
def render_ast_tree(ast: ASTNode, **kwargs) -> str:
    """Render AST as ASCII tree.

    Args:
        ast: The AST node to render
        **kwargs: Arguments passed to AsciiTreeRenderer

    Returns:
        ASCII tree string
    """
    return AsciiTreeRenderer.render(ast, **kwargs)


def render_compact_tree(ast: ASTNode) -> str:
    """Render AST as compact ASCII tree.

    Args:
        ast: The AST node to render

    Returns:
        Compact ASCII tree string
    """
    return CompactAsciiTreeRenderer.render(ast)


def render_detailed_tree(ast: ASTNode) -> str:
    """Render AST as detailed ASCII tree.

    Args:
        ast: The AST node to render

    Returns:
        Detailed ASCII tree string
    """
    return DetailedAsciiTreeRenderer.render(ast)
