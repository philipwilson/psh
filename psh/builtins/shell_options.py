"""Shell options builtin (shopt)."""

from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class ShoptBuiltin(Builtin):
    """Set and unset shell options."""

    @property
    def name(self) -> str:
        return "shopt"

    # Map of shopt option names to their state.options keys
    SHOPT_OPTIONS = {
        'dotglob': 'dotglob',
        'nullglob': 'nullglob',
        'extglob': 'extglob',
        'nocaseglob': 'nocaseglob',
        'globstar': 'globstar',
        'checkhash': 'checkhash',
    }

    def execute(self, args: List[str], shell: 'Shell') -> int:
        # Parse flags
        flag = None
        option_names = []

        i = 1
        while i < len(args):
            arg = args[i]
            if arg in ('-s', '-u', '-p', '-q'):
                if flag is not None and flag != arg:
                    self.error("cannot combine multiple flag options", shell)
                    return 1
                flag = arg
            elif arg == '--':
                i += 1
                option_names.extend(args[i:])
                break
            elif arg.startswith('-'):
                self.error(f"invalid option: {arg}", shell)
                return 2
            else:
                option_names.append(arg)
            i += 1

        # Validate option names if provided
        for opt in option_names:
            if opt not in self.SHOPT_OPTIONS:
                self.error(f"{opt}: invalid shell option name", shell)
                return 1

        # No flags and no options: list all options
        if flag is None and not option_names:
            return self._list_options(shell, reusable=False)

        # -p with no options: list all in reusable form
        if flag == '-p' and not option_names:
            return self._list_options(shell, reusable=True)

        # -p with options: list specific options in reusable form
        if flag == '-p':
            return self._list_specific(option_names, shell, reusable=True)

        # No flag with options: show status of specific options
        if flag is None:
            return self._list_specific(option_names, shell, reusable=False)

        # -q: query silently (exit code only)
        if flag == '-q':
            for opt in option_names:
                key = self.SHOPT_OPTIONS[opt]
                if not shell.state.options.get(key, False):
                    return 1
            return 0

        # -s: set (enable) options
        if flag == '-s':
            for opt in option_names:
                key = self.SHOPT_OPTIONS[opt]
                shell.state.options[key] = True
            return 0

        # -u: unset (disable) options
        if flag == '-u':
            for opt in option_names:
                key = self.SHOPT_OPTIONS[opt]
                shell.state.options[key] = False
            return 0

        return 0

    def _list_options(self, shell: 'Shell', reusable: bool) -> int:
        """List all shopt options."""
        for opt in sorted(self.SHOPT_OPTIONS):
            key = self.SHOPT_OPTIONS[opt]
            enabled = shell.state.options.get(key, False)
            self._print_option(opt, enabled, shell, reusable)
        return 0

    def _list_specific(self, option_names: List[str], shell: 'Shell',
                       reusable: bool) -> int:
        """List specific shopt options."""
        for opt in option_names:
            key = self.SHOPT_OPTIONS[opt]
            enabled = shell.state.options.get(key, False)
            self._print_option(opt, enabled, shell, reusable)
        return 0

    def _print_option(self, name: str, enabled: bool, shell: 'Shell',
                      reusable: bool) -> None:
        """Print a single option's status."""
        if reusable:
            flag = '-s' if enabled else '-u'
            self.write_line(f"shopt {flag} {name}", shell)
        else:
            status = 'on' if enabled else 'off'
            self.write_line(f"{name}\t{status}", shell)

    @property
    def help(self) -> str:
        return """shopt: shopt [-pqsu] [optname ...]

    Toggle shell optional behavior.

    Options:
      -s    Set (enable) each optname
      -u    Unset (disable) each optname
      -p    Print in reusable form (shopt -s/-u optname)
      -q    Query silently; exit code indicates status

    Without options, list all settable options with their status.
    With optname but no flags, show the status of those options.

    Available options:
      checkhash    Re-verify hashed command paths before executing them
      dotglob      Glob patterns match files beginning with '.'
      extglob      Extended pattern matching: ?()|*()|+()|@()|!()
      globstar     '**' matches all files and directories recursively
      nocaseglob   Case-insensitive pathname expansion
      nullglob     Patterns with no matches expand to nothing"""
