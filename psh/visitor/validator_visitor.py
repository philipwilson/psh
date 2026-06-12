"""
AST validator visitor that checks for semantic errors and warnings.

This visitor demonstrates how to use the visitor pattern for AST analysis,
collecting errors and warnings about the code structure.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set

from ..ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    ArrayElementAssignment,
    # Array nodes
    ArrayInitialization,
    # Core nodes
    ASTNode,
    BraceGroup,
    BreakStatement,
    CaseConditional,
    # Case components
    CaseItem,
    ContinueStatement,
    CStyleForLoop,
    EnhancedTestStatement,
    ForLoop,
    # Function nodes
    FunctionDef,
    IfConditional,
    Pipeline,
    Redirect,
    SelectLoop,
    SimpleCommand,
    StatementList,
    SubshellGroup,
    TopLevel,
    UntilLoop,
    # Control structures
    WhileLoop,
)
from .base import ASTVisitor


class Severity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """A validation issue found in the AST."""
    severity: Severity
    message: str
    node_type: str
    context: Optional[str] = None


class ValidatorVisitor(ASTVisitor[None]):
    """
    Visitor that validates AST correctness and collects issues.

    This visitor checks for:
    - Semantic errors (break/continue outside loops, etc.)
    - Common mistakes and anti-patterns
    - Potential bugs or suspicious constructs
    - Style issues and best practices
    """

    def __init__(self):
        """Initialize the validator."""
        super().__init__()
        self.issues: List[ValidationIssue] = []
        self.in_function: bool = False
        self.in_loop: int = 0  # Nesting level of loops
        self.function_names: Set[str] = set()
        self.variable_names: Set[str] = set()
        self.current_context: List[str] = []  # Stack of contexts

    def _push_context(self, context: str):
        """Push a new context onto the stack."""
        self.current_context.append(context)

    def _pop_context(self):
        """Pop the current context from the stack."""
        if self.current_context:
            self.current_context.pop()

    def _get_context(self) -> Optional[str]:
        """Get the current context string."""
        return ' > '.join(self.current_context) if self.current_context else None

    def _add_error(self, message: str, node: ASTNode):
        """Add an error for the given node."""
        self.issues.append(ValidationIssue(
            severity=Severity.ERROR,
            message=message,
            node_type=node.__class__.__name__,
            context=self._get_context()
        ))

    def _add_warning(self, message: str, node: ASTNode):
        """Add a warning for the given node."""
        self.issues.append(ValidationIssue(
            severity=Severity.WARNING,
            message=message,
            node_type=node.__class__.__name__,
            context=self._get_context()
        ))

    def _add_info(self, message: str, node: ASTNode):
        """Add an info message for the given node."""
        self.issues.append(ValidationIssue(
            severity=Severity.INFO,
            message=message,
            node_type=node.__class__.__name__,
            context=self._get_context()
        ))

    def _visit_redirects(self, node: ASTNode):
        """Validate redirects carried by *node* (compound commands too)."""
        for redirect in getattr(node, 'redirects', []):
            self.visit(redirect)

    # Top-level nodes

    def visit_TopLevel(self, node: TopLevel) -> None:
        """Validate top-level script."""
        for item in node.items:
            self.visit(item)

    def visit_StatementList(self, node: StatementList) -> None:
        """Validate a list of statements."""
        for stmt in node.statements:
            self.visit(stmt)

    # Command nodes

    def visit_SimpleCommand(self, node: SimpleCommand) -> None:
        """Validate a simple command."""
        if not node.args and not node.array_assignments:
            self._add_error("Empty command with no arguments or assignments", node)
            return

        if node.args:
            cmd = node.args[0]

            # Check for common mistakes
            if cmd == 'cd' and len(node.args) > 2:
                self._add_warning(
                    f"cd: too many arguments (got {len(node.args) - 1}, expected 0 or 1)",
                    node
                )

            # Check for deprecated commands
            if cmd == 'which':
                self._add_info(
                    "Consider using 'command -v' instead of 'which' for better portability",
                    node
                )

            # Check for useless cat
            if cmd == 'cat' and len(node.args) == 2 and node in getattr(self, '_in_pipeline', []):
                self._add_warning(
                    "Useless use of cat - consider using input redirection instead",
                    node
                )

            # Track variable usage in assignments
            for arg in node.args[1:]:
                if '=' in arg and not arg.startswith('='):
                    var_name = arg.split('=', 1)[0]
                    self.variable_names.add(var_name)

        # Validate array assignments
        for assignment in node.array_assignments:
            self.visit(assignment)

        # Validate redirections
        for redirect in node.redirects:
            self.visit(redirect)

    def visit_Pipeline(self, node: Pipeline) -> None:
        """Validate a pipeline."""
        if not node.commands:
            self._add_error("Empty pipeline with no commands", node)
            return

        # Track that we're in a pipeline for context
        old_pipeline = getattr(self, '_in_pipeline', None)
        self._in_pipeline = node.commands

        # Check for redundant pipelines - disabled by default as it's too noisy
        # if len(node.commands) == 1 and not node.negated:
        #     self._add_info(
        #         "Single-command pipeline can be simplified to just the command",
        #         node
        #     )

        # Visit all commands
        for i, cmd in enumerate(node.commands):
            if i > 0:
                self._push_context(f"pipeline command {i + 1}")
            self.visit(cmd)
            if i > 0:
                self._pop_context()

        self._in_pipeline = old_pipeline

    def visit_AndOrList(self, node: AndOrList) -> None:
        """Validate an and/or list."""
        if not node.pipelines:
            self._add_error("Empty and/or list with no pipelines", node)
            return

        # Check operator count matches pipeline count
        if len(node.operators) != len(node.pipelines) - 1:
            self._add_error(
                f"Mismatched operators and pipelines: {len(node.operators)} operators "
                f"for {len(node.pipelines)} pipelines",
                node
            )

        # Visit all pipelines
        for pipeline in node.pipelines:
            self.visit(pipeline)

    # Control structures

    def visit_WhileLoop(self, node: WhileLoop) -> None:
        """Validate a while loop."""
        self._push_context("while loop")
        self.in_loop += 1

        # Check condition
        if not node.condition.statements:
            self._add_warning("While loop with empty condition will loop forever", node)

        self.visit(node.condition)
        self.visit(node.body)

        self.in_loop -= 1
        self._pop_context()
        self._visit_redirects(node)

    def visit_UntilLoop(self, node: UntilLoop) -> None:
        """Validate an until loop (mirrors while: condition + body + loop nesting)."""
        self._push_context("until loop")
        self.in_loop += 1

        # Check condition
        if not node.condition.statements:
            self._add_warning("Until loop with empty condition will loop forever", node)

        self.visit(node.condition)
        self.visit(node.body)

        self.in_loop -= 1
        self._pop_context()
        self._visit_redirects(node)

    def visit_ForLoop(self, node: ForLoop) -> None:
        """Validate a for loop."""
        self._push_context(f"for loop (var: {node.variable})")
        self.in_loop += 1

        # Check for empty items
        if not node.items:
            self._add_warning("For loop with no items will not execute", node)

        # Check variable name
        if node.variable.isdigit():
            self._add_error(f"Invalid variable name '{node.variable}' (cannot be numeric)", node)

        # Track loop variable
        self.variable_names.add(node.variable)

        self.visit(node.body)

        self.in_loop -= 1
        self._pop_context()
        self._visit_redirects(node)

    def visit_CStyleForLoop(self, node: CStyleForLoop) -> None:
        """Validate a C-style for loop."""
        self._push_context("C-style for loop")
        self.in_loop += 1

        # Check for infinite loop patterns
        if not node.condition_expr:
            self._add_warning(
                "C-style for loop with no condition will loop forever "
                "(use 'while true' for clarity)",
                node
            )

        self.visit(node.body)

        self.in_loop -= 1
        self._pop_context()
        self._visit_redirects(node)

    def visit_IfConditional(self, node: IfConditional) -> None:
        """Validate an if statement."""
        self._push_context("if statement")

        # Check condition
        if not node.condition.statements:
            self._add_error("If statement with empty condition", node)

        self.visit(node.condition)

        # Check then part
        if not node.then_part.statements:
            self._add_warning("If statement with empty then block", node)

        self.visit(node.then_part)

        # Check elif parts
        for i, (condition, then_part) in enumerate(node.elif_parts):
            self._push_context(f"elif {i + 1}")

            if not condition.statements:
                self._add_error("Elif with empty condition", node)

            self.visit(condition)
            self.visit(then_part)

            self._pop_context()

        # Check else part
        if node.else_part:
            self._push_context("else")
            self.visit(node.else_part)
            self._pop_context()

        self._pop_context()
        self._visit_redirects(node)

    def visit_CaseConditional(self, node: CaseConditional) -> None:
        """Validate a case statement."""
        self._push_context(f"case statement (expr: {node.expr})")

        if not node.items:
            self._add_warning("Case statement with no patterns", node)

        # Check for duplicate patterns
        seen_patterns: Set[str] = set()
        for item in node.items:
            for pattern in item.patterns:
                if pattern.pattern in seen_patterns:
                    self._add_warning(
                        f"Duplicate case pattern '{pattern.pattern}'",
                        node
                    )
                seen_patterns.add(pattern.pattern)

            self.visit(item)

        self._pop_context()
        self._visit_redirects(node)

    def visit_CaseItem(self, node: CaseItem) -> None:
        """Validate a case item."""
        if not node.patterns:
            self._add_error("Case item with no patterns", node)

        patterns_str = ', '.join(p.pattern for p in node.patterns)
        self._push_context(f"case pattern: {patterns_str}")

        self.visit(node.commands)

        # Check terminator usage
        if node.terminator == ';&' or node.terminator == ';;&':
            self._add_info(
                f"Using advanced case terminator '{node.terminator}' - "
                "ensure this is intentional",
                node
            )

        self._pop_context()

    def visit_SelectLoop(self, node: SelectLoop) -> None:
        """Validate a select loop."""
        self._push_context(f"select loop (var: {node.variable})")
        self.in_loop += 1

        if not node.items:
            self._add_warning("Select loop with no items", node)

        # Track loop variable
        self.variable_names.add(node.variable)

        self.visit(node.body)

        self.in_loop -= 1
        self._pop_context()
        self._visit_redirects(node)

    # Group commands

    def visit_SubshellGroup(self, node: SubshellGroup) -> None:
        """Validate a subshell group ( ... )."""
        self._push_context("subshell group")
        self.visit(node.statements)
        self._pop_context()
        self._visit_redirects(node)

    def visit_BraceGroup(self, node: BraceGroup) -> None:
        """Validate a brace group { ...; }."""
        self._push_context("brace group")
        self.visit(node.statements)
        self._pop_context()
        self._visit_redirects(node)

    def visit_ArithmeticEvaluation(self, node: ArithmeticEvaluation) -> None:
        """Validate an arithmetic command (( ... ))."""
        if not node.expression.strip():
            self._add_warning("Arithmetic command with empty expression", node)
        self._visit_redirects(node)

    # Break/Continue validation

    def visit_BreakStatement(self, node: BreakStatement) -> None:
        """Validate a break statement."""
        if self.in_loop == 0:
            self._add_error("break: only meaningful in a `for', `while', or `until' loop", node)
        elif node.level > self.in_loop:
            self._add_error(
                f"break: loop count {node.level} exceeds maximum nesting level {self.in_loop}",
                node
            )

    def visit_ContinueStatement(self, node: ContinueStatement) -> None:
        """Validate a continue statement."""
        if self.in_loop == 0:
            self._add_error("continue: only meaningful in a `for', `while', or `until' loop", node)
        elif node.level > self.in_loop:
            self._add_error(
                f"continue: loop count {node.level} exceeds maximum nesting level {self.in_loop}",
                node
            )

    # Function validation

    def visit_FunctionDef(self, node: FunctionDef) -> None:
        """Validate a function definition."""
        # Check for duplicate function names
        if node.name in self.function_names:
            self._add_warning(f"Redefinition of function '{node.name}'", node)

        self.function_names.add(node.name)

        # Check function name validity
        if node.name[0].isdigit():
            self._add_error(f"Invalid function name '{node.name}' (cannot start with digit)", node)

        # Visit function body
        old_in_function = self.in_function
        self.in_function = True
        self._push_context(f"function {node.name}")

        self.visit(node.body)

        self._pop_context()
        self.in_function = old_in_function
        self._visit_redirects(node)

    # Array validation

    def visit_ArrayInitialization(self, node: ArrayInitialization) -> None:
        """Validate array initialization."""
        self.variable_names.add(node.name)

        # Check for type consistency in elements
        if node.element_types:
            first_type = node.element_types[0]
            if not all(t == first_type for t in node.element_types):
                self._add_info(
                    f"Array '{node.name}' initialized with mixed element types",
                    node
                )

    def visit_ArrayElementAssignment(self, node: ArrayElementAssignment) -> None:
        """Validate array element assignment."""
        self.variable_names.add(node.name)

        # For now, basic validation only
        # More sophisticated checks could validate index expressions

    # Redirection validation

    def visit_Redirect(self, node: Redirect) -> None:
        """Validate a redirection."""
        # Check for common mistakes
        if node.type == '>' and node.target in ['&1', '&2']:
            self._add_error(
                f"Invalid redirection syntax '>{node.target}' - use '>&{node.target[1:]}' instead",
                node
            )

        # Warn about noclobber
        if node.type == '>' and node.target != '/dev/null':
            self._add_info(
                "Consider using '>|' to force overwrite or '>>' to append",
                node
            )

    def visit_EnhancedTestStatement(self, node: EnhancedTestStatement) -> None:
        """Validate enhanced test statement."""
        # The test expression itself is not validated here (operands are
        # plain strings); only the attached redirects are checked.
        self._visit_redirects(node)

    def generic_visit(self, node: ASTNode) -> None:
        """Default handling for unknown nodes."""
        # For nodes we don't specifically handle, do nothing
        pass

    def get_summary(self) -> str:
        """Get a summary of validation results."""
        if not self.issues:
            return "No issues found - AST is valid!"

        # Count by severity
        error_count = sum(1 for i in self.issues if i.severity == Severity.ERROR)
        warning_count = sum(1 for i in self.issues if i.severity == Severity.WARNING)
        info_count = sum(1 for i in self.issues if i.severity == Severity.INFO)

        lines = [f"Found {len(self.issues)} issue(s):"]
        if error_count:
            lines.append(f"  - {error_count} error(s)")
        if warning_count:
            lines.append(f"  - {warning_count} warning(s)")
        if info_count:
            lines.append(f"  - {info_count} info message(s)")

        lines.append("")

        # Group by severity
        for severity in [Severity.ERROR, Severity.WARNING, Severity.INFO]:
            severity_issues = [i for i in self.issues if i.severity == severity]
            if severity_issues:
                lines.append(f"{severity.value.upper()}S:")
                for issue in severity_issues:
                    prefix = f"  [{issue.node_type}]"
                    if issue.context:
                        prefix += f" in {issue.context}"
                    lines.append(f"{prefix}: {issue.message}")
                lines.append("")

        return '\n'.join(lines).rstrip()
