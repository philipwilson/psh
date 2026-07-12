"""Signal handling builtins (trap)."""

from typing import TYPE_CHECKING, List

from ..core import SpecialBuiltinUsageError
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class TrapBuiltin(Builtin):
    """Set signal handlers and exit traps."""

    @property
    def name(self) -> str:
        return "trap"

    @property
    def synopsis(self) -> str:
        # bash's exact usage string (also printed on usage errors).
        return "trap [-lp] [[arg] signal_spec ...]"

    @property
    def description(self) -> str:
        return "Set signal handlers and exit traps"

    @property
    def help_text(self) -> str:
        return """trap: Set signal handlers and exit traps

SYNOPSIS
    trap [action] [condition...]
    trap [condition...]
    trap -l
    trap -p [condition...]

DESCRIPTION
    Sets trap handlers for signals and shell exit. When a signal is received,
    the specified action is executed.

OPTIONS
    -l      List signal names and numbers
    -p      Print current trap settings

ACTIONS
    action  Command string to execute when signal is received
    ''      Ignore the signal
    -       Reset signal to default behavior

    With no action — a single signal spec, or conditions led by a signal
    number (POSIX `trap 2 15`) — each condition is reset to default.

CONDITIONS
    Signal names (HUP, INT, QUIT, TERM, USR1, WINCH, etc.),
    with or without the SIG prefix, case-insensitive
    Signal numbers (1, 2, 3, 9, 15, etc.)
    EXIT (or 0)   Execute when shell exits
    DEBUG   Execute before each command (bash extension)
    ERR     Execute when command returns non-zero (bash extension)

EXAMPLES
    trap 'echo "Interrupted"' INT         # Catch Ctrl+C
    trap 'cleanup; exit' EXIT             # Run cleanup on exit
    trap 'cleanup' 0                      # Same, POSIX numeric form
    trap '' QUIT                          # Ignore SIGQUIT
    trap - TERM                           # Reset SIGTERM to default
    trap 2 15                             # Reset SIGINT and SIGTERM
    trap -l                               # List all signals
    trap -p                               # Show all current traps
    trap -p INT EXIT                      # Show specific traps

EXIT STATUS
    Returns 0 unless an invalid signal is specified.
"""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the trap builtin."""
        # Options come first (bash grammar `trap [-lp] ...`), parsed by the
        # shared getopt-style walker over the flag set "lp": they CLUSTER
        # (`-lp`, `-pl`), split across words (`-p -l`), stop at `--`, at a bare
        # `-` (the reset ACTION, not an option — parse_flags_ordered's len==1
        # guard), or at the first non-option operand. On a bad flag char bash
        # reports the offending CHAR + usage line and a POSIX-mode
        # non-interactive shell exits (special-builtin usage error, like
        # `unset`); parse_flags prints error+usage, we raise. An action
        # beginning with '-' needs `--` first (`trap -- '-x' INT`).
        opts, operands = self.parse_flags(args, shell, flags='lp')
        if opts is None:
            raise SpecialBuiltinUsageError(2, suppressible=True)
        list_flag = opts['l']
        print_flag = opts['p']

        # -l dominates when present: bash's `trap -lp` / `-pl` / `-l INT`
        # prints the signal listing and ignores both -p and any operands.
        if list_flag:
            # (the listing string already ends with a newline)
            self.write(shell.trap_manager.list_signals(), shell)
            return 0

        if print_flag:
            # Show the queried traps, or all of them with no operands. Any
            # leading `--` was already consumed above (`trap -p -- INT`, and
            # bare `trap -p --` shows all traps like `trap -p`).
            output, invalid = shell.trap_manager.show_traps(operands or None)
            if output:
                self.write_line(output, shell)
            for spec in invalid:
                self.error(f"{spec}: invalid signal specification", shell)
            return 1 if invalid else 0

        # No -l/-p. With no operands — bare `trap`, or `trap --` — show all
        # traps (same as `trap -p`).
        if not operands:
            output, _ = shell.trap_manager.show_traps()
            if output:
                self.write_line(output, shell)
            return 0

        # Reset forms take NO action operand: POSIX says a first operand
        # that is an unsigned decimal integer (and a valid signal) makes
        # ALL operands conditions to reset (`trap 2 15`, `trap 0`); bash
        # additionally resets for a single operand naming any signal
        # (`trap INT`). Anything else is action + conditions.
        first = operands[0]
        if ((first.isdecimal() or len(operands) == 1)
                and shell.trap_manager.is_signal_spec(first)):
            return shell.trap_manager.remove_trap(operands)

        if len(operands) < 2:
            # A single operand that is not a resettable signal spec is a
            # USAGE error (bash: `trap foo` prints the usage line, rc 2,
            # and a POSIX-mode non-interactive shell exits).
            self.usage(f"usage: {self.synopsis}", shell)
            raise SpecialBuiltinUsageError(2, suppressible=True)

        return shell.trap_manager.set_trap(operands[0], operands[1:])
