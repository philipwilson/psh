"""
Subshell and brace group execution support for the PSH executor.

This module handles execution of subshells and brace groups with proper
process isolation and environment management.
"""

import sys
from typing import TYPE_CHECKING, List

from .process_launcher import ProcessConfig, ProcessRole

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
        # The launcher applies the unified child signal policy on fork
        self.launcher = shell.process_launcher

    def execute_subshell(self, node: 'SubshellGroup', context: 'ExecutionContext') -> int:
        """
        Execute subshell group (...) in isolated environment.

        Unlike ``execute_brace_group``, this needs no visitor: a subshell forks
        a fresh ``Shell`` and runs its statements there, rather than re-entering
        the current visitor.

        Args:
            node: The SubshellGroup AST node
            context: Current execution context

        Returns:
            Exit status code
        """
        return self._execute_in_subshell(node.statements, node.redirects, node.background,
                                         errexit_suppress=context.errexit_suppress)

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

    def _execute_in_subshell(self, statements, redirects: List['Redirect'], background: bool,
                             errexit_suppress: int = 0) -> int:
        """Execute statements in an isolated subshell environment."""
        if background:
            return self._execute_background_subshell(statements, redirects)

        # Execute in foreground subshell with proper isolation
        return self._execute_foreground_subshell(statements, redirects,
                                                 errexit_suppress=errexit_suppress)

    def _execute_foreground_subshell(self, statements, redirects: List['Redirect'],
                                     errexit_suppress: int = 0) -> int:
        """Execute subshell in foreground with proper isolation."""
        # Manage terminal control only when this shell actually owns the
        # terminal (real capability check — no test-runner sniffing).
        original_pgid = self.job_manager.terminal_pgid_if_owned()
        is_interactive = original_pgid is not None
        if self.state.options.get('debug-exec'):
            print(f"DEBUG Subshell: terminal owner pgid={original_pgid}", file=sys.stderr)

        # Create execution function
        def execute_fn():
            # Import Shell here to avoid circular import. (Signal handlers
            # are only installed by run_interactive_loop(), which a forked
            # child never enters — no env-var marker needed.)
            from ..shell import Shell

            # Create new shell instance with copied environment
            subshell = Shell.for_subshell(self.shell)

            # Mark as forked child so builtins use os.write() which respects dup2()
            # This is critical for output redirection to work correctly in subshells
            subshell.state.in_forked_child = True

            # Inherit the parent's set -e suppression: a subshell that is
            # e.g. an if-condition or a non-final && / || member must not
            # errexit internally (bash).
            subshell._errexit_suppress_seed = errexit_suppress

            # Inherit I/O streams from parent shell for test compatibility
            subshell.stdout = self.shell.stdout
            subshell.stderr = self.shell.stderr
            subshell.stdin = self.shell.stdin

            # Apply redirections if any
            if redirects:
                subshell.io_manager.apply_redirections(redirects)

            # Execute statements in isolated environment
            exit_code = subshell.execute_command_list(statements)

            # A subshell runs its own EXIT trap when it finishes (bash):
            # (trap 'echo bye' EXIT; ...) prints bye on subshell exit.
            try:
                subshell.trap_manager.execute_exit_trap()
            except Exception:
                pass

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

        # Hand the terminal to the subshell's process group if interactive
        if is_interactive and original_pgid is not None:
            self.job_manager.transfer_terminal_control(pgid, "Subshell")

        # Create job for tracking the subshell
        job = self.job_manager.create_job(pgid, "<subshell>")
        job.add_process(pid, "subshell")
        job.foreground = True

        # Use job manager to wait (handles SIGCHLD properly)
        exit_status = self.job_manager.wait_for_job(job)

        # Reclaim the terminal for the parent shell if interactive
        if is_interactive:
            self.job_manager.restore_shell_foreground()

        # Clean up job
        from .job_control import JobState
        if job.state == JobState.DONE:
            self.job_manager.remove_job(job.job_id)

        return exit_status

    def _execute_background_subshell(self, statements, redirects: List['Redirect']) -> int:
        """Execute subshell in background with job control tracking."""
        # Create execution function
        def execute_fn():
            # Import Shell lazily to avoid circular dependency
            from ..shell import Shell

            subshell = Shell.for_subshell(self.shell)

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
                # A backgrounded subshell is still a subshell: it runs its own
                # EXIT trap when it finishes, exactly like the foreground path.
                try:
                    subshell.trap_manager.execute_exit_trap()
                except Exception:
                    pass
                # Flush output streams before returning
                try:
                    subshell.stdout.flush()
                    subshell.stderr.flush()
                except (OSError, ValueError):
                    pass

            return exit_code

        return self.launcher.launch_background_job(
            execute_fn, "<subshell>", "subshell", is_shell_process=True)

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

        return self.launcher.launch_background_job(
            execute_fn, "<brace-group>", "brace-group", is_shell_process=True)
