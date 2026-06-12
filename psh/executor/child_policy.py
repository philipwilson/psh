"""Unified child process signal policy.

Every fork path must fork via fork_with_signal_window() and call
apply_child_signal_policy() immediately after the fork in the child
branch. This ensures consistent signal handling across ProcessLauncher,
command substitution, and process substitution forks: the parent-side
half (block termination signals across the fork window) lives in
fork_with_signal_window(); the child-side half (reset handlers, then
unblock) lives in apply_child_signal_policy().
"""

import os
import signal


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
