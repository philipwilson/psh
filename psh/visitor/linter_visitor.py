"""
Linter visitor that performs code quality checks on shell scripts.

This visitor identifies potential issues and style problems in shell scripts,
providing warnings and suggestions for improvement.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set

from ..ast_nodes import ASTNode, FunctionDef, IfConditional, Pipeline, SimpleCommand, TopLevel
from .base import ASTVisitor
from .constants import COMMON_COMMANDS, SHELL_BUILTINS, TEST_OPERATORS
from .traversal import visit_children


class LintLevel(Enum):
    """Severity levels for lint issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    STYLE = "style"


@dataclass
class LintIssue:
    """Represents a single lint issue found in the script."""
    level: LintLevel
    message: str
    line: int = 0
    column: int = 0
    suggestion: Optional[str] = None

    def format(self) -> str:
        """Format the issue for display."""
        location = f"line {self.line}" if self.line > 0 else "script"
        result = f"[{self.level.value}] {location}: {self.message}"
        if self.suggestion:
            result += f"\n  Suggestion: {self.suggestion}"
        return result


@dataclass
class LinterConfig:
    """Configuration for the linter."""
    # Enable/disable specific checks
    check_undefined_vars: bool = True
    check_unused_vars: bool = True
    check_command_existence: bool = True
    check_quote_usage: bool = True
    check_error_handling: bool = True
    check_style: bool = True
    check_security: bool = True

    # Style preferences
    function_naming_pattern: str = r'^[a-z_][a-z0-9_]*$'
    max_line_length: int = 120
    prefer_double_brackets: bool = True


class LinterVisitor(ASTVisitor[None]):
    """
    Visitor that performs linting checks on shell scripts.

    This visitor analyzes the AST to find potential issues including:
    - Undefined/unused variables
    - Missing quotes that could cause word splitting
    - Commands that might not exist
    - Missing error handling
    - Style issues
    - Security concerns
    """

    def __init__(self, config: Optional[LinterConfig] = None):
        """Initialize linter with optional configuration."""
        super().__init__()
        self.config = config or LinterConfig()
        self.issues: List[LintIssue] = []

        # Variable tracking
        self.defined_vars: Set[str] = set()
        self.used_vars: Set[str] = set()
        self.exported_vars: Set[str] = set()

        # Function tracking
        self.defined_functions: Set[str] = set()
        self.used_functions: Set[str] = set()

        # Common shell builtins and commands
        self.builtins = SHELL_BUILTINS

        # Common external commands (not exhaustive)
        self.common_commands = COMMON_COMMANDS

        # Commands that should be used with caution
        self.dangerous_commands = {
            'rm': "Consider using 'rm -i' for interactive confirmation",
            'eval': "Eval can execute arbitrary code, ensure input is trusted",
            'exec': "Exec replaces the current shell, use with caution",
        }

        # Track context
        self._in_function = False
        self._in_subshell = False
        self._has_error_handling = False

    def add_issue(self, level: LintLevel, message: str,
                  suggestion: Optional[str] = None, line: int = 0):
        """Add a lint issue."""
        self.issues.append(LintIssue(level, message, line, suggestion=suggestion))

    def get_issues(self) -> List[LintIssue]:
        """Get all lint issues found."""
        return self.issues

    def get_summary(self) -> str:
        """Get a formatted summary of all issues."""
        if not self.issues:
            return "No issues found!"

        # Group by severity
        by_level = {}
        for issue in self.issues:
            by_level.setdefault(issue.level, []).append(issue)

        lines = ["Linting Summary:"]
        lines.append("=" * 50)

        # Count by level
        counts = []
        for level in LintLevel:
            if level in by_level:
                counts.append(f"{len(by_level[level])} {level.value}s")
        lines.append(f"Found {len(self.issues)} issues: " + ", ".join(counts))
        lines.append("")

        # Display issues by level
        for level in [LintLevel.ERROR, LintLevel.WARNING, LintLevel.INFO, LintLevel.STYLE]:
            if level in by_level:
                lines.append(f"\n{level.value.upper()}S:")
                lines.append("-" * 30)
                for issue in by_level[level]:
                    lines.append(issue.format())

        return "\n".join(lines)

    # Visitor methods

    def visit_TopLevel(self, node: TopLevel) -> None:
        """Visit top-level script."""
        # Visit all items
        for item in node.items:
            self.visit(item)

        # Check for unused variables
        if self.config.check_unused_vars:
            unused = self.defined_vars - self.used_vars - self.exported_vars
            # Filter out special variables
            unused = {v for v in unused if not v.startswith('_') and v not in {'@', '*', '#', '?', '$', '!'}}
            for var in sorted(unused):
                self.add_issue(
                    LintLevel.WARNING,
                    f"Variable '{var}' is defined but never used",
                    suggestion="Remove unused variable or export it if needed externally"
                )

        # Check for undefined functions
        undefined_funcs = self.used_functions - self.defined_functions
        for func in sorted(undefined_funcs):
            if func not in self.builtins and func not in self.common_commands:
                self.add_issue(
                    LintLevel.WARNING,
                    f"Function '{func}' is called but not defined",
                    suggestion="Define the function or check for typos"
                )

        # Check for missing error handling
        if self.config.check_error_handling and not self._has_error_handling:
            self.add_issue(
                LintLevel.INFO,
                "Script has no explicit error handling",
                suggestion="Consider adding 'set -e' or checking exit codes"
            )

    def visit_SimpleCommand(self, node: SimpleCommand) -> None:
        """Visit simple command."""
        if not node.args:
            return

        cmd = node.args[0]

        # Track function calls
        self.used_functions.add(cmd)

        # Check for dangerous commands
        if self.config.check_security and cmd in self.dangerous_commands:
            self.add_issue(
                LintLevel.WARNING,
                f"Use of potentially dangerous command '{cmd}'",
                suggestion=self.dangerous_commands[cmd]
            )

        # Check for variable assignments
        for arg in node.args:
            if '=' in arg and self._is_assignment(arg):
                var_name = arg.split('=', 1)[0]
                self.defined_vars.add(var_name)

        # Check specific commands
        if cmd == 'set':
            self._check_set_command(node.args[1:])
        elif cmd == 'export':
            self._check_export_command(node.args[1:])
        elif cmd == 'test' or cmd == '[':
            self._check_test_command(node.args[1:])
        elif cmd in ['rm', 'mv', 'cp'] and len(node.args) > 1:
            self._check_file_command(cmd, node.args[1:])

        # Check for command existence (basic check)
        if self.config.check_command_existence:
            if (cmd not in self.builtins and
                cmd not in self.common_commands and
                cmd not in self.defined_functions and
                not cmd.startswith('./') and
                not cmd.startswith('/') and
                not '=' in cmd):
                self.add_issue(
                    LintLevel.INFO,
                    f"Command '{cmd}' might not be available",
                    suggestion="Ensure the command exists or use 'command -v' to check"
                )

        # Visit args for variable usage
        for arg in node.args[1:]:
            if '$' in arg:
                self._check_variable_usage(arg)

    def visit_FunctionDef(self, node: FunctionDef) -> None:
        """Visit function definition."""
        self.defined_functions.add(node.name)

        # Check function naming
        if self.config.check_style:
            import re
            if not re.match(self.config.function_naming_pattern, node.name):
                self.add_issue(
                    LintLevel.STYLE,
                    f"Function name '{node.name}' doesn't match naming convention",
                    suggestion="Use lowercase with underscores (e.g., my_function)"
                )

        # Visit body in function context
        old_in_function = self._in_function
        self._in_function = True
        self.visit(node.body)
        self._in_function = old_in_function

    def visit_IfConditional(self, node: IfConditional) -> None:
        """Visit if statement."""
        # Check condition
        self.visit(node.condition)
        self.visit(node.then_part)

        # Check elif parts
        for elif_cond, elif_then in node.elif_parts:
            self.visit(elif_cond)
            self.visit(elif_then)

        # Check else
        if node.else_part:
            self.visit(node.else_part)

    def visit_Pipeline(self, node: Pipeline) -> None:
        """Visit pipeline."""
        # Check for useless use of cat
        if len(node.commands) >= 2:
            first_cmd = node.commands[0]
            if (isinstance(first_cmd, SimpleCommand) and
                first_cmd.args and first_cmd.args[0] == 'cat' and
                len(first_cmd.args) == 2):
                second_cmd = node.commands[1]
                if isinstance(second_cmd, SimpleCommand) and second_cmd.args:
                    next_cmd = second_cmd.args[0]
                    if next_cmd in ['grep', 'sed', 'awk', 'head', 'tail']:
                        self.add_issue(
                            LintLevel.STYLE,
                            "Useless use of cat",
                            suggestion=f"Use '{next_cmd} {first_cmd.args[1]}' directly"
                        )

        # Visit all commands
        for cmd in node.commands:
            self.visit(cmd)

    # Helper methods

    def _is_assignment(self, arg: str) -> bool:
        """Check if argument is a variable assignment."""
        if '=' not in arg:
            return False
        var_part = arg.split('=', 1)[0]
        # Valid variable name starts with letter or underscore
        if not var_part or not (var_part[0].isalpha() or var_part[0] == '_'):
            return False
        # Rest must be alphanumeric or underscore
        return all(c.isalnum() or c == '_' for c in var_part[1:])

    def _check_variable_usage(self, text: str) -> None:
        """Check for variable usage in text."""
        import re
        # Find all variable references
        var_pattern = r'\$(?:([A-Za-z_][A-Za-z0-9_]*)|{([A-Za-z_][A-Za-z0-9_]*)[^}]*})'
        for match in re.finditer(var_pattern, text):
            var_name = match.group(1) or match.group(2)
            if var_name:
                self.used_vars.add(var_name)

                # Check if variable is defined
                if (self.config.check_undefined_vars and
                    var_name not in self.defined_vars and
                    var_name not in ['PATH', 'HOME', 'USER', 'SHELL', 'PWD',
                                     'OLDPWD', 'IFS', 'PS1', 'PS2', 'PS3', 'PS4']):
                    self.add_issue(
                        LintLevel.WARNING,
                        f"Variable '{var_name}' may be undefined",
                        suggestion="Define the variable or use ${var:-default}"
                    )

    def _check_set_command(self, args: List[str]) -> None:
        """Check set command for error handling."""
        for arg in args:
            if arg == '-e' or arg == '-o' and 'errexit' in args:
                self._has_error_handling = True
            elif arg == '-u' or arg == '-o' and 'nounset' in args:
                # Good practice
                pass

    def _check_export_command(self, args: List[str]) -> None:
        """Check export command."""
        for arg in args:
            if '=' in arg:
                var_name = arg.split('=', 1)[0]
                self.defined_vars.add(var_name)
                self.exported_vars.add(var_name)
            else:
                self.exported_vars.add(arg)

    def _check_test_command(self, args: List[str]) -> None:
        """Check test/[ command usage."""
        if not args:
            return

        # Check for missing quotes on variables
        if self.config.check_quote_usage:
            for i, arg in enumerate(args):
                if arg.startswith('$') and ' ' not in arg:
                    # Check if it's in a context where it should be quoted
                    if i > 0 and args[i-1] in TEST_OPERATORS:
                        self.add_issue(
                            LintLevel.WARNING,
                            f"Unquoted variable '{arg}' in test command",
                            suggestion=f'Use "{arg}" to prevent word splitting'
                        )

        # Suggest [[ over [
        if self.config.prefer_double_brackets and args and args[-1] == ']':
            self.add_issue(
                LintLevel.STYLE,
                "Consider using [[ ]] instead of [ ]",
                suggestion="[[ ]] is safer and more feature-rich"
            )

    def _check_file_command(self, cmd: str, args: List[str]) -> None:
        """Check file manipulation commands."""
        if cmd == 'rm' and '-f' not in args and '-i' not in args:
            self.add_issue(
                LintLevel.INFO,
                f"'{cmd}' without -i flag",
                suggestion="Consider using 'rm -i' for safety"
            )

        # Check for unquoted variables that might contain spaces
        if self.config.check_quote_usage:
            for arg in args:
                if arg.startswith('$') and not arg.startswith('"$'):
                    self.add_issue(
                        LintLevel.WARNING,
                        f"Unquoted variable '{arg}' in {cmd} command",
                        suggestion=f'Use "{arg}" to handle filenames with spaces'
                    )

    def generic_visit(self, node: ASTNode) -> None:
        """Descend into child nodes for unhandled node types."""
        visit_children(self, node)
