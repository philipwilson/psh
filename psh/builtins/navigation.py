"""Directory navigation builtins (cd)."""

import os
from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class CdBuiltin(Builtin):
    """Change directory."""

    @property
    def name(self) -> str:
        return "cd"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Change the current working directory."""
        # Store current directory as the old directory (use logical path if available)
        try:
            pwd = shell.state.get_variable('PWD')
            # Check if PWD is a valid string (not None or mock)
            current_dir = pwd if isinstance(pwd, str) and pwd else os.getcwd()
        except (AttributeError, TypeError):
            # Handle case where shell.state is a mock or doesn't exist
            current_dir = os.getcwd()

        # Parse the -L (logical, default) / -P (physical) options. A bare '-'
        # is NOT an option — it is the "previous directory" operand — and '--'
        # ends option parsing (both handled by the len>1 guard / explicit check).
        physical = False
        i = 1
        while (i < len(args) and args[i].startswith('-')
               and len(args[i]) > 1 and args[i] != '--'):
            flag = args[i]
            if all(c in 'LP' for c in flag[1:]):
                physical = flag[-1] == 'P'  # clustered/repeated: last wins
            else:
                self.error(f"{flag}: invalid option", shell)
                self.write_error_line("cd: usage: cd [-L|-P] [dir]", shell)
                return 2
            i += 1
        if i < len(args) and args[i] == '--':
            i += 1
        operands = args[i:]
        if len(operands) > 1:
            # bash: `cd a b` is an error and does not change directory.
            self.error("too many arguments", shell)
            return 1

        if operands:
            path = operands[0]

            # Handle cd - (change to previous directory)
            if path == '-':
                # The shell variable, not os.environ: OLDPWD=/x cd - and
                # assignments must be honored (bash)
                oldpwd = shell.state.get_variable('OLDPWD')
                if not oldpwd:
                    self.error("OLDPWD not set", shell)
                    return 1
                path = oldpwd
                # Print the directory we're changing to (bash behavior)
                print_new_dir = True
            else:
                print_new_dir = False
        else:
            # No argument - go to home directory. Use the HOME shell
            # variable (HOME=/x; cd must honor the assignment — bash),
            # and error like bash when it is unset.
            path = shell.state.get_variable('HOME')
            if not path:
                self.error("HOME not set", shell)
                return 1
            print_new_dir = False

        # Expand tilde if shell supports it
        if hasattr(shell, '_expand_tilde'):
            path = shell._expand_tilde(path)

        # For relative paths, check CDPATH for directory search
        actual_path = path
        found_in_cdpath = False

        if not os.path.isabs(path):
            # If it's not a relative path starting with . or .., search CDPATH
            if not (path.startswith('./') or path.startswith('../') or path == '.' or path == '..'):
                # Check both shell variables and environment variables for CDPATH
                cdpath = shell.state.get_variable('CDPATH') or shell.env.get('CDPATH', '')
                if cdpath:
                    # Split CDPATH on colons and search each directory
                    for search_dir in cdpath.split(':'):
                        if search_dir == '':
                            # Empty string in CDPATH means current directory
                            search_dir = '.'

                        candidate_path = os.path.join(search_dir, path)
                        if os.path.isdir(candidate_path):
                            actual_path = candidate_path
                            found_in_cdpath = True
                            break

        # bash: `cd ""` (empty operand) is a no-op success — the shell stays
        # in the current directory rather than erroring on chdir(""). CDPATH
        # is still searched first (above), so `CDPATH=/usr cd ""` still
        # changes to /usr; only an operand that CDPATH did not resolve
        # short-circuits here (probe-verified against bash 5.2).
        if actual_path == '' and not found_in_cdpath:
            return 0

        try:
            # Compute the logical new directory path
            if os.path.isabs(actual_path):
                # Absolute path - use as-is
                logical_new_dir = actual_path
            else:
                # Relative path - resolve logically from current PWD
                try:
                    pwd = shell.state.get_variable('PWD')
                    logical_current = pwd if isinstance(pwd, str) and pwd else os.getcwd()
                except (AttributeError, TypeError):
                    logical_current = os.getcwd()
                logical_new_dir = os.path.normpath(os.path.join(logical_current, actual_path))

            # Change to the actual directory
            os.chdir(actual_path)

            # cd -P records the PHYSICAL location (symlinks resolved) as PWD,
            # rather than the logical symlink-named path (bash).
            if physical:
                logical_new_dir = os.getcwd()

            # If found via CDPATH, print the full path (bash behavior)
            if found_in_cdpath:
                self.write_line(logical_new_dir, shell)

            # Update PWD and OLDPWD: both carry the EXPORT attribute in bash
            # (`declare -p PWD` → declare -x ...), and export_variable's observer
            # keeps shell.env in sync — the single env interface, no direct poke
            # (appraisal H3). Routing solely through export_variable also fixes a
            # stale-env leak: the old raw `shell.env['OLDPWD'] = ...` wrote even
            # when a readonly OLDPWD rejected the variable update, so an external
            # child saw the new value where bash keeps the old.
            #
            # The cwd has ALREADY changed (os.chdir succeeded); bash updates
            # PWD and OLDPWD INDEPENDENTLY — a readonly OLDPWD still lets PWD
            # update (and vice versa) — reports the readonly variable, and does
            # NOT undo the directory change. The old order set OLDPWD first and
            # let its ReadonlyVariableError skip the PWD update, so
            # `readonly OLDPWD; cd /` left PWD stale (bash updates it).
            from ..core import ReadonlyVariableError
            readonly_name = None
            for vname, vval in (('OLDPWD', current_dir),
                                ('PWD', logical_new_dir)):
                try:
                    shell.state.export_variable(vname, vval)
                except ReadonlyVariableError as e:
                    readonly_name = e.name
                except (AttributeError, TypeError):
                    # Handle case where shell.state is a mock
                    pass
            if readonly_name is not None:
                # bash reports `NAME: readonly variable` (no `cd:` prefix),
                # rc 1, but the directory change stands.
                self.report_error(f"{readonly_name}: readonly variable", shell)
                return 1

            # Print new directory for cd - command
            if print_new_dir:
                self.write_line(logical_new_dir, shell)

            return 0
        except FileNotFoundError:
            self.error(f"{path}: No such file or directory", shell)
            return 1
        except NotADirectoryError:
            self.error(f"{path}: Not a directory", shell)
            return 1
        except PermissionError:
            self.error(f"{path}: Permission denied", shell)
            return 1
        except OSError as e:
            self.error(str(e), shell)
            return 1

    @property
    def help(self) -> str:
        return """cd: cd [dir]
    Change the current directory to DIR.

    The default DIR is the value of the HOME shell variable.

    The variable CDPATH defines the search path for directories.
    When DIR is a relative path not starting with './' or '../',
    cd searches the directories in CDPATH (colon-separated list)
    for a directory named DIR. If found, the full path is printed.

    Special directories:
      ~     User's home directory
      -     Previous working directory

    Examples:
      cd              # Go to $HOME
      cd /usr/local   # Absolute path
      cd mydir        # Relative path (may search CDPATH)
      cd ./mydir      # Relative path (current dir only)
      cd -            # Previous directory

    Exit Status:
    Returns 0 if the directory is changed; non-zero otherwise."""

    @property
    def synopsis(self) -> str:
        return "cd [dir]"

    @property
    def description(self) -> str:
        return "Change directory"
