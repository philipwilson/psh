"""
Pipeline execution support for the PSH executor.

This module provides the PipelineContext class and PipelineExecutor for
handling pipeline execution with proper process management and job control.
"""

import os
import signal
import sys
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..core import LoopBreak, LoopContinue
from ..core.exceptions import FunctionReturn
from .process_launcher import ProcessConfig, ProcessRole

if TYPE_CHECKING:
    from ..ast_nodes import ASTNode, Pipeline
    from ..shell import Shell
    from .context import ExecutionContext
    from .core import ExecutorVisitor
    from .job_control import Job, JobManager


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
        # The launcher applies the unified child signal policy on fork
        self.launcher = shell.process_launcher

    def execute(self, node: 'Pipeline', context: 'ExecutionContext',
                visitor: 'ExecutorVisitor') -> int:
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
                         visitor: 'ExecutorVisitor') -> int:
        """Execute pipeline without NOT handling."""
        if len(node.commands) == 1:
            # Single command, no pipeline needed
            status = visitor.visit(node.commands[0])
            self.state.pipestatus = [status]
            return status

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
        pgid: Optional[int] = None
        pids: List[int] = []

        # Create new context for pipeline execution
        pipeline_context = context.pipeline_context_enter()

        # Manage terminal control only when this shell actually owns the
        # terminal (real capability check — no test-runner sniffing).
        original_pgid = self.job_manager.terminal_pgid_if_owned()
        if self.state.options.get('debug-exec'):
            print(f"DEBUG Pipeline: Original terminal PGID: {original_pgid}", file=sys.stderr)

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
                        # Create forked context. Each pipeline component runs in
                        # its OWN subshell, so it is a fresh control-flow scope:
                        # the enclosing loop nesting is not visible (a `break N`
                        # here can't escape into the parent's loop), matching the
                        # plain-subshell path and bash.
                        child_context = pipeline_context.fork_context()
                        child_context.loop_depth = 0

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
                        try:
                            return visitor.visit(cmd_node)
                        except FunctionReturn as fr:
                            # `return` inside a pipelined compound exits THIS
                            # subshell with the return code (bash: it cannot
                            # return from the enclosing function — the function
                            # body is in the parent process).
                            return fr.exit_code
                        except (LoopBreak, LoopContinue):
                            # A break/continue that escapes the subshell's own
                            # loops just ends the subshell (status 0); it must
                            # not surface as an internal "psh: error:".
                            return 0

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

            # The pipeline always has >=2 commands here (single commands take an
            # earlier path), so the launch loop ran and set pgid to a real pgid.
            assert pgid is not None

            # Per-process command strings for the job table
            proc_entries = [(pid, self._command_to_string(node.commands[i]))
                            for i, pid in enumerate(pids)]

            # Close pipes in parent
            pipeline_ctx.close_pipes()

            if is_background:
                # Background pipeline: register the job and print the
                # interactive "[N] PID" notice (bash prints the pid of the
                # LAST process — the same value $! receives)
                pipeline_ctx.job = self.job_manager.launch_background(
                    pgid, command_string, proc_entries)
                return 0

            # Foreground pipeline: create job entry for tracking
            job = self.job_manager.create_job(pgid, command_string)
            for pid, cmd_str in proc_entries:
                job.add_process(pid, cmd_str)
            pipeline_ctx.job = job

            # Hand the terminal to the pipeline's process group immediately;
            # this prevents SIGTTOU in children before the wait starts
            if original_pgid is not None:
                self.job_manager.transfer_terminal_control(pgid, "Pipeline")

            # Wait for pipeline completion
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
            # Reclaim the terminal for the shell on error
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

        # Always collect every member's status so PIPESTATUS is populated
        all_statuses = self.job_manager.wait_for_job(job, collect_all_statuses=True)
        if not isinstance(all_statuses, list):
            all_statuses = [all_statuses]
        self.state.pipestatus = list(all_statuses)

        if self.state.options.get('pipefail') and len(node.commands) > 1:
            # Return rightmost non-zero exit status, or 0 if all succeeded
            exit_status = 0
            for status in reversed(all_statuses):
                if status != 0:
                    exit_status = status
                    break
        else:
            # Normal behavior: return exit status of last command
            exit_status = all_statuses[-1]

        # Reclaim the terminal (if we handed it over) and clear
        # foreground-job bookkeeping (a stopped job stays as %+).
        self.job_manager.finish_foreground_job(original_pgid is not None, job)

        # Remove completed job
        from .job_control import JobState
        if job.state == JobState.DONE:
            self.job_manager.remove_job(job.job_id)

        return exit_status

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
