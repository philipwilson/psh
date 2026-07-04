"""Trap management for PSH shell."""
import signal
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..utils.signal_utils import (
    list_all_signals,
    signal_name_to_number,
    signal_number_to_name,
)
from .exceptions import FunctionReturn, LoopBreak, LoopContinue

if TYPE_CHECKING:
    from ..shell import Shell

class TrapManager:
    """Manages trap handlers for the shell."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Signal traps queued by the (async-signal-unsafe) Python handler;
        # executed at command boundaries via run_pending_traps(), so trap
        # actions never re-enter the parser/executor mid-command.
        self.pending_traps: list = []
        # Re-entrancy guard: a DEBUG/ERR action must not fire DEBUG/ERR
        # traps for its own commands.
        self._in_debug_err_trap = False
        # Re-entrancy guard: a function returning while a RETURN action runs
        # must not fire RETURN again (bash 5.2 recurses forever on
        # `trap 'return 3' RETURN`; psh deterministically fires once).
        self._in_return_trap = False
        # Depth of trap actions currently executing. While non-zero,
        # $BASH_COMMAND is frozen at the interrupted command (bash: "the
        # command executing at the time of the trap").
        self._trap_action_depth = 0

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

        exit_code = 0
        for signal_spec in signals:
            # Normalize to one canonical key (SIGINT / 2 / INT all -> INT) so
            # every path — storage here and the name-keyed SignalManager
            # dispatch — agrees on the key.
            canonical = self._canonical_signal_key(signal_spec)
            if canonical is None:
                print(f"trap: {signal_spec}: invalid signal specification",
                      file=self.state.stderr)
                # bash reports the bad spec but keeps processing the rest.
                exit_code = 1
                continue
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

        return exit_code

    # Signals whose OS handlers psh manages elsewhere (SignalManager's
    # trap-checking handlers and job-control bookkeeping). For these, traps
    # work through the existing handlers; we must not overwrite them.
    _MANAGED_SIGNALS = frozenset({
        signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT,
        signal.SIGCHLD, signal.SIGTSTP, signal.SIGTTOU, signal.SIGTTIN,
        getattr(signal, 'SIGWINCH', None),
    }) - {None}

    def _signum(self, signal_spec: str) -> Optional[int]:
        """The OS signal number for a canonical trap key, or None for
        pseudo-signals (EXIT/DEBUG/ERR)."""
        return signal_name_to_number(signal_spec)

    def _canonical_signal_key(self, signal_spec: str) -> Optional[str]:
        """Canonical ``trap_handlers`` key for a user signal spec.

        Resolves every platform signal name (with or without the ``SIG``
        prefix, case-insensitively) and every signal number to the bare
        canonical name (``SIGINT`` / ``2`` / ``int`` all -> ``INT``), via
        the same ``signal_utils`` tables that ``trap -l``/``kill -l`` list —
        the single key every path uses, so a trap set under any spelling is
        found by the name-keyed dispatch in SignalManager. Condition ``0``
        is the EXIT trap (POSIX: ``trap 'cmd' 0``); the pseudo-signals
        EXIT/DEBUG/ERR/RETURN pass through unchanged. Returns ``None`` for
        a spec that is not a valid signal.
        """
        spec = signal_spec.upper()
        if spec in self._PSEUDO_SIGNALS:
            return spec
        if spec.isdecimal():
            # POSIX: condition 0 means the shell-exit trap.
            return 'EXIT' if int(spec) == 0 else signal_number_to_name(int(spec))
        num = signal_name_to_number(spec)
        return signal_number_to_name(num) if num is not None else None

    def is_signal_spec(self, signal_spec: str) -> bool:
        """Whether ``signal_spec`` names a signal or pseudo-signal that
        ``trap`` accepts (used by the builtin's reset-form parse)."""
        return self._canonical_signal_key(signal_spec) is not None

    def _set_signal_handler(self, signal_spec: str, action: str):
        """Set a signal handler for the given signal."""
        # Special handling for pseudo-signals
        if signal_spec in self._PSEUDO_SIGNALS:
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
        if signal_spec in self._PSEUDO_SIGNALS:
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
        if signal_spec in self._PSEUDO_SIGNALS:
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

    def enter_subshell_trap_environment(self) -> None:
        """Establish subshell-environment trap semantics after a fork.

        bash resets every non-ignored inherited trap to its default action
        on entry to a subshell environment; the trap stays visible to
        ``trap`` (listing) until the first ``trap`` modification, then is
        dropped. Ignored ('') traps stay ignored.

        For a fresh child ``Shell`` this repeats what ``ShellState.adopt``
        already computed (idempotent). For a backgrounded compound that
        REUSES the parent Shell object in the fork (bg brace group /
        function), ``adopt`` never ran, so this is what stops a PARENT trap
        from firing in the child. Uses the same errtrace/ERR exemption
        adopt does, then re-aligns the OS dispositions.
        """
        live = set()
        if self.state.options.get('errtrace'):
            live.add('ERR')
        self.state.inherited_traps = {
            name for name, action in self.state.trap_handlers.items()
            if action != '' and name not in live
        }
        self.sync_forked_child_dispositions()

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
            # While the action runs, $BASH_COMMAND stays the interrupted
            # command (bash) — see set_bash_command.
            self._trap_action_depth += 1
            try:
                self.shell.run_command(action, add_to_history=False,
                                       base_line=base_line)
            finally:
                self._trap_action_depth -= 1

            # For most signals, restore the exit code
            # EXIT trap should preserve the exit code it sets
            if signal_name != 'EXIT':
                self.state.last_exit_code = saved_exit_code

        except (FunctionReturn, LoopBreak, LoopContinue):
            # `return` / `break` / `continue` in a trap action act on the
            # enclosing function/loop (bash: `trap 'return 9' USR1` returns
            # 9 from the function the signal interrupted; `trap break USR1`
            # exits the enclosing loop with status 0). Control-flow signals
            # deliberately do not derive from PshError, and must not be
            # swallowed by the defect guard below — re-raise so they unwind
            # from run_pending_traps to the enclosing executor. (`exit`
            # already works: SystemExit is not an Exception.)
            raise
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

    def show_traps(self, signals: Optional[List[str]] = None) -> Tuple[str, List[str]]:
        """Render trap settings for `trap` / `trap -p`.

        Args:
            signals: Specific signal specs to show (kept in query order,
                like bash), or None for all traps (bash's numeric order)

        Returns:
            (display, invalid): the formatted trap lines, plus any query
            specs that are not valid signals (bash reports each on stderr
            and exits 1 — the builtin does that reporting).
        """
        invalid: List[str] = []
        if signals is None:
            signals_to_show = sorted(self.state.trap_handlers,
                                     key=self._trap_sort_key)
        else:
            # Canonicalize each query spec to the same key traps are stored
            # under (so `trap -p SIGINT` / `trap -p 2` find a trap set on INT).
            signals_to_show = []
            for sig in signals:
                canonical = self._canonical_signal_key(sig)
                if canonical is None:
                    invalid.append(sig)
                elif canonical in self.state.trap_handlers:
                    signals_to_show.append(canonical)

        output_lines = []
        for signal_name in signals_to_show:
            action = self.state.trap_handlers[signal_name]
            if action == '':
                action_display = "''"
            else:
                # Quote the action for display
                action_display = f"'{action}'"
            display_name = self._canonical_trap_name(signal_name)
            output_lines.append(f"trap -- {action_display} {display_name}")

        return '\n'.join(output_lines), invalid

    def _trap_sort_key(self, signal_name: str) -> int:
        """bash's trap-listing order: EXIT (signal 0) first, real signals
        by number, then the pseudo-signals DEBUG, ERR and RETURN after
        them all (bash 5.2 lists them in exactly that order)."""
        if signal_name == 'EXIT':
            return 0
        if signal_name == 'DEBUG':
            return signal.NSIG + 1
        if signal_name == 'ERR':
            return signal.NSIG + 2
        if signal_name == 'RETURN':
            return signal.NSIG + 3
        return self._signum(signal_name) or 0

    # Pseudo-signals are printed WITHOUT a SIG prefix (bash); real signals
    # are printed with their canonical SIG-prefixed name.
    _PSEUDO_SIGNALS = frozenset({'EXIT', 'ERR', 'DEBUG', 'RETURN'})

    def _canonical_trap_name(self, signal_name: str) -> str:
        """Canonical name for `trap -p` output (bash-compatible).

        Real signals get the ``SIG`` prefix (``TERM`` -> ``SIGTERM``);
        pseudo-signals (EXIT/ERR/DEBUG/RETURN) are printed bare. Keys are
        always canonical bare names (see _canonical_signal_key), so a trap
        set as ``trap ... 15`` prints as SIGTERM.
        """
        if signal_name in self._PSEUDO_SIGNALS:
            return signal_name
        return f"SIG{signal_name}"

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
        body is executing. For DEBUG (functrace), a function carrying the
        ``declare -ft`` trace attribute also inherits the trap — the check is
        against the INNERMOST function, so a non-traced function called from
        a traced one does not fire (bash).
        """
        if not self.state.function_stack:
            return True
        if self.state.options.get(trace_option):
            return True
        if trace_option == 'functrace':
            func = self.shell.function_manager.get_function(
                self.state.function_stack[-1])
            return func is not None and func.trace
        return False

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

    # ------------------------------------------------------------------
    # RETURN trap
    #
    # Unlike DEBUG/ERR (whose inheritance is a fire-time check against
    # errtrace/functrace), the RETURN trap uses bash's HIDING model, which
    # is observably different: on function entry without `set -T` (or the
    # function's -t trace attribute) the trap is REMOVED for the
    # function's extent — `trap -p RETURN` inside lists nothing, a trap
    # the BODY sets fires at that same function's return and persists
    # afterwards, and the hidden outer trap is restored only if the body
    # didn't install its own. Sourced files never hide it (a RETURN trap
    # fires at the end of every `source`, -T or not). Pinned by the truth
    # table in tmp/probes-r17t2-trap/cases_c_return.sh (bash 5.2).
    # ------------------------------------------------------------------

    def hide_return_trap_on_function_entry(self) -> Optional[str]:
        """Hide the RETURN trap for a function's extent (bash without -T).

        Returns the hidden action string for restore_return_trap_on_
        function_exit, or None when nothing was hidden. The caller decides
        WHETHER to hide (functrace / the function's trace attribute
        inherit the trap instead). Inherited-for-listing entries (a
        parent's trap in a subshell-style child) are not live and stay.
        """
        if ('RETURN' in self.state.trap_handlers
                and 'RETURN' not in self.state.inherited_traps):
            return self.state.trap_handlers.pop('RETURN')
        return None

    def restore_return_trap_on_function_exit(self, hidden: Optional[str]) -> None:
        """Restore a hidden RETURN trap when the function returns.

        A RETURN trap the body installed WINS and persists after the
        function (bash: the hidden outer action is discarded) — restore
        only when no RETURN trap is currently set.
        """
        if hidden is not None and 'RETURN' not in self.state.trap_handlers:
            self.state.trap_handlers['RETURN'] = hidden

    def execute_return_trap(self) -> Optional[int]:
        """Fire the RETURN trap at a function return or end of `source`.

        Runs with the returning context still in place (FUNCNAME/locals —
        the caller fires before popping scope/stack) and with $? = the
        status of the last command executed BEFORE the return (bash);
        execute_trap's save/restore keeps the action's own commands from
        changing the pending return status.

        Returns an override exit status when the action itself executed
        `return N` (POSIX: return in a trap action returns from the trap);
        None otherwise. This adoption is a deliberate divergence with two
        faces, pinned in tests/integration/job_control/test_trap_actions.py:

        * fired at a FUNCTION return, bash 5.2 recurses forever (the
          action's `return` re-triggers the trap); psh fires once and
          adopts N.
        * fired at the end of `source`, bash rejects the `return` ("can
          only `return' from a function or sourced script" — the sourced
          file has already finished) and keeps the source's own status;
          psh adopts N here too, one consistent rule for both fire points.
        """
        if self._in_return_trap:
            return None
        if not self.get_handler('RETURN'):
            return None
        self._in_return_trap = True
        try:
            self.execute_trap('RETURN')
        except FunctionReturn as fr:
            return fr.exit_code
        finally:
            self._in_return_trap = False
        return None

    def set_bash_command(self, command: object) -> None:
        """Record $BASH_COMMAND — the command being/about to be executed.

        Called by the executor's dispatch chokepoints (simple commands,
        pipeline members, for/case/(( ))/[[ ]] headers) BEFORE the DEBUG
        trap fires, with either the AST node (rendered lazily — and only —
        when $BASH_COMMAND is actually read; see ShellState.bash_command)
        or a cheap pre-rendered string. While a trap action is executing,
        updates are suppressed so $BASH_COMMAND keeps the interrupted
        command (bash: "unless the shell is executing a command as a
        result of a trap, in which case it is the command executing at
        the time of the trap").
        """
        if self._trap_action_depth == 0:
            self.state.bash_command = command

    def queue_trap(self, signal_name: str):
        """Queue a signal trap from handler context (async-signal path)."""
        self.pending_traps.append(signal_name)

    def run_pending_traps(self):
        """Execute queued signal traps (called at command boundaries)."""
        while self.pending_traps:
            self.execute_trap(self.pending_traps.pop(0))
