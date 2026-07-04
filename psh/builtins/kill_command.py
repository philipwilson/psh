"""Kill builtin command for sending signals to processes."""

import os
import signal
from typing import TYPE_CHECKING, List, Tuple

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
            self.error(f"usage: {self.synopsis}", shell)
            return 2

        # Parse arguments
        signal_num, targets, list_signals = self._parse_args(args[1:])

        if list_signals:
            return self._list_signals(targets, shell)

        if not targets:
            self.error("no process specified", shell)
            return 2

        # Resolve targets to actual PIDs
        pids = self._resolve_targets(targets, shell)
        if not pids:
            return 1

        # Send signals to processes
        return self._send_signals(signal_num, pids, shell)

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

    def _resolve_targets(self, targets: List[str], shell: 'Shell') -> List[int]:
        """Resolve target specifications to actual PIDs."""
        pids = []

        for target in targets:
            try:
                if target.startswith('%'):
                    # Job specification
                    job = shell.job_manager.parse_job_spec(target)
                    if job is None:
                        self.error(f"{target}: no such job", shell)
                        continue

                    # Add all process PIDs from the job
                    for process in job.processes:
                        pids.append(process.pid)
                else:
                    # Process ID
                    pid = int(target)
                    pids.append(pid)
            except ValueError:
                self.error(f"{target}: invalid process id", shell)
                continue
            except (OSError, KeyError) as e:
                self.error(f"{target}: {e}", shell)
                continue

        return pids

    def _send_signals(self, signal_num: int, pids: List[int], shell: 'Shell') -> int:
        """Send signal to list of PIDs."""
        success_count = 0

        for pid in pids:
            try:
                if pid == 0:
                    # Signal current process group
                    os.killpg(os.getpgrp(), signal_num)
                elif pid < 0:
                    # Signal process group
                    os.killpg(abs(pid), signal_num)
                else:
                    # Signal individual process
                    os.kill(pid, signal_num)
                success_count += 1
            except ProcessLookupError:
                self.error(f"({pid}) - No such process", shell)
            except PermissionError:
                self.error(f"({pid}) - Operation not permitted", shell)
            except OSError as e:
                self.error(f"({pid}) - {e}", shell)

        # Return 0 if at least one signal was sent successfully
        return 0 if success_count > 0 else 1

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
