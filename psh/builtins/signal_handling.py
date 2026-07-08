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
        if not hasattr(shell, 'trap_manager'):
            # Initialize trap manager if not already done
            from ..core import TrapManager
            shell.trap_manager = TrapManager(shell)

        # Parse options
        if len(args) == 1:
            # No arguments - show all traps (same as trap -p)
            output, _ = shell.trap_manager.show_traps()
            if output:
                self.write_line(output, shell)
            return 0

        # Check for options
        if args[1] == '-l':
            # List signals (string already ends with a newline)
            self.write(shell.trap_manager.list_signals(), shell)
            return 0

        if args[1] == '-p':
            # Show traps (all, or the specific signals queried). POSIX: a
            # leading -- ends option processing on this path too (`trap -p
            # -- INT`); bare `trap -p --` shows all traps, like `trap -p`.
            specs = args[2:]
            if specs and specs[0] == '--':
                specs = specs[1:]
            output, invalid = shell.trap_manager.show_traps(specs or None)
            if output:
                self.write_line(output, shell)
            for spec in invalid:
                self.error(f"{spec}: invalid signal specification", shell)
            return 1 if invalid else 0

        # Any other leading dash word is an INVALID OPTION (bash): an action
        # beginning with '-' needs `--` first (`trap -- '-x' INT`), so
        # `trap -q`, `trap -q 'x' INT` and `trap '-echo hi' INT` all report
        # the first option character, print the usage line, and fail with
        # the usage status 2 (probe-verified vs bash 5.2; a POSIX-mode
        # non-interactive shell exits). A bare '-' (reset form) and '--'
        # are not options.
        if (args[1].startswith('-') and args[1] not in ('-', '--')):
            self.error(f"{args[1][:2]}: invalid option", shell)
            self.error(f"usage: {self.synopsis}", shell)
            raise SpecialBuiltinUsageError(2, suppressible=True)

        # POSIX: -- ends option processing; the next argument is the action.
        # This is the standard defensive idiom: trap -- 'action' SIGNAL
        arg_start = 1
        if args[arg_start] == '--':
            arg_start += 1
            if len(args) == arg_start:
                # Bare `trap --` behaves like bare `trap`: show all traps
                output, _ = shell.trap_manager.show_traps()
                if output:
                    self.write_line(output, shell)
                return 0

        operands = args[arg_start:]

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
            self.error(f"usage: {self.synopsis}", shell)
            raise SpecialBuiltinUsageError(2, suppressible=True)

        return shell.trap_manager.set_trap(operands[0], operands[1:])
