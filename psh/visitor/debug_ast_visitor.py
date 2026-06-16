"""
Debug AST visitor that formats AST nodes for debugging output.

This visitor replaces the static ASTFormatter utility with a cleaner
visitor-based implementation.
"""

from typing import Sequence

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
    UntilLoop,
    # Control structures
    WhileLoop,
)
from .base import ASTVisitor


class DebugASTVisitor(ASTVisitor[str]):
    """
    Visitor that formats AST nodes for debug output.

    This visitor produces a hierarchical text representation of the AST
    structure, useful for debugging parser output and understanding how
    shell commands are parsed.
    """

    def __init__(self, indent: int = 2):
        """
        Initialize the debug formatter.

        Args:
            indent: Number of spaces per indentation level
        """
        super().__init__()
        self.indent_size = indent
        self.level = 0

    def _indent(self) -> str:
        """Get current indentation string."""
        return ' ' * (self.level * self.indent_size)

    def _format_header(self, node_type: str, extra: str = "") -> str:
        """Format a node header with optional extra info."""
        if extra:
            return f"{self._indent()}{node_type}: {extra}\n"
        else:
            return f"{self._indent()}{node_type}:\n"

    def _visit_child(self, child: ASTNode) -> str:
        """Visit a child node with increased indentation."""
        self.level += 1
        result = self.visit(child)
        self.level -= 1
        return result

    def _visit_children(self, children: Sequence[ASTNode]) -> str:
        """Visit multiple child nodes."""
        return ''.join(self._visit_child(child) for child in children)

    # Top-level nodes

    def visit_TopLevel(self, node: TopLevel) -> str:
        """Format top-level script."""
        result = self._format_header("TopLevel")
        return result + self._visit_children(node.items)

    def visit_StatementList(self, node: StatementList) -> str:
        """Format statement list (alias: CommandList)."""
        result = self._format_header("CommandList")
        return result + self._visit_children(node.statements)

    # Command nodes

    def visit_SimpleCommand(self, node: SimpleCommand) -> str:
        """Format simple command."""
        cmd_str = ' '.join(node.args) if node.args else "(empty)"
        if node.background:
            cmd_str += " &"

        result = self._format_header("SimpleCommand", cmd_str)

        # Show array assignments
        if node.array_assignments:
            self.level += 1
            result += f"{self._indent()}Array Assignments:\n"
            result += self._visit_children(node.array_assignments)
            self.level -= 1

        # Show Word structure if present
        if node.words:
            self.level += 1
            word_descs = []
            for w in node.words:
                if w.is_quoted:
                    qc = w.effective_quote_char or '?'
                    word_descs.append(f'quoted({qc})')
                elif w.is_variable_expansion:
                    word_descs.append('expansion')
                elif w.has_expansion_parts:
                    word_descs.append('composite')
                else:
                    word_descs.append('literal')
            result += f"{self._indent()}Words: [{", ".join(word_descs)}]\n"
            self.level -= 1

        # Show redirections
        if node.redirects:
            self.level += 1
            result += f"{self._indent()}Redirects:\n"
            result += self._visit_children(node.redirects)
            self.level -= 1

        return result

    def visit_Pipeline(self, node: Pipeline) -> str:
        """Format pipeline."""
        header = "Pipeline"
        if node.negated:
            header += " (negated)"
        result = self._format_header(header)
        return result + self._visit_children(node.commands)

    def visit_AndOrList(self, node: AndOrList) -> str:
        """Format and/or list."""
        result = self._format_header("AndOrList")

        for i, pipeline in enumerate(node.pipelines):
            if i > 0 and i - 1 < len(node.operators):
                self.level += 1
                result += f"{self._indent()}Operator: {node.operators[i-1]}\n"
                self.level -= 1
            result += self._visit_child(pipeline)

        return result

    # Control structures

    def visit_WhileLoop(self, node: WhileLoop) -> str:
        """Format while loop."""
        result = self._format_header("WhileLoop")

        self.level += 1
        result += f"{self._indent()}Condition:\n"
        result += self._visit_child(node.condition)

        result += f"{self._indent()}Body:\n"
        result += self._visit_child(node.body)
        self.level -= 1

        return result

    def visit_UntilLoop(self, node: UntilLoop) -> str:
        """Format until loop."""
        result = self._format_header("UntilLoop")

        self.level += 1
        result += f"{self._indent()}Condition:\n"
        result += self._visit_child(node.condition)

        result += f"{self._indent()}Body:\n"
        result += self._visit_child(node.body)
        self.level -= 1

        return result

    def visit_SubshellGroup(self, node: SubshellGroup) -> str:
        """Format subshell group ( ... )."""
        return self._format_group(node, "SubshellGroup")

    def visit_BraceGroup(self, node: BraceGroup) -> str:
        """Format brace group { ...; }."""
        return self._format_group(node, "BraceGroup")

    def _format_group(self, node, header: str) -> str:
        """Shared formatting for subshell / brace groups."""
        if node.background:
            header += " (background)"
        result = self._format_header(header)

        self.level += 1
        result += f"{self._indent()}Statements:\n"
        result += self._visit_child(node.statements)
        if node.redirects:
            result += f"{self._indent()}Redirects:\n"
            result += self._visit_children(node.redirects)
        self.level -= 1

        return result

    def visit_ForLoop(self, node: ForLoop) -> str:
        """Format for loop."""
        result = self._format_header(f"ForLoop (var: {node.variable})")

        self.level += 1
        result += f"{self._indent()}Items: {node.items}\n"
        result += f"{self._indent()}Body:\n"
        result += self._visit_child(node.body)
        self.level -= 1

        return result

    def visit_CStyleForLoop(self, node: CStyleForLoop) -> str:
        """Format C-style for loop."""
        result = self._format_header("CStyleForLoop")

        self.level += 1
        if node.init_expr:
            result += f"{self._indent()}Init: {node.init_expr}\n"
        if node.condition_expr:
            result += f"{self._indent()}Condition: {node.condition_expr}\n"
        if node.update_expr:
            result += f"{self._indent()}Update: {node.update_expr}\n"

        result += f"{self._indent()}Body:\n"
        result += self._visit_child(node.body)
        self.level -= 1

        return result

    def visit_IfConditional(self, node: IfConditional) -> str:
        """Format if statement."""
        result = self._format_header("IfConditional")

        self.level += 1
        result += f"{self._indent()}Condition:\n"
        result += self._visit_child(node.condition)

        result += f"{self._indent()}Then:\n"
        result += self._visit_child(node.then_part)

        # elif parts
        for i, (condition, then_part) in enumerate(node.elif_parts):
            result += f"{self._indent()}Elif {i+1} Condition:\n"
            result += self._visit_child(condition)
            result += f"{self._indent()}Elif {i+1} Then:\n"
            result += self._visit_child(then_part)

        # else part
        if node.else_part:
            result += f"{self._indent()}Else:\n"
            result += self._visit_child(node.else_part)

        self.level -= 1
        return result

    def visit_CaseConditional(self, node: CaseConditional) -> str:
        """Format case statement."""
        result = self._format_header(f"CaseStatement (expr: {node.expr})")
        return result + self._visit_children(node.items)

    def visit_CaseItem(self, node: CaseItem) -> str:
        """Format case item."""
        patterns = ' | '.join(p.pattern for p in node.patterns)
        result = self._format_header(f"CaseItem (patterns: {patterns})")

        self.level += 1
        result += f"{self._indent()}Commands:\n"
        result += self._visit_child(node.commands)
        result += f"{self._indent()}Terminator: {node.terminator}\n"
        self.level -= 1

        return result

    def visit_SelectLoop(self, node: SelectLoop) -> str:
        """Format select loop."""
        result = self._format_header(f"SelectLoop (var: {node.variable})")

        self.level += 1
        result += f"{self._indent()}Items: {node.items}\n"
        result += f"{self._indent()}Body:\n"
        result += self._visit_child(node.body)
        self.level -= 1

        return result

    # Other statement types

    def visit_FunctionDef(self, node: FunctionDef) -> str:
        """Format function definition."""
        result = self._format_header(f"FunctionDef (name: {node.name})")

        self.level += 1
        result += f"{self._indent()}Body:\n"
        result += self._visit_child(node.body)
        self.level -= 1

        return result

    def visit_BreakStatement(self, node: BreakStatement) -> str:
        """Format break statement."""
        return self._format_header(f"BreakStatement (level: {self._loop_level(node)})")

    def visit_ContinueStatement(self, node: ContinueStatement) -> str:
        """Format continue statement."""
        return self._format_header(f"ContinueStatement (level: {self._loop_level(node)})")

    @staticmethod
    def _loop_level(node) -> str:
        """Describe a break/continue level for debug output: the raw argument
        words when present (``$n``, ``foo``), else the literal int level."""
        if node.level_words:
            return ' '.join(w.source_text() for w in node.level_words)
        return str(node.level)

    def visit_ArithmeticEvaluation(self, node: ArithmeticEvaluation) -> str:
        """Format arithmetic command."""
        return self._format_header(f"ArithmeticCommand", f"(({node.expression}))")

    # Test expressions

    def visit_EnhancedTestStatement(self, node: EnhancedTestStatement) -> str:
        """Format enhanced test statement."""
        result = self._format_header("EnhancedTest [[...]]")

        self.level += 1
        result += f"{self._indent()}Expression:\n"
        result += self._visit_child(node.expression)
        self.level -= 1

        return result

    def visit_BinaryTestExpression(self, node: BinaryTestExpression) -> str:
        """Format binary test expression."""
        return self._format_header("BinaryTest", f"{node.left} {node.operator} {node.right}")

    def visit_UnaryTestExpression(self, node: UnaryTestExpression) -> str:
        """Format unary test expression."""
        return self._format_header("UnaryTest", f"{node.operator} {node.operand}")

    def visit_CompoundTestExpression(self, node: CompoundTestExpression) -> str:
        """Format compound test expression."""
        result = self._format_header(f"CompoundTest ({node.operator})")

        self.level += 1
        result += f"{self._indent()}Left:\n"
        result += self._visit_child(node.left)
        result += f"{self._indent()}Right:\n"
        result += self._visit_child(node.right)
        self.level -= 1

        return result

    def visit_NegatedTestExpression(self, node: NegatedTestExpression) -> str:
        """Format negated test expression."""
        result = self._format_header("NegatedTest (!)")
        return result + self._visit_child(node.expression)

    # Array assignments

    def visit_ArrayInitialization(self, node: ArrayInitialization) -> str:
        """Format array initialization."""
        op = '+=' if node.is_append else '='
        elements = ' '.join(repr(e) for e in node.elements)
        return self._format_header("ArrayInit", f"{node.name}{op}({elements})")

    def visit_ArrayElementAssignment(self, node: ArrayElementAssignment) -> str:
        """Format array element assignment."""
        op = '+=' if node.is_append else '='
        if isinstance(node.index, str):
            index_str = node.index
        else:
            # Token list
            index_str = ''.join(token.value for token in node.index)

        return self._format_header("ArrayElement", f"{node.name}[{index_str}]{op}{repr(node.value)}")

    # Redirections

    def visit_Redirect(self, node: Redirect) -> str:
        """Format redirection."""
        parts = []

        if node.fd is not None:
            parts.append(f"fd={node.fd}")

        parts.append(f"type={node.type}")

        if node.dup_fd is not None:
            parts.append(f"dup_fd={node.dup_fd}")
        else:
            parts.append(f"target={repr(node.target)}")

        if node.heredoc_content is not None:
            parts.append(f"heredoc=<{len(node.heredoc_content)} chars>")

        return self._format_header("Redirect", ', '.join(parts))

    def visit_ProcessSubstitution(self, node: ProcessSubstitution) -> str:
        """Format process substitution."""
        direction = '<' if node.direction == 'in' else '>'
        return self._format_header("ProcessSub", f"{direction}({node.command})")

    def generic_visit(self, node: ASTNode) -> str:
        """Default formatting for unknown nodes."""
        # For unknown nodes, try to display basic info
        node_type = node.__class__.__name__

        # Try to extract some useful info
        info_parts = []
        if hasattr(node, '__dict__'):
            for key, value in node.__dict__.items():
                if not key.startswith('_') and isinstance(value, (str, int, bool)):
                    info_parts.append(f"{key}={repr(value)}")

        if info_parts:
            return self._format_header(node_type, ', '.join(info_parts[:3]))
        else:
            return self._format_header(node_type, "(unknown)")
