"""Help builtin command."""

import fnmatch
from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class HelpBuiltin(Builtin):
    """Display information about builtin commands."""

    @property
    def name(self) -> str:
        return "help"

    @property
    def synopsis(self) -> str:
        return "help [-dms] [pattern ...]"

    @property
    def description(self) -> str:
        return "Display information about builtin commands"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the help builtin."""
        # -d/-s/-m are boolean flags (clusterable, e.g. -dm); patterns are
        # operands. The shared helper matches bash's invalid-option message.
        opts, patterns = self.parse_flags(args, shell, flags='dsm')
        if opts is None:
            return 2
        show_descriptions = opts['d']
        show_synopsis_only = opts['s']
        show_manpage = opts['m']

        # Get all builtin instances (no duplicates from aliases)
        registry = shell.builtin_registry
        all_builtins = registry.instances()

        # Filter builtins by patterns if provided
        if patterns:
            matched_builtins = []
            for builtin_obj in all_builtins:
                for pattern in patterns:
                    if fnmatch.fnmatch(builtin_obj.name, pattern):
                        matched_builtins.append(builtin_obj)
                        break

            if not matched_builtins:
                self.error(f"no help topics match `{', '.join(patterns)}'", shell)
                return 1

            builtins_to_show = matched_builtins
        else:
            builtins_to_show = all_builtins

        # Sort builtins by name
        builtins_to_show.sort(key=lambda b: b.name)

        # Display help based on mode
        if patterns and not show_descriptions and not show_synopsis_only:
            # Show detailed help for specific patterns
            for builtin_obj in builtins_to_show:
                self._show_detailed_help(builtin_obj, shell, show_manpage)
                if len(builtins_to_show) > 1:
                    self.write_line("", shell)  # Add blank line between multiple helps
        elif show_descriptions:
            # Show brief descriptions
            self._show_descriptions(builtins_to_show, shell)
        elif show_synopsis_only:
            # Show synopsis only
            self._show_synopsis(builtins_to_show, shell)
        else:
            # Show default listing
            self._show_default_listing(builtins_to_show, shell)

        return 0

    def _show_default_listing(self, builtins: List[Builtin], shell: 'Shell') -> None:
        """Show default help listing similar to bash."""
        # The canonical version is psh.version.__version__ (the same string the
        # `version` builtin and $PSH_VERSION report) — no hardcoded fallback.
        from ..version import __version__
        self.write_line("PSH Shell, version " + __version__, shell)
        self.write_line("These shell commands are defined internally. Type 'help name' to find out more", shell)
        self.write_line("about the function 'name'.", shell)
        self.write_line("", shell)
        self.write_line("Debug options available via 'set -o' or command line:", shell)
        self.write_line("  debug-ast                Show AST before execution", shell)
        self.write_line("  debug-tokens             Show tokens during parsing", shell)
        self.write_line("  debug-scopes             Show variable scope operations", shell)
        self.write_line("  debug-expansion          Show parameter/command expansions", shell)
        self.write_line("  debug-expansion-detail   Show detailed expansion steps", shell)
        self.write_line("  debug-exec               Show execution flow", shell)
        self.write_line("  debug-exec-fork          Show fork/exec details", shell)
        self.write_line("Use 'debug OPTION on/off' or 'debug-ast' for dedicated debug control.", shell)
        self.write_line("", shell)

        # Calculate column layout
        max_width = 79  # Terminal width
        max_name_len = max(len(b.synopsis) for b in builtins) if builtins else 0
        col_width = min(max_name_len + 2, max_width // 2)

        # Group builtins into columns
        for i in range(0, len(builtins), 2):
            line = ""

            # First column
            builtin1 = builtins[i]
            synopsis1 = builtin1.synopsis
            if len(synopsis1) > col_width - 2:
                synopsis1 = synopsis1[:col_width - 5] + "..."
            line += f" {synopsis1:<{col_width-1}}"

            # Second column if available
            if i + 1 < len(builtins):
                builtin2 = builtins[i + 1]
                synopsis2 = builtin2.synopsis
                if len(synopsis2) > col_width - 2:
                    synopsis2 = synopsis2[:col_width - 5] + "..."
                line += f" {synopsis2}"

            self.write_line(line, shell)

    def _show_descriptions(self, builtins: List[Builtin], shell: 'Shell') -> None:
        """Show brief descriptions (-d mode)."""
        for builtin_obj in builtins:
            self.write_line(f"{builtin_obj.name} - {builtin_obj.description}", shell)

    def _show_synopsis(self, builtins: List[Builtin], shell: 'Shell') -> None:
        """Show synopsis only (-s mode)."""
        for builtin_obj in builtins:
            self.write_line(f"{builtin_obj.name}: {builtin_obj.synopsis}", shell)

    def _show_detailed_help(self, builtin_obj: Builtin, shell: 'Shell', manpage_format: bool = False) -> None:
        """Show detailed help for a specific builtin."""
        if manpage_format:
            # Manpage format
            self.write_line("NAME", shell)
            self.write_line(f"    {builtin_obj.name} - {builtin_obj.description}", shell)
            self.write_line("", shell)
            self.write_line("SYNOPSIS", shell)
            self.write_line(f"    {builtin_obj.synopsis}", shell)
            self.write_line("", shell)
            self.write_line("DESCRIPTION", shell)

            # Parse help text for description
            help_text = builtin_obj.help
            lines = help_text.split('\n')
            for line in lines:
                if line.strip():
                    self.write_line(f"    {line}", shell)
                else:
                    self.write_line("", shell)
        else:
            # Standard format
            self.write_line(builtin_obj.help, shell)

    @property
    def help(self) -> str:
        return """help: help [-dms] [pattern ...]
    Display information about builtin commands.

    Displays brief summaries of builtin commands. If PATTERN is
    specified, gives detailed help on all commands matching PATTERN,
    otherwise the list of help topics is printed.

    Options:
      -d    output short description for each topic
      -m    display usage in pseudo-manpage format
      -s    output only a short usage synopsis for each topic matching
            PATTERN

    Arguments:
      PATTERN    Pattern specifying a help topic

    Exit Status:
    Returns success unless PATTERN is not found or an invalid option is given."""
