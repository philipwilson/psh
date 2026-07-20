"""
Subshell and brace group execution support for the PSH executor.

This module handles execution of subshells and brace groups with proper
process isolation and environment management.
"""

import os
import sys
from typing import TYPE_CHECKING, List

from ..io_redirect.manager import format_redirect_error
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

            # Foreground: apply redirections and execute in current environment.
            # A bad redirect target prints bash's diagnostic and yields False,
            # so the body does not run — status 1, `|| fallback` runs.
            with self.io_manager.guarded_redirections(node.redirects) as applied:
                if not applied:
                    return 1
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
        """Execute subshell in foreground with proper isolation.

        Runs through the shared foreground-job transaction
        (:class:`ForegroundJobSession`) exactly like an external command or a
        pipeline — the same registration, terminal transfer/reclaim, signal-
        death diagnostic (a subshell killed by SIGTERM now prints
        ``Terminated: 15`` like bash — #20 H12), current-job rotation, and
        exception cleanup.
        """
        from .foreground_session import ForegroundJobSession

        # Open the transaction BEFORE the launch: it captures the terminal
        # owner while this shell still owns it (a real capability check — no
        # test-runner sniffing).
        session = ForegroundJobSession.open(self.job_manager)
        if self.state.options.get('debug-exec'):
            print(f"DEBUG Subshell: terminal owner pgid={session.original_pgid}",
                  file=sys.stderr)

        # Create execution function
        def execute_fn():
            # Import Shell here to avoid circular import. (Signal handlers
            # are only installed by run_interactive_loop(), which a forked
            # child never enters — no env-var marker needed.)
            from ..shell import Shell
            from .child_policy import run_child_body

            # Create new shell instance with copied environment
            subshell = Shell.for_subshell(self.shell)

            # Inherit the parent's I/O streams for test compatibility; the
            # body and EXIT trap write through them, so set them BEFORE the
            # shared runner.
            subshell.stdout = self.shell.stdout
            subshell.stderr = self.shell.stderr
            subshell.stdin = self.shell.stdin

            # The body applies this subshell's own redirects then runs its
            # statements. On a bad target, print bash's diagnostic to fd 2
            # and end the subshell 1 (the shared redirect-error format)
            # instead of letting the raw OSError reach the child-error path.
            def body(sub) -> int:
                if redirects:
                    try:
                        sub.io_manager.apply_redirections(redirects)
                    except OSError as e:
                        os.write(2, (format_redirect_error(
                            e, location=sub.state.error_location_prefix())
                            + "\n").encode('utf-8', errors='replace'))
                        return 1
                return sub.execute_command_list(statements)

            # run_child_body owns the shared middle every child-Shell fork
            # performs: mark the forked child, sync OS signal dispositions to
            # the adopted trap state (parent's non-ignored traps take the
            # default action), seed the parent's set -e SUPPRESSION (a subshell
            # that is an if-condition or non-final &&/|| member must not
            # errexit internally — bash), run the body through the shared
            # exception→status taxonomy (a readonly/nameref abort or an
            # inherited-context `return` ends the subshell with its status —
            # f() { (return 5); } → $? = 5), and run the subshell's own EXIT
            # trap. A ( ) subshell is NOT a substitution: no in_substitution
            # diagnostic suppression, no loop-scope seed, no trap drop, no
            # errexit-option reset.
            exit_code = run_child_body(
                subshell, body, errexit_suppress=errexit_suppress)

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

        # The one foreground transaction: register (foreground-job tracking +
        # terminal transfer), wait, announce a signal death, reclaim the
        # terminal + drop the DONE job. try/finally = exception cleanup.
        try:
            session.register(pgid, "<subshell>", [(pid, "subshell")])
            exit_status = session.wait()
            session.report_signal_death()
        finally:
            session.finish()

        return exit_status

    def _execute_background_subshell(self, statements, redirects: List['Redirect']) -> int:
        """Execute subshell in background with job control tracking."""
        # Create execution function
        def execute_fn():
            # Import Shell lazily to avoid circular dependency
            from ..shell import Shell
            from .child_policy import run_background_shell_child

            subshell = Shell.for_subshell(self.shell)

            # Share I/O streams for consistent output handling
            subshell.stdout = self.shell.stdout
            subshell.stderr = self.shell.stderr
            subshell.stdin = self.shell.stdin

            # The shared bg-child runner owns the subshell-environment trap
            # reset, the managed-signal handler re-arm, the pending-trap pump
            # and the EXIT trap (on normal completion, and via the signal
            # handlers on an untrapped fatal signal). The body just applies
            # this subshell's own redirects and runs its statements.
            def body() -> int:
                saved_fds = []
                try:
                    if redirects:
                        saved_fds = subshell.io_manager.apply_redirections(redirects)
                except OSError as e:
                    os.write(2, (format_redirect_error(
                        e, location=subshell.state.error_location_prefix())
                        + "\n").encode('utf-8', errors='replace'))
                    return 1
                try:
                    return subshell.execute_command_list(statements)
                finally:
                    if saved_fds:
                        subshell.io_manager.restore_redirections(saved_fds)

            exit_code = run_background_shell_child(subshell, body)

            # Flush output streams before returning (os._exit() won't).
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
            from .child_policy import run_background_shell_child

            # A backgrounded brace group runs in a forked subshell environment
            # (the fork copies self.shell). The shared bg-child runner gives it
            # the same trap discipline as ( ... ) &: a PARENT trap is reset so
            # it does not fire here, a body-set managed-signal trap fires, and
            # the EXIT trap runs on completion / fatal signal. The body applies
            # the group's redirects and runs its statements in this environment.
            def body() -> int:
                saved_fds = []
                try:
                    if node.redirects:
                        saved_fds = self.io_manager.apply_redirections(node.redirects)
                except OSError as e:
                    os.write(2, (format_redirect_error(
                        e, location=self.state.error_location_prefix())
                        + "\n").encode('utf-8', errors='replace'))
                    return 1
                try:
                    return visitor.visit(node.statements)
                finally:
                    if saved_fds:
                        self.io_manager.restore_redirections(saved_fds)

            return run_background_shell_child(self.shell, body)

        return self.launcher.launch_background_job(
            execute_fn, "<brace-group>", "brace-group", is_shell_process=True)
