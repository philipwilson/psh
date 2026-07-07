"""
Pipeline execution support for the PSH executor.

This module provides the PipelineContext class and PipelineExecutor for
handling pipeline execution with proper process management and job control.
"""

import errno
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


def _close_quiet(fd: Optional[int]) -> None:
    """Close ``fd`` if set, ignoring an already-closed / invalid descriptor."""
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


class PipelineContext:
    """Rolling pipe construction and process tracking for one pipeline.

    One pipe is created per command boundary, just before forking the command
    that writes into it; after that fork the parent releases the descriptors it
    no longer needs and carries the boundary's read end forward as the next
    command's stdin. The parent therefore holds O(1) pipe descriptors
    regardless of pipeline length — the old design pre-opened all N-1 pipes,
    so the parent held O(N) and long pipelines hit EMFILE under an ordinary
    RLIMIT_NOFILE.
    """

    def __init__(self, job_manager: 'JobManager'):
        self.job_manager = job_manager
        self.processes: List[int] = []
        self.job: Optional['Job'] = None
        # Rolling state: the read end carried from the previous boundary, and
        # the pipe (read end / write end) created for the current command's
        # outgoing boundary.
        self._prev_read: Optional[int] = None
        self._pending_read: Optional[int] = None
        self._cur_write: Optional[int] = None

    def open_boundary(self, has_next: bool) -> Tuple[Optional[int], Optional[int], List[int]]:
        """Prepare the current command's endpoints just before forking it.

        Creates the outgoing pipe when the command has a successor, and returns
        ``(stdin_fd, stdout_fd, owned)`` — the endpoints the child wires onto
        0/1 and the full set of pipe descriptors it inherits and must close
        (``remap_fds`` keeps the ones serving as its stdin/stdout).
        """
        stdin_fd = self._prev_read
        if has_next:
            self._pending_read, self._cur_write = os.pipe()
            stdout_fd: Optional[int] = self._cur_write
        else:
            self._pending_read = None
            self._cur_write = None
            stdout_fd = None
        owned = [fd for fd in (self._prev_read, self._pending_read,
                               self._cur_write) if fd is not None]
        return stdin_fd, stdout_fd, owned

    def advance(self) -> None:
        """Release parent-side descriptors after forking the current command.

        The previous boundary's read end and this command's write end are now
        held by their child(ren); the parent closes its copies and carries the
        new boundary's read end forward as the next command's stdin. Only child
        N holds a given write end, so the reader downstream gets EOF when that
        child exits.
        """
        _close_quiet(self._prev_read)
        _close_quiet(self._cur_write)
        self._prev_read = self._pending_read
        self._pending_read = None
        self._cur_write = None

    def close_open_fds(self) -> None:
        """Close any pipe descriptors still open in the parent (error cleanup)."""
        _close_quiet(self._prev_read)
        _close_quiet(self._pending_read)
        _close_quiet(self._cur_write)
        self._prev_read = self._pending_read = self._cur_write = None

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
        if not node.commands:
            # An empty pipeline (a bare `!` / `time` prefix before a list
            # terminator) succeeds; execute() then applies any negation
            # (bash: `!` alone -> 1, `! !` -> 0).
            self.state.pipestatus = [0]
            return 0

        if len(node.commands) == 1:
            # Single command, no pipeline needed
            status = visitor.visit(node.commands[0])
            self.state.pipestatus = [status]
            return status

        # Multi-command pipeline. Pipes are created incrementally during the
        # fork loop below (rolling construction), so the parent never holds
        # more than one boundary's descriptors at a time.
        pipeline_ctx = PipelineContext(self.job_manager)

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

        n = len(node.commands)
        try:
            # Fork processes for each command, creating each pipe just before
            # the command that writes into it (rolling construction).
            for i, command in enumerate(node.commands):
                # $BASH_COMMAND: bash records each pipeline element in the
                # PARENT as it dispatches it (an ERR trap after `a | b`
                # reports the last element's text); each forked child also
                # re-records its own command before its DEBUG trap. The
                # node is stamped; text renders lazily on read.
                self.shell.trap_manager.set_bash_command(command)

                # Determine process role
                if i == 0:
                    role = ProcessRole.PIPELINE_LEADER
                else:
                    role = ProcessRole.PIPELINE_MEMBER

                # Open this command's outgoing pipe (when it has a successor)
                # and collect the endpoints it wires and the descriptors it
                # inherits and must close.
                stdin_fd, stdout_fd, owned = pipeline_ctx.open_boundary(
                    has_next=(i < n - 1))
                this_pipe_stderr = bool(
                    node.pipe_stderr and i < len(node.pipe_stderr)
                    and node.pipe_stderr[i])
                is_last = (i == n - 1)

                # Create execution function for this command
                def make_execute_fn(cmd_node, s_in, s_out, own, pstderr, last):
                    """Create execution function for pipeline command.

                    This closure captures this command's node and pipe endpoints
                    for execution.
                    """
                    def execute_fn():
                        # Create forked context. Each pipeline component runs
                        # in its OWN subshell process, so a break/continue here
                        # can never escape into the parent's loop — the except
                        # below just ends this subshell. loop_depth is still
                        # inherited so a bare `break | cat` inside a loop is
                        # silent (bash), not "only meaningful in a loop".
                        child_context = pipeline_context.fork_context()

                        # Wire stdin/stdout onto this member's pipe endpoints
                        # (collision-safe; closes the endpoints it doesn't use).
                        self._setup_pipeline_redirections(
                            s_in, s_out, own, pipe_stderr=pstderr)

                        # For the last command in foreground pipeline, restore terminal signals
                        if last and not is_background:
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
                        except (LoopBreak, LoopContinue) as e:
                            # A break/continue that escapes the subshell's own
                            # loops just ends the subshell with the signal's
                            # own status — 0 normally, 1 for the out-of-range
                            # `break 0` case (bash: `cat /dev/null | break 0`
                            # inside a loop yields pipeline status 1). It must
                            # not surface as an internal "psh: error:".
                            return e.exit_status or 0

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
                pid, pgid = self.launcher.launch(
                    make_execute_fn(command, stdin_fd, stdout_fd, owned,
                                    this_pipe_stderr, is_last), config)

                pids.append(pid)
                pipeline_ctx.add_process(pid)
                # Release the parent's copies of the endpoints just handed to
                # this child; carry the boundary read end forward as the next
                # command's stdin.
                pipeline_ctx.advance()

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

            # Rolling construction has already closed every data-pipe descriptor
            # in the parent as each child was forked, so there is nothing left
            # to close here.

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
            # A pipe()/fork()/setpgid() failure part-way through the launch loop
            # (F13). Roll the partial launch back transactionally rather than
            # leaking it: the children already forked are blocked on the sync
            # pipe (or, for the leader, already running), and closing the sync
            # pipe alone would RELEASE them to run an incomplete pipeline and
            # then linger as zombies. No Job record exists yet (it is created
            # only after the loop completes), so there is nothing to unpublish.
            self._rollback_partial_launch(
                pipeline_ctx, sync_pipe_r, sync_pipe_w, pgid, is_background)
            raise

    def _rollback_partial_launch(self, pipeline_ctx: 'PipelineContext',
                                 sync_pipe_r: int, sync_pipe_w: int,
                                 pgid: Optional[int],
                                 is_background: bool) -> None:
        """Undo a partially-launched pipeline (F13): signal, release, reap.

        Order matters. The launched members are SIGKILLed FIRST — before the
        sync gate is released — so none of them proceeds to run the incomplete
        pipeline; a member blocked on the sync-pipe read dies from the signal
        regardless. Only THEN is the sync pipe closed and every launched child
        reaped, so nothing is left running and nothing becomes a zombie. The
        terminal is finally reclaimed for the shell. Only the expected
        setpgid()-race errors are swallowed while signalling.
        """
        launched = list(pipeline_ctx.processes)

        # 1. Signal the partial process group once (the members share the
        #    leader's pgid), then each pid individually in case a setpgid race
        #    left a just-forked child briefly outside the group.
        if pgid is not None and launched:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except OSError:
                pass
        for pid in launched:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # already gone
            except OSError:
                pass

        # 2. Release the sync gate (any member the signal has not yet felled
        #    unblocks and is immediately killed by the pending SIGKILL).
        _close_quiet(sync_pipe_r)
        _close_quiet(sync_pipe_w)

        # 3. Reap every launched child so none is left as a zombie. The kill
        #    above guarantees each exits promptly, so this does not block.
        for pid in launched:
            while True:
                try:
                    os.waitpid(pid, 0)
                    break
                except OSError as e:
                    if e.errno == errno.EINTR:
                        continue
                    break  # ECHILD: already reaped elsewhere

        # 4. Close any pipe descriptors still open in the parent.
        pipeline_ctx.close_open_fds()

        # 5. Reclaim the terminal for the shell.
        if not is_background:
            self.job_manager.restore_shell_foreground()

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

        # The member whose status becomes the pipeline's exit status is also
        # the one whose signal death gets announced (bash).
        status_index = len(all_statuses) - 1
        if self.state.options.get('pipefail') and len(node.commands) > 1:
            # Return rightmost non-zero exit status, or 0 if all succeeded
            exit_status = 0
            for i in range(len(all_statuses) - 1, -1, -1):
                if all_statuses[i] != 0:
                    exit_status = all_statuses[i]
                    status_index = i
                    break
        else:
            # Normal behavior: return exit status of last command
            exit_status = all_statuses[-1]

        # Announce abnormal termination (Terminated / Segmentation fault /
        # ...) the way bash does for a signal-killed foreground pipeline.
        self._report_signal_death(job, status_index)

        # Reclaim the terminal (if we handed it over) and clear
        # foreground-job bookkeeping (a stopped job stays as %+).
        self.job_manager.finish_foreground_job(original_pgid is not None, job)

        # Remove completed job
        from .job_control import JobState
        if job.state == JobState.DONE:
            self.job_manager.remove_job(job.job_id)

        return exit_status

    def _report_signal_death(self, job: 'Job', index: int) -> None:
        """Announce a foreground pipeline member killed by a signal.

        bash prints the signal's description (``Terminated: 15``, ...) to
        stderr when the pipeline's EXIT STATUS reflects a signal death —
        i.e. the announced member is the one whose status the pipeline
        reports: the last member normally, the rightmost failing member
        under pipefail (pinned against bash 5.2 in
        tmp/probes-r17t2-grabbag/probe_c_pipeline_signal.sh). Any other
        member's signal death is silent, as is SIGINT/SIGPIPE (see
        abnormal_termination_message). This mirrors
        JobManager.report_abnormal_termination for single commands,
        including its silence inside command/process substitutions; psh
        emits just the bare signal message where bash sometimes adds a
        PID/command job-table wrapper (documented format difference).
        """
        if self.state.in_substitution:
            return
        if not 0 <= index < len(job.processes):
            return
        status = job.processes[index].status
        if status is None:
            return
        from .job_control import abnormal_termination_message
        message = abnormal_termination_message(status)
        if message is not None:
            print(message, file=self.state.stderr)

    def _setup_pipeline_redirections(self, stdin_fd: Optional[int],
                                     stdout_fd: Optional[int],
                                     owned: List[int],
                                     pipe_stderr: bool = False) -> None:
        """Wire this pipeline member's stdin/stdout onto its pipe endpoints.

        Built as one collision-safe remap rather than raw dup2s + a blanket
        close loop. The blanket loop was unsafe when descriptors 0 or 1 began
        closed (``exec 0<&-``, ``exec 1>&-``): ``os.pipe()`` then hands an
        endpoint back AS fd 0 or 1, ``dup2(fd, fd)`` is a no-op, and the loop
        destroys the live endpoint (D1/D2). remap_fds promotes endpoints out of
        the way, resolves the closed-fd remapping cycle, and closes every pipe
        descriptor this child ``owns`` except the ones now serving as its
        stdin/stdout.

        ``owned`` is exactly this member's inherited pipe endpoints (its own
        stdin/stdout ends plus its outgoing pipe's read end, which belongs to
        the next member) — O(1) per member under rolling construction.

        NOTE (verifier finding, v0.653): under rolling construction the SYNC
        pipe is created before any data pipe, so with fds 0/1 closed it is the
        sync pipe — not a data endpoint — that occupies the low descriptors.
        That ordering is co-responsible for the D1/D2 fix: reverting this
        method to raw dup2s currently passes the closed-fd matrix because of
        it. Keep BOTH: the ordering is an emergent property of rolling
        construction, while this remap is the explicit, self-contained
        guarantee that survives future reorderings.
        """
        pairs: List[Tuple[int, int]] = []
        if stdin_fd is not None:
            pairs.append((stdin_fd, 0))
        if stdout_fd is not None:
            pairs.append((stdout_fd, 1))
            # ``|&``: this member's stderr joins its stdout at the same pipe.
            if pipe_stderr:
                pairs.append((stdout_fd, 2))

        from ..io_redirect import remap_fds
        remap_fds(pairs, owned=owned)

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
