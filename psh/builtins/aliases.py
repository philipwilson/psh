"""Alias management builtins (alias, unalias)."""

from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


def _quote_alias_value(value: str) -> str:
    """Quote an alias value for reusable output, the way bash does
    (bash's sh_single_quote — the shared ``utils.escapes.single_quote``)."""
    from ..utils.escapes import single_quote
    return single_quote(value)


@builtin
class AliasBuiltin(Builtin):
    """Define or display aliases."""

    @property
    def name(self) -> str:
        return "alias"

    @property
    def synopsis(self) -> str:
        return "alias [-p] [name[=value] ... ]"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Define or display aliases."""
        opts, operands = self.parse_flags(args, shell, flags='p')
        if opts is None:
            return 2

        if opts['p'] or not operands:
            # bash quirk (alias.def): with -p, an empty alias table causes
            # an immediate successful return -- any operands are skipped.
            if not shell.alias_manager.aliases:
                return 0
            for name, value in sorted(shell.alias_manager.list_aliases()):
                self.write_line(
                    f"alias {name}={_quote_alias_value(value)}", shell)
            if not operands:
                return 0

        exit_code = 0
        for arg in operands:
            equals_pos = arg.find('=')
            if equals_pos > 0:
                # Assignment: name=value (a leading '=' is not an
                # assignment -- bash treats '=foo' as a name lookup).
                name = arg[:equals_pos]
                value = arg[equals_pos + 1:]
                try:
                    shell.alias_manager.define_alias(name, value)
                except ValueError:
                    self.error(f"`{name}': invalid alias name", shell)
                    exit_code = 1
            else:
                # Lookup: print the alias or report it missing.
                found = shell.alias_manager.get_alias(arg)
                if found is not None:
                    self.write_line(
                        f"alias {arg}={_quote_alias_value(found)}", shell)
                else:
                    self.error(f"{arg}: not found", shell)
                    exit_code = 1

        return exit_code

    @property
    def help(self) -> str:
        return """alias: alias [-p] [name[=value] ... ]

    Define or display aliases.

    Without arguments, print all aliases in reusable `alias name=value'
    form. With name=value arguments, define each name as an alias.
    With plain name arguments, print the named aliases.

    Options:
      -p    Print all defined aliases in reusable form"""


@builtin
class UnaliasBuiltin(Builtin):
    """Remove aliases."""

    @property
    def name(self) -> str:
        return "unalias"

    @property
    def synopsis(self) -> str:
        return "unalias [-a] name [name ...]"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Remove aliases."""
        opts, operands = self.parse_flags(args, shell, flags='a')
        if opts is None:
            return 2

        if opts['a']:
            # Remove all aliases; any operands are ignored (bash behavior).
            shell.alias_manager.clear_aliases()
            return 0

        if not operands:
            self.error(f"usage: {self.synopsis}", shell)
            return 2

        exit_code = 0
        for name in operands:
            if not shell.alias_manager.undefine_alias(name):
                self.error(f"{name}: not found", shell)
                exit_code = 1

        return exit_code

    @property
    def help(self) -> str:
        return """unalias: unalias [-a] name [name ...]

    Remove aliases.

    Options:
      -a    Remove all aliases

    Without -a, remove each named alias."""
