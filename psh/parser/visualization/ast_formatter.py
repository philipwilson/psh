"""AST Pretty Printer for human-readable output."""

from typing import Any, Dict, Optional

from ...ast_nodes import ASTNode
from ...visitor import ASTVisitor


class ASTPrettyPrinter(ASTVisitor[str]):
    """Pretty print AST with proper indentation and structure."""

    def __init__(self, indent_size: int = 2, show_positions: bool = False,
                 max_width: int = 80, compact_mode: bool = False):
        """Initialize the pretty printer.

        Args:
            indent_size: Number of spaces per indentation level
            show_positions: Whether to show token positions
            max_width: Maximum line width before wrapping
            compact_mode: Whether to use compact single-line format when possible
        """
        super().__init__()
        self.indent_size = indent_size
        self.show_positions = show_positions
        self.max_width = max_width
        self.compact_mode = compact_mode
        self.current_indent = 0

    def _indent(self) -> str:
        """Get current indentation string."""
        return ' ' * (self.current_indent * self.indent_size)

    def _format_node_header(self, node: ASTNode, name: str) -> str:
        """Format the header for a node with optional position info."""
        header = name
        if self.show_positions and hasattr(node, 'position'):
            header += f" @{node.position}"
        return header

    def _format_field(self, name: str, value: Any) -> str:
        """Format a field with proper indentation."""
        if value is None:
            return f"{self._indent()}{name}: None"
        elif isinstance(value, (str, int, bool)):
            return f"{self._indent()}{name}: {repr(value)}"
        elif isinstance(value, list):
            if not value:
                return f"{self._indent()}{name}: []"
            elif len(value) == 1 and self.compact_mode:
                # Try compact format for single items
                item_str = self.visit(value[0]) if hasattr(value[0], 'accept') else str(value[0])
                if len(item_str) < 40:
                    return f"{self._indent()}{name}: [{item_str}]"

            # Multi-line format
            lines = [f"{self._indent()}{name}: ["]
            self.current_indent += 1
            for i, item in enumerate(value):
                if hasattr(item, 'accept'):
                    item_str = self.visit(item)
                else:
                    item_str = f"{self._indent()}{repr(item)}"

                comma = "," if i < len(value) - 1 else ""
                lines.append(f"{item_str}{comma}")
            self.current_indent -= 1
            lines.append(f"{self._indent()}]")
            return "\n".join(lines)
        else:
            # Assume it's an AST node
            return f"{self._indent()}{name}:\n{self.visit(value)}"

    def _format_compact_node(self, node_name: str, fields: Dict[str, Any]) -> Optional[str]:
        """Try to format a simple node in compact form."""
        if not self.compact_mode:
            return None

        # Only compact if all fields are simple
        simple_fields = []
        for name, value in fields.items():
            if value is None:
                continue
            elif isinstance(value, (str, int, bool)):
                simple_fields.append(f"{name}={repr(value)}")
            elif isinstance(value, list) and not value:
                continue  # Skip empty lists
            else:
                return None  # Not simple enough

        if not simple_fields:
            compact = f"{node_name}()"
        else:
            compact = f"{node_name}({', '.join(simple_fields)})"

        # Only use compact if it fits on one line
        if len(compact) <= 60:
            return f"{self._indent()}{compact}"
        return None

    def visit_SimpleCommand(self, node) -> str:
        """Format simple command."""
        fields = {}
        if hasattr(node, 'args') and node.args:
            fields['args'] = node.args
        if hasattr(node, 'redirects') and node.redirects:
            fields['redirects'] = node.redirects
        if hasattr(node, 'variable_assignments') and node.variable_assignments:
            fields['assignments'] = node.variable_assignments

        # Try compact format for simple commands
        if compact := self._format_compact_node('SimpleCommand', fields):
            return compact

        # Multi-line format
        lines = [f"{self._indent()}{self._format_node_header(node, 'SimpleCommand')}:"]
        self.current_indent += 1

        for name, value in fields.items():
            if value:  # Only show non-empty fields
                lines.append(self._format_field(name, value))

        self.current_indent -= 1
        return "\n".join(lines)

    def visit_Pipeline(self, node) -> str:
        """Format pipeline."""
        lines = [f"{self._indent()}{self._format_node_header(node, 'Pipeline')}:"]
        self.current_indent += 1

        if hasattr(node, 'negated') and node.negated:
            lines.append(f"{self._indent()}negated: True")

        if hasattr(node, 'commands'):
            lines.append(self._format_field('commands', node.commands))

        self.current_indent -= 1
        return "\n".join(lines)

    def visit_AndOrList(self, node) -> str:
        """Format and/or list."""
        lines = [f"{self._indent()}{self._format_node_header(node, 'AndOrList')}:"]
        self.current_indent += 1

        if hasattr(node, 'left'):
            lines.append(self._format_field('left', node.left))
        if hasattr(node, 'operator'):
            lines.append(f"{self._indent()}operator: {repr(node.operator)}")
        if hasattr(node, 'right'):
            lines.append(self._format_field('right', node.right))

        self.current_indent -= 1
        return "\n".join(lines)

    def visit_IfConditional(self, node) -> str:
        """Format if conditional."""
        lines = [f"{self._indent()}{self._format_node_header(node, 'IfConditional')}:"]
        self.current_indent += 1

        if hasattr(node, 'condition'):
            lines.append(self._format_field('condition', node.condition))
        if hasattr(node, 'then_part'):
            lines.append(self._format_field('then_part', node.then_part))
        if hasattr(node, 'elif_parts') and node.elif_parts:
            lines.append(self._format_field('elif_parts', node.elif_parts))
        if hasattr(node, 'else_part') and node.else_part:
            lines.append(self._format_field('else_part', node.else_part))

        self.current_indent -= 1
        return "\n".join(lines)

    def visit_WhileLoop(self, node) -> str:
        """Format while loop."""
        lines = [f"{self._indent()}{self._format_node_header(node, 'WhileLoop')}:"]
        self.current_indent += 1

        if hasattr(node, 'condition'):
            lines.append(self._format_field('condition', node.condition))
        if hasattr(node, 'body'):
            lines.append(self._format_field('body', node.body))

        self.current_indent -= 1
        return "\n".join(lines)

    def visit_ForLoop(self, node) -> str:
        """Format for loop."""
        lines = [f"{self._indent()}{self._format_node_header(node, 'ForLoop')}:"]
        self.current_indent += 1

        if hasattr(node, 'variable'):
            lines.append(f"{self._indent()}variable: {repr(node.variable)}")
        if hasattr(node, 'iterable'):
            lines.append(self._format_field('iterable', node.iterable))
        if hasattr(node, 'body'):
            lines.append(self._format_field('body', node.body))

        self.current_indent -= 1
        return "\n".join(lines)

    def visit_CStyleForLoop(self, node) -> str:
        """Format C-style for loop."""
        lines = [f"{self._indent()}{self._format_node_header(node, 'CStyleForLoop')}:"]
        self.current_indent += 1

        if hasattr(node, 'init') and node.init:
            lines.append(self._format_field('init', node.init))
        if hasattr(node, 'condition') and node.condition:
            lines.append(self._format_field('condition', node.condition))
        if hasattr(node, 'update') and node.update:
            lines.append(self._format_field('update', node.update))
        if hasattr(node, 'body'):
            lines.append(self._format_field('body', node.body))

        self.current_indent -= 1
        return "\n".join(lines)

    def visit_CaseConditional(self, node) -> str:
        """Format case statement."""
        lines = [f"{self._indent()}{self._format_node_header(node, 'CaseConditional')}:"]
        self.current_indent += 1

        if hasattr(node, 'expression'):
            lines.append(self._format_field('expression', node.expression))
        if hasattr(node, 'cases'):
            lines.append(self._format_field('cases', node.cases))

        self.current_indent -= 1
        return "\n".join(lines)

    def visit_FunctionDef(self, node) -> str:
        """Format function definition."""
        lines = [f"{self._indent()}{self._format_node_header(node, 'FunctionDef')}:"]
        self.current_indent += 1

        if hasattr(node, 'name'):
            lines.append(f"{self._indent()}name: {repr(node.name)}")
        if hasattr(node, 'body'):
            lines.append(self._format_field('body', node.body))

        self.current_indent -= 1
        return "\n".join(lines)

    def visit_StatementList(self, node) -> str:
        """Format statement list."""
        if hasattr(node, 'statements') and node.statements:
            lines = [f"{self._indent()}{self._format_node_header(node, 'StatementList')}:"]
            self.current_indent += 1
            lines.append(self._format_field('statements', node.statements))
            self.current_indent -= 1
            return "\n".join(lines)
        else:
            return f"{self._indent()}StatementList: []"

    def visit_Redirect(self, node) -> str:
        """Format redirection."""
        fields = {}
        if hasattr(node, 'type'):
            fields['type'] = node.type
        if hasattr(node, 'fd') and node.fd is not None:
            fields['fd'] = node.fd
        if hasattr(node, 'target'):
            fields['target'] = node.target

        if compact := self._format_compact_node('Redirect', fields):
            return compact

        lines = [f"{self._indent()}{self._format_node_header(node, 'Redirect')}:"]
        self.current_indent += 1

        for name, value in fields.items():
            lines.append(self._format_field(name, value))

        self.current_indent -= 1
        return "\n".join(lines)

    def generic_visit(self, node: ASTNode) -> str:
        """Generic visitor for unknown node types."""
        node_name = node.__class__.__name__

        # Get all attributes that don't start with underscore
        attrs = {}
        for attr_name in dir(node):
            if not attr_name.startswith('_') and not callable(getattr(node, attr_name)):
                try:
                    value = getattr(node, attr_name)
                    if value is not None:
                        attrs[attr_name] = value
                except (AttributeError, TypeError):
                    continue

        if compact := self._format_compact_node(node_name, attrs):
            return compact

        lines = [f"{self._indent()}{self._format_node_header(node, node_name)}:"]
        if attrs:
            self.current_indent += 1
            for name, value in attrs.items():
                lines.append(self._format_field(name, value))
            self.current_indent -= 1

        return "\n".join(lines)


def format_ast(ast: ASTNode, **kwargs) -> str:
    """Convenience function to format an AST.

    Args:
        ast: The AST node to format
        **kwargs: Arguments passed to ASTPrettyPrinter

    Returns:
        Formatted string representation of the AST
    """
    formatter = ASTPrettyPrinter(**kwargs)
    return formatter.visit(ast)
