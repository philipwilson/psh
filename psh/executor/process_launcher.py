"""Unified process launcher for all command execution.

This module provides a centralized component for launching processes with
proper job control setup. It eliminates code duplication across pipelines,
external commands, and subshells.
"""

import os
import signal
import sys
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Optional, Tuple

from .child_policy import (
    CHILD_EXIT_EXCEPTIONS,
    flush_child_streams,
    fork_with_signal_window,
    map_child_exception,
)

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

            # 2b. POSIX asynchronous-list rules, applied only when job control
            # is OFF (non-interactive) to a standalone backgrounded job (a bg
            # pipeline's members set up their own stdin from the pipe and are
            # left alone). See bash: an async list with job control disabled
            # has its stdin redirected from /dev/null and ignores SIGINT/
            # SIGQUIT. This runs BEFORE io_setup so an explicit body redirect
            # (`cmd < file &`) still wins.
            if config.role == ProcessRole.SINGLE and not config.foreground:
                self._apply_async_job_defaults(config)

            # 3. Set up I/O redirections if provided
            if config.io_setup:
                config.io_setup()

            # 4. Execute command
            exit_code = execute_fn()

            # Ensure exit code is an integer
            if not isinstance(exit_code, int):
                exit_code = 0 if exit_code else 1

        except CHILD_EXIT_EXCEPTIONS as e:
            # A control-flow / exit exception reaching this launcher child's
            # top maps to the child's status via the ONE shared taxonomy
            # (child_policy.map_child_exception): `break`/`continue`/`return`
            # cannot cross the fork into the parent's loop/function (e.g.
            # `return 5 &`, `break & wait`), a fatal discard (TopLevelAbort —
            # readonly assignment / failglob in a pipeline member) is
            # contained at the process boundary with its status, and `exit`
            # (incl. bare `exit` → SystemExit(None) → 0) terminates only this
            # child. Silent — bash is; the message, if any, was printed at
            # the raise site. See map_child_exception for each arm's pin.
            exit_code = map_child_exception(e)

        except KeyboardInterrupt:
            # Ctrl-C — launcher-local (a leaf child may exec an external
            # binary; this arm is not part of the child-exit taxonomy).
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

    def _job_control_off(self) -> bool:
        """True when the shell runs without job control (non-interactive).

        psh enables job control only for the interactive REPL; a script, a
        ``-c`` string or piped stdin all run with it off — exactly where the
        POSIX asynchronous-list defaults (stdin ← /dev/null, ignore INT/QUIT)
        apply. Mirrors SignalManager._in_noninteractive_shell.
        """
        return (self.state.is_script_mode
                or not self.state.options.get('interactive', False))

    def _apply_async_job_defaults(self, config: ProcessConfig) -> None:
        """Apply the POSIX async-list defaults to this backgrounded child.

        Only when job control is off. Redirects stdin from /dev/null so a
        backgrounded reader (`read &`, `cat &`) does not steal the script's
        stdin. For a LEAF child (an external about to exec, or a bg builtin —
        not a shell-process compound) also sets SIGINT/SIGQUIT to SIG_IGN,
        which survives exec (POSIX). A shell-process compound instead re-arms
        the trap-checking handlers via run_background_shell_child, so a
        body-set INT/QUIT trap can still fire while the untrapped default is
        ignore.
        """
        if not self._job_control_off():
            return
        try:
            devnull = os.open(os.devnull, os.O_RDONLY)
            try:
                os.dup2(devnull, 0)
            finally:
                if devnull != 0:
                    os.close(devnull)
        except OSError:
            pass
        if not config.is_shell_process:
            for sig in (signal.SIGINT, signal.SIGQUIT):
                try:
                    signal.signal(sig, signal.SIG_IGN)
                except (OSError, ValueError):
                    pass

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

