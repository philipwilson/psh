"""
Command execution module for the PSH executor.

This module handles the execution of simple commands, including:
- Variable assignments
- Command expansion
- Builtin, function, and external command execution
- Redirection handling
"""

import sys
from typing import TYPE_CHECKING, List, Tuple

from ..core import (
    ReadonlyVariableError,
    extract_assignments,
    is_exported,
    is_valid_assignment,
)
from .strategies import (
    AliasExecutionStrategy,
    BuiltinExecutionStrategy,
    ExecutionStrategy,
    ExternalExecutionStrategy,
    FunctionExecutionStrategy,
    SpecialBuiltinExecutionStrategy,
)

if TYPE_CHECKING:
    from ..ast_nodes import SimpleCommand
    from ..shell import Shell
    from .context import ExecutionContext


class CommandExecutor:
    """
    Handles execution of simple commands.

    This class encapsulates all logic for executing SimpleCommand nodes,
    including variable assignments, expansions, and delegating to appropriate
    execution strategies.
    """

    def __init__(self, shell: 'Shell'):
        """Initialize the command executor with a shell instance."""
        self.shell = shell
        self.state = shell.state
        self.expansion_manager = shell.expansion_manager
        self.io_manager = shell.io_manager
        self.job_manager = shell.job_manager
        self.builtin_registry = shell.builtin_registry
        self.function_manager = shell.function_manager

        # Initialize execution strategies
        # Order matters: special builtins > functions > builtins > aliases > external (POSIX compliance)
        self.strategies = [
            SpecialBuiltinExecutionStrategy(),
            FunctionExecutionStrategy(),
            BuiltinExecutionStrategy(),
            AliasExecutionStrategy(),
            ExternalExecutionStrategy()
        ]

    def execute(self, node: 'SimpleCommand', context: 'ExecutionContext') -> int:
        """
        Execute a simple command and return exit status.

        Args:
            node: The SimpleCommand AST node to execute
            context: The current execution context

        Returns:
            Exit status code
        """
        try:
            # bash runs the DEBUG trap before each simple command
            self.shell.trap_manager.execute_debug_trap()

            # Handle array assignments first
            if node.array_assignments:
                for assignment in node.array_assignments:
                    self._handle_array_assignment(assignment)

            # Phase 1: Extract raw assignments (before expansion)
            raw_assignments = self._extract_assignments_raw(node)

            # Expand only the assignment values. Track command substitutions
            # run during expansion: a pure assignment's exit status is 0
            # unless a command substitution ran, in which case it is that
            # substitution's status (bash).
            self.state.last_cmdsub_status = None
            assignments = []
            for var, value, value_word in raw_assignments:
                expanded_value = self._expand_assignment_value_from_word(value, value_word)
                assignments.append((var, expanded_value))

            # Check if we have only assignments (no command)
            tokens_consumed = len(raw_assignments)

            if assignments and tokens_consumed == len(node.args):
                # Pure assignment (no command)
                return self._handle_pure_assignments(node, assignments)

            # Apply assignments for this command
            saved_vars = self._apply_command_assignments(assignments)
            is_special = False

            try:
                # Phase 2: Expand remaining arguments with assignments in effect
                # command_start_index needs to account for tokens consumed by assignments
                command_start_index = tokens_consumed
                if command_start_index >= len(node.args):
                    # No command to execute, but apply any redirections
                    # (e.g., ">file" should create/truncate the file)
                    if node.redirects:
                        with self.io_manager.with_redirections(node.redirects):
                            pass
                    return 0

                # Create a sub-node for command arguments only
                from ..ast_nodes import SimpleCommand
                words_slice = None
                if node.words is not None:
                    words_slice = node.words[command_start_index:]
                command_node = SimpleCommand(
                    args=node.args[command_start_index:],
                    redirects=node.redirects,
                    background=node.background,
                    words=words_slice,
                )


                # Check for bypass mechanisms before expansion
                bypass_aliases = False
                bypass_functions = False
                if command_node.args and command_node.args[0].startswith('\\'):
                    bypass_aliases = True
                    bypass_functions = True
                    # Remove backslash from the first argument for expansion
                    modified_args = [command_node.args[0][1:]] + command_node.args[1:]
                    # Also strip backslash from the first Word's LiteralPart
                    modified_words = command_node.words
                    if command_node.words and command_node.words[0].parts:
                        from ..ast_nodes import LiteralPart, Word
                        first_part = command_node.words[0].parts[0]
                        if isinstance(first_part, LiteralPart) and first_part.text.startswith('\\'):
                            new_part = LiteralPart(
                                first_part.text[1:], first_part.quoted, first_part.quote_char
                            )
                            new_word = Word(
                                parts=[new_part] + list(command_node.words[0].parts[1:]),
                                quote_type=command_node.words[0].quote_type,
                            )
                            modified_words = [new_word] + list(command_node.words[1:])
                    command_node = SimpleCommand(
                        args=modified_args,
                        redirects=command_node.redirects,
                        background=command_node.background,
                        words=modified_words,
                    )

                # Now expand command arguments with assignments in place
                expanded_args = self._expand_arguments(command_node)

                if not expanded_args:
                    return 0

                cmd_name = expanded_args[0]
                cmd_args = expanded_args[1:]

                # Check for empty command after expansion
                if not cmd_name:
                    return 0


                # Handle xtrace option
                if self.state.options.get('xtrace'):
                    self._print_xtrace(cmd_name, cmd_args)

                # Special handling for exec builtin (needs access to redirections)
                if cmd_name == 'exec':
                    return self._handle_exec_builtin(node, expanded_args, assignments)

                # Execute the command using appropriate strategy
                exit_code, is_special = self._execute_with_strategy(
                    cmd_name, cmd_args, node, context, bypass_aliases, bypass_functions
                )
                return exit_code

            finally:
                # POSIX: assignments before special builtins persist
                if not is_special:
                    self._restore_command_assignments(saved_vars)

        except Exception as e:
            # Import these here to avoid circular imports
            from ..builtins import FunctionReturn
            from ..core import (ExpansionError, LoopBreak, LoopContinue,
                                UnboundVariableError)

            # Re-raise control flow exceptions
            if isinstance(e, (FunctionReturn, LoopBreak, LoopContinue, SystemExit)):
                raise

            # Handle other exceptions
            if isinstance(e, ReadonlyVariableError):
                # Command-prefixed assignments (RO=v cmd): the command fails
                # with status 1 but, unlike a pure assignment, does not abort
                # the script (bash).
                print(f"psh: {e.name}: readonly variable", file=self.state.stderr)
                return 1

            if isinstance(e, UnboundVariableError):
                # set -u violation: print once and, like bash, abort a
                # non-interactive shell with status 127.
                print(f"psh: {e}", file=self.state.stderr)
                if self.shell.is_script_mode:
                    sys.exit(127)
                return 127

            if isinstance(e, ExpansionError):
                # Error message already printed by the expansion code
                expansion_exit_code = getattr(e, 'exit_code', 1)
                # In script mode, we should exit the shell
                if self.shell.is_script_mode:
                    sys.exit(expansion_exit_code)
                return expansion_exit_code

            # Last-resort guard: anything else is likely an internal defect.
            # Keep the shell alive but surface the traceback under --debug-exec
            # so the bug isn't hidden behind the generic message.
            if self.state.options.get('debug-exec'):
                import traceback
                traceback.print_exc(file=sys.stderr)
            print(f"psh: {e}", file=sys.stderr)
            return 1

    def _expand_arguments(self, node: 'SimpleCommand') -> List[str]:
        """Expand all arguments in a command."""
        return self.expansion_manager.expand_arguments(node)

    def _extract_assignments_raw(self, node: 'SimpleCommand') -> list:
        """Extract assignments from raw arguments before expansion.

        Returns list of (var_name, raw_value, word_or_none) tuples.
        The Word object is included when available so expansion can use
        structural quote information.
        """
        assignments = []
        i = 0

        while i < len(node.args):
            arg = node.args[i]

            # Use Word AST to determine if this argument is an assignment
            # candidate (i.e., a regular word, not a process substitution
            # or other special token).
            if self._is_assignment_candidate(node, i):
                if '=' in arg and self._is_valid_assignment(arg):
                    var, value = arg.split('=', 1)
                    word = node.words[i] if node.words and i < len(node.words) else None
                    assignments.append((var, value, word))
                    i += 1
                else:
                    # Stop at first non-assignment
                    break
            else:
                # Stop if we hit a non-word type (process sub, etc.)
                break

        return assignments

    @staticmethod
    def _is_assignment_candidate(node: 'SimpleCommand', index: int) -> bool:
        """Check if the argument at index is an assignment candidate.

        An argument is an assignment candidate if its Word AST contains
        only LiteralPart and ExpansionPart nodes (no process substitution
        or other special tokens), AND the variable-name portion (before
        the ``=``) consists entirely of unquoted LiteralPart text.
        Quoting any part of the variable name (e.g. ``"FOO"=bar``)
        disqualifies the word as an assignment per POSIX.
        """
        from ..ast_nodes import ExpansionPart, LiteralPart
        if node.words and index < len(node.words):
            word = node.words[index]
            # First pass: reject non-word tokens (process substitutions, etc.)
            for part in word.parts:
                if not isinstance(part, (LiteralPart, ExpansionPart)):
                    return False
                # Process substitution is stored as unquoted LiteralPart
                # starting with <( or >(
                if (isinstance(part, LiteralPart) and not part.quoted and
                        (part.text.startswith('<(') or part.text.startswith('>('))):
                    return False

            # Second pass: verify the variable-name portion is unquoted.
            # Walk parts accumulating text until we find '='.  Every part
            # (or portion of a part) before the '=' must be an unquoted
            # LiteralPart — any quoted part or ExpansionPart before '='
            # means this is not an assignment word.
            for part in word.parts:
                if isinstance(part, LiteralPart):
                    if '=' in part.text:
                        # Found the '='.  If this part is quoted, the
                        # variable name includes quoted text.
                        if part.quoted:
                            return False
                        # '=' is in an unquoted literal — valid so far
                        return True
                    # Part before '=' — must be unquoted literal
                    if part.quoted:
                        return False
                elif isinstance(part, ExpansionPart):
                    # Expansion before '=' means the name isn't a plain
                    # identifier (e.g. $FOO=bar is not an assignment)
                    return False

            # No '=' found in the Word parts at all
            return True
        # No Word AST available — assume it's a candidate
        return True

    def _extract_assignments(self, args: List[str]) -> List[Tuple[str, str]]:
        """Extract variable assignments from beginning of arguments."""
        return extract_assignments(args)

    def _is_valid_assignment(self, arg: str) -> bool:
        """Check if argument is a valid variable assignment."""
        return is_valid_assignment(arg)

    def _resolve_append(self, var: str, value: str):
        """Resolve NAME+= append assignments to (name, final_value).

        Plain variables append textually; integer (-i) variables append
        arithmetically — achieved by handing the INTEGER transform the
        expression "old+value" to evaluate, matching bash.
        """
        from ..core import VarAttributes
        if not var.endswith('+'):
            return var, value
        name = var[:-1]
        var_obj = self.state.scope_manager.get_variable_object(name)
        old = '' if var_obj is None or var_obj.value is None else str(var_obj.value)
        if (var_obj is not None and var_obj.attributes & VarAttributes.INTEGER
                and value.strip()):
            return name, f"({old or 0})+({value})"
        return name, old + value

    def _handle_pure_assignments(self, node: 'SimpleCommand',
                                assignments: List[Tuple[str, str]]) -> int:
        """Handle pure variable assignments (no command)."""
        # Apply redirections first
        with self.io_manager.with_redirections(node.redirects):
            # Handle xtrace for assignments
            if self.state.options.get('xtrace'):
                ps4 = self.state.get_variable('PS4', '+ ')
                for var, value in assignments:
                    trace_line = ps4 + f"{var}={value}\n"
                    self.state.stderr.write(trace_line)
                    self.state.stderr.flush()

            for var, value in assignments:
                # Values are already expanded in execute()
                var, value = self._resolve_append(var, value)
                try:
                    self.state.set_variable(var, value)
                except ReadonlyVariableError:
                    # bash: assignment to a readonly variable aborts a
                    # non-interactive shell with status 1.
                    print(f"psh: {var}: readonly variable", file=self.state.stderr)
                    if self.shell.is_script_mode:
                        sys.exit(1)
                    return 1

            # bash: a pure assignment's status is 0, unless a command
            # substitution ran while expanding the value — then it is the
            # substitution's status (cleared/recorded around expansion).
            if self.state.last_cmdsub_status is not None:
                return self.state.last_cmdsub_status
            return 0

    def _apply_command_assignments(self, assignments: List[Tuple[str, str]]) -> dict:
        """Apply variable assignments for command execution.

        For command-prefixed assignments (FOO=bar cmd), we need to:
        1. Set the variable in shell state (for builtins/functions that use $VAR)
        2. Set the variable in shell.env (for external commands that use os.environ)

        Returns a dict with both state and env values for restoration.
        """
        saved_vars = {}

        for var, value in assignments:
            var, value = self._resolve_append(var, value)
            # Save both shell state and environment values
            saved_vars[var] = {
                'state': self.state.get_variable(var),
                'env': self.shell.env.get(var)  # May be None if not in env
            }
            # Values are already expanded by _extract_assignments_raw / execute()
            try:
                self.state.set_variable(var, value)
                # Also set in shell.env for external commands
                self.shell.env[var] = value
            except ReadonlyVariableError:
                raise

        return saved_vars

    def _restore_command_assignments(self, saved_vars: dict):
        """Restore variables after command execution.

        Restores both shell state and shell.env to their original values.
        Command-prefixed assignments (FOO=bar cmd) are always temporary,
        even for exported variables.
        """
        for var, saved in saved_vars.items():
            # Restore shell state variable
            old_state_value = saved['state']
            if old_state_value is None:
                self.state.unset_variable(var)
            else:
                self.state.set_variable(var, old_state_value)

            # Restore shell.env
            old_env_value = saved['env']
            if old_env_value is None:
                # Variable wasn't in env before, remove it
                if var in self.shell.env:
                    del self.shell.env[var]
            else:
                self.shell.env[var] = old_env_value

    def _is_exported(self, var_name: str) -> bool:
        """Check if a variable is exported."""
        return is_exported(var_name)

    def _expand_assignment_value_from_word(self, value: str, word=None) -> str:
        """Expand a value used in variable assignment.

        Uses the Word AST's structural information to correctly handle
        quoting (e.g., single-quoted values remain literal).
        """
        if word is not None:
            return self._expand_assignment_word(word)
        # Fallback for cases without Word AST (shouldn't happen normally)
        if value.startswith('~'):
            value = self.expansion_manager.expand_tilde(value)
        if '$' in value or '`' in value:
            value = self.expansion_manager.expand_string_variables(value)
        return value

    def _expand_assignment_word(self, word) -> str:
        """Expand an assignment value using Word AST parts.

        Walks the Word's parts, expanding only what the quote context
        allows (single-quoted text stays literal, double-quoted text
        expands variables, unquoted text expands everything).
        """
        from ..ast_nodes import ExpansionPart, LiteralPart

        result_parts = []
        # Find the '=' in the parts and only expand the value portion
        found_eq = False
        for part in word.parts:
            if not found_eq:
                if isinstance(part, LiteralPart) and '=' in part.text:
                    # This part contains the '=' — take everything after it
                    eq_pos = part.text.index('=')
                    value_text = part.text[eq_pos + 1:]
                    if value_text:
                        if part.quoted and part.quote_char == "'":
                            result_parts.append(value_text)
                        elif part.quoted and part.quote_char == '"':
                            result_parts.append(value_text)
                        else:
                            # Unquoted text after = — expand tilde if first
                            if not result_parts and value_text.startswith('~'):
                                value_text = self.expansion_manager.expand_tilde(value_text)
                            result_parts.append(value_text)
                    found_eq = True
                    continue
                else:
                    # Skip parts before '=' (the variable name portion)
                    continue

            # Process value parts after '='
            if isinstance(part, LiteralPart):
                if part.quoted and part.quote_char == "'":
                    # Single-quoted: completely literal
                    result_parts.append(part.text)
                elif part.quoted and part.quote_char == '"':
                    # Double-quoted: literal (expansions are separate ExpansionParts)
                    # Process backslash escapes (\$, \\, \", \`)
                    text = part.text
                    if '\\' in text:
                        text = self.expansion_manager.process_dquote_escapes(text)
                    result_parts.append(text)
                else:
                    # Unquoted literal
                    text = part.text
                    if not result_parts and text.startswith('~'):
                        text = self.expansion_manager.expand_tilde(text)
                    result_parts.append(text)
            elif isinstance(part, ExpansionPart):
                expanded = self.expansion_manager.expand_expansion(part.expansion)
                result_parts.append(expanded)

        return ''.join(result_parts)

    def _print_xtrace(self, cmd_name: str, args: List[str]):
        """Print command trace if xtrace is enabled.

        Delegates to OptionHandler.print_xtrace so the PS4/format/flush policy
        lives in one place in core rather than being reimplemented here.
        """
        from ..core import OptionHandler
        OptionHandler.print_xtrace(self.state, [cmd_name] + args)

    def _execute_with_strategy(self, cmd_name: str, args: List[str],
                              node: 'SimpleCommand', context: 'ExecutionContext',
                              bypass_aliases: bool = False,
                              bypass_functions: bool = False) -> Tuple[int, bool]:
        """Execute command using the appropriate strategy.

        Returns:
            A tuple of (exit_code, is_special_builtin).  The second element
            is True when the command was resolved to a SpecialBuiltinExecutionStrategy,
            which signals the caller that POSIX prefix-assignment persistence applies.
        """
        # Note: The 'command' builtin handles its own bypass logic internally

        # Create strategy list based on bypass requirements
        strategies_to_exclude = []
        if bypass_aliases:
            strategies_to_exclude.append(AliasExecutionStrategy)
        if bypass_functions:
            strategies_to_exclude.append(FunctionExecutionStrategy)
            # Note: bypass_functions should NOT exclude special builtins

        if strategies_to_exclude:
            strategies_to_use = [
                strategy for strategy in self.strategies
                if not any(isinstance(strategy, exc_type) for exc_type in strategies_to_exclude)
            ]
        else:
            strategies_to_use = self.strategies

        # Find the right strategy
        for strategy in strategies_to_use:
            if strategy.can_execute(cmd_name, self.shell):
                is_special = isinstance(strategy, SpecialBuiltinExecutionStrategy)
                # Check if this is a builtin that needs special redirection handling.
                # In a forked child, builtins use os.write() on raw FDs, so
                # redirections must be applied via os.dup2() (with_redirections)
                # rather than Python-level sys.stdout replacement
                # (setup_builtin_redirections).
                is_forked = self.state.in_forked_child
                if isinstance(strategy, (SpecialBuiltinExecutionStrategy, BuiltinExecutionStrategy)) and not context.in_pipeline and not is_forked:
                    exit_code = self._execute_builtin_with_redirections(
                        cmd_name, args, node, context, strategy
                    )
                    return exit_code, is_special
                elif isinstance(strategy, ExternalExecutionStrategy):
                    # External commands apply their redirections in the
                    # forked child (setup_child_redirections). Applying them
                    # here too resolved `2>&1` against already-redirected
                    # fds and ran heredoc/target command substitutions twice.
                    exit_code = strategy.execute(
                        cmd_name, args, self.shell, context,
                        node.redirects, node.background,
                        visitor=getattr(self, '_visitor', None),
                    )
                    return exit_code, is_special
                else:
                    # Apply fd-level redirections for functions, aliases,
                    # builtins in pipelines, and builtins in forked children
                    with self.io_manager.with_redirections(node.redirects):
                        exit_code = strategy.execute(
                            cmd_name, args, self.shell, context,
                            node.redirects, node.background,
                            visitor=getattr(self, '_visitor', None),
                        )
                        return exit_code, is_special

        # Should never reach here as ExternalExecutionStrategy handles everything
        return 127, False

    def _execute_builtin_with_redirections(self, cmd_name: str, args: List[str],
                                          node: 'SimpleCommand', context: 'ExecutionContext',
                                          strategy: ExecutionStrategy) -> int:
        """Execute builtin with special redirection handling."""
        # DEBUG: Log builtin redirection setup
        if self.state.options.get('debug-exec'):
            print(f"DEBUG CommandExecutor: Setting up builtin redirections for '{cmd_name}'",
                  file=sys.stderr)
            print(f"DEBUG CommandExecutor: Redirections: {[r.type for r in node.redirects]}",
                  file=sys.stderr)

        # Builtins need special redirection handling
        stdin_backup, stdout_backup, stderr_backup, stdin_fd_backup = \
            self.io_manager.setup_builtin_redirections(node)
        try:
            # Update shell streams for builtins that might use them
            self.shell.stdout = sys.stdout
            self.shell.stderr = sys.stderr
            self.shell.stdin = sys.stdin

            # Execute builtin
            return strategy.execute(
                cmd_name, args, self.shell, context,
                node.redirects, node.background,
                visitor=getattr(self, '_visitor', None),
            )
        finally:
            self.io_manager.restore_builtin_redirections(
                stdin_backup, stdout_backup, stderr_backup, stdin_fd_backup
            )
            # Reset shell stream references
            # Preserve StringIO objects for test frameworks
            import io
            if not isinstance(self.shell.stdout, io.StringIO):
                self.shell.stdout = sys.stdout
            if not isinstance(self.shell.stderr, io.StringIO):
                self.shell.stderr = sys.stderr
            if not isinstance(self.shell.stdin, io.StringIO):
                self.shell.stdin = sys.stdin

    def _handle_array_assignment(self, assignment):
        """Handle array initialization or element assignment."""
        from ..ast_nodes import ArrayElementAssignment, ArrayInitialization
        from .array import ArrayOperationExecutor

        # Create array executor for this operation
        array_executor = ArrayOperationExecutor(self.shell)

        if isinstance(assignment, ArrayInitialization):
            return array_executor.execute_array_initialization(assignment)
        elif isinstance(assignment, ArrayElementAssignment):
            return array_executor.execute_array_element_assignment(assignment)
        else:
            return 0

    def _handle_exec_builtin(self, node: 'SimpleCommand', command_args: List[str],
                            assignments: List[tuple]) -> int:
        """Handle exec builtin with access to redirections."""
        # Get the exec builtin for command execution
        exec_builtin = self.builtin_registry.get('exec')
        if not exec_builtin:
            print("psh: exec: builtin not found", file=sys.stderr)
            return 127

        # Remove 'exec' from command args
        args = command_args[1:] if command_args and command_args[0] == 'exec' else command_args

        if not args:
            # exec without command - apply redirections permanently
            # and make variable assignments permanent
            if assignments:
                # Make assignments permanent by exporting them
                for var, value in assignments:
                    self.state.set_variable(var, value)
                    # Also export to environment
                    self.shell.env[var] = value
                    import os
                    os.environ[var] = value

            if node.redirects:
                try:
                    self.io_manager.apply_permanent_redirections(node.redirects)
                    return 0
                except OSError as e:
                    print(f"psh: exec: {e}", file=sys.stderr)
                    return 1
            else:
                # No redirections, just succeed
                return 0
        else:
            # exec with command - use the builtin's execute method
            return exec_builtin.execute(['exec'] + args, self.shell)
