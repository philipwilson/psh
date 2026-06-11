"""Kill builtin command for sending signals to processes."""

import os
import signal
from typing import TYPE_CHECKING, Dict, List, Tuple

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


# POSIX signal name to number mapping
SIGNAL_NAMES: Dict[str, int] = {
    'HUP': signal.SIGHUP,
    'INT': signal.SIGINT,
    'QUIT': signal.SIGQUIT,
    'ILL': signal.SIGILL,
    'TRAP': signal.SIGTRAP,
    'ABRT': signal.SIGABRT,
    'BUS': signal.SIGBUS,
    'FPE': signal.SIGFPE,
    'KILL': signal.SIGKILL,
    'USR1': signal.SIGUSR1,
    'SEGV': signal.SIGSEGV,
    'USR2': signal.SIGUSR2,
    'PIPE': signal.SIGPIPE,
    'ALRM': signal.SIGALRM,
    'TERM': signal.SIGTERM,
    'CHLD': signal.SIGCHLD,
    'CONT': signal.SIGCONT,
    'STOP': signal.SIGSTOP,
    'TSTP': signal.SIGTSTP,
    'TTIN': signal.SIGTTIN,
    'TTOU': signal.SIGTTOU,
    'URG': signal.SIGURG,
    'XCPU': signal.SIGXCPU,
    'XFSZ': signal.SIGXFSZ,
    'VTALRM': signal.SIGVTALRM,
    'PROF': signal.SIGPROF,
    'WINCH': signal.SIGWINCH,
    'IO': signal.SIGIO,
    'SYS': signal.SIGSYS,
}

# Signal number to name mapping (for -l listing)
SIGNAL_NUMBERS: Dict[int, str] = {v: k for k, v in SIGNAL_NAMES.items()}


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
        signal_num = signal.SIGTERM  # Default signal
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
                raise ValueError(f"invalid signal number: {signal_str}")

        # Parse as signal name
        signal_name = signal_str.upper()

        # Remove SIG prefix if present
        if signal_name.startswith('SIG'):
            signal_name = signal_name[3:]

        if signal_name not in SIGNAL_NAMES:
            raise ValueError(f"invalid signal name: {signal_str}")

        return SIGNAL_NAMES[signal_name]

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

    def _list_signals(self, exit_statuses: List[str], shell: 'Shell') -> int:
        """List signal names, optionally for specific exit statuses."""
        if not exit_statuses:
            # List all signals
            signal_names = []
            for i in range(1, 32):  # Standard signal range
                if i in SIGNAL_NUMBERS:
                    signal_names.append(f"{i}) SIG{SIGNAL_NUMBERS[i]}")
                else:
                    signal_names.append(f"{i}) {i}")

            # Print in columns
            for i in range(0, len(signal_names), 4):
                row = signal_names[i:i+4]
                self.write_line('\t'.join(f"{name:<15}" for name in row), shell)

            return 0

        # Show signals for specific exit statuses
        for exit_str in exit_statuses:
            try:
                exit_status = int(exit_str)
                if exit_status > 128:
                    # Exit status from signal = 128 + signal_number
                    signal_num = exit_status - 128
                    if signal_num in SIGNAL_NUMBERS:
                        self.write_line(f"SIG{SIGNAL_NUMBERS[signal_num]}", shell)
                    else:
                        self.write_line(f"{signal_num}", shell)
                else:
                    self.write_line(f"Exit status {exit_status} not from signal", shell)
            except ValueError:
                self.error(f"{exit_str}: invalid exit status", shell)
                return 1

        return 0
