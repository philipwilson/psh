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
        # Parse options
        show_descriptions = False
        show_synopsis_only = False
        show_manpage = False
        patterns = []

        i = 1
        while i < len(args):
            arg = args[i]
            if arg.startswith('-') and len(arg) > 1 and not arg.startswith('--'):
                # Parse option flags
                for flag in arg[1:]:
                    if flag == 'd':
                        show_descriptions = True
                    elif flag == 's':
                        show_synopsis_only = True
                    elif flag == 'm':
                        show_manpage = True
                    else:
                        self.error(f"invalid option -- '{flag}'", shell)
                        self._show_usage(shell)
                        return 2
            elif arg == '--':
                # End of options
                patterns.extend(args[i+1:])
                break
            else:
                # Pattern argument
                patterns.append(arg)
            i += 1

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
                    print(file=shell.stdout)  # Add blank line between multiple helps
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

    def _show_usage(self, shell: 'Shell') -> None:
        """Show usage information."""
        print(f"Usage: {self.synopsis}", file=shell.stderr)
        print("Options:", file=shell.stderr)
        print("  -d    output short description for each topic", file=shell.stderr)
        print("  -m    display usage in pseudo-manpage format", file=shell.stderr)
        print("  -s    output only a short usage synopsis for each topic", file=shell.stderr)

    def _show_default_listing(self, builtins: List[Builtin], shell: 'Shell') -> None:
        """Show default help listing similar to bash."""
        output = shell.stdout

        # Get version from shell state or fallback to hardcoded version
        version = getattr(shell.state, 'version', None) or shell.state.get_variable('PSH_VERSION', '0.54.0')
        print("PSH Shell, version " + str(version), file=output)
        print("These shell commands are defined internally. Type 'help name' to find out more", file=output)
        print("about the function 'name'.", file=output)
        print(file=output)
        print("Debug options available via 'set -o' or command line:", file=output)
        print("  debug-ast                Show AST before execution", file=output)
        print("  debug-tokens             Show tokens during parsing", file=output)
        print("  debug-scopes             Show variable scope operations", file=output)
        print("  debug-expansion          Show parameter/command expansions", file=output)
        print("  debug-expansion-detail   Show detailed expansion steps", file=output)
        print("  debug-exec               Show execution flow", file=output)
        print("  debug-exec-fork          Show fork/exec details", file=output)
        print("Use 'debug OPTION on/off' or 'debug-ast' for dedicated debug control.", file=output)
        print(file=output)

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

            print(line, file=output)

    def _show_descriptions(self, builtins: List[Builtin], shell: 'Shell') -> None:
        """Show brief descriptions (-d mode)."""
        output = shell.stdout

        for builtin_obj in builtins:
            print(f"{builtin_obj.name} - {builtin_obj.description}", file=output)

    def _show_synopsis(self, builtins: List[Builtin], shell: 'Shell') -> None:
        """Show synopsis only (-s mode)."""
        output = shell.stdout

        for builtin_obj in builtins:
            print(f"{builtin_obj.name}: {builtin_obj.synopsis}", file=output)

    def _show_detailed_help(self, builtin_obj: Builtin, shell: 'Shell', manpage_format: bool = False) -> None:
        """Show detailed help for a specific builtin."""
        output = shell.stdout

        if manpage_format:
            # Manpage format
            print("NAME", file=output)
            print(f"    {builtin_obj.name} - {builtin_obj.description}", file=output)
            print(file=output)
            print("SYNOPSIS", file=output)
            print(f"    {builtin_obj.synopsis}", file=output)
            print(file=output)
            print("DESCRIPTION", file=output)

            # Parse help text for description
            help_text = builtin_obj.help
            lines = help_text.split('\n')
            for line in lines:
                if line.strip():
                    print(f"    {line}", file=output)
                else:
                    print(file=output)
        else:
            # Standard format
            print(builtin_obj.help, file=output)

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
