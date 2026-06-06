"""
Subshell and brace group execution support for the PSH executor.

This module handles execution of subshells and brace groups with proper
process isolation and environment management.
"""

import os
import sys
from typing import TYPE_CHECKING, List

from .process_launcher import ProcessConfig, ProcessLauncher, ProcessRole

if TYPE_CHECKING:
    from psh.visitor import ASTVisitor

    from ..ast_nodes import BraceGroup, Redirect, SubshellGroup
    from ..shell import Shell
    from .context import ExecutionContext


class SubshellExecutor:
    """
    Handles subshell and brace group execution.

    This class encapsulates logic for:
    - Subshell execution with process isolation
    - Brace group execution in current shell
    - Background execution of both constructs
    - Proper job control integration
    """

    def __init__(self, shell: 'Shell'):
        """Initialize the subshell executor with a shell instance."""
        self.shell = shell
        self.state = shell.state
        self.job_manager = shell.job_manager
        self.io_manager = shell.io_manager
        # Use centralized child signal reset (H3)
        self.launcher = ProcessLauncher(shell.state, shell.job_manager, shell.io_manager,
                                        shell.interactive_manager.signal_manager)

    def execute_subshell(self, node: 'SubshellGroup', context: 'ExecutionContext',
                        visitor: 'ASTVisitor[int]') -> int:
        """
        Execute subshell group (...) in isolated environment.

        Args:
            node: The SubshellGroup AST node
            context: Current execution context
            visitor: Visitor for executing child nodes

        Returns:
            Exit status code
        """
        return self._execute_in_subshell(node.statements, node.redirects, node.background)

    def execute_brace_group(self, node: 'BraceGroup', context: 'ExecutionContext',
                           visitor: 'ASTVisitor[int]') -> int:
        """
        Execute brace group {...} in current shell environment.

        Key differences from subshells:
        - No fork() - executes in current process
        - Variable assignments persist
        - Directory changes persist
        - More efficient (no subprocess overhead)

        Args:
            node: The BraceGroup AST node
            context: Current execution context
            visitor: Visitor for executing child nodes

        Returns:
            Exit status code
        """
        # Save pipeline context
        old_pipeline = context.in_pipeline
        context.in_pipeline = False

        try:
            if node.background:
                # Background brace groups need to fork; do NOT execute
                # in the parent first (that would cause double execution).
                return self._execute_background_brace_group(node, visitor)

            # Foreground: apply redirections and execute in current environment
            with self.io_manager.with_redirections(node.redirects):
                return visitor.visit(node.statements)
        finally:
            context.in_pipeline = old_pipeline

    def _execute_in_subshell(self, statements, redirects: List['Redirect'], background: bool) -> int:
        """Execute statements in an isolated subshell environment."""
        if background:
            return self._execute_background_subshell(statements, redirects)

        # Execute in foreground subshell with proper isolation
        return self._execute_foreground_subshell(statements, redirects)

    def _execute_foreground_subshell(self, statements, redirects: List['Redirect']) -> int:
        """Execute subshell in foreground with proper isolation."""
        # Save current terminal foreground process group
        original_pgid = None
        # Check if we're in interactive mode (stdin is a tty and not in script mode)
        # AND we're actually the foreground process group (not running under pytest/etc)
        # Also check for pytest environment to be extra safe
        is_pytest = 'PYTEST_CURRENT_TEST' in os.environ or 'pytest' in sys.modules
        is_interactive = sys.stdin.isatty() and not self.shell.is_script_mode and not is_pytest
        if is_interactive:
            try:
                current_fg_pgid = os.tcgetpgrp(0)
                our_pgid = os.getpgrp()
                # Debug: log the check
                if self.state.options.get('debug-exec'):
                    print(f"DEBUG Subshell: isatty={sys.stdin.isatty()}, script_mode={self.shell.is_script_mode}", file=sys.stderr)
                    print(f"DEBUG Subshell: current_fg_pgid={current_fg_pgid}, our_pgid={our_pgid}", file=sys.stderr)
                # Only treat as interactive if WE are the foreground process group
                # This prevents issues when running under pytest with -s flag
                if current_fg_pgid == our_pgid:
                    original_pgid = current_fg_pgid
                    if self.state.options.get('debug-exec'):
                        print(f"DEBUG Subshell: Will manage terminal control", file=sys.stderr)
                else:
                    # We're not in control of the terminal, don't try to manipulate it
                    is_interactive = False
                    if self.state.options.get('debug-exec'):
                        print(f"DEBUG Subshell: Skipping terminal control (not foreground)", file=sys.stderr)
            except OSError as e:
                if self.state.options.get('debug-exec'):
                    print(f"DEBUG Subshell: Exception checking terminal: {e}", file=sys.stderr)
                is_interactive = False

        # Create execution function
        def execute_fn():
            # Import Shell here to avoid circular import
            # Mark that we're in a forked child BEFORE creating the Shell
            # This prevents the child from trying to set up job control/signals
            import os

            from ..shell import Shell
            os.environ['PSH_IN_FORKED_CHILD'] = '1'

            try:
                # Create new shell instance with copied environment
                subshell = Shell(
                    debug_ast=self.shell.state.debug_ast,
                    debug_tokens=self.shell.state.debug_tokens,
                    parent_shell=self.shell,  # Copy variables/functions
                    norc=True
                )

                # Mark as forked child so builtins use os.write() which respects dup2()
                # This is critical for output redirection to work correctly in subshells
                subshell.state.in_forked_child = True
            finally:
                # Clean up the environment variable
                if 'PSH_IN_FORKED_CHILD' in os.environ:
                    del os.environ['PSH_IN_FORKED_CHILD']

            # Inherit I/O streams from parent shell for test compatibility
            subshell.stdout = self.shell.stdout
            subshell.stderr = self.shell.stderr
            subshell.stdin = self.shell.stdin

            # Apply redirections if any
            if redirects:
                subshell.io_manager.apply_redirections(redirects)

            # Execute statements in isolated environment
            exit_code = subshell.execute_command_list(statements)

            # Flush output streams before returning
            # This is critical because os._exit() doesn't flush buffers
            try:
                subshell.stdout.flush()
                subshell.stderr.flush()
            except (OSError, ValueError):
                pass

            return exit_code

        # Configure launch
        config = ProcessConfig(
            role=ProcessRole.SINGLE,
            foreground=True,
            is_shell_process=True
        )

        pid, pgid = self.launcher.launch(execute_fn, config)

        # Transfer terminal control to subshell if interactive (H5)
        if is_interactive and original_pgid is not None:
            self.job_manager.transfer_terminal_control(pgid, "Subshell")

        # Create job for tracking the subshell
        job = self.job_manager.create_job(pgid, "<subshell>")
        job.add_process(pid, "subshell")
        job.foreground = True

        # Use job manager to wait (handles SIGCHLD properly)
        exit_status = self.job_manager.wait_for_job(job)

        # Restore terminal control to parent shell if interactive (H4)
        if is_interactive:
            self.job_manager.restore_shell_foreground()

        # Clean up job
        if job.state.name == 'DONE':
            self.job_manager.remove_job(job.job_id)

        return exit_status

    def _execute_background_subshell(self, statements, redirects: List['Redirect']) -> int:
        """Execute subshell in background with job control tracking."""
        # Create execution function
        def execute_fn():
            # Import Shell lazily to avoid circular dependency
            from ..shell import Shell

            subshell = Shell(
                debug_ast=self.shell.state.debug_ast,
                debug_tokens=self.shell.state.debug_tokens,
                parent_shell=self.shell,
                norc=True
            )

            # Share I/O streams for consistent output handling
            subshell.stdout = self.shell.stdout
            subshell.stderr = self.shell.stderr
            subshell.stdin = self.shell.stdin

            exit_code = 0
            saved_fds = []
            try:
                if redirects:
                    saved_fds = subshell.io_manager.apply_redirections(redirects)
                exit_code = subshell.execute_command_list(statements)
            finally:
                if saved_fds:
                    subshell.io_manager.restore_redirections(saved_fds)
                # Flush output streams before returning
                try:
                    subshell.stdout.flush()
                    subshell.stderr.flush()
                except (OSError, ValueError):
                    pass

            return exit_code

        # Configure launch
        config = ProcessConfig(
            role=ProcessRole.SINGLE,
            foreground=False,
            is_shell_process=True
        )

        pid, pgid = self.launcher.launch(execute_fn, config)

        # Create and register background job
        job = self.job_manager.create_job(pgid, "<subshell>")
        job.add_process(pid, "subshell")
        self.job_manager.register_background_job(job, shell_state=self.shell.state, last_pid=pid)

        if not self.shell.is_script_mode:
            print(f"[{job.job_id}] {job.pgid}", file=self.shell.stderr)

        return 0

    def _execute_background_brace_group(self, node: 'BraceGroup',
                                       visitor: 'ASTVisitor[int]') -> int:
        """
        Execute brace group in background.

        Note: Background execution requires forking, but the brace group
        semantics are preserved within the forked process.
        """
        # Create execution function
        def execute_fn():
            # Execute the brace group in current environment (no new shell)
            # Apply redirections first
            exit_code = 0
            saved_fds = []
            try:
                if node.redirects:
                    saved_fds = self.io_manager.apply_redirections(node.redirects)
                exit_code = visitor.visit(node.statements)
            finally:
                if saved_fds:
                    self.io_manager.restore_redirections(saved_fds)

            return exit_code

        # Configure launch
        config = ProcessConfig(
            role=ProcessRole.SINGLE,
            foreground=False,
            is_shell_process=True
        )

        pid, pgid = self.launcher.launch(execute_fn, config)

        # Create and register background job
        job = self.job_manager.create_job(pgid, "<brace-group>")
        job.add_process(pid, "brace-group")
        self.job_manager.register_background_job(job, shell_state=self.shell.state, last_pid=pid)

        if not self.shell.is_script_mode:
            print(f"[{job.job_id}] {job.pgid}", file=self.shell.stderr)

        return 0
