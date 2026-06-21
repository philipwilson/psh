"""Unified process launcher for all command execution.

This module provides a centralized component for launching processes with
proper job control setup. It eliminates code duplication across pipelines,
external commands, and subshells.
"""

import os
import sys
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Optional, Tuple

from .child_policy import flush_child_streams, fork_with_signal_window

if TYPE_CHECKING:
    from ..core.state import ShellState
    from ..interactive.signal_manager import SignalManager
    from ..io_redirect import IOManager
    from .job_control import JobManager


class ProcessRole(Enum):
    """Role of process in job control structure."""
    SINGLE = "single"                    # Standalone command
    PIPELINE_LEADER = "pipeline_leader"  # First command in pipeline
    PIPELINE_MEMBER = "pipeline_member"  # Non-first command in pipeline


@dataclass
class ProcessConfig:
    """Configuration for launching a process.

    Attributes:
        role: The process's role in job control
        pgid: Process group to join (None = create new)
        foreground: Whether this is a foreground job
        sync_pipe_r: Read end of sync pipe (pipeline synchronization)
        sync_pipe_w: Write end of sync pipe (pipeline synchronization)
        io_setup: Optional callback for I/O redirection setup
        is_shell_process: If True, keep SIGTTOU=SIG_IGN after signal reset
            (for subshells/brace groups that may call tcsetpgrp())
    """
    role: ProcessRole
    pgid: Optional[int] = None
    foreground: bool = True
    sync_pipe_r: Optional[int] = None
    sync_pipe_w: Optional[int] = None
    io_setup: Optional[Callable] = None
    is_shell_process: bool = False


class ProcessLauncher:
    """Unified component for launching processes with proper job control.

    This class centralizes all process creation logic to ensure consistency
    across pipelines, external commands, and background jobs. It handles:

    - Process forking and error handling
    - Process group setup and synchronization
    - Signal handler reset in child processes
    - Job creation and tracking
    - Terminal control transfer

    Usage:
        launcher = shell.process_launcher  # the single shared instance

        # Simple foreground command
        config = ProcessConfig(role=ProcessRole.SINGLE, foreground=True)
        pid, pgid = launcher.launch(lambda: execute_command(), config)

        # Pipeline member with synchronization
        config = ProcessConfig(
            role=ProcessRole.PIPELINE_MEMBER,
            pgid=leader_pgid,
            sync_pipe_r=pipe_r
        )
        pid, pgid = launcher.launch(lambda: execute_command(), config)
    """

    def __init__(self, shell_state: 'ShellState', job_manager: 'JobManager',
                 io_manager: 'IOManager', signal_manager: 'SignalManager'):
        """Initialize the process launcher.

        Args:
            shell_state: Shell state for options and configuration
            job_manager: Job manager for tracking processes
            io_manager: I/O manager for redirections
            signal_manager: Signal manager used to reset the child's
                signal handlers to defaults after fork
        """
        self.state = shell_state
        self.job_manager = job_manager
        self.io_manager = io_manager
        self.signal_manager = signal_manager

    def launch(self, execute_fn: Callable[[], int],
               config: ProcessConfig) -> Tuple[int, int]:
        """Launch a process with proper job control setup.

        This is the main entry point for process creation. It handles forking,
        child/parent setup, and returns process information.

        Args:
            execute_fn: Function to execute in child (returns exit code)
            config: Process configuration

        Returns:
            (pid, pgid) tuple - process ID and process group ID

        Raises:
            OSError: If fork() fails
        """
        # Flush Python's stdout/stderr before forking to prevent buffered content
        # from being inherited by the child process and potentially written to
        # redirected output files
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except (AttributeError, OSError):
            # stdout/stderr might not support flush() in some contexts
            pass

        # Fork with termination signals blocked across the fork window
        # (the v0.300 lost-signal race fix — see fork_with_signal_window's
        # docstring in child_policy.py). The child unblocks them in
        # apply_child_signal_policy() after resetting handlers to SIG_DFL.
        pid = fork_with_signal_window()

        if pid == 0:  # Child process
            # apply_child_signal_policy() (called in _child_setup_and_exec)
            # resets handlers to SIG_DFL and unblocks these signals.
            self._child_setup_and_exec(execute_fn, config)
            # Does not return - child exits via os._exit()

        # Parent process
        pgid = self._parent_setup(pid, config)
        return pid, pgid

    def launch_background_job(self, execute_fn: Callable[[], int],
                             command_string: str, proc_label: str, *,
                             is_shell_process: bool = False) -> int:
        """Fork *execute_fn* as a background job and register it.

        The single launch+register sequence shared by every ``cmd &`` path —
        backgrounded builtins, functions, subshells and brace groups: launch a
        non-foreground SINGLE process, then register it as a job (which prints
        the interactive ``[N] PID`` notice and sets ``$!``). Returns 0 (a
        backgrounded command's own status is always success).
        """
        config = ProcessConfig(role=ProcessRole.SINGLE, foreground=False,
                               is_shell_process=is_shell_process)
        pid, pgid = self.launch(execute_fn, config)
        self.job_manager.launch_background(pgid, command_string,
                                           [(pid, proc_label)])
        return 0

    def _child_setup_and_exec(self, execute_fn: Callable[[], int],
                              config: ProcessConfig):
        """Child process setup and execution.

        This method handles all child process initialization:
        1. Set process group (with synchronization if needed)
        2. Reset signal handlers to default
        3. Set up I/O redirections
        4. Execute the command function
        5. Exit cleanly

        This is deliberately NOT child_policy.run_child_shell() (the
        substitution-child runner): launcher children need process-group
        and sync-pipe setup that substitutions don't have, may exec an
        external binary (so KeyboardInterrupt -> 130 and the non-int
        coercion matter), and reuse the parent Shell object in the
        forked copy rather than building a child Shell. The shared
        pieces ARE shared code: fork_with_signal_window(),
        apply_child_signal_policy(), and flush_child_streams() all come
        from child_policy.

        Args:
            execute_fn: Function to execute
            config: Process configuration
        """
        exit_code = 127  # Default: command not found

        try:
            # 1. Set process group based on role
            if config.role == ProcessRole.PIPELINE_LEADER:
                # First in pipeline: become process group leader
                os.setpgid(0, 0)

                # Close both sync pipe ends (leader doesn't wait)
                if config.sync_pipe_r is not None:
                    try:
                        os.close(config.sync_pipe_r)
                    except OSError:
                        pass
                if config.sync_pipe_w is not None:
                    try:
                        os.close(config.sync_pipe_w)
                    except OSError:
                        pass

                if self.state.options.get('debug-exec'):
                    print(f"DEBUG ProcessLauncher: Child {os.getpid()} is pipeline leader",
                          file=sys.stderr)

            elif config.role == ProcessRole.PIPELINE_MEMBER:
                # Non-first in pipeline: block on the sync pipe until the
                # parent has forked every member and set up the process
                # group, so no member runs before the group exists

                # Close write end (child won't write to it)
                if config.sync_pipe_w is not None:
                    try:
                        os.close(config.sync_pipe_w)
                    except OSError:
                        pass

                # Wait for parent to close its write end
                if config.sync_pipe_r is not None:
                    try:
                        # Block on read - will unblock when parent closes write end
                        os.read(config.sync_pipe_r, 1)
                    except OSError:
                        pass  # EOF or error - parent closed pipe
                    finally:
                        try:
                            os.close(config.sync_pipe_r)
                        except OSError:
                            pass

                if self.state.options.get('debug-exec'):
                    current_pgid = os.getpgrp()
                    print(f"DEBUG ProcessLauncher: Child {os.getpid()} synchronized, "
                          f"pgid={current_pgid}", file=sys.stderr)

            elif config.role == ProcessRole.SINGLE:
                # Standalone command: create own process group
                os.setpgid(0, 0)

                if self.state.options.get('debug-exec'):
                    print(f"DEBUG ProcessLauncher: Child {os.getpid()} is single command",
                          file=sys.stderr)

            # 2. Reset signals to default (unified child policy)
            from .child_policy import apply_child_signal_policy
            apply_child_signal_policy(
                self.signal_manager, self.state,
                is_shell_process=config.is_shell_process,
            )

            # 3. Set up I/O redirections if provided
            if config.io_setup:
                config.io_setup()

            # 4. Execute command
            exit_code = execute_fn()

            # Ensure exit code is an integer
            if not isinstance(exit_code, int):
                exit_code = 0 if exit_code else 1

        except SystemExit as e:
            # Handle explicit exit() calls
            exit_code = e.code if isinstance(e.code, int) else 1

        except KeyboardInterrupt:
            # Ctrl-C
            exit_code = 130  # 128 + SIGINT(2)

        except Exception as e:
            # Unexpected error
            print(f"psh: error: {e}", file=sys.stderr)
            if self.state.options.get('debug-exec'):
                import traceback
                traceback.print_exc()
            exit_code = 1

        finally:
            # Ensure we always exit cleanly (shared flush discipline —
            # os._exit() does not flush Python-level buffers)
            flush_child_streams(sys.stdout, sys.stderr)
            os._exit(exit_code)

    def _parent_setup(self, pid: int, config: ProcessConfig) -> int:
        """Parent process setup after fork.

        This method handles process group assignment from the parent side.
        It must be called immediately after fork() to coordinate with the child.

        Args:
            pid: Child process ID
            config: Process configuration

        Returns:
            Process group ID
        """
        # Determine process group
        if config.role == ProcessRole.PIPELINE_LEADER or config.role == ProcessRole.SINGLE:
            # Child becomes its own process group leader
            pgid = pid
            try:
                os.setpgid(pid, pid)
            except OSError:
                pass  # Child may have already set it (race condition)
        else:
            # Child joins existing process group
            pgid = config.pgid if config.pgid is not None else pid
            try:
                os.setpgid(pid, pgid)
                if self.state.options.get('debug-exec'):
                    print(f"DEBUG ProcessLauncher: Parent set child {pid} to pgid {pgid}",
                          file=sys.stderr)
            except OSError as e:
                if self.state.options.get('debug-exec'):
                    print(f"DEBUG ProcessLauncher: Parent failed to set pgid for {pid}: {e}",
                          file=sys.stderr)
                pass  # Child may have already set it

        return pgid

