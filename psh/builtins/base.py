"""Base class for shell builtins."""

import os
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from ..shell import Shell


class Builtin(ABC):
    """Abstract base class for all shell builtins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the primary command name."""
        pass

    @property
    def aliases(self) -> List[str]:
        """Return any command aliases."""
        return []

    @abstractmethod
    def execute(self, args: List[str], shell: 'Shell') -> int:
        """
        Execute the builtin command.

        Args:
            args: Command arguments, including the command name as args[0]
            shell: The shell instance for accessing state and I/O

        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        pass

    @property
    def synopsis(self) -> str:
        """Return brief command syntax for the builtin."""
        return f"{self.name}"

    @property
    def description(self) -> str:
        """Return one-line description for the builtin."""
        return self.__class__.__doc__ or 'no description available'

    @property
    def help(self) -> str:
        """Return detailed help text for the builtin."""
        return f"{self.synopsis}\n    {self.description}"

    def write(self, text: str, shell: 'Shell') -> None:
        """Write to the builtin's stdout.

        In a forked child (pipeline member, background job) builtins write
        at the fd level so dup2-based redirections apply; in the parent they
        write to shell.stdout so shell-level redirections and test capture
        apply. This replaces the in_forked_child/os.write dance that used to
        be copied into each builtin.
        """
        if shell.state.in_forked_child:
            os.write(1, text.encode('utf-8', errors='replace'))
        else:
            stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
            stdout.write(text)
            stdout.flush()

    def write_line(self, text: str, shell: 'Shell') -> None:
        """Write one line to the builtin's stdout (see write())."""
        self.write(text + '\n', shell)

    def error(self, message: str, shell: 'Shell') -> None:
        """Print an error message to stderr."""
        if shell.state.in_forked_child:
            os.write(2, f"{self.name}: {message}\n".encode('utf-8', errors='replace'))
            return
        stderr = shell.stderr if hasattr(shell, 'stderr') else sys.stderr
        print(f"{self.name}: {message}", file=stderr)
        stderr.flush()

    def parse_flags(self, args: List[str], shell: 'Shell',
                    flags: str = '', value_flags: str = ''
                    ) -> Tuple[Optional[dict], List[str]]:
        """Parse leading single-dash options from args (getopt-style).

        Args:
            args: Full argv including the command name at args[0].
            flags: Characters allowed as boolean flags (clusterable: -ab).
            value_flags: Characters that consume an argument (-d X or -dX).

        Returns:
            (opts, operands). opts maps each declared flag char to
            True/False (bool flags) or its value/None (value flags);
            operands are the remaining arguments after options and an
            optional ``--``. On an invalid option an error is printed and
            (None, args) is returned — callers should ``return 2``.
        """
        opts: dict = {c: False for c in flags}
        opts.update({c: None for c in value_flags})
        i = 1
        while i < len(args):
            arg = args[i]
            if arg == '--':
                i += 1
                break
            if not arg.startswith('-') or len(arg) == 1:
                break
            consumed_value = False
            for pos, ch in enumerate(arg[1:]):
                if ch in value_flags:
                    rest = arg[pos + 2:]
                    if rest:
                        opts[ch] = rest
                    elif i + 1 < len(args):
                        i += 1
                        opts[ch] = args[i]
                    else:
                        self.error(f"-{ch}: option requires an argument", shell)
                        return None, args
                    consumed_value = True
                    break
                elif ch in flags:
                    opts[ch] = True
                else:
                    self.error(f"-{ch}: invalid option", shell)
                    self.error(f"usage: {self.synopsis}", shell)
                    return None, args
            i += 1
            if consumed_value:
                continue
        return opts, args[i:]
