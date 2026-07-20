"""Directory navigation builtins (cd) and the shared PWD/OLDPWD machinery.

This module owns the TWO primitives every directory-changing builtin shares:

* :func:`current_logical_dir` — the one READ of "where are we?" (the logical
  ``PWD`` variable, preserving symlink-named paths, with env/physical
  fallbacks). ``cd``, ``pushd``, ``popd`` and ``dirs`` all consult it; they
  used to read different sources (shell variable vs ``shell.env``).
* :func:`update_pwd_vars` — the one WRITER of ``PWD``/``OLDPWD`` after a
  successful chdir, with bash's readonly semantics. The readonly fix used to
  live only in ``cd`` while ``pushd``/``popd`` carried divergent copies
  (appraisal r19 H2 — the "three updaters" defect factory in miniature).
"""
import os
from typing import TYPE_CHECKING, List

from ..core import ReadonlyVariableError
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


def current_logical_dir(shell: 'Shell') -> str:
    """The shell's logical current directory.

    The ``PWD`` shell variable is authoritative — cd/pushd/popd maintain it,
    and it preserves the symlink-named (logical) path where ``os.getcwd()``
    would return the resolved physical one. Falls back to the environment,
    then the physical cwd. This is the single cwd READ used by ``cd`` and
    the directory-stack builtins.
    """
    pwd = shell.state.get_variable('PWD')
    if isinstance(pwd, str) and pwd:
        return pwd
    return shell.env.get('PWD') or os.getcwd()


def update_pwd_vars(builtin: Builtin, shell: 'Shell',
                    new_logical: str, old_logical: str) -> bool:
    """Update OLDPWD and PWD after a successful directory change.

    The ONE updater shared by ``cd``, ``pushd`` and ``popd``. Both variables
    carry the EXPORT attribute in bash (``declare -p PWD`` → declare -x ...),
    and export_variable's observer keeps shell.env in sync — the single env
    interface, no direct poke (appraisal H3). Routing solely through
    export_variable also avoids a stale-env leak: a raw ``shell.env[...]``
    write would update the environment even when a readonly variable
    rejected the shell-variable update, so an external child would see the
    new value where bash keeps the old.

    The cwd has ALREADY changed when this runs (os.chdir succeeded); bash
    updates PWD and OLDPWD INDEPENDENTLY — a readonly OLDPWD still lets PWD
    update (and vice versa) — reports ``NAME: readonly variable`` BARE
    (``report_error``: no builtin-name prefix; probe-pinned for cd AND
    pushd/popd), and the directory change STANDS. Returns True when both
    updated, False after reporting a readonly failure — the caller then
    fails with rc 1 but must NOT undo the chdir.
    """
    readonly_name = None
    for vname, vval in (('OLDPWD', old_logical), ('PWD', new_logical)):
        try:
            shell.state.export_variable(vname, vval)
        except ReadonlyVariableError as e:
            readonly_name = e.name
    if readonly_name is not None:
        builtin.report_error(f"{readonly_name}: readonly variable", shell)
        return False
    return True


@builtin
class CdBuiltin(Builtin):
    """Change directory."""

    @property
    def name(self) -> str:
        return "cd"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Change the current working directory."""
        # Store current directory as the old directory (the shared logical
        # cwd read — the PWD variable when set, else env/physical fallback).
        current_dir = current_logical_dir(shell)

        # Parse the -L (logical, default) / -P (physical) options via the shared
        # ordered walker: a bare '-' is NOT an option — it is the "previous
        # directory" operand (parse_flags_ordered's len==1 guard) — and '--'
        # ends option parsing. Order matters: -L/-P is last-wins (`cd -LP` is
        # physical, `cd -PL` logical), so we replay the events in order. On a
        # bad flag char bash reports the offending CHAR (`cd -Lx` -> "-x") plus
        # the usage line (rc 2); parse_flags_ordered handles both — the old
        # loop reported the whole cluster.
        events, operands = self.parse_flags_ordered(args, shell, flags='LP')
        if events is None:
            return 2
        physical = False
        for ch, _ in events:
            physical = (ch == 'P')  # last of -L/-P wins
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

        # For relative paths, check CDPATH for directory search
        actual_path = path
        found_in_cdpath = False

        if not os.path.isabs(path):
            # If it's not a relative path starting with . or .., search CDPATH
            if not (path.startswith('./') or path.startswith('../') or path == '.' or path == '..'):
                # CDPATH is read from the VARIABLE (tri-state), never the child-env
                # projection: a declared-unset `local CDPATH` must shadow an outer
                # export (bash NOCD), not resurrect it (#20 H13 / CV2).
                cdpath = shell.state.get_variable('CDPATH')
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
                # Relative path - resolve logically from the current PWD
                logical_new_dir = os.path.normpath(
                    os.path.join(current_dir, actual_path))

            # Change to the actual directory
            os.chdir(actual_path)

            # cd -P records the PHYSICAL location (symlinks resolved) as PWD,
            # rather than the logical symlink-named path (bash).
            if physical:
                logical_new_dir = os.getcwd()

            # If found via CDPATH, print the full path (bash behavior)
            if found_in_cdpath:
                self.write_line(logical_new_dir, shell)

            # Print the new directory for `cd -` BEFORE attempting the
            # variable updates: bash prints the directory first and THEN the
            # readonly diagnostic when PWD/OLDPWD is readonly (probe: `cd /tmp;
            # cd /var; readonly PWD; cd -` -> "/tmp" then the error, rc 1).
            if print_new_dir:
                self.write_line(logical_new_dir, shell)

            # The shared updater (see module docstring): independent PWD and
            # OLDPWD updates, bare readonly report, chdir stands. rc 1 on a
            # readonly failure — bash's cd fails while keeping the new cwd.
            if not update_pwd_vars(self, shell, logical_new_dir, current_dir):
                return 1

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
        return """cd: cd [-L|-P] [dir]
    Change the current directory to DIR.

    The default DIR is the value of the HOME shell variable.

    Options:
      -L    follow symbolic links: PWD keeps the logical path (default)
      -P    use the physical directory structure: PWD has symlinks resolved

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
        # Includes the option group so parse_flags_ordered's usage line reads
        # `cd: usage: cd [-L|-P] [dir]` on a bad option (bash-shaped).
        return "cd [-L|-P] [dir]"

    @property
    def description(self) -> str:
        return "Change directory"
