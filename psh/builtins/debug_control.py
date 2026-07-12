"""Debug control commands for convenient AST debugging."""

from typing import TYPE_CHECKING, Dict, List

from ..core.option_registry import DEBUG_OPTION_NAMES
from ..utils import get_signal_registry
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


def _derive_debug_option_map() -> Dict[str, str]:
    """``{short_name: registry_name}`` for the ``debug-*`` toggles the ``debug``
    builtin exposes (``ast``/``tokens``/``scopes``/``expansion``/``exec``).

    Membership is DERIVED from the option registry's DEBUG category rather than
    pasted three times — so a new ``_spec(..., OptionCategory.DEBUG)`` appears
    here (and in ``help``) automatically, and a name the registry does not have
    (the former phantom ``parser`` row) cannot be advertised. The two internal
    sub-variants ``debug-expansion-detail`` / ``debug-exec-fork`` are filtered
    out by the "no further hyphen in the short name" rule, keeping the exposed
    set behaviorally identical to before.
    """
    result: Dict[str, str] = {}
    for name in DEBUG_OPTION_NAMES:
        short = name[len('debug-'):] if name.startswith('debug-') else name
        if '-' not in short:
            result[short] = name
    return result


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
            self.write_line(f"AST debugging {status} (format: {format_name})", shell)
            return 0

        elif len(args) == 2:
            arg = args[1].lower()

            if arg in ('on', 'enable', 'true', '1'):
                shell.state.options['debug-ast'] = True
                format_name = shell.state.scope_manager.get_variable('PSH_AST_FORMAT') or 'tree'
                self.write_line(f"AST debugging enabled (format: {format_name})", shell)
                return 0

            elif arg in ('off', 'disable', 'false', '0'):
                shell.state.options['debug-ast'] = False
                self.write_line("AST debugging disabled", shell)
                return 0

            elif arg in ('tree', 'pretty', 'compact', 'dot', 'sexp'):
                # Format specified - enable debug and set format
                shell.state.options['debug-ast'] = True
                shell.state.scope_manager.set_variable('PSH_AST_FORMAT', arg)
                self.write_line(f"AST debugging enabled (format: {arg})", shell)
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
                self.write_line(f"AST debugging enabled (format: {format_arg})", shell)
            else:
                shell.state.options['debug-ast'] = False
                self.write_line("AST debugging disabled", shell)

            return 0

        else:
            self.error("too many arguments", shell)
            self.error("Use: debug-ast [on|off] [tree|pretty|compact|dot|sexp]", shell)
            return 1


@builtin
class DebugBuiltin(Builtin):
    """Control various debug options."""

    name = "debug"

    # The one option map (short name -> registry option key), derived from the
    # option registry's DEBUG category. Used by every execute() branch AND by
    # help, so parsing and documentation cannot drift.
    _OPTION_MAP = _derive_debug_option_map()
    _OPTION_DESCRIPTIONS = {
        'ast': 'AST debugging',
        'tokens': 'Token debugging',
        'scopes': 'Scope debugging',
        'expansion': 'Expansion debugging',
        'exec': 'Execution debugging',
    }

    @property
    def synopsis(self) -> str:
        return "debug [OPTION] [on|off]"

    @property
    def help(self) -> str:
        options = "\n".join(
            f"      {short:<12} {self._OPTION_DESCRIPTIONS.get(short, '')}".rstrip()
            for short in self._OPTION_MAP)
        return f"""debug: debug [OPTION] [on|off]
    Control various debug options.

    With no arguments, shows the current state of all debug options.
    With an OPTION name alone, toggles that option on/off.
    With an OPTION and on/off, sets that option explicitly.

    Options:
{options}

    Exit Status:
    Returns success unless an invalid option is given."""

    def execute(self, args: List[str], shell) -> int:
        """Execute the debug builtin."""
        if len(args) == 1:
            # Show all debug options
            self.write_line("Debug Options:", shell)
            for name, option_key in self._OPTION_MAP.items():
                status = "on" if shell.state.options.get(option_key, False) else "off"
                self.write_line(f"  {name:<12} {status}", shell)

            # Show AST format if AST debugging is on
            if shell.state.options.get('debug-ast', False):
                format_name = shell.state.scope_manager.get_variable('PSH_AST_FORMAT') or 'tree'
                self.write_line(f"  ast-format   {format_name}", shell)

            return 0

        elif len(args) == 2:
            # Toggle option
            option = args[1].lower()

            if option not in self._OPTION_MAP:
                self.error(f"unknown debug option: {option}", shell)
                self.error("Valid options: "
                           + ", ".join(self._OPTION_MAP), shell)
                return 1

            option_key = self._OPTION_MAP[option]
            current = shell.state.options.get(option_key, False)
            shell.state.options[option_key] = not current
            status = "enabled" if not current else "disabled"
            self.write_line(f"Debug {option} {status}", shell)

            # Special handling for debug-scopes
            if option == 'scopes':
                shell.state.scope_manager.enable_debug(not current)

            return 0

        elif len(args) == 3:
            # Set option on/off
            option = args[1].lower()
            action = args[2].lower()

            if option not in self._OPTION_MAP:
                self.error(f"unknown debug option: {option}", shell)
                return 1

            if action in ('on', 'enable', 'true', '1'):
                shell.state.options[self._OPTION_MAP[option]] = True
                self.write_line(f"Debug {option} enabled", shell)

                # Special handling for debug-scopes
                if option == 'scopes':
                    shell.state.scope_manager.enable_debug(True)

            elif action in ('off', 'disable', 'false', '0'):
                shell.state.options[self._OPTION_MAP[option]] = False
                self.write_line(f"Debug {option} disabled", shell)

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
                self.write_line(self.help, shell)
                return 0
            else:
                self.error(f"unknown option: {arg}", shell)
                self.error("Use: signals [-v|--verbose] [-h|--help]", shell)
                return 1

        # Get the signal registry

        registry = get_signal_registry(create=False)

        if registry is None:
            self.error("signal registry not initialized", shell)
            return 1

        # Generate and print report
        report = registry.report(verbose=verbose)
        self.write_line(report, shell)

        return 0
