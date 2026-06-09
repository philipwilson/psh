"""Debug control commands for convenient AST debugging."""

import sys
from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class DebugASTBuiltin(Builtin):
    """Control AST debugging options."""

    name = "debug-ast"

    @property
    def synopsis(self) -> str:
        return "debug-ast [on|off] [FORMAT]"

    @property
    def help(self) -> str:
        return """debug-ast: debug-ast [on|off] [FORMAT]
    Control AST debugging options.

    With no arguments, toggles AST debugging on/off.

    Arguments:
      on|off     Enable or disable AST debugging (default: toggle)
      FORMAT     AST format: tree, pretty, compact, dot, sexp (default: tree)

    A format name alone (e.g. 'debug-ast pretty') enables debugging with
    that format.

    Exit Status:
    Returns success unless an invalid argument is given."""

    def execute(self, args: List[str], shell) -> int:
        """Execute the debug-ast builtin."""
        if len(args) == 1:
            # No arguments - toggle debug-ast
            current = shell.state.options.get('debug-ast', False)
            shell.state.options['debug-ast'] = not current
            status = "enabled" if not current else "disabled"
            format_name = shell.state.scope_manager.get_variable('PSH_AST_FORMAT') or 'tree'
            print(f"AST debugging {status} (format: {format_name})", file=shell.stdout)
            return 0

        elif len(args) == 2:
            arg = args[1].lower()

            if arg in ('on', 'enable', 'true', '1'):
                shell.state.options['debug-ast'] = True
                format_name = shell.state.scope_manager.get_variable('PSH_AST_FORMAT') or 'tree'
                print(f"AST debugging enabled (format: {format_name})", file=shell.stdout)
                return 0

            elif arg in ('off', 'disable', 'false', '0'):
                shell.state.options['debug-ast'] = False
                print("AST debugging disabled", file=shell.stdout)
                return 0

            elif arg in ('tree', 'pretty', 'compact', 'dot', 'sexp'):
                # Format specified - enable debug and set format
                shell.state.options['debug-ast'] = True
                shell.state.scope_manager.set_variable('PSH_AST_FORMAT', arg)
                print(f"AST debugging enabled (format: {arg})", file=shell.stdout)
                return 0

            else:
                self.error(f"invalid argument: {args[1]}", shell)
                self.error("Use: debug-ast [on|off] [tree|pretty|compact|dot|sexp]", shell)
                return 1

        elif len(args) == 3:
            # Enable/disable and format
            action = args[1].lower()
            format_arg = args[2].lower()

            if action not in ('on', 'enable', 'true', '1', 'off', 'disable', 'false', '0'):
                self.error(f"invalid action: {action}", shell)
                return 1

            if format_arg not in ('tree', 'pretty', 'compact', 'dot', 'sexp'):
                self.error(f"invalid format: {format_arg}", shell)
                return 1

            if action in ('on', 'enable', 'true', '1'):
                shell.state.options['debug-ast'] = True
                shell.state.scope_manager.set_variable('PSH_AST_FORMAT', format_arg)
                print(f"AST debugging enabled (format: {format_arg})", file=shell.stdout)
            else:
                shell.state.options['debug-ast'] = False
                print("AST debugging disabled", file=shell.stdout)

            return 0

        else:
            self.error("too many arguments", shell)
            self.error("Use: debug-ast [on|off] [tree|pretty|compact|dot|sexp]", shell)
            return 1


@builtin
class DebugBuiltin(Builtin):
    """Control various debug options."""

    name = "debug"

    @property
    def synopsis(self) -> str:
        return "debug [OPTION] [on|off]"

    @property
    def help(self) -> str:
        return """debug: debug [OPTION] [on|off]
    Control various debug options.

    With no arguments, shows the current state of all debug options.
    With an OPTION name alone, toggles that option on/off.
    With an OPTION and on/off, sets that option explicitly.

    Options:
      ast          AST debugging
      tokens       Token debugging
      scopes       Scope debugging
      expansion    Expansion debugging
      exec         Execution debugging
      parser       Parser tracing

    Exit Status:
    Returns success unless an invalid option is given."""

    def execute(self, args: List[str], shell) -> int:
        """Execute the debug builtin."""
        if len(args) == 1:
            # Show all debug options
            print("Debug Options:", file=shell.stdout)
            debug_options = {
                'ast': 'debug-ast',
                'tokens': 'debug-tokens',
                'scopes': 'debug-scopes',
                'expansion': 'debug-expansion',
                'exec': 'debug-exec'
            }

            for name, option_key in debug_options.items():
                status = "on" if shell.state.options.get(option_key, False) else "off"
                print(f"  {name:<12} {status}", file=shell.stdout)

            # Show AST format if AST debugging is on
            if shell.state.options.get('debug-ast', False):
                format_name = shell.state.scope_manager.get_variable('PSH_AST_FORMAT') or 'tree'
                print(f"  ast-format   {format_name}", file=shell.stdout)

            return 0

        elif len(args) == 2:
            # Toggle option
            option = args[1].lower()
            option_map = {
                'ast': 'debug-ast',
                'tokens': 'debug-tokens',
                'scopes': 'debug-scopes',
                'expansion': 'debug-expansion',
                'exec': 'debug-exec'
            }

            if option not in option_map:
                self.error(f"unknown debug option: {option}", shell)
                self.error("Valid options: ast, tokens, scopes, expansion, exec", shell)
                return 1

            option_key = option_map[option]
            current = shell.state.options.get(option_key, False)
            shell.state.options[option_key] = not current
            status = "enabled" if not current else "disabled"
            print(f"Debug {option} {status}", file=shell.stdout)

            # Special handling for debug-scopes
            if option == 'scopes':
                shell.state.scope_manager.enable_debug(not current)

            return 0

        elif len(args) == 3:
            # Set option on/off
            option = args[1].lower()
            action = args[2].lower()

            option_map = {
                'ast': 'debug-ast',
                'tokens': 'debug-tokens',
                'scopes': 'debug-scopes',
                'expansion': 'debug-expansion',
                'exec': 'debug-exec'
            }

            if option not in option_map:
                self.error(f"unknown debug option: {option}", shell)
                return 1

            if action in ('on', 'enable', 'true', '1'):
                shell.state.options[option_map[option]] = True
                print(f"Debug {option} enabled", file=shell.stdout)

                # Special handling for debug-scopes
                if option == 'scopes':
                    shell.state.scope_manager.enable_debug(True)

            elif action in ('off', 'disable', 'false', '0'):
                shell.state.options[option_map[option]] = False
                print(f"Debug {option} disabled", file=shell.stdout)

                # Special handling for debug-scopes
                if option == 'scopes':
                    shell.state.scope_manager.enable_debug(False)

            else:
                self.error(f"invalid action: {action}", shell)
                self.error("Use: on, off, enable, disable, true, false, 1, or 0", shell)
                return 1

            return 0

        else:
            self.error("too many arguments", shell)
            return 1


@builtin
class SignalsBuiltin(Builtin):
    """Show signal handler state and history."""

    name = "signals"

    @property
    def synopsis(self) -> str:
        return "signals [-v]"

    @property
    def help(self) -> str:
        return """signals: signals [-v]
    Show signal handler state and history.

    Displays the current signal handler registrations. With -v, also
    shows the full signal history and stack traces.

    Options:
      -v, --verbose     Show full history and stack traces
      -h, --help        Show this help message

    Exit Status:
    Returns success unless the signal registry is not initialized."""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the signals builtin."""
        # Parse options
        verbose = False

        for arg in args[1:]:
            if arg in ('-v', '--verbose'):
                verbose = True
            elif arg in ('-h', '--help'):
                print(self.__doc__, file=shell.stdout)
                return 0
            else:
                self.error(f"unknown option: {arg}", shell)
                self.error("Use: signals [-v|--verbose] [-h|--help]", shell)
                return 1

        # Get the signal registry
        from ..utils import get_signal_registry

        registry = get_signal_registry(create=False)

        if registry is None:
            print("Signal registry not initialized", file=sys.stderr)
            return 1

        # Generate and print report
        report = registry.report(verbose=verbose)
        print(report, file=shell.stdout)

        return 0
