"""Kill builtin command for sending signals to processes."""

import os
import signal
from typing import TYPE_CHECKING, List, Tuple

from ..executor.job_control import JobSpecOutcome, jobspec_error_messages
from ..utils.signal_utils import (
    list_all_signals,
    signal_name_to_number,
    signal_number_to_name,
)
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class KillBuiltin(Builtin):
    """Send signals to processes."""

    @property
    def name(self) -> str:
        return "kill"

    @property
    def synopsis(self) -> str:
        return "kill [-s signal | -signal] pid... | kill -l [exit_status]"

    @property
    def description(self) -> str:
        return "Send signals to processes or list signal names"

    @property
    def help(self) -> str:
        return """kill: kill [-s signal | -signal] pid... | kill -l [exit_status]
    Send signals to processes or list signal names.

    The kill utility sends a signal to the process or processes specified
    by each pid operand.

    Options:
      -l        List supported signal names. If exit_status is specified,
                show the signal name corresponding to that exit status.
      -s signal Specify the signal to send (case-insensitive, without SIG prefix)
      -signal   Specify signal by name (e.g., -TERM) or number (e.g., -15)

    Arguments:
      pid       Process ID to signal. Can be:
                - Positive integer: signal that process
                - 0: signal current process group
                - Negative integer: signal process group abs(pid)
                - %jobspec: signal job (e.g., %1, %+, %-, %string)

    Default signal is TERM (15) if none specified.

    Exit Status:
    Returns 0 if at least one signal was sent successfully; non-zero otherwise."""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the kill builtin."""
        try:
            return self._execute_kill(args, shell)
        except (OSError, ValueError) as e:
            self.error(str(e), shell)
            return 1

    def _execute_kill(self, args: List[str], shell: 'Shell') -> int:
        """Main kill execution logic."""
        if len(args) == 1:
            # No arguments - show usage
            self.usage(f"usage: {self.synopsis}", shell)
            return 2

        # Parse arguments
        signal_num, targets, list_signals = self._parse_args(args[1:])

        if list_signals:
            return self._list_signals(targets, shell)

        if not targets:
            self.error("no process specified", shell)
            return 2

        # Signal each target; success if at least one was delivered (bash).
        success_count = 0
        for target in targets:
            if self._signal_target(signal_num, target, shell):
                success_count += 1
        return 0 if success_count > 0 else 1

    def _parse_args(self, args: List[str]) -> Tuple[int, List[str], bool]:
        """Parse kill command arguments.

        Returns:
            Tuple of (signal_number, target_list, list_signals_flag)
        """
        signal_num: int = signal.SIGTERM  # Default signal
        targets = []
        list_signals = False
        i = 0

        while i < len(args):
            arg = args[i]

            if arg == '-l':
                list_signals = True
                i += 1
                # Remaining args are exit statuses for -l
                targets.extend(args[i:])
                break
            elif arg.startswith('-s'):
                # -s signal_name format
                if arg == '-s':
                    # Signal name is next argument
                    if i + 1 >= len(args):
                        raise ValueError("option requires an argument -- 's'")
                    signal_str = args[i + 1]
                    i += 2
                else:
                    # -ssignal_name format
                    signal_str = arg[2:]
                    i += 1

                signal_num = self._parse_signal(signal_str)
            elif arg.startswith('-') and len(arg) > 1 and arg != '--':
                # -signal_name or -signal_number format
                signal_str = arg[1:]
                signal_num = self._parse_signal(signal_str)
                i += 1
            elif arg == '--':
                # End of options
                i += 1
                targets.extend(args[i:])
                break
            else:
                # This and remaining args are targets
                targets.extend(args[i:])
                break

        return signal_num, targets, list_signals

    def _parse_signal(self, signal_str: str) -> int:
        """Parse a signal name or number into signal number."""
        if not signal_str:
            raise ValueError("invalid signal specification")

        # Check if it looks like a number (including negative)
        if signal_str.lstrip('-').isdigit():
            try:
                signal_num = int(signal_str)
                if signal_num < 0 or signal_num > 64:
                    raise ValueError(f"invalid signal number: {signal_num}")
                return signal_num
            except ValueError:
                raise ValueError(f"invalid signal number: {signal_str}") from None

        # Parse as signal name (with or without SIG prefix, case-insensitive)
        num = signal_name_to_number(signal_str)
        if num is None:
            raise ValueError(f"invalid signal name: {signal_str}")
        return num

    def _signal_target(self, signal_num: int, target: str,
                       shell: 'Shell') -> bool:
        """Deliver ``signal_num`` to one target; True if it was delivered.

        A ``%jobspec`` signals the job's process group ONCE via
        ``os.killpg(job.pgid, ...)`` — bash signals the group, not each
        recorded member PID. The old per-member expansion raised a spurious
        "No such process" for a pipeline member that had already exited even
        though the live members were signalled successfully.

        A bare operand is a process id: ``0`` signals the current process
        group, a negative value signals process group ``abs(pid)``, and a
        positive value signals that one process.
        """
        if target.startswith('%'):
            result = shell.job_manager.resolve_job_spec(target)
            if result.outcome is not JobSpecOutcome.FOUND or result.job is None:
                for msg in jobspec_error_messages(result, target):
                    self.error(msg, shell)
                return False
            pgid = result.job.pgid
            return self._deliver(lambda: os.killpg(pgid, signal_num),
                                 target, shell)

        try:
            pid = int(target)
        except ValueError:
            self.error(f"{target}: invalid process id", shell)
            return False

        if pid == 0:
            return self._deliver(
                lambda: os.killpg(os.getpgrp(), signal_num), pid, shell)
        if pid < 0:
            return self._deliver(
                lambda: os.killpg(abs(pid), signal_num), pid, shell)
        return self._deliver(lambda: os.kill(pid, signal_num), pid, shell)

    def _deliver(self, action, who, shell: 'Shell') -> bool:
        """Run a signal-sending ``action``, reporting the bash diagnostic."""
        try:
            action()
            return True
        except ProcessLookupError:
            self.error(f"({who}) - No such process", shell)
        except PermissionError:
            self.error(f"({who}) - Operation not permitted", shell)
        except OSError as e:
            self.error(f"({who}) - {e}", shell)
        return False

    def _list_signals(self, specs: List[str], shell: 'Shell') -> int:
        """Implement `kill -l [sigspec...]` (bash-compatible).

        With no argument, list all signals (NUM) SIGNAME, bash column layout).
        With a NUMBER N: if N > 128 print the name for signal N-128 (exit-status
        convention), otherwise print the name for signal N (no SIG prefix).
        With a NAME (with or without SIG prefix): print its number.
        """
        if not specs:
            # write() (not write_line) — list_all_signals already ends in '\n'
            self.write(list_all_signals(), shell)
            return 0

        exit_code = 0
        for spec in specs:
            # A numeric spec: print the signal NAME.
            if spec.lstrip('-').isdigit():
                num = int(spec)
                # bash maps the pseudo "signal 0" (the EXIT trap) to EXIT.
                if num == 0:
                    self.write_line("EXIT", shell)
                    continue
                if num > 128:
                    num -= 128
                name = signal_number_to_name(num)
                if name is None:
                    self.error(f"{spec}: invalid signal specification", shell)
                    exit_code = 1
                else:
                    self.write_line(name, shell)
                continue

            # A name spec: print the signal NUMBER.
            resolved = signal_name_to_number(spec)
            if resolved is None:
                self.error(f"{spec}: invalid signal specification", shell)
                exit_code = 1
            else:
                self.write_line(str(resolved), shell)

        return exit_code
