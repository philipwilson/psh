"""Parser selection builtin."""

from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell

PARSERS = {
    'recursive_descent': ['rd', 'recursive', 'default'],
    'combinator': ['pc', 'functional'],
}

PARSER_LABELS = {
    'recursive_descent': 'production',
    'combinator': 'experimental',
}


@builtin
class ParserSelectBuiltin(Builtin):
    """Select the active parser implementation."""
    name = 'parser-select'

    @property
    def synopsis(self) -> str:
        return "parser-select [PARSER]"

    @property
    def help(self) -> str:
        return """parser-select: parser-select [PARSER]
    Select the active parser implementation.

    With no arguments, lists available parsers and marks the active one.

    Parsers:
      recursive_descent  Production recursive descent parser (default)
                         Aliases: rd, recursive, default
      combinator         Educational combinator parser (not production-
                         supported; may lag on edge cases)
                         Aliases: pc, functional

    Exit Status:
    Returns success unless an unknown parser is given."""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute parser-select command."""
        if len(args) < 2:
            current = shell.active_parser
            for name, aliases in PARSERS.items():
                marker = '*' if name == current else ' '
                alias_str = ', '.join(aliases)
                label = PARSER_LABELS.get(name, '')
                shell.stdout.write(f" {marker} {name} [{label}] (aliases: {alias_str})\n")
            return 0

        requested = args[1]
        target = None
        for name, aliases in PARSERS.items():
            if requested == name or requested in aliases:
                target = name
                break

        if target is None:
            self.error(f"unknown parser: {requested}", shell)
            return 1

        shell.active_parser = target
        return 0
