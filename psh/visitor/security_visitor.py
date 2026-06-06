"""
Security analysis visitor for PSH.

This visitor analyzes AST for potential security vulnerabilities and
dangerous patterns in shell scripts.
"""

import re
from typing import Dict, List

from ..ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    ASTNode,
    CaseConditional,
    ForLoop,
    FunctionDef,
    IfConditional,
    Pipeline,
    Redirect,
    SimpleCommand,
    StatementList,
    TopLevel,
    WhileLoop,
)
from .analysis_helpers import has_unquoted_expansion
from .base import ASTVisitor
from .constants import DANGEROUS_COMMANDS, SENSITIVE_COMMANDS
from .traversal import visit_children


class SecurityIssue:
    """Represents a security issue found in the AST."""

    def __init__(self, severity: str, issue_type: str, message: str, node: ASTNode):
        self.severity = severity  # 'HIGH', 'MEDIUM', 'LOW'
        self.issue_type = issue_type
        self.message = message
        self.node = node

    def __str__(self):
        return f"[{self.severity}] {self.issue_type}: {self.message}"


class SecurityVisitor(ASTVisitor[None]):
    """
    Analyze AST for security vulnerabilities.

    Detects:
    - Command injection risks
    - Unsafe use of eval
    - World-writable file permissions
    - Unquoted variable expansions that could be exploited
    - Dangerous commands and patterns
    """

    def __init__(self):
        """Initialize the security visitor."""
        super().__init__()
        self.issues: List[SecurityIssue] = []
        self.in_function = False
        self.function_stack = []

        # Dangerous commands that should be flagged
        self.dangerous_commands = DANGEROUS_COMMANDS

        # Commands that need careful handling
        self.sensitive_commands = SENSITIVE_COMMANDS

    def visit_SimpleCommand(self, node: SimpleCommand) -> None:
        """Analyze simple commands for security issues."""
        if not node.args:
            return

        cmd = node.args[0]

        # Check for dangerous commands
        if cmd in self.dangerous_commands:
            self.issues.append(SecurityIssue(
                'HIGH',
                'DANGEROUS_COMMAND',
                f"{cmd}: {self.dangerous_commands[cmd]}",
                node
            ))

        # Check for sensitive commands
        if cmd in self.sensitive_commands:
            self.issues.append(SecurityIssue(
                'MEDIUM',
                'SENSITIVE_COMMAND',
                f"{cmd}: {self.sensitive_commands[cmd]}",
                node
            ))

        # Check for world-writable permissions in chmod
        if cmd == 'chmod' and len(node.args) > 1:
            for arg in node.args[1:]:
                if self._is_world_writable_permission(arg):
                    self.issues.append(SecurityIssue(
                        'HIGH',
                        'WORLD_WRITABLE',
                        f"chmod {arg}: Creates world-writable files - security risk",
                        node
                    ))

        # Check for unquoted variable expansions in dangerous contexts
        if cmd in ['eval', 'sh', 'bash', 'zsh', 'ksh']:
            words = node.words if node.words else []
            if len(words) > 1:
                for i, (arg, word) in enumerate(zip(node.args[1:], words[1:])):
                    # Variable expansion or unquoted word with $
                    if word.is_variable_expansion or has_unquoted_expansion(word, arg):
                        self.issues.append(SecurityIssue(
                            'HIGH',
                            'UNQUOTED_EXPANSION',
                            f"Unquoted variable in {cmd} - potential command injection",
                            node
                        ))
            else:
                # Fallback: check args directly if no Word info
                for arg in node.args[1:]:
                    if '$' in arg:
                        self.issues.append(SecurityIssue(
                            'HIGH',
                            'UNQUOTED_EXPANSION',
                            f"Unquoted variable in {cmd} - potential command injection",
                            node
                        ))

        # Check for rm -rf on root directories
        if cmd == 'rm' and '-rf' in ' '.join(node.args):
            for arg in node.args:
                if arg in ['/', '/*', '/bin', '/usr', '/etc', '/var', '/home']:
                    self.issues.append(SecurityIssue(
                        'HIGH',
                        'DANGEROUS_RM',
                        f"rm -rf {arg}: Extremely dangerous operation",
                        node
                    ))

        # Check for curl/wget piped to sh
        if cmd in ['curl', 'wget'] and self._is_piped_to_shell(node):
            self.issues.append(SecurityIssue(
                'HIGH',
                'REMOTE_CODE_EXECUTION',
                f"{cmd} piped to shell: Executing remote code without verification",
                node
            ))

        # Also check redirects on the command
        for redirect in node.redirects:
            self.visit_Redirect(redirect)

    def visit_Pipeline(self, node: Pipeline) -> None:
        """Analyze pipelines for security issues."""
        # Check for dangerous pipeline patterns
        commands = []
        for cmd in node.commands:
            if isinstance(cmd, SimpleCommand) and cmd.args:
                commands.append(cmd.args[0])
            self.visit(cmd)

        # Detect curl/wget | sh pattern
        if len(commands) >= 2:
            if commands[0] in ['curl', 'wget'] and commands[-1] in ['sh', 'bash', 'zsh', 'ksh']:
                self.issues.append(SecurityIssue(
                    'HIGH',
                    'REMOTE_CODE_EXECUTION',
                    'Downloading and executing remote code without verification',
                    node
                ))

    def visit_Redirect(self, node: Redirect) -> None:
        """Analyze redirections for security issues."""
        # Check for redirecting to sensitive files
        sensitive_files = ['/etc/passwd', '/etc/shadow', '/etc/sudoers']
        if node.target in sensitive_files and node.type in ['>', '>>']:
            self.issues.append(SecurityIssue(
                'HIGH',
                'SENSITIVE_FILE_WRITE',
                f"Writing to sensitive file: {node.target}",
                node
            ))

    def visit_FunctionDef(self, node: FunctionDef) -> None:
        """Analyze function definitions."""
        self.in_function = True
        self.function_stack.append(node.name)
        self.visit(node.body)
        self.function_stack.pop()
        self.in_function = bool(self.function_stack)

    def visit_ForLoop(self, node: ForLoop) -> None:
        """Analyze for loops for security issues."""
        # Check for iterating over unquoted command substitution
        for item in node.items:
            if item.startswith('$(') or item.startswith('`'):
                self.issues.append(SecurityIssue(
                    'MEDIUM',
                    'UNQUOTED_SUBSTITUTION',
                    'Iterating over unquoted command substitution - may break on spaces',
                    node
                ))

        # Continue analyzing the body
        self.visit(node.body)

    def visit_ArithmeticEvaluation(self, node: ArithmeticEvaluation) -> None:
        """Analyze arithmetic expressions."""
        # Check for variable expansion that could lead to code execution
        # Note: In the AST, variables have already been parsed so $ is removed
        expr = node.expression.strip()

        # Remove spaces, digits, operators, and parentheses to see what's left
        test_expr = expr
        for char in '0123456789+-*/%()= \t<>!&|^~':
            test_expr = test_expr.replace(char, '')

        # If we have any alphabetic characters left, it's likely a variable
        if test_expr and any(c.isalpha() or c == '_' for c in test_expr):
            self.issues.append(SecurityIssue(
                'MEDIUM',
                'ARITHMETIC_INJECTION',
                'Variable expansion in arithmetic - ensure variables contain only numbers',
                node
            ))

    # Visit methods for other nodes that just traverse
    def visit_TopLevel(self, node: TopLevel) -> None:
        for item in node.items:
            self.visit(item)

    def visit_StatementList(self, node: StatementList) -> None:
        for stmt in node.statements:
            self.visit(stmt)

    def visit_AndOrList(self, node: AndOrList) -> None:
        for pipeline in node.pipelines:
            self.visit(pipeline)

    def visit_IfConditional(self, node: IfConditional) -> None:
        self.visit(node.condition)
        self.visit(node.then_part)
        for cond, then in node.elif_parts:
            self.visit(cond)
            self.visit(then)
        if node.else_part:
            self.visit(node.else_part)

    def visit_WhileLoop(self, node: WhileLoop) -> None:
        self.visit(node.condition)
        self.visit(node.body)

    def visit_CaseConditional(self, node: CaseConditional) -> None:
        for item in node.items:
            self.visit(item.commands)

    # Helper methods

    def _is_world_writable_permission(self, perm: str) -> bool:
        """Check if a permission string makes files world-writable."""
        # Check for octal permissions
        if re.match(r'^\d{3,4}$', perm):
            # Check if other-write bit is set (xx2, xx3, xx6, xx7)
            return int(perm[-1]) & 2 != 0
        # Check for symbolic permissions
        elif 'o+w' in perm or 'a+w' in perm or 'o=w' in perm:
            return True
        elif perm == '777' or perm == '0777':
            return True
        return False

    def _is_piped_to_shell(self, node: SimpleCommand) -> bool:
        """Check if command is part of a pipeline to a shell."""
        # This is a simplified check - would need parent context
        # In real implementation, would check parent Pipeline node
        return False

    def get_report(self) -> Dict[str, any]:
        """Get a security report."""
        high = [i for i in self.issues if i.severity == 'HIGH']
        medium = [i for i in self.issues if i.severity == 'MEDIUM']
        low = [i for i in self.issues if i.severity == 'LOW']

        return {
            'total_issues': len(self.issues),
            'high_severity': len(high),
            'medium_severity': len(medium),
            'low_severity': len(low),
            'issues': self.issues
        }

    def get_summary(self) -> str:
        """Get a formatted summary of security issues."""
        if not self.issues:
            return "No security issues found!"

        # Group by severity
        high = [i for i in self.issues if i.severity == 'HIGH']
        medium = [i for i in self.issues if i.severity == 'MEDIUM']
        low = [i for i in self.issues if i.severity == 'LOW']

        lines = ["Security Analysis Summary:"]
        lines.append("═" * 30)
        lines.append(f"Total Issues: {len(self.issues)}")
        lines.append(f"  High Risk:   {len(high):>3}")
        lines.append(f"  Medium Risk: {len(medium):>3}")
        lines.append(f"  Low Risk:    {len(low):>3}")
        lines.append("")

        # Show issues by severity
        for severity, issues in [("HIGH", high), ("MEDIUM", medium), ("LOW", low)]:
            if issues:
                lines.append(f"{severity} RISK ISSUES:")
                for issue in issues:
                    lines.append(f"  • {issue.message}")
                lines.append("")

        return "\n".join(lines)

    def generic_visit(self, node: ASTNode) -> None:
        """Descend into child nodes for unhandled node types."""
        visit_children(self, node)
