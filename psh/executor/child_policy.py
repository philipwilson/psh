"""Unified child process signal policy.

Every fork path must call apply_child_signal_policy() immediately after
os.fork() in the child branch. This ensures consistent signal handling
across ProcessLauncher, command substitution, process substitution, and
redirect process substitution forks.
"""

import signal


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
