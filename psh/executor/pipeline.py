"""
Pipeline execution support for the PSH executor.

This module provides the PipelineContext class and PipelineExecutor for
handling pipeline execution with proper process management and job control.
"""

import os
import signal
import sys
from typing import TYPE_CHECKING, List, Optional, Tuple

from .process_launcher import ProcessConfig, ProcessLauncher, ProcessRole

if TYPE_CHECKING:
    from psh.visitor import ASTVisitor

    from ..ast_nodes import ASTNode, Pipeline
    from ..job_control import Job, JobManager
    from ..shell import Shell
    from .context import ExecutionContext


class PipelineContext:
    """Context for managing pipeline execution state."""

    def __init__(self, job_manager: 'JobManager'):
        self.job_manager = job_manager
        self.pipes: List[Tuple[int, int]] = []
        self.processes: List[int] = []
        self.job: Optional['Job'] = None

    def add_pipe(self) -> int:
        """Add a new pipe for the pipeline."""
        self.pipes.append(os.pipe())
        return len(self.pipes) - 1

    def get_stdin_fd(self, index: int) -> Optional[int]:
        """Get stdin file descriptor for command at index."""
        if index > 0 and index <= len(self.pipes):
            return self.pipes[index - 1][0]
        return None

    def get_stdout_fd(self, index: int) -> Optional[int]:
        """Get stdout file descriptor for command at index."""
        if index < len(self.pipes):
            return self.pipes[index][1]
        return None

    def close_pipes(self):
        """Close all pipes in parent process."""
        for read_fd, write_fd in self.pipes:
            try:
                os.close(read_fd)
                os.close(write_fd)
            except OSError:
                pass

    def add_process(self, pid: int):
        """Add a process to the pipeline."""
        self.processes.append(pid)


class PipelineExecutor:
    """
    Handles execution of pipelines.

    This class encapsulates all logic for executing Pipeline nodes,
    including process forking, pipe management, job control, and
    terminal control.
    """

    def __init__(self, shell: 'Shell'):
        """Initialize the pipeline executor with a shell instance."""
        self.shell = shell
        self.state = shell.state
        self.job_manager = shell.job_manager
        # Use centralized child signal reset (H3)
        self.launcher = ProcessLauncher(shell.state, shell.job_manager, shell.io_manager,
                                        shell.interactive_manager.signal_manager)

    def execute(self, node: 'Pipeline', context: 'ExecutionContext',
                visitor: 'ASTVisitor[int]') -> int:
        """
        Execute a pipeline and return exit status.

        Args:
            node: The Pipeline AST node to execute
            context: The current execution context
            visitor: The visitor to use for executing individual commands

        Returns:
            Exit status code
        """
        # Handle NOT operator
        if node.negated:
            exit_status = self._execute_pipeline(node, context, visitor)
            # Invert exit status for NOT
            return 0 if exit_status != 0 else 1
        else:
            return self._execute_pipeline(node, context, visitor)

    def _execute_pipeline(self, node: 'Pipeline', context: 'ExecutionContext',
                         visitor: 'ASTVisitor[int]') -> int:
        """Execute pipeline without NOT handling."""
        # In eval test mode, try to execute simple pipelines without forking to enable output capture
        if (hasattr(self.state, 'eval_test_mode') and self.state.eval_test_mode and
            self._is_simple_builtin_pipeline(node)):
            return self._execute_simple_pipeline_in_test_mode(node, context, visitor)
        else:
            return self._execute_pipeline_with_forking(node, context, visitor)

    def _execute_pipeline_with_forking(self, node: 'Pipeline', context: 'ExecutionContext',
                                     visitor: 'ASTVisitor[int]') -> int:
        """Execute pipeline with forking (original implementation)."""
        if len(node.commands) == 1:
            # Single command, no pipeline needed
            return visitor.visit(node.commands[0])

        # Multi-command pipeline
        pipeline_ctx = PipelineContext(self.job_manager)

        # Create pipes
        for i in range(len(node.commands) - 1):
            pipeline_ctx.add_pipe()

        # Check if pipeline runs in background (last command determines)
        is_background = node.commands[-1].background if node.commands else False

        # Build command string for job tracking
        command_string = self._pipeline_to_string(node)

        # Set terminal title to show running pipeline
        if not is_background and self.state.options.get('interactive'):
            from ..interactive.title import command_title, set_terminal_title
            set_terminal_title(command_title(command_string, self.shell))

        # Variables to track pgid
        pgid = None
        pids = []

        # Create new context for pipeline execution
        pipeline_context = context.pipeline_context_enter()
        pipeline_context = pipeline_context.with_pipeline_context(pipeline_ctx)

        # Save original terminal process group for restoration
        # Skip terminal control when running under pytest to avoid SIGTTOU issues
        is_pytest = 'PYTEST_CURRENT_TEST' in os.environ or 'pytest' in sys.modules
        if is_pytest:
            original_pgid = None
        else:
            try:
                original_pgid = os.tcgetpgrp(0)
                if self.state.options.get('debug-exec'):
                    print(f"DEBUG Pipeline: Original terminal PGID: {original_pgid}", file=sys.stderr)
            except OSError as e:
                if self.state.options.get('debug-exec'):
                    print(f"DEBUG Pipeline: Cannot get original PGID: {e}", file=sys.stderr)
                original_pgid = None

        # Create synchronization pipe for process group setup
        # This replaces the time.sleep() polling loop with atomic synchronization
        sync_pipe_r, sync_pipe_w = os.pipe()

        try:
            # Fork processes for each command
            for i, command in enumerate(node.commands):
                # Determine process role
                if i == 0:
                    role = ProcessRole.PIPELINE_LEADER
                else:
                    role = ProcessRole.PIPELINE_MEMBER

                # Create execution function for this command
                def make_execute_fn(cmd_index, cmd_node):
                    """Create execution function for pipeline command.

                    This closure captures the command index and node for execution.
                    """
                    def execute_fn():
                        # Create forked context
                        child_context = pipeline_context.fork_context()

                        # Set up pipeline redirections (stdin/stdout, and stderr for |&)
                        self._setup_pipeline_redirections(
                            cmd_index, pipeline_ctx,
                            pipe_stderr=node.pipe_stderr if node.pipe_stderr else None
                        )

                        # For the last command in foreground pipeline, restore terminal signals
                        if cmd_index == len(node.commands) - 1 and not is_background:
                            signal.signal(signal.SIGTTOU, signal.SIG_DFL)
                            signal.signal(signal.SIGTTIN, signal.SIG_DFL)

                        # Execute command with pipeline context
                        # IMPORTANT: Update visitor's context to use the child_context
                        visitor.context = child_context
                        exit_status = visitor.visit(cmd_node)

                        return exit_status

                    return execute_fn

                # Configure process launch
                config = ProcessConfig(
                    role=role,
                    pgid=pgid if i > 0 else None,
                    foreground=not is_background,
                    sync_pipe_r=sync_pipe_r,
                    sync_pipe_w=sync_pipe_w,
                    io_setup=None  # I/O setup is done in execute_fn
                )

                # Launch the process
                pid, pgid = self.launcher.launch(make_execute_fn(i, command), config)

                pids.append(pid)
                pipeline_ctx.add_process(pid)

            # All children forked and process groups set
            # Signal children by closing sync pipe
            try:
                os.close(sync_pipe_r)
            except OSError:
                pass
            try:
                os.close(sync_pipe_w)
            except OSError:
                pass

            if self.state.options.get('debug-exec'):
                print(f"DEBUG Pipeline: Process group synchronization complete, pgid={pgid}", file=sys.stderr)

            # Create job entry for tracking
            job = self.job_manager.create_job(pgid, command_string)
            for i, pid in enumerate(pids):
                cmd_str = self._command_to_string(node.commands[i])
                job.add_process(pid, cmd_str)
            pipeline_ctx.job = job

            # Close pipes in parent
            pipeline_ctx.close_pipes()

            # Transfer terminal control immediately for foreground pipelines (H5)
            # This prevents SIGTTOU in children before wait method is called
            if not is_background and original_pgid is not None:
                self.job_manager.transfer_terminal_control(pgid, "Pipeline")

            # Wait for pipeline completion
            if is_background:
                # Background pipeline
                last_pid = pids[-1] if pids else job.pgid
                self.job_manager.register_background_job(job, shell_state=self.state, last_pid=last_pid)
                print(f"[{job.job_id}] {job.pgid}", file=self.shell.stderr)
                return 0
            else:
                # Foreground pipeline - wait for completion
                return self._wait_for_foreground_pipeline(job, node, original_pgid)

        except (OSError, ValueError):
            # Clean up sync pipe on error
            try:
                os.close(sync_pipe_r)
            except OSError:
                pass
            try:
                os.close(sync_pipe_w)
            except OSError:
                pass
            # Clean up pipes on error
            pipeline_ctx.close_pipes()
            # Restore terminal control on error (H4)
            if not is_background:
                self.job_manager.restore_shell_foreground()
            raise

    def _wait_for_foreground_pipeline(self, job: 'Job', node: 'Pipeline', original_pgid: Optional[int] = None) -> int:
        """Wait for a foreground pipeline to complete."""
        job.foreground = True
        self.job_manager.set_foreground_job(job)

        # Note: original_pgid is intentionally None when terminal control was
        # not transferred (e.g., in pytest or non-interactive subshells).
        # Do NOT re-fetch it here — that would cause tcsetpgrp() to be called
        # from a background process group, triggering SIGTTOU.

        if self.state.options.get('pipefail') and len(node.commands) > 1:
            # Get all exit statuses for pipefail
            all_statuses = self.job_manager.wait_for_job(job, collect_all_statuses=True)
            if isinstance(all_statuses, list):
                # Return rightmost non-zero exit status, or 0 if all succeeded
                exit_status = 0
                for status in reversed(all_statuses):
                    if status != 0:
                        exit_status = status
                        break
            else:
                exit_status = all_statuses
        else:
            # Normal behavior: return exit status of last command
            exit_status = self.job_manager.wait_for_job(job)

        # Restore terminal control and clean up foreground job state (H4)
        if original_pgid is not None:
            # Terminal control was transferred — restore it to the shell
            self.job_manager.restore_shell_foreground()
        else:
            # Terminal control was NOT transferred — just clean up state
            self.job_manager.set_foreground_job(None)
            if self.job_manager.shell_state is not None and hasattr(self.job_manager.shell_state, 'foreground_pgid'):
                self.job_manager.shell_state.foreground_pgid = None

        # Remove completed job
        from ..job_control import JobState
        if job.state == JobState.DONE:
            self.job_manager.remove_job(job.job_id)

        return exit_status

    def _is_simple_builtin_pipeline(self, node: 'Pipeline') -> bool:
        """Check if this is a simple pipeline that can be executed without forking in test mode."""
        from ..ast_nodes import SimpleCommand

        # Must be a pipeline with exactly 2 commands
        if len(node.commands) != 2:
            return False

        # Both commands must be SimpleCommands
        for cmd in node.commands:
            if not isinstance(cmd, SimpleCommand):
                return False

        # For test mode, we can handle simple cases even with external commands
        # This is safe because we're only doing it in test environments
        return True

    def _is_builtin_command(self, cmd_name: str) -> bool:
        """Check if a command is a PSH builtin."""
        from ..builtins import registry
        return cmd_name in registry

    def _execute_simple_pipeline_in_test_mode(self, node: 'Pipeline', context: 'ExecutionContext',
                                           visitor: 'ASTVisitor[int]') -> int:
        """Execute simple pipeline without forking for test output capture."""
        from ..ast_nodes import SimpleCommand

        # This is a simplified pipeline execution for test mode only
        # It uses subprocess.run with pipes to simulate shell pipeline behavior

        first_cmd = node.commands[0]
        second_cmd = node.commands[1]

        # Check if we can handle this with StringIO (both are builtins)
        if (isinstance(first_cmd, SimpleCommand) and isinstance(second_cmd, SimpleCommand) and
            first_cmd.args and second_cmd.args):

            first_cmd_name = str(first_cmd.args[0])
            second_cmd_name = str(second_cmd.args[0])

            if (self._is_builtin_command(first_cmd_name) and
                self._is_builtin_command(second_cmd_name)):
                return self._execute_builtin_to_builtin_pipeline(first_cmd, second_cmd, visitor)
            else:
                return self._execute_mixed_pipeline_in_test_mode(first_cmd, second_cmd, context, visitor)

        # Fallback to mixed mode
        return self._execute_mixed_pipeline_in_test_mode(first_cmd, second_cmd, context, visitor)

    def _execute_builtin_to_builtin_pipeline(self, first_cmd, second_cmd, visitor):
        """Execute builtin-to-builtin pipeline using StringIO."""
        import io

        # Save current stdout/stdin
        original_stdout = self.shell.stdout
        original_stdin = self.shell.stdin

        # Create a StringIO buffer to capture output from first command
        pipe_buffer = io.StringIO()

        try:
            # Redirect first command's output to buffer
            self.shell.stdout = pipe_buffer

            # Execute first command
            exit_code1 = visitor.visit(first_cmd)

            # Get the output from first command
            pipe_output = pipe_buffer.getvalue()

            # Restore original stdout for second command
            self.shell.stdout = original_stdout

            # Create a StringIO input for second command to read from
            pipe_input = io.StringIO(pipe_output)

            # Redirect second command's input from pipe
            self.shell.stdin = pipe_input

            # Execute second command
            exit_code2 = visitor.visit(second_cmd)

            # Pipeline exit status is that of the last command (unless pipefail is set)
            if self.state.options.get('pipefail'):
                return exit_code1 if exit_code1 != 0 else exit_code2
            else:
                return exit_code2

        finally:
            # Restore original stdout/stdin
            self.shell.stdout = original_stdout
            self.shell.stdin = original_stdin

    def _execute_mixed_pipeline_in_test_mode(self, first_cmd, second_cmd, context, visitor):
        """Execute pipeline with potential external commands using subprocess."""
        import subprocess

        from ..ast_nodes import SimpleCommand

        # For mixed pipelines in test mode, use subprocess to maintain output capture
        if isinstance(first_cmd, SimpleCommand) and isinstance(second_cmd, SimpleCommand):
            first_args = [str(arg) for arg in first_cmd.args]
            second_args = [str(arg) for arg in second_cmd.args]

            try:
                # Run the pipeline using subprocess
                # First command
                proc1 = subprocess.Popen(
                    first_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=self.shell.env
                )

                # Second command
                proc2 = subprocess.Popen(
                    second_args,
                    stdin=proc1.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=self.shell.env
                )

                # Close first process stdout to allow proc1 to receive SIGPIPE
                proc1.stdout.close()

                # Wait for completion and get output
                stdout, stderr = proc2.communicate()
                proc1.wait()

                # Write output to shell's stdout (which should be captured by pytest)
                if stdout:
                    self.shell.stdout.write(stdout)
                    self.shell.stdout.flush()

                if stderr:
                    self.shell.stderr.write(stderr)
                    self.shell.stderr.flush()

                # Return exit status of last command
                return proc2.returncode

            except FileNotFoundError:
                # If command not found, try executing as builtins
                return self._execute_builtin_to_builtin_pipeline(first_cmd, second_cmd, visitor)
            except (OSError, subprocess.SubprocessError):
                # Fallback to original forking method with a real Pipeline node
                from ..ast_nodes import Pipeline
                fallback_node = Pipeline(
                    commands=[first_cmd, second_cmd],
                    negated=False,
                )
                return self._execute_pipeline_with_forking(
                    fallback_node, context, visitor
                )

        # Fallback for non-SimpleCommand cases
        return visitor.visit(first_cmd)

    def _setup_pipeline_redirections(self, index: int, pipeline_ctx: PipelineContext,
                                     pipe_stderr: Optional[List[bool]] = None):
        """Set up stdin/stdout for command in pipeline."""
        # Redirect stdin from previous pipe
        stdin_fd = pipeline_ctx.get_stdin_fd(index)
        if stdin_fd is not None:
            os.dup2(stdin_fd, 0)

        # Redirect stdout to next pipe
        stdout_fd = pipeline_ctx.get_stdout_fd(index)
        if stdout_fd is not None:
            os.dup2(stdout_fd, 1)

        # If |& was used, also redirect stderr to the pipe
        # pipe_stderr[i] is True if |& connects command i to command i+1
        if pipe_stderr and index < len(pipe_stderr) and pipe_stderr[index]:
            # stderr goes to same place as stdout (already pointing at pipe)
            os.dup2(1, 2)

        # Close all pipe file descriptors in child
        for read_fd, write_fd in pipeline_ctx.pipes:
            os.close(read_fd)
            os.close(write_fd)

    def _pipeline_to_string(self, node: 'Pipeline') -> str:
        """Convert pipeline to string representation."""
        return " | ".join(self._command_to_string(cmd) for cmd in node.commands)

    def _command_to_string(self, cmd: 'ASTNode') -> str:
        """Convert command to string representation."""
        from ..ast_nodes import SimpleCommand
        if isinstance(cmd, SimpleCommand):
            # Convert args to strings (in case they're RichToken objects)
            str_args = [str(arg) for arg in cmd.args]
            return " ".join(str_args)
        else:
            return f"<{type(cmd).__name__}>"
