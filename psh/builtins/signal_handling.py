"""Signal handling builtins (trap)."""

from typing import TYPE_CHECKING, List

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
        return "trap [action] [condition...]"

    @property
    def description(self) -> str:
        return "Set signal handlers and exit traps"

    @property
    def help_text(self) -> str:
        return """trap: Set signal handlers and exit traps

SYNOPSIS
    trap [action] [condition...]
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

CONDITIONS
    Signal names (HUP, INT, QUIT, TERM, USR1, USR2, etc.)
    Signal numbers (1, 2, 3, 9, 15, etc.)
    EXIT    Execute when shell exits
    DEBUG   Execute before each command (bash extension)
    ERR     Execute when command returns non-zero (bash extension)

EXAMPLES
    trap 'echo "Interrupted"' INT         # Catch Ctrl+C
    trap 'cleanup; exit' EXIT             # Run cleanup on exit
    trap '' QUIT                          # Ignore SIGQUIT
    trap - TERM                           # Reset SIGTERM to default
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
            output = shell.trap_manager.show_traps()
            if output:
                print(output, file=shell.state.stdout)
            return 0

        # Check for options
        if args[1] == '-l':
            # List signals
            signals = shell.trap_manager.list_signals()
            for signal_info in signals:
                print(signal_info, file=shell.state.stdout)
            return 0

        if args[1] == '-p':
            # Show traps
            if len(args) == 2:
                # Show all traps
                output = shell.trap_manager.show_traps()
            else:
                # Show specific traps
                output = shell.trap_manager.show_traps(args[2:])
            if output:
                print(output, file=shell.state.stdout)
            return 0

        # POSIX: -- ends option processing; the next argument is the action.
        # This is the standard defensive idiom: trap -- 'action' SIGNAL
        arg_start = 1
        if args[arg_start] == '--':
            arg_start += 1
            if len(args) == arg_start:
                # Bare `trap --` behaves like bare `trap`: show all traps
                output = shell.trap_manager.show_traps()
                if output:
                    print(output, file=shell.state.stdout)
                return 0

        # Parse action and signals
        if len(args) < arg_start + 2:
            print("trap: usage: trap [action] [condition...]", file=shell.state.stderr)
            return 2

        action = args[arg_start]
        signals = args[arg_start + 1:]

        return shell.trap_manager.set_trap(action, signals)
