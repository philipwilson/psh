"""
AST formatter visitor that pretty-prints AST nodes.

This visitor demonstrates how to traverse the AST and produce formatted output,
useful for debugging and understanding AST structure.
"""

from ..ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    ArrayElementAssignment,
    # Array nodes
    ArrayInitialization,
    # Core nodes
    ASTNode,
    BinaryTestExpression,
    BraceGroup,
    BreakStatement,
    CaseConditional,
    # Case statement components
    CaseItem,
    CompoundTestExpression,
    ContinueStatement,
    CStyleForLoop,
    EnhancedTestStatement,
    ForLoop,
    # Function and test nodes
    FunctionDef,
    IfConditional,
    NegatedTestExpression,
    Pipeline,
    ProcessSubstitution,
    Redirect,
    SelectLoop,
    SimpleCommand,
    StatementList,
    SubshellGroup,
    TopLevel,
    UnaryTestExpression,
    # Control structures
    WhileLoop,
)
from .base import ASTVisitor


class FormatterVisitor(ASTVisitor[str]):
    """
    Visitor that formats AST nodes as readable text.

    This visitor can be used to:
    - Pretty-print AST structure for debugging
    - Generate shell script from AST
    - Display formatted command output
    """

    def __init__(self, indent: int = 2):
        """
        Initialize the formatter.

        Args:
            indent: Number of spaces per indentation level
        """
        super().__init__()
        self.indent = indent
        self.level = 0

    def _indent(self) -> str:
        """Get current indentation string."""
        return ' ' * (self.level * self.indent)

    def _increase_indent(self):
        """Increase indentation level."""
        self.level += 1

    def _decrease_indent(self):
        """Decrease indentation level."""
        self.level = max(0, self.level - 1)

    @staticmethod
    def _format_word(word) -> str:
        """Format a Word by reconstructing from its parts with quoting.

        Groups consecutive parts that share the same quote context so
        that ``"$HOME/bin"`` is emitted as one quoted region rather than
        ``"$HOME""/bin"``.
        """
        # Group consecutive parts by their quote context
        groups: list = []  # [(quote_char_or_None, [text, ...])]
        for part in word.parts:
            qc = getattr(part, 'quote_char', None) if getattr(part, 'quoted', False) else None
            text = str(part)
            if groups and groups[-1][0] == qc:
                groups[-1][1].append(text)
            else:
                groups.append((qc, [text]))

        result: list = []
        for qc, texts in groups:
            content = ''.join(texts)
            if qc:
                if qc == "$'":
                    result.append(f"$'{content}'")
                else:
                    result.append(f'{qc}{content}{qc}')
            else:
                result.append(content)
        return ''.join(result)

    # Top-level nodes

    def visit_TopLevel(self, node: TopLevel) -> str:
        """Format top-level script."""
        parts = []
        for item in node.items:
            parts.append(self.visit(item))
        return '\n\n'.join(parts)

    def visit_StatementList(self, node: StatementList) -> str:
        """Format a list of statements."""
        parts = []
        for stmt in node.statements:
            parts.append(self.visit(stmt))
        return '\n'.join(parts)

    # Command nodes

    def visit_SimpleCommand(self, node: SimpleCommand) -> str:
        """Format a simple command."""
        parts = []

        # Array assignments
        for assignment in node.array_assignments:
            parts.append(self.visit(assignment))

        # Command and arguments — reconstruct from Word parts to
        # preserve per-part quoting in composite words.
        words = node.words if node.words else []
        for i, arg in enumerate(node.args):
            word = words[i] if i < len(words) else None
            if word and word.parts:
                parts.append(self._format_word(word))
            else:
                parts.append(arg)

        # Redirections
        for redirect in node.redirects:
            parts.append(self.visit(redirect))

        # Background
        if node.background:
            parts.append('&')

        return self._indent() + ' '.join(parts)

    def visit_Pipeline(self, node: Pipeline) -> str:
        """Format a pipeline."""
        parts = []

        # Save indent level for pipeline components
        saved_level = self.level
        self.level = 0

        for cmd in node.commands:
            parts.append(self.visit(cmd).strip())

        self.level = saved_level

        result = ' | '.join(parts)
        if node.negated:
            result = '! ' + result

        return self._indent() + result

    def visit_AndOrList(self, node: AndOrList) -> str:
        """Format an and/or list."""
        if not node.pipelines:
            return ''

        parts = [self.visit(node.pipelines[0])]

        for i, op in enumerate(node.operators):
            if i + 1 < len(node.pipelines):
                parts.append(f' {op} ')
                parts.append(self.visit(node.pipelines[i + 1]).strip())

        return ''.join(parts)

    # Control structures

    def visit_WhileLoop(self, node: WhileLoop) -> str:
        """Format a while loop."""
        lines = []

        lines.append(self._indent() + 'while')
        self._increase_indent()
        lines.append(self.visit(node.condition))
        self._decrease_indent()

        lines.append(self._indent() + 'do')
        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        # Add redirections
        if node.redirects:
            redirect_str = ' '.join(self.visit(r) for r in node.redirects)
            lines[-1] += ' ' + redirect_str

        return '\n'.join(lines)

    def visit_ForLoop(self, node: ForLoop) -> str:
        """Format a for loop."""
        lines = []

        # Format items with proper quoting
        items = []
        for item in node.items:
            if ' ' in item or any(c in item for c in '*?[]'):
                items.append(f'"{item}"')
            else:
                items.append(item)

        lines.append(f"{self._indent()}for {node.variable} in {' '.join(items)}")
        lines.append(self._indent() + 'do')

        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        # Add redirections
        if node.redirects:
            redirect_str = ' '.join(self.visit(r) for r in node.redirects)
            lines[-1] += ' ' + redirect_str

        return '\n'.join(lines)

    def visit_CStyleForLoop(self, node: CStyleForLoop) -> str:
        """Format a C-style for loop."""
        lines = []

        init = node.init_expr or ''
        cond = node.condition_expr or ''
        update = node.update_expr or ''

        lines.append(f"{self._indent()}for (({init}; {cond}; {update}))")
        lines.append(self._indent() + 'do')

        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        # Add redirections
        if node.redirects:
            redirect_str = ' '.join(self.visit(r) for r in node.redirects)
            lines[-1] += ' ' + redirect_str

        return '\n'.join(lines)

    def visit_IfConditional(self, node: IfConditional) -> str:
        """Format an if statement."""
        lines = []

        lines.append(self._indent() + 'if')
        self._increase_indent()
        lines.append(self.visit(node.condition))
        self._decrease_indent()

        lines.append(self._indent() + 'then')
        self._increase_indent()
        lines.append(self.visit(node.then_part))
        self._decrease_indent()

        # elif parts
        for condition, then_part in node.elif_parts:
            lines.append(self._indent() + 'elif')
            self._increase_indent()
            lines.append(self.visit(condition))
            self._decrease_indent()

            lines.append(self._indent() + 'then')
            self._increase_indent()
            lines.append(self.visit(then_part))
            self._decrease_indent()

        # else part
        if node.else_part:
            lines.append(self._indent() + 'else')
            self._increase_indent()
            lines.append(self.visit(node.else_part))
            self._decrease_indent()

        lines.append(self._indent() + 'fi')

        # Add redirections
        if node.redirects:
            redirect_str = ' '.join(self.visit(r) for r in node.redirects)
            lines[-1] += ' ' + redirect_str

        return '\n'.join(lines)

    def visit_CaseConditional(self, node: CaseConditional) -> str:
        """Format a case statement."""
        lines = []

        lines.append(f"{self._indent()}case {node.expr} in")

        self._increase_indent()
        for item in node.items:
            lines.append(self.visit(item))
        self._decrease_indent()

        lines.append(self._indent() + 'esac')

        # Add redirections
        if node.redirects:
            redirect_str = ' '.join(self.visit(r) for r in node.redirects)
            lines[-1] += ' ' + redirect_str

        return '\n'.join(lines)

    def visit_CaseItem(self, node: CaseItem) -> str:
        """Format a case item."""
        lines = []

        # Format patterns
        patterns = [p.pattern for p in node.patterns]
        lines.append(f"{self._indent()}{' | '.join(patterns)})")

        # Format commands
        self._increase_indent()
        if node.commands.statements:
            lines.append(self.visit(node.commands))
        self._decrease_indent()

        # Add terminator
        lines.append(f"{self._indent()}{node.terminator}")

        return '\n'.join(lines)

    def visit_SelectLoop(self, node: SelectLoop) -> str:
        """Format a select loop."""
        lines = []

        items = ' '.join(f'"{item}"' if ' ' in item else item for item in node.items)
        lines.append(f"{self._indent()}select {node.variable} in {items}")
        lines.append(self._indent() + 'do')

        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        # Add redirections
        if node.redirects:
            redirect_str = ' '.join(self.visit(r) for r in node.redirects)
            lines[-1] += ' ' + redirect_str

        return '\n'.join(lines)

    # Other statement types

    def visit_FunctionDef(self, node: FunctionDef) -> str:
        """Format a function definition."""
        lines = []
        lines.append(f"{self._indent()}{node.name}() {{")

        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + '}')
        return '\n'.join(lines)

    def visit_BreakStatement(self, node: BreakStatement) -> str:
        """Format a break statement."""
        if node.level == 1:
            return self._indent() + 'break'
        else:
            return f"{self._indent()}break {node.level}"

    def visit_ContinueStatement(self, node: ContinueStatement) -> str:
        """Format a continue statement."""
        if node.level == 1:
            return self._indent() + 'continue'
        else:
            return f"{self._indent()}continue {node.level}"

    def visit_ArithmeticEvaluation(self, node: ArithmeticEvaluation) -> str:
        """Format an arithmetic command."""
        return f"{self._indent()}(({node.expression}))"

    def visit_SubshellGroup(self, node: SubshellGroup) -> str:
        """Format a subshell group ``( ... )``."""
        return self._format_group(node, '(', ')')

    def visit_BraceGroup(self, node: BraceGroup) -> str:
        """Format a brace group ``{ ...; }``."""
        return self._format_group(node, '{', '}')

    def _format_group(self, node, opener: str, closer: str) -> str:
        """Shared multi-line formatting for subshell / brace groups."""
        lines = [self._indent() + opener]
        self._increase_indent()
        lines.append(self.visit(node.statements))
        self._decrease_indent()
        lines.append(self._indent() + closer)
        if node.redirects:
            lines[-1] += ' ' + ' '.join(self.visit(r) for r in node.redirects)
        if node.background:
            lines[-1] += ' &'
        return '\n'.join(lines)

    # Test expressions

    def visit_EnhancedTestStatement(self, node: EnhancedTestStatement) -> str:
        """Format an enhanced test statement."""
        expr_str = self.visit(node.expression)
        result = f"{self._indent()}[[ {expr_str} ]]"

        # Add redirections
        if node.redirects:
            redirect_str = ' '.join(self.visit(r) for r in node.redirects)
            result += ' ' + redirect_str

        return result

    def visit_BinaryTestExpression(self, node: BinaryTestExpression) -> str:
        """Format a binary test expression."""
        return f"{node.left} {node.operator} {node.right}"

    def visit_UnaryTestExpression(self, node: UnaryTestExpression) -> str:
        """Format a unary test expression."""
        return f"{node.operator} {node.operand}"

    def visit_CompoundTestExpression(self, node: CompoundTestExpression) -> str:
        """Format a compound test expression."""
        left = self.visit(node.left)
        right = self.visit(node.right)
        return f"{left} {node.operator} {right}"

    def visit_NegatedTestExpression(self, node: NegatedTestExpression) -> str:
        """Format a negated test expression."""
        expr = self.visit(node.expression)
        return f"! {expr}"

    # Array assignments

    def visit_ArrayInitialization(self, node: ArrayInitialization) -> str:
        """Format array initialization."""
        elements = []
        for i, elem in enumerate(node.elements):
            if i < len(node.element_types) and node.element_types[i] == 'STRING':
                quote = node.element_quote_types[i] if i < len(node.element_quote_types) else '"'
                if quote is None:
                    quote = '"'
                elements.append(f'{quote}{elem}{quote}')
            else:
                elements.append(elem)

        op = '+=' if node.is_append else '='
        return f"{node.name}{op}({' '.join(elements)})"

    def visit_ArrayElementAssignment(self, node: ArrayElementAssignment) -> str:
        """Format array element assignment."""
        # Handle both string and token list indices
        if isinstance(node.index, str):
            index_str = node.index
        else:
            # Token list - reconstruct the expression
            index_str = ''.join(token.value for token in node.index)

        op = '+=' if node.is_append else '='

        if node.value_type == 'STRING' and node.value_quote_type:
            value_str = f'{node.value_quote_type}{node.value}{node.value_quote_type}'
        else:
            value_str = node.value

        return f"{node.name}[{index_str}]{op}{value_str}"

    # Redirections

    def visit_Redirect(self, node: Redirect) -> str:
        """Format a redirection."""
        parts = []

        # Check if fd is already encoded in the type (like 2>, 2>>)
        if node.type.startswith('2') and node.fd == 2:
            # fd is already part of the type, don't duplicate it
            parts.append(node.type)
        else:
            # For other redirections, prepend fd if specified
            if node.fd is not None:
                parts.append(str(node.fd))
            parts.append(node.type)

        if node.dup_fd is not None:
            parts.append(str(node.dup_fd))
        else:
            parts.append(node.target)

        return ''.join(parts)

    def visit_ProcessSubstitution(self, node: ProcessSubstitution) -> str:
        """Format a process substitution."""
        return str(node)

    def generic_visit(self, node: ASTNode) -> str:
        """Default formatting for unknown nodes."""
        return f"{self._indent()}# Unknown node: {node.__class__.__name__}"
