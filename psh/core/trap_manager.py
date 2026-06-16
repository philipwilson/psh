"""Trap management for PSH shell."""
import signal
from typing import TYPE_CHECKING, List, Optional

from ..utils.signal_utils import list_all_signals

if TYPE_CHECKING:
    from ..shell import Shell

class TrapManager:
    """Manages trap handlers for the shell."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Map signal names to numbers
        self.signal_map = {
            'HUP': signal.SIGHUP,
            'INT': signal.SIGINT,
            'QUIT': signal.SIGQUIT,
            'TERM': signal.SIGTERM,
            'USR1': signal.SIGUSR1,
            'USR2': signal.SIGUSR2,
            'ALRM': signal.SIGALRM,
            'CHLD': signal.SIGCHLD,
            'CONT': signal.SIGCONT,
            'TSTP': signal.SIGTSTP,
            'TTIN': signal.SIGTTIN,
            'TTOU': signal.SIGTTOU,
            'PIPE': signal.SIGPIPE,
            # Special pseudo-signals
            'EXIT': 'EXIT',   # Shell exit
            'DEBUG': 'DEBUG', # Before each command (bash extension)
            'ERR': 'ERR',     # Command error (bash extension)
        }

        # Reverse mapping for display purposes
        self.signal_names = {v: k for k, v in self.signal_map.items() if isinstance(v, int)}

        # Signal traps queued by the (async-signal-unsafe) Python handler;
        # executed at command boundaries via run_pending_traps(), so trap
        # actions never re-enter the parser/executor mid-command.
        self.pending_traps: list = []
        # Re-entrancy guard: a DEBUG/ERR action must not fire DEBUG/ERR
        # traps for its own commands.
        self._in_debug_err_trap = False

        # Add numbered mappings for every signal the platform supports
        # (no handler-swapping probe needed).
        for signum in sorted(int(s) for s in signal.valid_signals()):
            if str(signum) not in self.signal_map:
                self.signal_map[str(signum)] = signum
            if signum not in self.signal_names:
                self.signal_names[signum] = str(signum)

    def set_trap(self, action: str, signals: List[str]) -> int:
        """Set trap handler for signals.

        Args:
            action: Command string to execute, or empty string to ignore, or '-' to reset
            signals: List of signal names/numbers

        Returns:
            Exit code (0 for success, 1 for error)
        """
        for signal_spec in signals:
            signal_spec = signal_spec.upper()

            # Validate signal
            if signal_spec not in self.signal_map:
                try:
                    # Try as number
                    signal_num = int(signal_spec)
                    if signal_num not in self.signal_names:
                        print(f"trap: {signal_spec}: invalid signal specification", file=self.state.stderr)
                        return 1
                    signal_spec = str(signal_num)
                except ValueError:
                    print(f"trap: {signal_spec}: invalid signal specification", file=self.state.stderr)
                    return 1

            if action == '-':
                # Reset to default
                self._reset_trap(signal_spec)
            elif action == '':
                # Ignore signal
                self._ignore_signal(signal_spec)
            else:
                # Set trap action
                self._set_signal_handler(signal_spec, action)

        return 0

    # Signals whose OS handlers psh manages elsewhere (SignalManager's
    # trap-checking handlers and job-control bookkeeping). For these, traps
    # work through the existing handlers; we must not overwrite them.
    _MANAGED_SIGNALS = frozenset({
        signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT,
        signal.SIGCHLD, signal.SIGTSTP, signal.SIGTTOU, signal.SIGTTIN,
        getattr(signal, 'SIGWINCH', None),
    }) - {None}

    def _signum(self, signal_spec: str):
        """The OS signal number for a trap spec, or None for pseudo-signals."""
        num = self.signal_map.get(signal_spec)
        if isinstance(num, int):
            return num
        try:
            return int(signal_spec)
        except (TypeError, ValueError):
            return None

    def _set_signal_handler(self, signal_spec: str, action: str):
        """Set a signal handler for the given signal."""
        # Special handling for pseudo-signals
        if signal_spec in ('EXIT', 'DEBUG', 'ERR'):
            self.state.trap_handlers[signal_spec] = action
            return

        self.state.trap_handlers[signal_spec] = action

        # Signals outside the managed set (USR1, USR2, ALRM, ...) have no
        # psh handler installed by default — the shell would simply die on
        # delivery. Install a queueing handler: the trap action runs at the
        # next command boundary (run_pending_traps), like bash.
        signum = self._signum(signal_spec)
        if signum is not None and signum not in self._MANAGED_SIGNALS:
            spec = signal_spec

            def _queueing_handler(_signum, _frame, _spec=spec):
                self.queue_trap(_spec)

            try:
                signal.signal(signum, _queueing_handler)
            except (OSError, ValueError):
                pass  # uncatchable (KILL/STOP) or not in main thread

    def _ignore_signal(self, signal_spec: str):
        """Set signal to be ignored."""
        # Special handling for pseudo-signals
        if signal_spec in ('EXIT', 'DEBUG', 'ERR'):
            self.state.trap_handlers[signal_spec] = ''
            return

        self.state.trap_handlers[signal_spec] = ''
        signum = self._signum(signal_spec)
        if signum is not None and signum not in self._MANAGED_SIGNALS:
            try:
                signal.signal(signum, signal.SIG_IGN)
            except (OSError, ValueError):
                pass

    def _reset_trap(self, signal_spec: str):
        """Reset signal to default behavior."""
        # Special handling for pseudo-signals
        if signal_spec in ('EXIT', 'DEBUG', 'ERR'):
            if signal_spec in self.state.trap_handlers:
                del self.state.trap_handlers[signal_spec]
            return

        if signal_spec in self.state.trap_handlers:
            del self.state.trap_handlers[signal_spec]
        signum = self._signum(signal_spec)
        if signum is not None and signum not in self._MANAGED_SIGNALS:
            try:
                signal.signal(signum, signal.SIG_DFL)
            except (OSError, ValueError):
                pass

    def remove_trap(self, signals: List[str]) -> int:
        """Remove trap handlers (same as set_trap with action '-')."""
        return self.set_trap('-', signals)

    def get_handler(self, signal_spec: str) -> Optional[str]:
        """Return the trap action set for a signal.

        Returns None if no trap is set; the empty string means the signal is
        ignored; otherwise the command string to run. Public accessor so callers
        need not reach into ``state.trap_handlers``.
        """
        return self.state.trap_handlers.get(signal_spec)

    def execute_trap(self, signal_name: str):
        """Execute trap handler for given signal.

        Args:
            signal_name: Name of the signal that was received
        """
        action = self.state.trap_handlers.get(signal_name)
        if not action:
            # No trap set, or empty action ('' = signal ignored)
            return

        # Execute the trap command in the current shell context
        try:
            # Save current exit code
            saved_exit_code = self.state.last_exit_code

            # Execute trap command. ERR and DEBUG fire synchronously, tied to a
            # command, so bash runs their actions with $LINENO = that command's
            # current line. EXIT and signal traps fire asynchronously (no
            # invoking command) and bash runs them with $LINENO counting from
            # the action's own line 1. See Shell.run_command's base_line.
            if signal_name in ('ERR', 'DEBUG'):
                base_line = self.state.scope_manager.get_current_line_number()
            else:
                base_line = 1
            self.shell.run_command(action, add_to_history=False,
                                   base_line=base_line)

            # For most signals, restore the exit code
            # EXIT trap should preserve the exit code it sets
            if signal_name != 'EXIT':
                self.state.last_exit_code = saved_exit_code

        except Exception as e:
            # Trap execution failed, but don't crash the shell
            print(f"trap: error executing trap for {signal_name}: {e}", file=self.state.stderr)

    def list_signals(self) -> str:
        """Render the full signal listing for `trap -l`.

        Identical to `kill -l` (bash): real signals only, NUM) SIGNAME in
        bash's column layout. Shares the single source of truth in
        psh.utils.signal_utils so the two listings can never drift apart.
        """
        return list_all_signals()

    def show_traps(self, signals: Optional[List[str]] = None) -> str:
        """Show current trap settings.

        Args:
            signals: Specific signals to show, or None for all

        Returns:
            Formatted trap display string
        """
        if signals is None:
            # Show all traps
            signals_to_show = list(self.state.trap_handlers.keys())
        else:
            # Show specific signals
            signals_to_show = []
            for sig in signals:
                sig = sig.upper()
                if sig in self.signal_map:
                    signals_to_show.append(sig)
                else:
                    try:
                        signal_num = int(sig)
                        if signal_num in self.signal_names:
                            signals_to_show.append(str(signal_num))
                    except ValueError:
                        pass

        output_lines = []
        for signal_name in sorted(signals_to_show):
            if signal_name in self.state.trap_handlers:
                action = self.state.trap_handlers[signal_name]
                if action == '':
                    action_display = "''"
                else:
                    # Quote the action for display
                    action_display = f"'{action}'"
                display_name = self._canonical_trap_name(signal_name)
                output_lines.append(f"trap -- {action_display} {display_name}")

        return '\n'.join(output_lines)

    # Pseudo-signals are printed WITHOUT a SIG prefix (bash); real signals
    # are printed with their canonical SIG-prefixed name.
    _PSEUDO_SIGNALS = frozenset({'EXIT', 'ERR', 'DEBUG', 'RETURN'})

    def _canonical_trap_name(self, signal_name: str) -> str:
        """Canonical name for `trap -p` output (bash-compatible).

        Real signals get the ``SIG`` prefix (``TERM`` -> ``SIGTERM``);
        pseudo-signals (EXIT/ERR/DEBUG/RETURN) are printed bare.
        """
        name = signal_name.upper()
        if name in self._PSEUDO_SIGNALS:
            return name
        # A numerically-keyed trap (e.g. set via `trap ... 15`) resolves to
        # its canonical signal name (bash: SIGTERM, not SIG15).
        try:
            num = int(name)
        except ValueError:
            pass
        else:
            name = self.signal_names.get(num, name)
        if name.startswith('SIG'):
            return name
        return f"SIG{name}"

    def execute_exit_trap(self):
        """Execute EXIT trap if set.

        Idempotent: the EXIT trap fires at most once per shell, no matter
        how many exit paths reach here (explicit ``exit`` builtin, end of a
        ``-c`` string, end of a script, end of piped stdin).
        """
        if getattr(self, '_exit_trap_executed', False):
            return
        if 'EXIT' in self.state.trap_handlers:
            self._exit_trap_executed = True
            self.execute_trap('EXIT')

    def execute_debug_trap(self):
        """Execute DEBUG trap if set (called before each simple command)."""
        if self._in_debug_err_trap:
            return
        if self.state.trap_handlers.get('DEBUG'):
            self._in_debug_err_trap = True
            try:
                self.execute_trap('DEBUG')
            finally:
                self._in_debug_err_trap = False

    def execute_err_trap(self, exit_code: int):
        """Execute ERR trap if set and command failed.

        Args:
            exit_code: Exit code of the failed command
        """
        if self._in_debug_err_trap:
            return
        if self.state.trap_handlers.get('ERR') and exit_code != 0:
            self._in_debug_err_trap = True
            try:
                self.execute_trap('ERR')
            finally:
                self._in_debug_err_trap = False

    def queue_trap(self, signal_name: str):
        """Queue a signal trap from handler context (async-signal path)."""
        self.pending_traps.append(signal_name)

    def run_pending_traps(self):
        """Execute queued signal traps (called at command boundaries)."""
        while self.pending_traps:
            self.execute_trap(self.pending_traps.pop(0))
