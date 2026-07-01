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
        # The first trap modification in a subshell-style child drops ALL
        # of the parent's inherited-for-listing entries (bash probe:
        # `trap A USR1; (trap - TERM; trap)` lists nothing). Ignored ('')
        # traps are genuinely in effect, not inherited, and stay.
        self.drop_inherited_traps()

        for signal_spec in signals:
            # Normalize to one canonical key (SIGINT / 2 / INT all -> INT) so
            # every path — storage here and the name-keyed SignalManager
            # dispatch — agrees on the key.
            canonical = self._canonical_signal_key(signal_spec)
            if canonical is None:
                print(f"trap: {signal_spec}: invalid signal specification",
                      file=self.state.stderr)
                return 1
            signal_spec = canonical

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

    def _canonical_signal_key(self, signal_spec: str) -> Optional[str]:
        """Canonical ``trap_handlers`` key for a user signal spec.

        Resolves a ``SIG``-prefixed name (``SIGINT``) and a signal number
        (``2``) to the bare signal name (``INT``) — the single key every
        path uses, so a trap set as ``SIGINT`` or ``2`` is found by the
        name-keyed dispatch in SignalManager (which the raw-spec keying used
        to miss: ``trap … SIGINT`` was rejected and ``trap … 2`` for a
        managed signal never fired). The real pseudo-signals EXIT/DEBUG/ERR
        pass through unchanged (RETURN is deliberately not accepted, matching
        bash here). Returns ``None`` for a spec that is not a valid signal.
        """
        spec = signal_spec.upper()
        if spec in ('EXIT', 'DEBUG', 'ERR'):
            return spec
        if spec.startswith('SIG') and len(spec) > 3:
            spec = spec[3:]
        signum = self._signum(spec)
        if signum is None or signum not in self.signal_names:
            return None
        return self.signal_names[signum]

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

    def drop_inherited_traps(self) -> None:
        """Discard parent traps kept only for listing (see ShellState.adopt).

        Called by set_trap (bash: a subshell's first trap modification drops
        them all) and for process-substitution children, which never list
        them (bash probe: `trap A USR1; cat <(trap)` prints nothing).
        """
        for name in self.state.inherited_traps:
            self.state.trap_handlers.pop(name, None)
        self.state.inherited_traps.clear()

    def sync_forked_child_dispositions(self) -> None:
        """Align OS signal dispositions with adopted trap state after a fork.

        Ignored ('') traps stay SIG_IGN — bash keeps ignored signals ignored
        in subshell-style children. A parent's non-ignored trap is reset to
        the DEFAULT action: the fork copied the parent's queueing handler,
        which would otherwise swallow the signal (bash: the child dies).
        Managed signals were already reset by apply_child_signal_policy.

        Called EXPLICITLY by the fork sites (SubshellExecutor's forked
        children and child_policy.run_child_shell) right after the child
        Shell is built — forked-ness must never be inferred (a pid check
        also matches an IN-PROCESS child built inside a forked child, e.g.
        the env builtin's child Shell in a subshell, and would clobber the
        enclosing shell's live handlers process-wide). An in-process child
        must NOT call this: no fork happened, and the hosting process's
        dispositions belong to the enclosing shell.
        """
        for name, action in self.state.trap_handlers.items():
            signum = self._signum(name)
            if signum is None:
                continue  # pseudo-signals (EXIT/DEBUG/ERR): no OS handler
            try:
                if action == '':
                    signal.signal(signum, signal.SIG_IGN)
                elif (name in self.state.inherited_traps
                      and signum not in self._MANAGED_SIGNALS):
                    signal.signal(signum, signal.SIG_DFL)
            except (OSError, ValueError):
                pass  # uncatchable (KILL/STOP) or not in main thread

    def get_handler(self, signal_spec: str) -> Optional[str]:
        """Return the LIVE trap action for a signal.

        Returns None if no trap is set — including for an inherited-for-listing
        entry (a parent's trap in a subshell-style child never fires; it is
        visible only to show_traps). The empty string means the signal is
        ignored; otherwise the command string to run. Public accessor so
        callers need not reach into ``state.trap_handlers``.
        """
        if signal_spec in self.state.inherited_traps:
            return None
        return self.state.trap_handlers.get(signal_spec)

    def execute_trap(self, signal_name: str):
        """Execute trap handler for given signal.

        Args:
            signal_name: Name of the signal that was received
        """
        action = self.get_handler(signal_name)
        if not action:
            # No trap set, empty action ('' = signal ignored), or an
            # inherited-for-listing entry (never fires in this shell)
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
            # Show specific signals — canonicalize each query spec to the same
            # key traps are stored under (so `trap -p SIGINT` / `trap -p 2`
            # find a trap set on INT).
            signals_to_show = []
            for sig in signals:
                canonical = self._canonical_signal_key(sig)
                if canonical is not None:
                    signals_to_show.append(canonical)

        output_lines = []
        for signal_name in sorted(signals_to_show, key=self._trap_sort_key):
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

    def _trap_sort_key(self, signal_name: str) -> int:
        """bash's trap-listing order: EXIT (signal 0) first, real signals
        by number, then the pseudo-signals DEBUG and ERR after them all."""
        if signal_name == 'EXIT':
            return 0
        if signal_name == 'DEBUG':
            return signal.NSIG + 1
        if signal_name == 'ERR':
            return signal.NSIG + 2
        return self._signum(signal_name) or 0

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
        if self.get_handler('EXIT'):
            self._exit_trap_executed = True
            self.execute_trap('EXIT')

    def _inherited_into_function(self, trace_option: str) -> bool:
        """Whether a DEBUG/ERR/RETURN trap fires while inside a function body.

        bash does NOT run these traps inside a function (or its sub-calls)
        unless the relevant trace option is set: ``errtrace`` (``set -E``) for
        ERR, ``functrace`` (``set -T``) for DEBUG/RETURN. At top level the trap
        always fires. ``function_stack`` is non-empty exactly while a function
        body is executing.
        """
        if not self.state.function_stack:
            return True
        return bool(self.state.options.get(trace_option))

    def execute_debug_trap(self):
        """Execute DEBUG trap if set (called before each simple command)."""
        if self._in_debug_err_trap:
            return
        if not self._inherited_into_function('functrace'):
            return
        if self.get_handler('DEBUG'):
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
        if not self._inherited_into_function('errtrace'):
            return
        if self.get_handler('ERR') and exit_code != 0:
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
