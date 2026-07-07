"""
Linter visitor that performs code quality checks on shell scripts.

This visitor identifies potential issues and style problems in shell scripts,
providing warnings and suggestions for improvement.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set

from ..ast_nodes import (
    ASTNode,
    FunctionDef,
    IfConditional,
    Pipeline,
    Program,
    Redirect,
    SimpleCommand,
    Word,
)
from .analysis_helpers import RedirectTraversalMixin
from .base import ASTVisitor
from .constants import COMMON_COMMANDS, SHELL_BUILTINS, TEST_OPERATORS
from .traversal import visit_children, visit_word_substitution_bodies
from .word_analysis import (
    has_unquoted_variable_expansion,
    iter_variable_references,
    iter_variable_references_in_text,
)


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


class LinterVisitor(RedirectTraversalMixin, ASTVisitor[None]):
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
        by_level: Dict[LintLevel, List[LintIssue]] = {}
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

    def visit_Program(self, node: Program) -> None:
        """Visit a program (the canonical root)."""
        for statement in node.statements:
            self.visit(statement)
        self._check_program_level_issues()

    def _check_program_level_issues(self) -> None:
        """Root-level lint checks run after the whole program is traversed."""
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
            self._check_test_command(node.words[1:])
        elif cmd in ['rm', 'mv', 'cp'] and len(node.args) > 1:
            self._check_file_command(cmd, node.words[1:])

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

        # Visit args for variable usage. Read references STRUCTURALLY from each
        # argument's Word AST (parts) rather than regexing the rendered string;
        # this skips command/arithmetic substitutions and honors quoting and
        # ``${var:-default}`` defaults through the parsed model.
        for word in node.words[1:]:
            self._check_word_variable_usage(word)

        # Apply the same checks to redirect targets (e.g. `cmd > $undefined.log`).
        self._visit_redirects(node)

        # Lint the commands inside any $(...)/<(...)/>(...) argument. Visits the
        # substitution body's statements (not its Program), so per-command
        # checks fire on the inner commands without re-running the root-level
        # (unused-var / error-handling) checks for each substitution.
        visit_word_substitution_bodies(self, node)

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

        # A function definition can carry redirects (`f() { ...; } > log`).
        self._visit_redirects(node)

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

        # An if statement can carry redirects (`if ...; fi > log`).
        self._visit_redirects(node)

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

    def visit_Redirect(self, node: Redirect) -> None:
        """Apply word/expansion checks to a redirection's target and body.

        Redirect targets are ordinary words (``cmd > $undefined.log``) and so
        deserve the same variable-usage analysis as command arguments — they
        were silently skipped before. ``dup_fd`` redirects (``2>&1``) carry a
        synthetic ``&N`` target with no expansion and are left alone. Heredoc
        and here-string bodies undergo expansion unless the delimiter/quote
        disabled it, so their ``$var`` references count as variable usage too.
        """
        # Target word: only meaningful for non-dup redirects (a dup like 2>&1
        # has dup_fd set and a synthetic "&1" target, not an expandable word).
        if node.dup_fd is None and node.target and '$' in node.target:
            self._check_variable_usage(node.target)

        # Heredoc / here-string body: expanded unless quoted.
        body = node.heredoc_content
        if body and '$' in body and not node.heredoc_quoted and node.quote_type != "'":
            self._check_variable_usage(body)

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

    def _check_word_variable_usage(self, word: Word) -> None:
        """Register/validate the variable references in a command-argument Word.

        References are read STRUCTURALLY from the Word's parts
        (:func:`iter_variable_references`): command/arithmetic substitutions are
        not variable references and are skipped, and ``${a[i]}`` yields the bare
        name ``a``. Nested operator-word references (``${x:-$y}``) are recovered
        via the documented string fallback inside ``iter_variable_references``.
        """
        for ref in iter_variable_references(word):
            self._register_variable_use(ref.name)

    def _check_variable_usage(self, text: str) -> None:
        """Check for variable usage in a raw STRING (redirect target / heredoc body).

        These come from string fields on the ``Redirect`` node, not from a Word,
        so the documented string fallback is used to recover references.
        """
        for ref in iter_variable_references_in_text(text):
            self._register_variable_use(ref.name)

    def _register_variable_use(self, var_name: str) -> None:
        """Record a variable use and warn if it is (likely) undefined.

        Only identifier-shaped names are considered: special parameters
        (``$?``, ``$@``, ``$#``, ...) and positional parameters (``$1``) are
        always defined and are never user-declared, so they are not tracked or
        warned on (matching the historical identifier-only scope).
        """
        if not (var_name[:1].isalpha() or var_name[:1] == '_'):
            return
        self.used_vars.add(var_name)
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

    def _check_test_command(self, words: List[Word]) -> None:
        """Check test/[ command usage (operands, after the command word)."""
        if not words:
            return
        rendered = [w.display_text() for w in words]

        # Check for missing quotes on variables — detected structurally from
        # the Word parts rather than by scanning for a leading '$'.
        if self.config.check_quote_usage:
            for i, word in enumerate(words):
                if has_unquoted_variable_expansion(word):
                    # Check if it's in a context where it should be quoted
                    if i > 0 and rendered[i-1] in TEST_OPERATORS:
                        self.add_issue(
                            LintLevel.WARNING,
                            f"Unquoted variable '{rendered[i]}' in test command",
                            suggestion=f'Use "{rendered[i]}" to prevent word splitting'
                        )

        # Suggest [[ over [
        if self.config.prefer_double_brackets and rendered and rendered[-1] == ']':
            self.add_issue(
                LintLevel.STYLE,
                "Consider using [[ ]] instead of [ ]",
                suggestion="[[ ]] is safer and more feature-rich"
            )

    def _check_file_command(self, cmd: str, words: List[Word]) -> None:
        """Check file manipulation commands (operands, after the command word)."""
        rendered = [w.display_text() for w in words]
        if cmd == 'rm' and '-f' not in rendered and '-i' not in rendered:
            self.add_issue(
                LintLevel.INFO,
                f"'{cmd}' without -i flag",
                suggestion="Consider using 'rm -i' for safety"
            )

        # Check for unquoted variables that might contain spaces — read from
        # the Word parts (catches embedded/braced forms a leading-'$' scan misses).
        if self.config.check_quote_usage:
            for word in words:
                if has_unquoted_variable_expansion(word):
                    arg = word.display_text()
                    self.add_issue(
                        LintLevel.WARNING,
                        f"Unquoted variable '{arg}' in {cmd} command",
                        suggestion=f'Use "{arg}" to handle filenames with spaces'
                    )

    def generic_visit(self, node: ASTNode) -> None:
        """Descend into child nodes for unhandled node types."""
        visit_children(self, node)
