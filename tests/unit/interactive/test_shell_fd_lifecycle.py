"""Regression pins for the Shell fd lifecycle (reappraisal #18 Tier-3, T3-4).

The SignalManager's SIGCHLD/SIGWINCH self-pipes were once allocated eagerly in
*every* Shell (two ``os.pipe()``s = 4 fds/Shell), reclaimed only by cyclic GC —
so a burst of transient Shell instances (tests, the ``env`` builtin's child,
subshell helpers) held a sawtooth of self-pipe fds until collection. They are
now:

* **lazy** — opened only when a shell installs interactive signal handlers
  (``setup_signal_handlers`` → ``_setup_interactive_mode_handlers``); a
  transient/non-interactive shell opens none; and
* **explicitly releasable** — ``Shell.close()`` (and the context-manager
  protocol) frees them immediately instead of waiting for GC.

These tests pin both properties by counting the process's open fds. They run
purely in-process and touch no global signal dispositions (notifiers are forced
open via the private ``_ensure_*`` helpers, exactly what interactive setup does,
minus the ``signal.signal`` calls), so they need no ``serial`` marker.
"""

import gc
import os

import pytest

from psh.shell import Shell


def _fd_count() -> int:
    """Portable count of this process's open fds.

    macOS and Linux both expose ``/dev/fd``; Linux also has ``/proc/self/fd``.
    ``os.listdir`` opens (and closes) one directory fd internally, which appears
    in the listing while the call runs — but that contribution is identical on
    every call, so it cancels out of the *deltas* these tests assert on.
    """
    for path in ('/dev/fd', '/proc/self/fd'):
        try:
            return len(os.listdir(path))
        except OSError:
            continue
    pytest.skip("no /dev/fd or /proc/self/fd on this platform")
    return 0  # unreachable; keeps type checkers happy


def test_transient_shells_do_not_leak_notifier_fds():
    """200 non-interactive Shells add ~0 fds — lazy allocation.

    Under the old eager allocation this was 4 fds/Shell (= 800 for 200 held
    references). Lazy allocation opens the self-pipes only for a shell that
    installs interactive signal handlers, so a batch of transient shells adds
    essentially nothing.
    """
    gc.collect()
    base = _fd_count()
    shells = [Shell(norc=True) for _ in range(200)]
    try:
        gc.collect()
        held = _fd_count()
        delta = held - base
        # Eager alloc would be ~800 here; assert far below that with slack for
        # any incidental fds so the pin is robust but still catches a regression
        # to eager allocation decisively.
        assert delta < 50, (
            f"200 transient Shells added {delta} fds "
            f"({delta / 200:.3f}/Shell); lazy allocation should add ~0")
    finally:
        for shell in shells:
            shell.close()
        shells.clear()
        gc.collect()


def test_close_releases_allocated_notifier_fds():
    """A shell that DID allocate the self-pipes releases them on close().

    Also asserts close() is idempotent and that exactly the two self-pipes
    (4 fds) are what gets allocated/freed.
    """
    gc.collect()
    base = _fd_count()
    shell = Shell(norc=True)
    sm = shell.interactive_manager.signal_manager
    # Force allocation the way _setup_interactive_mode_handlers does, without
    # perturbing the process's global signal dispositions.
    sm._ensure_sigchld_notifier()
    sm._ensure_sigwinch_notifier()
    allocated = _fd_count()
    assert allocated - base == 4, (
        f"two self-pipes should add 4 fds, got {allocated - base}")

    shell.close()
    gc.collect()
    assert _fd_count() == base, "close() must release the notifier fds"

    # Idempotent: a second close() is a harmless no-op.
    shell.close()
    assert _fd_count() == base


def test_context_manager_closes_shell_on_exit():
    """``with Shell(...) as shell:`` frees the shell's fds at block exit."""
    gc.collect()
    base = _fd_count()
    with Shell(norc=True) as shell:
        sm = shell.interactive_manager.signal_manager
        sm._ensure_sigchld_notifier()
        sm._ensure_sigwinch_notifier()
        assert _fd_count() - base == 4
    gc.collect()
    assert _fd_count() == base, "__exit__ should close the shell and free fds"


def test_closed_shell_still_usable():
    """close() only frees re-creatable resources — the shell keeps working.

    Signal-notifier self-pipes are re-allocated on demand, so a shell that has
    been closed can still run commands (and, if it later installs interactive
    handlers, re-open its self-pipes).
    """
    shell = Shell(norc=True)
    shell.close()
    # Running after close must not crash.
    assert shell.run_command("true") == 0
    assert shell.run_command("false") == 1


def test_env_builtin_keeps_fd_count_bounded():
    """Many ``env CMD`` invocations don't accumulate fds.

    ``env`` runs each command in a nested in-process child Shell; that child is
    now closed after the run, and (being non-interactive) allocates no notifier
    fds in the first place. Either way the process fd count stays flat.
    """
    shell = Shell(norc=True)
    try:
        gc.collect()
        base = _fd_count()
        peak = base
        for _ in range(100):
            assert shell.run_command("env true") == 0
            peak = max(peak, _fd_count())
        gc.collect()
        after = _fd_count()
        assert after - base < 40, (
            f"100 env invocations leaked {after - base} fds (peak +{peak - base})")
    finally:
        shell.close()
