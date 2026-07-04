"""Signal handling manager for interactive shell."""
import os
import signal
from typing import TYPE_CHECKING, Callable, Dict

from ..executor.job_control import JobState
from ..utils import SignalNotifier, get_signal_registry
from ..utils.signal_utils import signal_number_to_name
from .base import InteractiveComponent

if TYPE_CHECKING:
    from ..utils.signal_utils import SignalRegistry


class SignalManager(InteractiveComponent):
    """Manages signal handling for the interactive shell."""

    def __init__(self, shell):
        super().__init__(shell)
        self._original_handlers: Dict[int, Callable] = {}

        # Self-pipe for safe SIGCHLD handling
        self._sigchld_notifier = SignalNotifier()

        # Self-pipe for safe SIGWINCH handling (terminal resize)
        self._sigwinch_notifier = SignalNotifier()

        # Guard against reentrancy in notification processing
        self._in_sigchld_processing = False

        # Get global signal registry for tracking (create=True always returns
        # one; the return type is Optional only for the create=False lookup).
        registry = get_signal_registry(create=True)
        assert registry is not None
        self._signal_registry: "SignalRegistry" = registry

    def setup_signal_handlers(self):
        """Configure signal handlers based on shell mode."""
        # Recreate the self-pipes if a previous restore_default_handlers()
        # closed them, so setup → restore → setup (e.g. an embedder running
        # the interactive loop twice on one Shell) keeps working.
        if self._sigchld_notifier.get_fd() < 0:
            self._sigchld_notifier = SignalNotifier()
        if self._sigwinch_notifier.get_fd() < 0:
            self._sigwinch_notifier = SignalNotifier()
        if self.state.is_script_mode:
            self._setup_script_mode_handlers()
        else:
            self._setup_interactive_mode_handlers()

    def _install_handler(self, sig: int, handler, component: str):
        """Install a handler, remembering the ORIGINAL disposition.

        setup_signal_handlers() can legitimately run twice on one shell
        (psh's __main__ installs handlers at startup and the interactive
        loop re-runs setup). ``setdefault`` keeps the disposition saved by
        the FIRST setup, so restore_default_handlers() returns to the
        pre-psh state rather than to one of our own handlers.
        """
        previous = self._signal_registry.register(sig, handler, component)
        self._original_handlers.setdefault(sig, previous)

    def _setup_script_mode_handlers(self):
        """Set up simpler signal handling for script mode."""
        # Script mode: Still check for traps, but use default for job control signals
        # Trappable signals should check for user-defined traps
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
            self._install_handler(sig, self._handle_signal_with_trap_check,
                                  "SignalManager:script")
        # Job control signals: use default in script mode (can be stopped/suspended)
        self._install_handler(signal.SIGTSTP, signal.SIG_DFL, "SignalManager:script")
        self._install_handler(signal.SIGTTOU, signal.SIG_IGN, "SignalManager:script")
        self._install_handler(signal.SIGTTIN, signal.SIG_IGN, "SignalManager:script")
        self._install_handler(signal.SIGCHLD, signal.SIG_DFL, "SignalManager:script")
        self._install_handler(signal.SIGPIPE, signal.SIG_DFL, "SignalManager:script")

    def _setup_interactive_mode_handlers(self):
        """Set up full signal handling for interactive mode."""
        # Store original handlers for restoration and register with tracking
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
            self._install_handler(sig, self._handle_signal_with_trap_check,
                                  "SignalManager:interactive")
        self._install_handler(signal.SIGTSTP, signal.SIG_IGN, "SignalManager:interactive")
        self._install_handler(signal.SIGTTOU, signal.SIG_IGN, "SignalManager:interactive")
        self._install_handler(signal.SIGTTIN, signal.SIG_IGN, "SignalManager:interactive")
        self._install_handler(signal.SIGCHLD, self._handle_sigchld, "SignalManager:interactive")
        self._install_handler(signal.SIGPIPE, signal.SIG_DFL, "SignalManager:interactive")
        self._install_handler(signal.SIGWINCH, self._handle_sigwinch, "SignalManager:interactive")

    def restore_default_handlers(self):
        """Restore default signal handlers."""
        # Restore all saved handlers
        for sig, handler in self._original_handlers.items():
            try:
                self._signal_registry.register(sig, handler, "SignalManager:restore")
            except (OSError, ValueError):
                # Signal may not be valid on this platform
                pass
        self._original_handlers.clear()

        # Clean up signal notifier resources
        if hasattr(self, '_sigchld_notifier'):
            self._sigchld_notifier.close()
        if hasattr(self, '_sigwinch_notifier'):
            self._sigwinch_notifier.close()

    def _handle_signal_with_trap_check(self, signum, frame):
        """Handle signals with trap checking."""
        # Trap handlers are keyed by canonical bare signal name (the same
        # signal_utils table TrapManager canonicalizes specs through).
        signal_name = None
        if hasattr(self.shell, 'trap_manager'):
            signal_name = signal_number_to_name(signum)

        # Check if there's a user-defined trap for this signal
        if signal_name and hasattr(self.shell, 'trap_manager'):
            action = self.shell.trap_manager.get_handler(signal_name)
            if action is not None:
                if action == '':
                    # Signal is ignored
                    return
                else:
                    # Queue the trap: actions run at the next command
                    # boundary, never inside the signal handler (which
                    # could re-enter the parser/executor mid-command).
                    self.shell.trap_manager.queue_trap(signal_name)
                    return

        # No trap set. In a non-interactive shell, match bash's default
        # disposition for the signal; a live interactive REPL keeps its own.
        if signum == signal.SIGINT:
            self._handle_sigint(signum, frame)
        elif self._in_noninteractive_shell():
            # bash never terminates a non-interactive shell on an untrapped
            # SIGQUIT (its default disposition there is "ignore"); every other
            # signal here terminates it — run the EXIT trap, then re-raise.
            if signum != signal.SIGQUIT:
                self._terminate_from_signal(signum)
        else:
            # Interactive REPL: preserve existing re-raise behavior.
            self._signal_registry.register(signum, signal.SIG_DFL, "SignalManager:default")
            os.kill(os.getpid(), signum)

    def _in_noninteractive_shell(self) -> bool:
        """True for a non-interactive whole-shell run (script file, ``-c``
        string, or piped stdin) — everything that runs through
        ``execute_as_main`` rather than the live interactive REPL.

        ``is_script_mode`` covers script files and ``-c``; piped stdin has it
        unset but is still non-interactive, so also treat "not interactive" as
        non-interactive. The interactive REPL (``interactive`` set,
        ``is_script_mode`` clear) is the one case that keeps its own
        fatal-signal behavior (out of scope for the EXIT-trap-on-signal fix).
        """
        return (self.state.is_script_mode
                or not self.state.options.get('interactive', False))

    def _handle_sigint(self, signum, frame):
        """Handle Ctrl-C (SIGINT) default behavior."""
        if self._in_noninteractive_shell():
            # Non-interactive: SIGINT terminates the shell — run the EXIT trap,
            # then re-raise so the parent sees a true signal death.
            self._terminate_from_signal(signum)
        else:
            # In interactive mode, just print a newline - the command loop will handle the rest
            print()
            # The signal will be delivered to the foreground process group
            # which is set in execute_pipeline

    def _terminate_from_signal(self, signum: int) -> None:
        """Die from an untrapped fatal signal the way bash does (non-interactive).

        Runs the EXIT trap exactly once — reusing the idempotent firing in
        TrapManager, the same one ``execute_as_main`` uses on the EOF /
        ``set -e`` / ``exit`` paths, so there is no duplicate logic and no
        double firing. Then flush buffered output (the ``os.kill`` below
        bypasses CPython's atexit flush, which would otherwise drop the
        trap's stdout), restore the signal's default disposition, and
        re-raise it so the parent's wait status is a genuine signal death
        (128+N) rather than a normal exit.

        The signal death ALWAYS wins over whatever the EXIT trap does. In
        particular, an EXIT trap that itself calls ``exit N`` makes the
        ``exit`` builtin raise ``SystemExit``; bash still reports a 128+N
        signal death in that case, so the trap execution is wrapped and any
        ``SystemExit`` (or other exception) escaping the body is swallowed —
        it must not bypass the restore-default + re-raise below. The EXIT
        trap still fires exactly once: TrapManager sets its idempotency flag
        before running the body, so an aborted body is not retried.
        """
        try:
            self.shell.trap_manager.execute_exit_trap()
        except SystemExit:
            # `exit N` inside the EXIT trap: bash keeps the signal death, so
            # discard the trap's exit request and fall through to re-raise.
            pass
        except BaseException:
            # Any other failure in the trap body must likewise not rob the
            # parent of the true signal-death wait status.
            pass
        for stream in (self.state.stdout, self.state.stderr):
            try:
                stream.flush()
            except (OSError, ValueError, AttributeError):
                pass
        self._signal_registry.register(signum, signal.SIG_DFL, "SignalManager:default")
        os.kill(os.getpid(), signum)

    def _handle_sigchld(self, signum, frame):
        """Minimal signal handler - just notify main loop.

        This is async-signal-safe (only calls os.write via SignalNotifier).
        The actual child reaping happens in process_sigchld_notifications().
        """
        self._sigchld_notifier.notify(signal.SIGCHLD)

    def process_sigchld_notifications(self):
        """Process pending SIGCHLD notifications.

        This should be called from the main REPL loop periodically.
        It does the actual job reaping outside of signal handler context,
        which is safe and avoids reentrancy issues.
        """
        # Prevent reentrancy
        if self._in_sigchld_processing:
            return

        self._in_sigchld_processing = True
        try:
            # Drain notification pipe
            notifications = self._sigchld_notifier.drain_notifications()

            if not notifications:
                return

            # Now do the actual child reaping (safe outside signal context)
            while True:
                try:
                    wait_flags = os.WNOHANG
                    if hasattr(os, "WUNTRACED"):
                        wait_flags |= os.WUNTRACED
                    pid, status = os.waitpid(-1, wait_flags)
                    if pid == 0:
                        break

                    job = self.job_manager.get_job_by_pid(pid)
                    if job:
                        job.update_process_status(pid, status)
                        job.update_state()

                        # Check if entire job is stopped
                        if job.state == JobState.STOPPED and job.foreground:
                            # Stopped foreground job - mark as not notified so it will be shown
                            job.notified = False

                            # The foreground job just stopped — take the
                            # terminal back so the shell can show a prompt
                            self.job_manager.transfer_terminal_control(os.getpgrp(), "SignalManager:SIGCHLD")

                except OSError:
                    # No more children
                    break
        finally:
            self._in_sigchld_processing = False

    def _handle_sigwinch(self, signum, frame):
        """Handle terminal resize signal - async-signal-safe.

        Just notifies via self-pipe; actual redraw happens in main loop.
        """
        self._sigwinch_notifier.notify(signal.SIGWINCH)

    def get_sigwinch_fd(self) -> int:
        """Get file descriptor for SIGWINCH notifications.

        The line editor's KeyDecoder multiplexes this with stdin via
        select() and drains it when readable, yielding a Resize event.

        Returns:
            Read file descriptor for SIGWINCH notifications
        """
        return self._sigwinch_notifier.get_fd()

    def ensure_foreground(self):
        """Ensure shell is in its own process group and is foreground."""
        shell_pid = os.getpid()
        shell_pgid = os.getpgrp()

        try:
            # Only set process group if we're not already the leader
            if shell_pgid != shell_pid:
                os.setpgid(0, shell_pid)

            # Make shell the foreground process group on the terminal
            self.job_manager.transfer_terminal_control(shell_pid, "SignalManager:ensure_foreground")
        except OSError:
            # Not a terminal or already set
            pass

    def reset_child_signals(self):
        """Reset all signals to default in child process.

        This should be called in all forked child processes to ensure
        they don't inherit the shell's custom signal handlers. The signal
        list and the per-signal disposition policy (SIG_DFL, or SIG_IGN
        for a ``trap '' SIG`` ignore that must survive exec) live in
        :meth:`exec_image_dispositions` — the single source of truth
        shared with the ``exec`` builtin's direct-exec path.

        This method is platform-safe and will skip signals not available
        on the current platform.
        """
        for sig, disposition in self.exec_image_dispositions():
            try:
                signal.signal(sig, disposition)
            except (OSError, ValueError):
                # Signal not available on this platform
                pass

    def exec_image_dispositions(self):
        """The ``(signal, disposition)`` pairs an exec'd image must see.

        The single source of truth for reconciling the shell's Python-level
        signal handling with what an external program should inherit —
        shared by :meth:`reset_child_signals` (forked children) and
        :meth:`prepare_signals_for_exec` (the ``exec`` builtin replacing
        the shell directly), so both exec paths agree.

        A signal IGNORED by trap (`trap '' SIG`) must STAY ignored in the
        child and across exec — POSIX: exec preserves SIG_IGN for signals
        set to ignore. psh implements managed-signal traps (INT/TERM/HUP/
        QUIT, ...) with Python-level handlers, which the kernel resets to
        SIG_DFL on exec — so the empty-action IGNORE case must be
        materialized as a real SIG_IGN first (`trap "" INT; bash -c
        'trap -p INT'` printed nothing before this reconciliation). Only
        the empty-action IGNORE case inherits; a signal trapped WITH an
        action resets to default (the handler can't cross exec).

        SIGXFSZ is in the list because CPython itself sets it to SIG_IGN
        at interpreter startup — without an explicit reset, every program
        psh execs inherits an ignored SIGXFSZ that a bash-launched program
        would not (probe: `bash -c 'trap -p'` under psh showed
        `trap -- '' SIGXFSZ`).
        """
        signals_to_reset = [
            signal.SIGINT,
            signal.SIGQUIT,
            # SIGTERM/SIGHUP: the shell installs Python-level trap-check
            # handlers for these; a child must not inherit them (bash
            # resets non-ignored signal dispositions in children, and an
            # inherited Python handler could swallow a signal delivered
            # before exec).
            signal.SIGTERM,
            signal.SIGHUP,
            signal.SIGTSTP,
            signal.SIGTTOU,
            signal.SIGTTIN,
            signal.SIGCHLD,
            signal.SIGPIPE,
            signal.SIGWINCH,
        ]
        if hasattr(signal, 'SIGXFSZ'):
            signals_to_reset.append(signal.SIGXFSZ)

        trap_manager = getattr(self.shell, 'trap_manager', None)
        pairs = []
        for sig in signals_to_reset:
            disposition = signal.SIG_DFL
            if trap_manager is not None:
                name = signal_number_to_name(sig)
                if name is not None and trap_manager.get_handler(name) == '':
                    disposition = signal.SIG_IGN
            pairs.append((sig, disposition))
        return pairs

    def prepare_signals_for_exec(self):
        """Apply the exec-image dispositions to the CURRENT process.

        Used by the ``exec`` builtin just before ``os.execvpe`` replaces
        the shell: the same keep-SIG_IGN-for-``trap ''`` / default-
        everything-else reconciliation that forked children get from
        :meth:`reset_child_signals` (the v0.593 fix covered only the
        fork+exec path; a DIRECT ``trap "" INT; exec cmd`` still lost the
        ignore because the kernel reset psh's Python-level INT handler to
        SIG_DFL on exec).

        Returns a ``restore()`` callable that reinstates the saved
        dispositions — the exec-failed path (127/126) must put the
        surviving shell's handlers back.
        """
        saved = []
        for sig, disposition in self.exec_image_dispositions():
            try:
                previous = signal.getsignal(sig)
                signal.signal(sig, disposition)
            except (OSError, ValueError):
                # Signal not available on this platform
                continue
            if previous is not None:
                # getsignal() returns None for a handler not installed
                # from Python — that disposition can't be reinstated, so
                # it is (rarely) left reconciled on the failure path.
                saved.append((sig, previous))

        def restore():
            for sig, previous in saved:
                try:
                    signal.signal(sig, previous)
                except (OSError, ValueError):
                    pass

        return restore
