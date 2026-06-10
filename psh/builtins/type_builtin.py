"""Type builtin command to display command type information."""

import os
import sys
from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class TypeBuiltin(Builtin):
    """Display information about command types."""

    # Reserved words reported as "keyword" (bash's list)
    SHELL_KEYWORDS = frozenset({
        'if', 'then', 'else', 'elif', 'fi', 'case', 'esac', 'for',
        'select', 'while', 'until', 'do', 'done', 'in', 'function',
        'time', '{', '}', '!', '[[', ']]', 'coproc',
    })

    @property
    def name(self) -> str:
        return "type"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Display information about command types."""
        if len(args) < 2:
            self.error("usage: type [-afptP] name [name ...]", shell)
            return 2

        # Parse options
        show_all = False
        type_only = False
        path_only = False
        force_path = False
        file_only = False

        i = 1
        while i < len(args) and args[i].startswith('-'):
            opt = args[i]
            if opt == '--':
                i += 1
                break
            elif opt == '-a':
                show_all = True
            elif opt == '-t':
                type_only = True
            elif opt == '-p':
                path_only = True
            elif opt == '-P':
                force_path = True
            elif opt == '-f':
                file_only = True
            else:
                self.error(f"invalid option: {opt}", shell)
                return 2
            i += 1

        # Process remaining arguments as names to check
        if i >= len(args):
            self.error("usage: type [-afptP] name [name ...]", shell)
            return 2

        exit_code = 0
        for name in args[i:]:
            found = False

            # Check aliases first (unless -f is specified)
            if not file_only and not force_path and name in shell.alias_manager.aliases:
                alias_value = shell.alias_manager.aliases[name]
                if type_only:
                    print("alias", file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                elif path_only:
                    # Path only mode doesn't show aliases
                    pass
                else:
                    print(f"{name} is aliased to `{alias_value}'",
                          file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                found = True
                if not show_all:
                    continue

            # Check shell keywords (bash order: alias > keyword > function)
            if not force_path and not file_only and name in self.SHELL_KEYWORDS:
                if type_only:
                    print("keyword", file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                elif path_only:
                    pass
                else:
                    print(f"{name} is a shell keyword",
                          file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                found = True
                if not show_all:
                    continue

            # Check functions (unless -P or -f is specified)
            if not force_path and not file_only and name in shell.function_manager.functions:
                if type_only:
                    print("function", file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                elif path_only:
                    # Path only mode doesn't show functions
                    pass
                else:
                    print(f"{name} is a function",
                          file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                    # TODO: Could show function definition here
                found = True
                if not show_all:
                    continue

            # Check builtins (unless -P is specified). Use has() so aliased
            # builtin names (e.g. `readarray` for mapfile) are recognised too.
            if not force_path and shell.builtin_registry.has(name):
                if type_only:
                    print("builtin", file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                elif path_only:
                    # Path only mode doesn't show builtins
                    pass
                else:
                    print(f"{name} is a shell builtin",
                          file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                found = True
                if not show_all:
                    continue

            # Check in PATH
            paths = self._find_in_path(name, shell.env.get('PATH', ''))
            if paths:
                if type_only:
                    print("file", file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                else:
                    for path in paths:
                        print(f"{name} is {path}",
                              file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                        if not show_all:
                            break
                found = True

            # If not found anywhere
            if not found:
                if not type_only and not path_only:
                    self.error(f"{name}: not found", shell)
                exit_code = 1

        return exit_code

    def _find_in_path(self, name: str, path_str: str) -> List[str]:
        """Find all occurrences of a command in PATH."""
        if not path_str:
            return []

        # If name contains a slash, check it directly
        if '/' in name:
            if os.path.isfile(name) and os.access(name, os.X_OK):
                return [os.path.abspath(name)]
            return []

        # Search in PATH
        found_paths = []
        for dir_path in path_str.split(':'):
            if not dir_path:
                continue
            full_path = os.path.join(dir_path, name)
            if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                found_paths.append(full_path)

        return found_paths

    @property
    def help(self) -> str:
        return """type: type [-afptP] name [name ...]

    Display information about command type.

    For each NAME, indicate how it would be interpreted if used as a
    command name.

    Options:
      -a    display all locations containing an executable named NAME;
            includes aliases, builtins, and functions, if and only if
            the `-p' option is not also used
      -f    suppress shell function lookup
      -P    force a PATH search for each NAME, even if it is an alias,
            builtin, or function, and returns the name of the disk file
            that would be executed
      -p    returns either the name of the disk file that would be executed,
            or nothing if `type -t NAME' would not return `file'
      -t    output a single word which is one of `alias', `builtin',
            `file', `function', or `keyword', if NAME is an alias, shell
            builtin, disk file, shell function, or shell reserved word,
            respectively

    Arguments:
      NAME  Command name to be interpreted.

    Exit Status:
    Returns success if all of the NAMEs are found; fails if any are not found."""
