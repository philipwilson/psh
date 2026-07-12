"""Becoming a healthy psh child process.

This module is the one-stop chapter for what every forked psh child has
in common, separated from what any particular child *does*:

- fork_with_signal_window() — how to fork (termination signals blocked
  across the window; the parent-side half of the signal policy).
- apply_child_signal_policy() — the child-side half: reset handlers to
  SIG_DFL, then unblock.
- map_child_exception() — the ONE taxonomy: how a control-flow/exit
  exception at a forked child's top becomes the child's exit code
  (TopLevelAbort/FunctionReturn/LoopBreak/LoopContinue/SystemExit). Every
  fork site catches CHILD_EXIT_EXCEPTIONS and delegates here, so the
  mapping (including SystemExit(None) → 0) lives in one place.
- run_child_body() — the shared MIDDLE of every child that builds a child
  Shell: fork-child flags, trap-disposition sync/drop, errexit seeding,
  body execution via map_child_exception, and the child's EXIT trap.
  Shared by run_child_shell (substitutions) and SubshellExecutor's
  foreground-subshell body.
- run_child_shell() — the shared child-body runner for substitution
  children (command substitution, process substitution): signal policy,
  fd plumbing hook, child Shell construction, run_child_body, stream
  flushing, os._exit(). The caller supplies only the two site-specific
  pieces: the fd plumbing (io_setup) and the body (what this child runs).
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

from ..core.exceptions import (
    FunctionReturn,
    LoopBreak,
    LoopContinue,
    TopLevelAbort,
)

if TYPE_CHECKING:
    from ..shell import Shell

# The control-flow / exit exceptions a forked child's body may raise at its
# top. Caught as a group at every fork site; the code mapping lives once in
# map_child_exception (below). KeyboardInterrupt (→130) and unexpected
# Exceptions are deliberately NOT here — only the launcher's leaf-child path
# arms them (it may exec an external binary).
CHILD_EXIT_EXCEPTIONS = (
    TopLevelAbort, FunctionReturn, LoopBreak, LoopContinue, SystemExit,
)


def map_child_exception(exc: BaseException) -> int:
    """Map a control-flow / exit exception at a forked child's top to the
    child's exit code — the ONE taxonomy every fork site shares.

    A forked psh child is a process boundary: ``break``/``continue``/``return``
    cannot reach the loop/function they name (those live in the parent's
    stack, in the un-forked copy), and ``exit`` must terminate only this
    child. So each of these exceptions ends the child with a status:

    - TopLevelAbort (a fatal assignment/expansion discard) → its ``.status``.
    - FunctionReturn (``return`` in an inherited function/sourced context) →
      its ``.exit_code`` (bash: ``f(){ x=$(return 3); }`` leaves ``$?``=3).
    - LoopBreak/LoopContinue (a break/continue escaping the child's own
      loops) → its ``.exit_status``, or 0 (bash: ``x=$(break 0)`` in a loop
      leaves ``$?``=1).
    - SystemExit (the ``exit`` builtin) → its integer code; ``exit`` with no
      argument, i.e. ``SystemExit(None)``, → 0 (Python's own convention for a
      bare ``sys.exit()``); a non-int, non-None code → 1.

    Only the five CHILD_EXIT_EXCEPTIONS are handled; anything else re-raises
    (callers catch exactly that group before calling this). KeyboardInterrupt
    (→130) and unexpected Exceptions stay caller-local — see the module note.
    """
    if isinstance(exc, TopLevelAbort):
        return exc.status
    if isinstance(exc, FunctionReturn):
        return exc.exit_code
    if isinstance(exc, (LoopBreak, LoopContinue)):
        return exc.exit_status or 0
    if isinstance(exc, SystemExit):
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    raise exc


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


def run_background_shell_child(shell: 'Shell',
                               body: Callable[[], int]) -> int:
    """Run a backgrounded compound body with full trap discipline.

    The shared "what every backgrounded shell-process child does" wrapper,
    called from inside the ProcessLauncher child (the bg execute_fn), after
    apply_child_signal_policy() has reset handlers and the child Shell is
    built. Used by every in-process backgrounded compound —  ``( ... ) &``,
    ``{ ...; } &`` and a backgrounded function call — so the four background
    trap symptoms are fixed in one place, mirroring the main shell:

    1. enter_subshell_trap_environment() — a PARENT trap does not fire in
       the child (non-ignored inherited traps reset to default); then
       install_child_trap_handlers(background=True) re-arms the managed
       (INT/TERM/HUP/QUIT) handlers so a body-set ``trap`` for one of them
       actually fires, and marks this a job-control-off async job (untrapped
       INT/QUIT are ignored).
    2. exit_code = body() — control-flow exceptions map to a status exactly
       as run_child_shell / ProcessLauncher do (a subshell boundary; break/
       return cannot cross the fork).
    3. finally: pump any queued signal traps, then run the EXIT trap. bash
       runs a backgrounded compound's EXIT trap on normal completion; the
       untrapped-fatal-signal path runs it instead via
       _terminate_from_signal (both idempotent — TrapManager guards it).

    Returns the exit code (this runs inside execute_fn, which returns to
    ProcessLauncher._child_setup_and_exec — NOT a NoReturn context).
    """
    shell.trap_manager.enter_subshell_trap_environment()
    shell.interactive_manager.signal_manager.install_child_trap_handlers(
        background=True)

    exit_code = 0
    try:
        exit_code = body()
        if not isinstance(exit_code, int):
            exit_code = 0 if exit_code else 1
    except CHILD_EXIT_EXCEPTIONS as e:
        # A control-flow/exit exception at the body's top: subshell boundary,
        # so break/return cannot cross the fork; map via the shared taxonomy.
        exit_code = map_child_exception(e)
    finally:
        # A managed-signal trap queued while the body ran (e.g. after the
        # last statement) still fires; then the EXIT trap runs on the way
        # out, as it does for the main shell and a foreground subshell.
        try:
            shell.trap_manager.run_pending_traps()
        except SystemExit as e:
            code = e.code
            if isinstance(code, int):
                exit_code = code
        except Exception:
            pass
        try:
            shell.trap_manager.execute_exit_trap()
        except SystemExit as e:
            code = e.code
            if isinstance(code, int):
                exit_code = code
        except Exception:
            pass
    return exit_code


def run_child_body(child_shell: 'Shell',
                   body: Callable[['Shell'], int],
                   *,
                   errexit_suppress: int = 0,
                   in_substitution: bool = False,
                   drop_traps: bool = False,
                   reset_errexit: bool = False,
                   loop_seed: Optional[int] = None) -> int:
    """Run a forked shell-process child's body and map its outcome to an
    exit code — the shared MIDDLE of every child that builds a child Shell.

    The caller has already built *child_shell* (``Shell.for_subshell``) and
    plumbed its streams; this runner performs the steps a foreground
    subshell (``SubshellExecutor``) and a substitution child
    (``run_child_shell``) do identically, in the order both require:

    1. mark the forked child (``state.in_forked_child``); for a substitution
       child (``in_substitution``) also suppress the abnormal-termination
       diagnostic (Terminated / Segmentation fault …, which bash omits
       inside substitutions) and, with ``loop_seed``, keep the enclosing
       loop scope visible — so ``x=$(break)`` in a loop is SILENT, though
       the break still cannot cross the fork.
    2. ``sync_forked_child_dispositions()`` — this process IS a fresh fork,
       so the parent's non-ignored traps take the default OS action and
       ignored ('') ones stay ignored; done BEFORE any drop. With
       ``drop_traps`` the parent's inherited-for-listing trap entries are
       then dropped (a process-substitution child never lists them:
       ``trap A USR1; cat <(trap)`` prints nothing).
    3. seed the errexit SUPPRESSION count of the forking context (an
       if/while condition, non-final ``&&``/``||`` member, ``!``) so
       ``set -e`` inside the body cannot re-arm aborting — in bash the
       child is a memory copy. With ``reset_errexit`` the errexit OPTION
       itself is additionally cleared (bash resets ``set -e`` in
       command-substitution children, unlike ``( )`` subshells and process
       substitutions which inherit it).
    4. ``exit_code = body(child_shell)``; a control-flow/exit exception at
       its top maps via ``map_child_exception`` — this is a subshell
       boundary, so ``break``/``return`` cannot cross and ``exit``
       terminates only this child.
    5. the child's own EXIT trap if the body set one (bash:
       ``x=$(trap 'echo bye' EXIT)`` captures "bye"). Idempotent — the exit
       builtin's SystemExit path already fired it; inherited EXIT traps
       never fire (see ``TrapManager.get_handler``). ``exit`` inside the
       EXIT trap sets the child's status.

    Returns the exit code. The CALLER owns the surrounding fork lifecycle
    (signal policy, ``Shell`` construction, stream flush, ``os._exit`` vs
    return to the launcher) — those differ between ``run_child_shell``
    (NoReturn) and the foreground-subshell body (returns to ProcessLauncher,
    which flushes and exits).
    """
    child_shell.state.in_forked_child = True
    if in_substitution:
        child_shell.state.in_substitution = True
    if loop_seed is not None:
        child_shell._loop_depth_seed = loop_seed
    child_shell.trap_manager.sync_forked_child_dispositions()
    if drop_traps:
        child_shell.trap_manager.drop_inherited_traps()
    child_shell._errexit_suppress_seed = errexit_suppress
    if reset_errexit:
        child_shell.state.options['errexit'] = False

    try:
        exit_code = body(child_shell)
    except CHILD_EXIT_EXCEPTIONS as e:
        exit_code = map_child_exception(e)

    try:
        child_shell.trap_manager.execute_exit_trap()
    except SystemExit as e:
        exit_code = map_child_exception(e)
    except Exception:
        pass

    return exit_code


def run_child_shell(parent_shell: 'Shell',
                    body: Callable[['Shell'], int],
                    *,
                    norc: bool = True,
                    io_setup: Optional[Callable[[], None]] = None,
                    inherit_traps: bool = True,
                    reset_errexit: bool = False,
                    error_label: str = 'forked child') -> NoReturn:
    """Run the body of a forked substitution child; never returns.

    This is the shared "what every substitution child does" runner,
    called immediately after fork_with_signal_window() returns 0 in
    the child branch. It owns the fork-lifecycle pieces unique to a
    substitution child and delegates the shared middle to run_child_body:

    1. apply_child_signal_policy() — reset handlers, unblock the fork
       window (always with is_shell_process=True: substitution children
       run shell commands, never exec an external binary directly).
    2. io_setup() — the caller's pipe/dup2 plumbing. It runs BEFORE the
       child Shell is built because Shell construction inspects the
       process's fds (interactive detection via isatty(0)); the child
       shell must see the post-plumbing world.
    3. Shell.for_subshell(parent_shell, norc=norc) — the child Shell.
    4. run_child_body(...) with in_substitution=True — the shared middle:
       trap-disposition sync (drop_traps=not inherit_traps: process-
       substitution children never list inherited traps, unlike the
       command-substitution POSIX saved=$(trap) idiom), errexit-suppression
       seeding from the forking context (+ reset_errexit clearing the
       option for command substitution), body execution with the shared
       exception→status taxonomy, and the child's own EXIT trap. The
       loop-scope and errexit-suppression seeds come from the parent's
       current executor.
    5. flush_child_streams() over the child shell's streams and the
       process-wide sys streams (see its docstring).
    6. os._exit(exit_code).

    Any other exception escaping steps 1-5 is reported on fd 2 as
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
        from ..shell import Shell
        child_shell = Shell.for_subshell(parent_shell, norc=norc)

        # The loop-scope and errexit-suppression seeds come from the parent's
        # current executor (None only for an in-process child Shell built
        # without an active executor, e.g. the env builtin's).
        parent_executor = parent_shell._current_executor
        loop_seed = (parent_executor.context.loop_depth
                     if parent_executor is not None else None)
        errexit_suppress = (parent_executor.context.errexit_suppress
                            if parent_executor is not None else 0)

        exit_code = run_child_body(
            child_shell, body,
            errexit_suppress=errexit_suppress,
            in_substitution=True,
            drop_traps=not inherit_traps,
            reset_errexit=reset_errexit,
            loop_seed=loop_seed,
        )

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
