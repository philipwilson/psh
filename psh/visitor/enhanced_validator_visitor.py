"""
Enhanced AST validator with comprehensive validation including undefined variables,
command validation, quoting analysis, and security checks.

This visitor extends the base ValidatorVisitor with more sophisticated analysis
capabilities while maintaining backward compatibility.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from ..ast_nodes import (
    # Core nodes
    ASTNode,
    ForLoop,
    FunctionDef,
    SimpleCommand,
    TopLevel,
)
from .analysis_helpers import has_unquoted_expansion
from .constants import (
    COMMON_TYPOS,
    DANGEROUS_COMMANDS,
    NUMERIC_COMPARISON_OPERATORS,
    SHELL_BUILTINS,
)
from .validator_visitor import ValidatorVisitor


@dataclass
class VariableInfo:
    """Information about a variable definition."""
    name: str
    defined_at: Optional[str] = None  # Context where defined
    is_exported: bool = False
    is_readonly: bool = False
    is_array: bool = False
    is_local: bool = False
    is_special: bool = False  # $?, $$, etc.
    is_positional: bool = False  # $1, $2, etc.


class VariableTracker:
    """Track variable definitions and usage across scopes."""

    def __init__(self):
        # Stack of scopes (global scope is always at index 0)
        self.scopes: List[Dict[str, VariableInfo]] = [{}]

        # Special variables that are always defined
        self.special_vars = {
            '?', '$', '!', '#', '@', '*', '-', '_', '0',
            'HOME', 'PATH', 'PWD', 'OLDPWD', 'SHELL', 'USER',
            'HOSTNAME', 'HOSTTYPE', 'OSTYPE', 'MACHTYPE',
            'RANDOM', 'LINENO', 'SECONDS', 'HISTCMD',
            'BASH_VERSION', 'BASH', 'IFS', 'PS1', 'PS2', 'PS3', 'PS4',
            'PPID', 'UID', 'EUID', 'GROUPS', 'SHELLOPTS',
            'PIPESTATUS', 'FUNCNAME', 'BASH_SOURCE', 'BASH_LINENO',
            'REPLY', 'HISTFILE', 'HISTSIZE', 'HISTFILESIZE',
            'LANG', 'LC_ALL', 'LC_COLLATE', 'LC_CTYPE', 'LC_MESSAGES',
            'TERM', 'COLUMNS', 'LINES'
        }

    def enter_scope(self, context: str = "function"):
        """Enter a new variable scope (e.g., function)."""
        self.scopes.append({})

    def exit_scope(self):
        """Exit current scope."""
        if len(self.scopes) > 1:
            self.scopes.pop()

    def define_variable(self, name: str, info: VariableInfo):
        """Define a variable in current scope."""
        self.scopes[-1][name] = info

    def lookup_variable(self, name: str) -> Optional[VariableInfo]:
        """Look up variable in all scopes from current to global."""
        # Check from current scope up to global
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]

        # Check if it's a special variable
        if name in self.special_vars:
            return VariableInfo(name=name, is_special=True)

        # Check if it's a positional parameter
        if name.isdigit():
            return VariableInfo(name=name, is_positional=True)

        return None

    def is_defined(self, name: str) -> bool:
        """Check if a variable is defined in any scope."""
        return self.lookup_variable(name) is not None

    def get_current_scope_vars(self) -> Set[str]:
        """Get all variables defined in current scope."""
        return set(self.scopes[-1].keys())

    def mark_exported(self, name: str):
        """Mark a variable as exported."""
        var_info = self.lookup_variable(name)
        if var_info and not var_info.is_special:
            var_info.is_exported = True

    def mark_readonly(self, name: str):
        """Mark a variable as readonly."""
        var_info = self.lookup_variable(name)
        if var_info and not var_info.is_special:
            var_info.is_readonly = True

    def mark_local(self, name: str):
        """Mark a variable as local to current scope."""
        if name in self.scopes[-1]:
            self.scopes[-1][name].is_local = True


@dataclass
class ValidatorConfig:
    """Configuration for the enhanced validator."""
    # Feature toggles
    check_undefined_vars: bool = True
    check_command_exists: bool = True
    check_quoting: bool = True
    check_security: bool = True

    # Undefined variable checking
    warn_undefined_in_conditionals: bool = True
    ignore_undefined_with_defaults: bool = True

    # Command checking
    check_typos: bool = True
    suggest_alternatives: bool = True

    # Quoting checks
    warn_unquoted_variables: bool = True
    warn_glob_expansion: bool = True
    strict_quoting: bool = False

    # Security checks
    warn_dangerous_commands: bool = True
    check_command_injection: bool = True
    check_file_permissions: bool = True
    check_eval_usage: bool = True


class EnhancedValidatorVisitor(ValidatorVisitor):
    """
    Enhanced validator with comprehensive validation checks.

    This visitor extends the base validator with:
    - Undefined variable detection
    - Command existence and typo checking
    - Quoting analysis
    - Security vulnerability detection
    """

    def __init__(self, config: Optional[ValidatorConfig] = None):
        """Initialize the enhanced validator with optional configuration."""
        super().__init__()
        self.config = config or ValidatorConfig()
        self.var_tracker = VariableTracker()

        # Builtin commands for existence checking
        self.builtin_commands = SHELL_BUILTINS

        # Common command typos
        self.common_typos = COMMON_TYPOS

        # Dangerous commands for security checks
        self.dangerous_commands = DANGEROUS_COMMANDS

        self._current_function = None

    # Override parent visit methods to add enhanced checks

    def visit_TopLevel(self, node: TopLevel) -> None:
        """Visit top-level with enhanced validation."""
        # Initialize any global variables from environment
        # In a real implementation, we might parse .bashrc or similar
        super().visit_TopLevel(node)

    def visit_SimpleCommand(self, node: SimpleCommand) -> None:
        """Enhanced simple command validation."""
        # Call parent validation first
        super().visit_SimpleCommand(node)

        if not node.args:
            return

        cmd = node.args[0]

        # Check for variable assignments
        self._process_variable_assignments(node)

        # Check command existence and typos
        if self.config.check_command_exists:
            self._check_command_exists(cmd, node)

        # Check for undefined variables in arguments
        if self.config.check_undefined_vars:
            self._check_undefined_variables_in_command(node)

        # Check quoting issues
        if self.config.check_quoting:
            self._check_quoting_issues(node)

        # Security checks
        if self.config.check_security:
            self._check_security_issues(node)

        # Special handling for certain commands
        self._handle_special_commands(node)

        # Check for common test command issues
        if cmd in ['[', 'test'] and len(node.args) > 2:
            self._check_test_command_quoting(node)

    def visit_FunctionDef(self, node: FunctionDef) -> None:
        """Enhanced function definition handling."""
        # Enter new scope for local variables
        self.var_tracker.enter_scope(f"function {node.name}")
        self._current_function = node.name

        # Define positional parameters in function scope
        # $0 is the function name, $1, $2, etc. are arguments
        self.var_tracker.define_variable(
            '0',
            VariableInfo(name='0', defined_at=f"function {node.name}", is_positional=True)
        )

        # Call parent implementation
        super().visit_FunctionDef(node)

        # Exit scope
        self.var_tracker.exit_scope()
        self._current_function = None

    def visit_ForLoop(self, node: ForLoop) -> None:
        """Enhanced for loop validation."""
        # Define the loop variable
        self.var_tracker.define_variable(
            node.variable,
            VariableInfo(name=node.variable, defined_at=self._get_context())
        )

        # Check items for undefined variables
        if self.config.check_undefined_vars:
            for item in node.items:
                if item.startswith('$'):
                    var_name = self._extract_variable_name(item)
                    if var_name and not self.var_tracker.is_defined(var_name):
                        self._add_warning(
                            f"Possible use of undefined variable '${var_name}' in for loop items",
                            node
                        )

        # Call parent implementation
        super().visit_ForLoop(node)

    # Helper methods for enhanced validation

    def _process_variable_assignments(self, node: SimpleCommand):
        """Process variable assignments in a command."""
        for i, arg in enumerate(node.args):
            # Check for VAR=value pattern
            if '=' in arg and not arg.startswith('='):
                parts = arg.split('=', 1)
                if parts[0] and parts[0].replace('_', '').replace('-', '').isalnum():
                    var_name = parts[0]
                    value = parts[1] if len(parts) > 1 else ''

                    # This is a variable assignment
                    context = self._get_context()
                    is_local = self._current_function is not None and i > 0 and node.args[0] == 'local'

                    self.var_tracker.define_variable(
                        var_name,
                        VariableInfo(
                            name=var_name,
                            defined_at=context,
                            is_local=is_local
                        )
                    )

                    # Check the value for undefined variables
                    if self.config.check_undefined_vars:
                        self._check_string_for_undefined_vars(value, node)

        # Handle special builtins that affect variables
        if node.args:
            cmd = node.args[0]

            if cmd == 'export' and len(node.args) > 1:
                for arg in node.args[1:]:
                    if '=' in arg:
                        var_name = arg.split('=', 1)[0]
                    else:
                        var_name = arg
                    self.var_tracker.mark_exported(var_name)

            elif cmd == 'readonly' and len(node.args) > 1:
                for arg in node.args[1:]:
                    if '=' in arg:
                        var_name = arg.split('=', 1)[0]
                    else:
                        var_name = arg
                    self.var_tracker.mark_readonly(var_name)

            elif cmd == 'unset' and len(node.args) > 1:
                # We don't actually remove from tracker, but could mark as unset
                pass

    def _check_command_exists(self, cmd: str, node: SimpleCommand):
        """Check if a command exists or is a typo."""
        # Skip if it's a builtin
        if cmd in self.builtin_commands:
            return

        # Skip if it's a function we've seen
        if cmd in self.function_names:
            return

        # Check for common typos
        if self.config.check_typos and cmd in self.common_typos:
            suggestion = self.common_typos[cmd]
            self._add_warning(
                f"Possible typo: '{cmd}' - did you mean '{suggestion}'?",
                node
            )

        # Check for deprecated commands
        deprecated_commands = {
            'which': "Consider using 'command -v' or 'type' instead of 'which'",
            'ifconfig': "Consider using 'ip' instead of deprecated 'ifconfig'",
            'netstat': "Consider using 'ss' instead of deprecated 'netstat'",
            'service': "Consider using 'systemctl' instead of 'service' on systemd systems",
        }

        if cmd in deprecated_commands:
            self._add_info(deprecated_commands[cmd], node)

    def _check_undefined_variables_in_command(self, node: SimpleCommand):
        """Check for undefined variables in command arguments."""
        words = node.words if node.words else []
        for i, (arg, word) in enumerate(zip(node.args, words)):
            # Skip the command itself
            if i == 0:
                continue

            # Check based on Word structure
            if word.is_variable_expansion:
                # Direct variable reference like $VAR
                var_name = self._extract_variable_name(arg)
                if var_name and not self.var_tracker.is_defined(var_name):
                    if not self._has_parameter_default(arg):
                        self._add_warning(
                            f"Possible use of undefined variable '${var_name}'",
                            node
                        )
            else:
                self._check_string_for_undefined_vars(arg, node)

    def _check_string_for_undefined_vars(self, text: str, node: ASTNode):
        """Check a string for undefined variable references."""
        if not text:
            return

        # Pattern to match variable references
        # Matches $VAR, ${VAR}, ${VAR[index]}, etc.
        var_patterns = [
            (r'\$([A-Za-z_][A-Za-z0-9_]*)', 1),  # $VAR
            (r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', 1),  # ${VAR}
            (r'\$\{([A-Za-z_][A-Za-z0-9_]*)\[', 1),  # ${VAR[...]}
        ]

        for pattern, group in var_patterns:
            for match in re.finditer(pattern, text):
                var_name = match.group(group)

                # Check if variable is defined
                if not self.var_tracker.is_defined(var_name):
                    # Check if it has a default value (${VAR:-default} or ${VAR:=default})
                    start_pos = match.start()
                    if not self._has_default_at_position(text, start_pos):
                        # Additional context-specific checks
                        if self._should_warn_undefined(var_name, text, node):
                            self._add_warning(
                                f"Possible use of undefined variable '${var_name}'",
                                node
                            )

        # Also check for unquoted $@ in non-array context
        if '$@' in text and text.count('"') % 2 == 0:  # Even quotes means not inside quotes
            # Check if we're not in a for loop items list
            if not (isinstance(node, ForLoop) and '$@' in str(node.items)):
                self._add_info(
                    "Unquoted $@ should be \"$@\" to preserve arguments correctly",
                    node
                )

    def _check_quoting_issues(self, node: SimpleCommand):
        """Check for potential quoting issues."""
        words = node.words if node.words else []
        for i, (arg, word) in enumerate(zip(node.args, words)):
            # Skip command name
            if i == 0:
                continue

            # Check unquoted variables
            if has_unquoted_expansion(word, arg):
                # Skip numeric comparisons
                if i > 0 and node.args[i-1] in NUMERIC_COMPARISON_OPERATORS:
                    continue

                # Skip if it looks like an assignment
                if '=' in arg and i < len(node.args) - 1:
                    continue

                self._add_info(
                    f"Unquoted variable expansion '{arg}' may cause word splitting",
                    node
                )

            # Check for unquoted globs
            if word.is_unquoted_literal and any(c in arg for c in ['*', '?', '[']):
                if not self._looks_like_intentional_glob(arg, node):
                    self._add_warning(
                        f"Unquoted pattern '{arg}' will undergo pathname expansion",
                        node
                    )

    def _check_security_issues(self, node: SimpleCommand):
        """Check for potential security vulnerabilities."""
        if not node.args:
            return

        cmd = node.args[0]

        # Check dangerous commands
        if self.config.warn_dangerous_commands and cmd in self.dangerous_commands:
            self._add_warning(
                f"Security: {self.dangerous_commands[cmd]}",
                node
            )

        # Check for potential command injection
        if self.config.check_command_injection:
            words = node.words if node.words else []
            for i, arg in enumerate(node.args[1:], 1):
                # Look for unquoted variable expansions with dangerous characters
                if '$' in arg and any(char in arg for char in [';', '&&', '||', '|', '`']):
                    word = words[i] if i < len(words) else None
                    if word and not word.is_quoted:  # Unquoted
                        self._add_error(
                            f"Potential command injection: unquoted expansion '{arg}' contains shell metacharacters",
                            node
                        )

        # Check file permissions
        if self.config.check_file_permissions and cmd == 'chmod':
            for arg in node.args[1:]:
                if any(perm in arg for perm in ['777', 'a+w', 'o+w']):
                    self._add_warning(
                        "Security: Creating world-writable files is a security risk",
                        node
                    )
                elif '666' in arg:
                    self._add_warning(
                        "Security: Mode 666 makes files writable by everyone",
                        node
                    )

    def _handle_special_commands(self, node: SimpleCommand):
        """Special handling for commands that affect variable state."""
        if not node.args:
            return

        cmd = node.args[0]

        # Handle 'read' command - defines variables
        if cmd == 'read' and len(node.args) > 1:
            for arg in node.args[1:]:
                if not arg.startswith('-'):
                    self.var_tracker.define_variable(
                        arg,
                        VariableInfo(name=arg, defined_at=self._get_context())
                    )

        # Handle 'declare' and 'typeset'
        elif cmd in ['declare', 'typeset']:
            is_array = False
            for arg in node.args[1:]:
                if arg == '-a' or arg == '-A':
                    is_array = True
                elif '=' in arg and not arg.startswith('-'):
                    var_name = arg.split('=', 1)[0]
                    self.var_tracker.define_variable(
                        var_name,
                        VariableInfo(name=var_name, defined_at=self._get_context(), is_array=is_array)
                    )
                elif not arg.startswith('-'):
                    # Variable name without assignment
                    self.var_tracker.define_variable(
                        arg,
                        VariableInfo(name=arg, defined_at=self._get_context(), is_array=is_array)
                    )

    # Utility methods

    def _extract_variable_name(self, text: str) -> Optional[str]:
        """Extract variable name from various formats."""
        if text.startswith('$'):
            text = text[1:]

        # Handle ${VAR} format
        if text.startswith('{') and '}' in text:
            text = text[1:text.index('}')]

        # Extract just the variable name (before any operators)
        for op in [':-', ':=', ':+', ':?', '#', '##', '%', '%%', '/', '//', '^', '^^', ',', ',,', '[']:
            if op in text:
                text = text[:text.index(op)]
                break

        return text if text else None

    def _has_parameter_default(self, text: str) -> bool:
        """Check if a parameter expansion has a default value.

        Only matches :- or := inside ${...} delimiters so that these
        operator strings appearing in plain text don't cause false positives.
        """
        i = 0
        while i < len(text):
            start = text.find('${', i)
            if start == -1:
                break
            # Find matching closing brace, respecting nesting
            depth = 1
            j = start + 2
            while j < len(text) and depth > 0:
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                j += 1
            if depth == 0:
                content = text[start + 2:j - 1]
                if ':-' in content or ':=' in content:
                    return True
            i = j
        return False

    def _has_default_at_position(self, text: str, pos: int) -> bool:
        """Check if variable at position has a default value."""
        # Look for ${VAR:-default} or ${VAR:=default} pattern
        if pos > 0 and text[pos-1:pos+1] == '${':
            # Find the closing }
            close_pos = text.find('}', pos)
            if close_pos > 0:
                var_content = text[pos+1:close_pos]
                return ':-' in var_content or ':=' in var_content
        return False

    def _should_warn_undefined(self, var_name: str, context: str, node: ASTNode) -> bool:
        """Determine if we should warn about an undefined variable."""
        # Don't warn if it has a default and we're configured to ignore
        if self.config.ignore_undefined_with_defaults and self._has_parameter_default(context):
            return False

        # Don't warn for certain patterns (e.g., in conditionals checking existence)
        if self.config.warn_undefined_in_conditionals:
            # Check if we're in a test for variable existence
            if isinstance(node, SimpleCommand) and node.args and node.args[0] in ['test', '[']:
                # Look for patterns like: [ -z "$VAR" ] or [ -n "$VAR" ]
                for i, arg in enumerate(node.args):
                    if arg in ['-z', '-n'] and i + 1 < len(node.args):
                        next_arg = node.args[i + 1]
                        if var_name in next_arg:
                            return False

        return True

    def _looks_like_intentional_glob(self, pattern: str, node: SimpleCommand) -> bool:
        """Determine if a glob pattern appears intentional."""
        # Common intentional glob patterns
        intentional_patterns = [
            r'^\*\.\w+$',     # *.txt, *.py, etc.
            r'^\w+\*$',       # prefix*
            r'^\*\w+$',       # *suffix
            r'^\[[\w-]+\]',   # [a-z], [0-9], etc.
            r'^[\w/]+/\*$',   # dir/*
        ]

        for pat in intentional_patterns:
            if re.match(pat, pattern):
                return True

        # Commands that commonly use globs
        if node.args and node.args[0] in ['ls', 'rm', 'cp', 'mv', 'find', 'chmod', 'chown']:
            return True

        # In for loops, globs are often intentional
        # This would need more context from parent nodes

        return False

    def _check_test_command_quoting(self, node: SimpleCommand):
        """Check for common quoting issues in test commands."""
        args = node.args[1:]  # Skip the command itself
        words = node.words[1:] if node.words else []

        # Look for file test operators followed by unquoted variables
        file_ops = ['-f', '-d', '-e', '-r', '-w', '-x', '-s', '-L', '-h']
        string_ops = ['=', '==', '!=', '<', '>']

        for i, (arg, word) in enumerate(zip(args, words)):
            # Check if this is a file test operator
            if arg in file_ops and i + 1 < len(args):
                next_arg = args[i + 1]
                next_word = words[i + 1] if i + 1 < len(words) else None

                # If next arg is unquoted and contains variable
                if next_word and not next_word.is_quoted and '$' in next_arg:
                    self._add_warning(
                        f"Unquoted variable '{next_arg}' in test - may fail if value contains spaces",
                        node
                    )

            # Check string comparisons
            elif arg in string_ops:
                # Check both sides of operator
                if i > 0:
                    prev_arg = args[i - 1]
                    prev_word = words[i - 1] if i - 1 < len(words) else None
                    if prev_word and not prev_word.is_quoted and '$' in prev_arg:
                        self._add_warning(
                            f"Unquoted variable '{prev_arg}' in test comparison - use quotes",
                            node
                        )

                if i + 1 < len(args):
                    next_arg = args[i + 1]
                    next_word = words[i + 1] if i + 1 < len(words) else None
                    if next_word and not next_word.is_quoted and '$' in next_arg:
                        self._add_warning(
                            f"Unquoted variable '{next_arg}' in test comparison - use quotes",
                            node
                        )

    def get_detailed_summary(self) -> str:
        """Get a detailed summary including variable usage information."""
        lines = [super().get_summary()]

        # Add information about defined but unused variables
        # (This would require tracking variable usage, not just definition)

        return '\n'.join(lines)
