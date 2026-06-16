"""Shell syntax formatter for reconstructing shell code from AST nodes."""

from ..ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    BinaryTestExpression,
    BraceGroup,
    BreakStatement,
    CaseConditional,
    CommandList,
    CompoundTestExpression,
    ContinueStatement,
    CStyleForLoop,
    EnhancedTestStatement,
    ForLoop,
    FunctionDef,
    IfConditional,
    NegatedTestExpression,
    Pipeline,
    SelectLoop,
    SimpleCommand,
    SubshellGroup,
    TopLevel,
    UnaryTestExpression,
    UntilLoop,
    WhileLoop,
)


class ShellFormatter:
    """Formats AST nodes back into shell syntax."""

    @staticmethod
    def format(node, indent_level=0):
        """Format AST node as shell syntax."""
        indent = "    " * indent_level

        if isinstance(node, TopLevel):
            # Format top-level items
            return '\n'.join(ShellFormatter.format(item) for item in node.items)

        elif isinstance(node, FunctionDef):
            # Format function definition
            result = f"{node.name} () "
            result += ShellFormatter.format(node.body)
            return result

        elif isinstance(node, CommandList):
            # Format command list with proper semicolons
            parts = []
            for i, stmt in enumerate(node.statements):
                part = ShellFormatter.format(stmt, indent_level)
                # Add semicolon between statements if needed
                if i < len(node.statements) - 1:
                    if not part.rstrip().endswith(('&', ';')):
                        part = part.rstrip() + ';'
                parts.append(part)

            # If in a block context (with braces), format with newlines
            if indent_level > 0:
                return '\n'.join(f"{indent}{part}" for part in parts)
            else:
                return ' '.join(parts)

        elif isinstance(node, AndOrList):
            # Format pipelines with && and || operators
            result = ShellFormatter.format(node.pipelines[0], indent_level)
            for i, op in enumerate(node.operators):
                result += f" {op} "
                result += ShellFormatter.format(node.pipelines[i + 1], indent_level)
            return result

        elif isinstance(node, Pipeline):
            # Format pipeline with | between commands
            parts = []
            for cmd in node.commands:
                parts.append(ShellFormatter.format(cmd, indent_level))
            return ' | '.join(parts)

        elif isinstance(node, SimpleCommand):
            # Format simple command with arguments, preserving quotes
            parts = []
            words = node.words if node.words else []
            for i, arg in enumerate(node.args):
                word = words[i] if i < len(words) else None
                # Check if we need to add quotes back
                if word and word.effective_quote_char:
                    quote_char = word.effective_quote_char
                    parts.append(f"{quote_char}{arg}{quote_char}")
                else:
                    # Check if arg needs quoting (contains spaces or special chars)
                    if ' ' in arg or '\t' in arg or '\n' in arg or ';' in arg or '&' in arg or '|' in arg:
                        # Use single quotes if arg contains double quotes, otherwise use double quotes
                        if '"' in arg and "'" not in arg:
                            parts.append(f"'{arg}'")
                        else:
                            parts.append(f'"{arg}"')
                    else:
                        parts.append(arg)

            result = ' '.join(parts)

            # Add redirections
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)

            # Add background marker
            if node.background:
                result += ' &'

            return result

        elif isinstance(node, WhileLoop):
            result = "while "
            result += ShellFormatter.format(node.condition, indent_level)
            result += "; do\n"
            result += ShellFormatter.format(node.body, indent_level + 1)
            result += f"\n{indent}done"

            # Add redirections if present
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)

            return result
        elif isinstance(node, UntilLoop):
            result = "until "
            result += ShellFormatter.format(node.condition, indent_level)
            result += "; do\n"
            result += ShellFormatter.format(node.body, indent_level + 1)
            result += f"\n{indent}done"

            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)

            return result

        elif isinstance(node, ForLoop):
            result = f"for {node.variable} in"
            for item in node.items:
                result += f" {item}"
            result += "; do\n"
            result += ShellFormatter.format(node.body, indent_level + 1)
            result += f"\n{indent}done"

            # Add redirections if present
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)

            return result

        elif isinstance(node, CStyleForLoop):
            result = "for (("
            if node.init_expr:
                result += node.init_expr
            result += "; "
            if node.condition_expr:
                result += node.condition_expr
            result += "; "
            if node.update_expr:
                result += node.update_expr
            result += ")); do\n"
            result += ShellFormatter.format(node.body, indent_level + 1)
            result += f"\n{indent}done"

            # Add redirections if present
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)

            return result

        elif isinstance(node, IfConditional):
            result = "if "
            result += ShellFormatter.format(node.condition, indent_level)
            result += "; then\n"
            result += ShellFormatter.format(node.then_part, indent_level + 1)

            if node.else_part:
                result += f"\n{indent}else\n"
                result += ShellFormatter.format(node.else_part, indent_level + 1)

            result += f"\n{indent}fi"

            # Add redirections if present
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)

            return result

        elif isinstance(node, CaseConditional):
            result = f"case {node.expr} in\n"
            for case_item in node.items:
                result += ShellFormatter._format_case_item(case_item, indent_level + 1)
            result += f"{indent}esac"

            # Add redirections if present
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)

            return result

        elif isinstance(node, SelectLoop):
            result = f"select {node.variable} in"
            for item in node.items:
                result += f" {item}"
            result += "; do\n"
            result += ShellFormatter.format(node.body, indent_level + 1)
            result += f"\n{indent}done"

            # Add redirections if present
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)

            return result

        elif isinstance(node, ArithmeticEvaluation):
            result = f"(({node.expression}))"

            # Add redirections if present
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)

            return result

        elif isinstance(node, BreakStatement):
            return ShellFormatter._format_loop_control("break", node)

        elif isinstance(node, ContinueStatement):
            return ShellFormatter._format_loop_control("continue", node)

        elif isinstance(node, SubshellGroup):
            result = f"( {ShellFormatter.format(node.statements, indent_level)} )"
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)
            if node.background:
                result += ' &'
            return result

        elif isinstance(node, BraceGroup):
            # POSIX brace group: needs a terminator before the closing brace.
            result = f"{{ {ShellFormatter.format(node.statements, indent_level)}; }}"
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)
            if node.background:
                result += ' &'
            return result

        elif isinstance(node, EnhancedTestStatement):
            result = f"[[ {ShellFormatter._format_test_expression(node.expression)} ]]"
            for redirect in node.redirects:
                result += ' ' + ShellFormatter._format_redirect(redirect)
            return result

        else:
            # For compound commands when used as a body
            if hasattr(node, 'body') and isinstance(node.body, CommandList):
                result = "{ "
                result += ShellFormatter.format(node.body, indent_level)
                result += " }"
                return result

            # Fallback
            return f"# Unknown node type: {type(node).__name__}"

    @staticmethod
    def _format_loop_control(name: str, node) -> str:
        """Render a break/continue statement with its optional level argument.

        Prefers the raw argument words (``break $n``, ``break 2``); falls back
        to the literal int level for hand-built/combinator nodes that set only
        the int field.
        """
        words = getattr(node, 'level_words', None)
        if words:
            return ' '.join([name] + [w.source_text() for w in words])
        if node.level and node.level != 1:
            return f"{name} {node.level}"
        return name

    @staticmethod
    def _format_test_expression(expr) -> str:
        """Format a [[ ]] test expression tree back into shell syntax."""
        if isinstance(expr, UnaryTestExpression):
            return f"{expr.operator} {expr.operand}"
        elif isinstance(expr, BinaryTestExpression):
            return f"{expr.left} {expr.operator} {expr.right}"
        elif isinstance(expr, NegatedTestExpression):
            return f"! {ShellFormatter._format_test_expression(expr.expression)}"
        elif isinstance(expr, CompoundTestExpression):
            left = ShellFormatter._format_test_expression(expr.left)
            right = ShellFormatter._format_test_expression(expr.right)
            return f"{left} {expr.operator} {right}"
        # Fallback: a plain operand or unknown expression node
        return str(getattr(expr, 'value', expr))

    @staticmethod
    def _format_redirect(redirect):
        """Format a single redirection."""
        result = ""

        # Add file descriptor if specified
        if redirect.fd is not None:
            result += str(redirect.fd)

        # Add redirection operator
        result += redirect.type

        # Add target
        if redirect.dup_fd is not None:
            result += str(redirect.dup_fd)
        elif redirect.heredoc_content is not None:
            # For here documents, just show the delimiter
            result += redirect.target
        else:
            result += redirect.target

        return result

    @staticmethod
    def _format_case_item(item, indent_level):
        """Format a case item."""
        indent = "    " * indent_level
        result = indent

        # Format patterns
        result += '|'.join(item.patterns)
        result += ")\n"

        # Format commands
        result += ShellFormatter.format(item.commands, indent_level + 1)

        # Add terminator
        result += f"\n{indent}{item.terminator}\n"

        return result

    @staticmethod
    def format_function_body(func):
        """Format a function body for display."""
        # Functions have a CommandList body
        if hasattr(func.body, 'statements'):
            # Format with braces
            result = "{ \n"
            for stmt in func.body.statements:
                result += "    " + ShellFormatter.format(stmt, 1) + "\n"
            result += "}"
            return result
        else:
            # Fallback for other body types
            return "{\n    " + ShellFormatter.format(func.body, 1) + "\n}"
