"""Becoming a healthy psh child process.

This module is the one-stop chapter for what every forked psh child has
in common, separated from what any particular child *does*:

- fork_with_signal_window() — how to fork (termination signals blocked
  across the window; the parent-side half of the signal policy).
- apply_child_signal_policy() — the child-side half: reset handlers to
  SIG_DFL, then unblock.
- run_child_shell() — the shared child-body runner for substitution
  children (command substitution, process substitution): signal policy,
  fd plumbing hook, child Shell construction, body execution, exception
  → exit-code mapping, stream flushing, os._exit(). The caller supplies
  only the two site-specific pieces: the fd plumbing (io_setup) and the
  body (what this child runs).
- flush_child_streams() — the shared pre-os._exit() flush discipline
  (os._exit() does not flush Python-level buffers).

Every fork path must fork via fork_with_signal_window() and call
apply_child_signal_policy() immediately after the fork in the child
branch — substitution children get this by calling run_child_shell(),
which applies the policy first. ProcessLauncher children keep their own
body path (_child_setup_and_exec): they need process-group/sync-pipe
setup and may exec an external binary, and they reuse the parent Shell
in the forked copy rather than building a child Shell — but they share
this module's fork helper, signal policy, and flush discipline.
"""

import os
import signal
import sys
from typing import TYPE_CHECKING, Callable, NoReturn, Optional

if TYPE_CHECKING:
    from ..shell import Shell


def fork_with_signal_window() -> int:
    """fork() with termination signals blocked across the fork window.

    The shell installs Python-level handlers for SIGTERM/SIGINT/SIGHUP/
    SIGQUIT (trap support), and a forked child inherits them until
    apply_child_signal_policy() resets them to SIG_DFL. Without
    blocking, a signal aimed at the child in that window (e.g.
    ``sleep 5 & kill %1`` racing the fork) is consumed by Python's
    C-level handler and then silently LOST across exec() — the command
    would run to completion as if never signaled. Blocked, the signal
    stays kernel-pending until the child unblocks it in
    apply_child_signal_policy(), at which point the default action
    (termination) is taken with the correct status.

    Returns os.fork()'s result (0 in the child, the child's pid in the
    parent).  The PARENT's mask is restored ALWAYS — including when
    os.fork() itself raises (e.g. EAGAIN under process pressure);
    without that the shell would run with the signals blocked forever
    after a failed fork.  The CHILD does not restore: it must call
    apply_child_signal_policy(), which unblocks after resetting
    handlers to SIG_DFL.
    """
    block_set = {signal.SIGTERM, signal.SIGINT,
                 signal.SIGHUP, signal.SIGQUIT}
    old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, block_set)
    pid = None
    try:
        pid = os.fork()
    finally:
        if pid != 0:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
    return pid


def apply_child_signal_policy(signal_manager, state, is_shell_process=False):
    """Apply the standard signal policy for a forked child process.

    This is the single source of truth for child process signal setup.
    It must be called in every child immediately after fork().

    Steps:
        1. Mark state as forked child
        2. Temporarily ignore SIGTTOU (prevents STOP during setup)
        3. Reset all signals to SIG_DFL via signal_manager
        4. If is_shell_process, re-ignore SIGTTOU (shell processes may
           call tcsetpgrp() and must not be stopped by SIGTTOU)
        5. Unblock termination signals that the forking parent may have
           blocked across fork() (see ProcessLauncher.launch): any signal
           delivered during the fork window is kernel-pending and takes
           its default action here, with the correct termination status.

    Args:
        signal_manager: The SignalManager instance (provides reset_child_signals)
        state: The ShellState instance (sets in_forked_child flag)
        is_shell_process: True for subshells, brace groups, command/process
            substitution children that run shell commands (never exec an
            external binary). False for leaf processes that will exec.
    """
    state.in_forked_child = True

    # Temporarily ignore SIGTTOU to avoid being stopped during setup
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)

    # Reset all signals to default (SIGINT, SIGQUIT, SIGTERM, SIGHUP,
    # SIGTSTP, SIGTTOU, SIGTTIN, SIGCHLD, SIGPIPE, SIGWINCH)
    signal_manager.reset_child_signals()

    # Shell processes keep SIGTTOU ignored so they can call tcsetpgrp()
    # for job control without being stopped. Leaf processes keep SIG_DFL
    # from reset_child_signals().
    if is_shell_process:
        signal.signal(signal.SIGTTOU, signal.SIG_IGN)

    # Now that handlers are SIG_DFL, unblock the termination signals the
    # parent blocked around fork(). A signal that arrived in the window
    # is delivered here and terminates the child (its default action)
    # instead of being swallowed by an inherited Python handler and lost
    # across exec(). No-op when the parent didn't block.
    try:
        signal.pthread_sigmask(signal.SIG_UNBLOCK,
                               {signal.SIGTERM, signal.SIGINT,
                                signal.SIGHUP, signal.SIGQUIT})
    except (OSError, ValueError):
        pass


def flush_child_streams(*streams) -> None:
    """Flush Python-level stream buffers before os._exit().

    os._exit() does NOT flush Python's I/O buffers, so output a builtin
    wrote to a stream object (rather than via os.write) would be lost.
    Every child exit path must flush the streams its body may have
    written to before calling os._exit(). Streams that are closed,
    fd-less, or not flushable are skipped silently — at child exit there
    is nobody left to report to.
    """
    for stream in streams:
        try:
            stream.flush()
        except (OSError, ValueError, AttributeError):
            pass


def run_child_shell(parent_shell: 'Shell',
                    body: Callable[['Shell'], int],
                    *,
                    norc: bool = True,
                    io_setup: Optional[Callable[[], None]] = None,
                    error_label: str = 'forked child') -> NoReturn:
    """Run the body of a forked substitution child; never returns.

    This is the shared "what every substitution child does" runner,
    called immediately after fork_with_signal_window() returns 0 in
    the child branch. It owns everything generic about being a healthy
    psh child; the caller supplies only the site-specific pieces:

    1. apply_child_signal_policy() — reset handlers, unblock the fork
       window (always with is_shell_process=True: substitution children
       run shell commands, never exec an external binary directly).
    2. io_setup() — the caller's pipe/dup2 plumbing. It runs BEFORE the
       child Shell is built because Shell construction inspects the
       process's fds (interactive detection via isatty(0)); the child
       shell must see the post-plumbing world.
    3. Shell.for_subshell(parent_shell, norc=norc) — the child Shell,
       with state.in_forked_child set so builtins use fd-level I/O.
    4. exit_code = body(child_shell) — what THIS child does. A
       SystemExit (the exit builtin) maps to its code: substitutions
       run in a subshell, so exit must not unwind the parent's stack.
    5. flush_child_streams() over the child shell's streams and the
       process-wide sys streams (see its docstring).
    6. os._exit(exit_code).

    Any other exception escaping steps 1-6 is reported on fd 2 as
    ``psh: {error_label} error: ...`` followed by os._exit(1) — a
    forked child must NEVER return into the parent's call stack, and
    must never fail silently.
    """
    try:
        apply_child_signal_policy(
            parent_shell.interactive_manager.signal_manager,
            parent_shell.state,
            is_shell_process=True,
        )

        if io_setup is not None:
            io_setup()

        # Import here to avoid a circular import (shell -> executor).
        from ..core.exceptions import TopLevelAbort
        from ..shell import Shell
        child_shell = Shell.for_subshell(parent_shell, norc=norc)
        child_shell.state.in_forked_child = True

        try:
            exit_code = body(child_shell)
        except TopLevelAbort as e:
            # A fatal assignment error (readonly/nameref-cycle) aborts the
            # substitution child with its status — it must not unwind past the
            # fork into the parent.
            exit_code = e.status
        except SystemExit as e:
            # exit in a substitution terminates the child, not the parent.
            code = e.code
            exit_code = code if isinstance(code, int) else (0 if code is None else 1)

        flush_child_streams(child_shell.stdout, child_shell.stderr,
                            sys.stdout, sys.stderr)
        os._exit(exit_code)
    except Exception as e:
        # Surface the failure on fd 2 before exiting — a silent
        # bare-except here swallowed real defects in the past. fd 2 is
        # used directly: the child's sys.stderr may be a parent-side
        # capture object that dies with the forked copy.
        try:
            os.write(2, f"psh: {error_label} error: {e}\n"
                     .encode('utf-8', errors='replace'))
        except OSError:
            pass
        os._exit(1)
