"""
Execution strategies for different command types.

This module implements the Strategy pattern for command execution,
providing different strategies for builtins, functions, and external commands.
"""

import os
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

from .process_launcher import ProcessConfig, ProcessLauncher, ProcessRole

if TYPE_CHECKING:
    from ..ast_nodes import Redirect
    from ..shell import Shell
    from .context import ExecutionContext


class ExecutionStrategy(ABC):
    """Abstract base class for command execution strategies."""

    @abstractmethod
    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if this strategy can execute the given command."""
        pass

    @abstractmethod
    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute the command and return exit status."""
        pass


# POSIX special builtins that take precedence over functions
POSIX_SPECIAL_BUILTINS = {
    ':', 'break', 'continue', 'eval', 'exec', 'exit', 'export',
    'readonly', 'return', 'set', 'shift', 'trap', 'unset'
}


class SpecialBuiltinExecutionStrategy(ExecutionStrategy):
    """Strategy for executing POSIX special builtin commands that take precedence over functions."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if command is a POSIX special builtin."""
        return (cmd_name in POSIX_SPECIAL_BUILTINS and
                shell.builtin_registry.has(cmd_name))

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute a special builtin command."""
        if background:
            # Special builtins can run in background with subshell
            return self._execute_in_background(cmd_name, args, shell, context, redirects)

        builtin = shell.builtin_registry.get(cmd_name)
        if not builtin:
            return 127  # Command not found

        try:
            # Use the builtin's execute method
            # Builtins expect the command name as the first argument
            return builtin.execute([cmd_name] + args, shell)
        except SystemExit:
            # Some builtins like 'exit' raise SystemExit
            raise
        except Exception as e:
            # Import FunctionReturn here to avoid circular imports
            from ..builtins import FunctionReturn
            if isinstance(e, FunctionReturn):
                # FunctionReturn must propagate to be caught by function execution
                raise
            # Handle other exceptions
            print(f"psh: {cmd_name}: {e}", file=shell.stderr)
            return 1

    def _execute_in_background(self, cmd_name: str, args: List[str],
                              shell: 'Shell', context: 'ExecutionContext',
                              redirects: Optional[List['Redirect']]) -> int:
        """Execute special builtin in background (subshell)."""
        # Use same background execution logic as regular builtins
        return BuiltinExecutionStrategy()._execute_in_background(
            cmd_name, args, shell, context, redirects
        )


class BuiltinExecutionStrategy(ExecutionStrategy):
    """Strategy for executing regular builtin commands."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if command is a regular builtin (not a special builtin)."""
        return (shell.builtin_registry.has(cmd_name) and
                cmd_name not in POSIX_SPECIAL_BUILTINS)

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute a builtin command."""
        if background:
            # Run builtin in background by forking a subshell (bash compatibility)
            return self._execute_builtin_in_background(cmd_name, args, shell, context, redirects)

        builtin = shell.builtin_registry.get(cmd_name)
        if not builtin:
            return 127  # Command not found

        # DEBUG: Log builtin execution
        if shell.state.options.get('debug-exec'):
            print(f"DEBUG BuiltinStrategy: executing builtin '{cmd_name}' with args {args}",
                  file=sys.stderr)
            print(f"DEBUG BuiltinStrategy: in_pipeline={context.in_pipeline}, "
                  f"in_forked_child={context.in_forked_child}", file=sys.stderr)

        try:
            # Use the builtin's execute method
            # The builtin will check context.in_forked_child to determine output method
            # Builtins expect the command name as the first argument
            return builtin.execute([cmd_name] + args, shell)
        except SystemExit:
            # Some builtins like 'exit' raise SystemExit
            raise
        except Exception as e:
            # Import FunctionReturn here to avoid circular imports
            from ..builtins import FunctionReturn
            if isinstance(e, FunctionReturn):
                # FunctionReturn must propagate to be caught by function execution
                raise
            print(f"psh: {cmd_name}: {e}", file=sys.stderr)
            return 1

    def _execute_builtin_in_background(self, cmd_name: str, args: List[str],
                                     shell: 'Shell', context: 'ExecutionContext',
                                     redirects: Optional[List['Redirect']] = None) -> int:
        """Execute a builtin command in background by forking a subshell."""
        # Create process launcher with centralized child signal reset (H3)
        launcher = ProcessLauncher(shell.state, shell.job_manager, shell.io_manager,
                                   shell.interactive_manager.signal_manager)

        # Create execution function
        def execute_fn():
            # Apply redirections if any
            if redirects:
                from ..ast_nodes import SimpleCommand
                temp_command = SimpleCommand(args=[cmd_name] + args, redirects=redirects)
                shell.io_manager.setup_child_redirections(temp_command)

            # Execute the builtin
            builtin = shell.builtin_registry.get(cmd_name)
            if builtin:
                return builtin.execute([cmd_name] + args, shell)
            else:
                return 127

        # Configure as background job
        config = ProcessConfig(
            role=ProcessRole.SINGLE,
            foreground=False
        )

        pid, pgid = launcher.launch(execute_fn, config)

        # Create job and register it
        job = shell.job_manager.create_job(pgid, f"{cmd_name} {' '.join(args)}")
        job.add_process(pid, cmd_name)
        shell.job_manager.register_background_job(job, shell_state=shell.state, last_pid=pid)

        # Print job assignment notification (only in interactive mode)
        if not shell.state.is_script_mode:
            print(f"[{job.job_id}] {pid}")

        return 0


class FunctionExecutionStrategy(ExecutionStrategy):
    """Strategy for executing shell functions."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if command is a defined function."""
        return shell.function_manager.get_function(cmd_name) is not None

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute a shell function."""
        if background:
            # Functions can't run in background (in current implementation)
            print(f"psh: {cmd_name}: functions cannot be run in background",
                  file=sys.stderr)
            return 1

        # Import here to avoid circular imports
        from .function import FunctionOperationExecutor

        # Create a function executor to handle the call
        function_executor = FunctionOperationExecutor(shell)

        # Reuse the caller's visitor to preserve accumulated state;
        # fall back to creating a new one if not provided.
        if visitor is None:
            from .core import ExecutorVisitor
            visitor = ExecutorVisitor(shell)
            visitor.context = context

        return function_executor.execute_function_call(
            cmd_name, args, context, visitor, redirects
        )


class AliasExecutionStrategy(ExecutionStrategy):
    """Strategy for executing shell aliases."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if command is an alias."""
        # Check for bypass mechanisms first
        if cmd_name.startswith('\\'):
            return False  # Backslash escapes bypass aliases
        result = shell.alias_manager.has_alias(cmd_name)
        return result

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute an alias by expanding and re-executing."""
        alias_definition = shell.alias_manager.get_alias(cmd_name)
        if not alias_definition:
            return 127  # Should not happen if can_execute returned True

        # Prevent infinite recursion
        if cmd_name in shell.alias_manager.expanding:
            # Already expanding this alias, treat as external command
            return self._execute_as_external(cmd_name, args, shell, context, redirects, background)

        # Mark this alias as being expanded
        shell.alias_manager.expanding.add(cmd_name)

        try:
            # Create new command string by expanding the alias
            # If alias has trailing space, next word can also be expanded
            if alias_definition.endswith(' '):
                # Handle trailing space for chained alias expansion
                expanded_command = alias_definition + ' '.join(args)
            else:
                expanded_command = alias_definition + (' ' + ' '.join(args) if args else '')

            # Re-tokenize and parse the expanded command
            from ..lexer import tokenize
            from ..parser import Parser

            tokens = tokenize(expanded_command)
            parser = Parser(tokens, source_text=expanded_command)
            ast = parser.parse()

            # Reuse the caller's visitor to preserve accumulated state;
            # fall back to creating a new one if not provided.
            if visitor is None:
                from .core import ExecutorVisitor
                visitor = ExecutorVisitor(shell)
                visitor.context = context

            return visitor.visit(ast)

        finally:
            # Remove from expanding set
            shell.alias_manager.expanding.discard(cmd_name)

    def _execute_as_external(self, cmd_name: str, args: List[str],
                            shell: 'Shell', context: 'ExecutionContext',
                            redirects: Optional[List['Redirect']] = None,
                            background: bool = False) -> int:
        """Execute as external command when alias recursion is detected."""
        external_strategy = ExternalExecutionStrategy()
        return external_strategy.execute(cmd_name, args, shell, context, redirects, background)


class ExternalExecutionStrategy(ExecutionStrategy):
    """Strategy for executing external commands."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """External commands are the fallback - always return True."""
        return True

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute an external command."""
        full_args = [cmd_name] + args

        if context.in_pipeline:
            # In pipeline, use exec to replace current process
            try:
                # Set up redirections if any
                if redirects:
                    # Create a dummy command object for the io_manager
                    from ..ast_nodes import SimpleCommand
                    temp_command = SimpleCommand(args=full_args, redirects=redirects)
                    shell.io_manager.setup_child_redirections(temp_command)

                # Ensure we're in the correct process group before exec
                # This is important for commands that might fork after exec
                current_pgid = os.getpgrp()
                current_pid = os.getpid()

                if shell.state.options.get('debug-exec'):
                    print(f"DEBUG ExternalStrategy: Before exec - PID={current_pid}, PGID={current_pgid}",
                          file=sys.stderr)

                # Always explicitly set the process group to ensure it's inherited
                # This helps when execvpe creates a new process
                os.setpgid(0, current_pgid)

                os.execvpe(full_args[0], full_args, shell.env)
            except OSError as e:
                print(f"psh: {full_args[0]}: {e}", file=sys.stderr)
                os._exit(127)

        # Set terminal title to show running command
        if not background and not context.in_pipeline and shell.state.options.get('interactive'):
            from ..interactive.title import command_title, set_terminal_title
            set_terminal_title(command_title(cmd_name, shell))

        # Save current terminal foreground process group
        # Skip terminal control when running under pytest to avoid SIGTTOU issues
        original_pgid = None
        is_pytest = 'PYTEST_CURRENT_TEST' in os.environ or 'pytest' in sys.modules
        if not background and not is_pytest:
            try:
                original_pgid = os.tcgetpgrp(0)
            except OSError:
                pass

        # Create process launcher with centralized child signal reset (H3)
        launcher = ProcessLauncher(shell.state, shell.job_manager, shell.io_manager,
                                   shell.interactive_manager.signal_manager)

        # Create execution function
        def execute_fn():
            # Set up redirections if any
            if redirects:
                # Create a dummy command object for the io_manager
                from ..ast_nodes import SimpleCommand
                temp_command = SimpleCommand(args=full_args, redirects=redirects)
                shell.io_manager.setup_child_redirections(temp_command)

            # Execute the command with proper environment
            if shell.state.options.get('debug-exec'):
                print(f"DEBUG ExternalStrategy: execvpe {full_args[0]} with "
                      f"PATH={shell.env.get('PATH', 'NOT_SET')[:50]}...",
                      file=sys.stderr)

            try:
                os.execvpe(full_args[0], full_args, shell.env)
            except FileNotFoundError:
                # Write to stderr file descriptor
                error_msg = f"psh: {full_args[0]}: command not found\n"
                os.write(2, error_msg.encode('utf-8'))
                return 127
            except OSError as e:
                # Write to stderr file descriptor
                error_msg = f"psh: {full_args[0]}: {e}\n"
                os.write(2, error_msg.encode('utf-8'))
                return 126

            # Not reached if exec succeeds
            return 127

        # Configure launch
        config = ProcessConfig(
            role=ProcessRole.SINGLE,
            foreground=not background
        )

        pid, pgid = launcher.launch(execute_fn, config)

        # Create job for tracking
        job = shell.job_manager.create_job(pgid, " ".join(str(arg) for arg in full_args))
        job.add_process(pid, str(full_args[0]))

        if background:
            # Background job - register properly so current_job is set
            shell.job_manager.register_background_job(job, shell_state=shell.state, last_pid=pid)
            # Print job assignment notification (only in interactive mode)
            if not shell.state.is_script_mode:
                print(f"[{job.job_id}] {pid}")
            return 0
        else:
            # Foreground job - give it terminal control
            job.foreground = True
            shell.job_manager.set_foreground_job(job)

            # Transfer terminal control (H5)
            if original_pgid is not None:
                if shell.job_manager.transfer_terminal_control(pgid, "ExternalStrategy"):
                    shell.state.foreground_pgid = pgid

            # Use job manager to wait (it handles SIGCHLD)
            exit_status = shell.job_manager.wait_for_job(job)

            # Restore terminal control and clean up foreground job state (H4)
            if original_pgid is not None:
                # Terminal control was transferred — restore it to the shell
                shell.job_manager.restore_shell_foreground()
            else:
                # Terminal control was NOT transferred (e.g., pytest) — just clean up state
                shell.job_manager.set_foreground_job(None)
                if shell.job_manager.shell_state is not None and hasattr(shell.job_manager.shell_state, 'foreground_pgid'):
                    shell.job_manager.shell_state.foreground_pgid = None

            # Clean up
            from ..job_control import JobState
            if job.state == JobState.DONE:
                shell.job_manager.remove_job(job.job_id)

            return exit_status
