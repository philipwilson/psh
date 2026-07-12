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
    CStyleForLoop,
    ExpansionPart,
    ForLoop,
    FunctionDef,
    SimpleCommand,
    VariableExpansion,
)
from ..core.assignment_utils import SHELL_NAME
from .constants import (
    COMMON_TYPOS,
    DANGEROUS_COMMANDS,
    NUMERIC_COMPARISON_OPERATORS,
    PREDEFINED_VARIABLES,
    SHELL_BUILTINS,
    is_assignment,
)
from .validator_visitor import ValidatorVisitor
from .word_analysis import (
    contains_metacharacters_in_unquoted_expansion,
    is_arithmetic_only,
    iter_variable_references,
    iter_variable_references_in_text,
    unquoted_test_operands,
)


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

        # Special/predefined variables that are always defined. Single-sourced in
        # constants.PREDEFINED_VARIABLES so this and the linter's undefined-var
        # suppression list stay in agreement (they had drifted — the linter knew
        # only 11 names).
        self.special_vars = PREDEFINED_VARIABLES

    def enter_scope(self):
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

        self._current_function: Optional[str] = None

    # Override parent visit methods to add enhanced checks

    def visit_SimpleCommand(self, node: SimpleCommand) -> None:
        """Enhanced simple command validation."""
        # Call parent validation first
        super().visit_SimpleCommand(node)

        # Array initializations / element assignments define variables and can
        # appear with NO command word (`x=(1 2 3)` parses to empty args plus an
        # array_assignments prefix), so record them BEFORE the empty-args guard.
        self._process_array_assignments(node)

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
        self.var_tracker.enter_scope()
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

        # Check items for undefined variables. Read the per-item Word AST
        # (``item_words``) structurally: a command substitution item like
        # ``$(ls)`` is NOT a variable reference and is correctly skipped (the
        # old string scan flagged ``$(ls)`` as undefined variable ``(ls)``).
        if self.config.check_undefined_vars:
            for item_word in node.item_words:
                seen: Set[str] = set()
                for ref in iter_variable_references(item_word):
                    if ref.has_default or ref.name in seen:
                        continue
                    seen.add(ref.name)
                    if not self.var_tracker.is_defined(ref.name):
                        self._add_warning(
                            f"Possible use of undefined variable '${ref.name}' in for loop items",
                            node
                        )

        # Call parent implementation
        super().visit_ForLoop(node)

    def visit_CStyleForLoop(self, node: CStyleForLoop) -> None:
        """Enhanced C-style for loop validation.

        Register the variable(s) assigned in the init expression
        (`for ((i=0; ...))` defines `i`) so the loop body's use of `$i`
        is not reported as undefined.
        """
        for var_name in self._cstyle_init_vars(node.init_expr):
            self.var_tracker.define_variable(
                var_name,
                VariableInfo(name=var_name, defined_at=self._get_context())
            )

        # Call parent implementation (traverses body + redirects)
        super().visit_CStyleForLoop(node)

    @staticmethod
    def _cstyle_init_vars(init_expr: Optional[str]) -> List[str]:
        """Variable names assigned in a C-style for init expression.

        `i=0` -> ['i']; `i=0, j=1` (comma operator) -> ['i', 'j']. Only the
        left-hand identifier of each `=` assignment is taken; comparison/other
        operators are ignored.
        """
        if not init_expr:
            return []
        names: List[str] = []
        for clause in init_expr.split(','):
            match = re.match(rf'\s*({SHELL_NAME})\s*=', clause)
            if match:
                names.append(match.group(1))
        return names

    # Helper methods for enhanced validation

    def _process_array_assignments(self, node: SimpleCommand):
        """Record array names from ``arr=(...)`` / ``arr[i]=...`` as defined.

        Both ``ArrayInitialization`` and ``ArrayElementAssignment`` carry a
        ``.name``; without this, ``"${arr[@]}"`` later in the script is
        flagged as an undefined variable (the assignment is an array node, not
        a ``VAR=value`` string).
        """
        for assignment in getattr(node, 'array_assignments', []):
            name = getattr(assignment, 'name', None)
            if name:
                self.var_tracker.define_variable(
                    name,
                    VariableInfo(
                        name=name,
                        defined_at=self._get_context(),
                        is_array=True,
                    )
                )

    def _process_variable_assignments(self, node: SimpleCommand):
        """Process variable assignments in a command."""
        for i, arg in enumerate(node.args):
            # Check for VAR=value pattern using the canonical assignment
            # predicate. The old inline check accepted hyphens, treating
            # `a-b=c` as a definition of the (illegal) variable `a-b`.
            if is_assignment(arg):
                parts = arg.split('=', 1)
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
        """Check for undefined variables in command arguments.

        Variable references are read STRUCTURALLY from each ``Word``'s parts
        (:func:`iter_variable_references`) rather than regexed out of the
        rendered argument string. This drops index/operator debris from the
        name (``${a[0]}`` → ``a``), honors ``:-``/``:=`` defaults via the
        parsed operator, and reports each reference exactly once.
        """
        words = node.words if node.words else []
        for i, (arg, word) in enumerate(zip(node.args, words, strict=False)):
            # Skip the command itself
            if i == 0:
                continue

            # A word that is a single bare variable expansion ($VAR / ${VAR})
            # warns unconditionally on an undefined name; a variable embedded
            # in a larger word goes through the context-aware suppression
            # (existence tests, etc.). This mirrors the historical two-branch
            # split, now driven by structured references rather than regex.
            single_var = word.is_variable_expansion
            seen: Set[str] = set()
            for ref in iter_variable_references(word):
                if ref.has_default:
                    continue
                if ref.name in seen:
                    continue
                seen.add(ref.name)
                if self.var_tracker.is_defined(ref.name):
                    continue
                if single_var or self._should_warn_undefined(ref.name, arg, node):
                    self._add_warning(
                        f"Possible use of undefined variable '${ref.name}'",
                        node
                    )

            # "Unquoted $@" advisory. Historically only multi-part words (the
            # old string-scan branch) were checked; preserve that scope but
            # detect the unquoted ``$@`` STRUCTURALLY (an unquoted @-expansion
            # part) so an embedded quoted ``"$@"`` is not a false positive.
            if not single_var and self._has_unquoted_at(word):
                self._add_info(
                    "Unquoted $@ should be \"$@\" to preserve arguments correctly",
                    node
                )

    @staticmethod
    def _has_unquoted_at(word) -> bool:
        """True if the word contains an unquoted ``$@`` expansion part."""
        return any(
            isinstance(p, ExpansionPart)
            and not p.quoted
            and isinstance(p.expansion, VariableExpansion)
            and p.expansion.name == '@'
            for p in word.parts
        )

    def _check_string_for_undefined_vars(self, text: str, node: ASTNode):
        """Check a raw STRING for undefined variable references.

        Used for contexts the Word part model does not cover: assignment
        values (``FOO=$BAR``) and for-loop item strings. Variable references
        are recovered with the documented string fallback
        (:func:`iter_variable_references_in_text`); ``${VAR:-default}`` is
        suppressed via the parsed ``has_default`` flag.
        """
        if not text:
            return

        for ref in iter_variable_references_in_text(text):
            if ref.has_default:
                continue
            if self.var_tracker.is_defined(ref.name):
                continue
            if self._should_warn_undefined(ref.name, text, node):
                self._add_warning(
                    f"Possible use of undefined variable '${ref.name}'",
                    node
                )

        # NOTE: the unquoted-`$@` advisory is NOT applied on this string-fallback
        # path. It used to fire on the correctly-quoted `FOO="$@"` (assignment
        # values arrive post-quote-removal, so the even-quote-count test was
        # always true). The advisory has one structural implementation,
        # `_check_undefined_variables_in_command` via `_has_unquoted_at`, which
        # reads the Word parts and cannot be fooled by quote removal.

    def _check_quoting_issues(self, node: SimpleCommand):
        """Check for potential quoting issues."""
        words = node.words if node.words else []
        for i, (arg, word) in enumerate(zip(node.args, words, strict=False)):
            # Skip command name
            if i == 0:
                continue

            # Check unquoted expansions (word-split risk). Read the part model
            # directly: any unquoted $-expansion EXCEPT a bare arithmetic
            # expansion (whose result bash does not word-split).
            if word.has_unquoted_expansion and not is_arithmetic_only(word):
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

        # Check for potential command injection: an unquoted $-expansion sharing
        # a word with literal shell metacharacters. Detected structurally on the
        # word's parts (an unquoted expansion part + an unquoted literal metachar
        # part); normal parsing splits metacharacters into separate words, so
        # this fires only for quoted-then-stripped or manually-built words.
        if self.config.check_command_injection:
            words = node.words if node.words else []
            for i, arg in enumerate(node.args[1:], 1):
                word = words[i] if i < len(words) else None
                if word and contains_metacharacters_in_unquoted_expansion(word):
                    self._add_error(
                        f"Potential command injection: unquoted expansion '{arg}' contains shell metacharacters",
                        node
                    )

        # Check file permissions. Use the shared bit-check (constants.py) so
        # ALL world-writable octal modes are caught (757, 776, 737, ... — the
        # old substring scan only matched 777/666/a+w/o+w), single-sourced
        # with SecurityVisitor.
        if self.config.check_file_permissions and cmd == 'chmod':
            from .constants import is_world_writable_permission
            for arg in node.args[1:]:
                if is_world_writable_permission(arg):
                    self._add_warning(
                        "Security: Creating world-writable files is a security risk",
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

        # 'printf -v VAR ...' assigns VAR (like declare); the name follows -v.
        elif cmd == 'printf':
            for i in range(1, len(node.args) - 1):
                if node.args[i] == '-v':
                    name = node.args[i + 1].split('[', 1)[0]
                    self.var_tracker.define_variable(
                        name, VariableInfo(name=name, defined_at=self._get_context()))
                    break

        # 'mapfile'/'readarray' fill an array (bash default MAPFILE); the target
        # is the last non-option operand.
        elif cmd in ('mapfile', 'readarray'):
            target = 'MAPFILE'
            for arg in node.args[1:]:
                if not arg.startswith('-'):
                    target = arg.split('[', 1)[0]
            self.var_tracker.define_variable(
                target,
                VariableInfo(name=target, defined_at=self._get_context(), is_array=True))

        # 'getopts OPTSTRING NAME' sets NAME plus OPTARG/OPTIND each iteration.
        elif cmd == 'getopts' and len(node.args) > 2:
            for name in (node.args[2], 'OPTARG', 'OPTIND'):
                self.var_tracker.define_variable(
                    name, VariableInfo(name=name, defined_at=self._get_context()))

    # Utility methods

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
        """Check for common quoting issues in test/[ commands.

        Uses the shared `unquoted_test_operands` routine (word_analysis) so this
        and the linter's `_check_test_command` walk the same operator set and
        side-coverage instead of two drifting heuristics.
        """
        words = node.words[1:] if node.words else []
        rendered = [w.display_text() for w in words]
        for i in unquoted_test_operands(words):
            self._add_warning(
                f"Unquoted variable '{rendered[i]}' in test - may fail if value contains spaces",
                node
            )

