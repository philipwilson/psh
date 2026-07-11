"""Directory stack builtin commands (pushd, popd, dirs)."""

import os
from typing import TYPE_CHECKING, List, Optional

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


def _chdir_or_error(builtin: 'Builtin', target: str, shell: 'Shell') -> bool:
    """os.chdir(*target*), reporting a bash-style diagnostic on failure.

    Returns True on success, False on failure (message already printed). Shared
    by pushd/popd so a failed cd never leaves the stack out of sync with the
    cwd — callers mutate the stack only after this returns True.
    """
    try:
        os.chdir(target)
        return True
    except FileNotFoundError:
        builtin.error(f"{target}: No such file or directory", shell)
    except NotADirectoryError:
        builtin.error(f"{target}: Not a directory", shell)
    except PermissionError:
        builtin.error(f"{target}: Permission denied", shell)
    except OSError as e:
        builtin.error(f"{target}: {e.strerror or e}", shell)
    return False


def format_directory_for_display(directory: str, no_tilde: bool = False) -> str:
    """Render a stack entry for display, abbreviating $HOME as ``~``.

    Shared by pushd/popd/dirs. Uses ``home + os.sep`` for the prefix test so a
    sibling like ``/home/userfoo`` is not mangled into ``~foo`` (the earlier
    pushd/popd copies used a bare ``startswith(home)`` and had that bug).
    """
    if no_tilde:
        return directory

    home = os.path.expanduser('~')
    if directory == home:
        return '~'
    elif directory.startswith(home + os.sep):
        return '~' + directory[len(home):]
    return directory


class DirectoryStack:
    """Manages the directory stack for pushd/popd/dirs commands."""

    def __init__(self):
        self.stack = []  # Stack of directories, index 0 is current

    def initialize(self, current_dir: str):
        """Initialize stack with current directory."""
        self.stack = [current_dir]

    def copy(self) -> 'DirectoryStack':
        """Independent copy for a subshell-style child (ShellState.adopt):
        (dirs) shows the parent's stack; a child's pushd must not leak back.
        """
        new = DirectoryStack()
        new.stack = list(self.stack)
        return new

    def push(self, directory: str) -> str:
        """Push directory onto stack and return new current directory."""
        self.stack.insert(0, directory)
        return directory

    def pop(self, index: Optional[int] = None) -> Optional[str]:
        """Pop directory from stack. Returns new current directory or None if empty."""
        if len(self.stack) <= 1:
            return None  # Can't pop the last directory

        if index is None:
            # Pop current directory (index 0)
            self.stack.pop(0)
            return self.stack[0] if self.stack else None
        else:
            # Pop specific index
            if 0 <= index < len(self.stack):
                self.stack.pop(index)
                return self.stack[0] if self.stack else None
            return None

    def rotate(self, offset: int) -> Optional[str]:
        """Rotate stack by offset. Positive rotates left, negative rotates right."""
        if len(self.stack) <= 1:
            return None

        # Normalize offset to stack size
        offset = offset % len(self.stack)
        if offset == 0:
            return self.stack[0]  # No change

        # Rotate the stack
        self.stack = self.stack[offset:] + self.stack[:offset]
        return self.stack[0]

    def swap_top_two(self) -> Optional[str]:
        """Swap top two directories on stack."""
        if len(self.stack) < 2:
            return None

        self.stack[0], self.stack[1] = self.stack[1], self.stack[0]
        return self.stack[0]

    def clear(self):
        """Clear stack except current directory."""
        if self.stack:
            current = self.stack[0]
            self.stack = [current]

    def get_directory(self, index: int) -> Optional[str]:
        """Get directory at specific index."""
        if 0 <= index < len(self.stack):
            return self.stack[index]
        return None

    def size(self) -> int:
        """Get stack size."""
        return len(self.stack)

    def update_current(self, directory: str):
        """Update current directory (index 0) without changing stack structure."""
        if self.stack:
            self.stack[0] = directory
        else:
            self.stack = [directory]


@builtin
class PushdBuiltin(Builtin):
    """Push directory onto stack and change to it."""

    @property
    def name(self) -> str:
        return "pushd"

    @property
    def synopsis(self) -> str:
        return "pushd [-n] [dir | +N | -N]"

    @property
    def description(self) -> str:
        return "Add directories to stack and change directory"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute pushd command."""
        # Initialize directory stack if not present
        if not hasattr(shell.state, 'directory_stack'):
            shell.state.directory_stack = DirectoryStack()
            # Use PWD if available to preserve logical path, otherwise use physical path
            current_dir = shell.env.get('PWD', os.getcwd())
            shell.state.directory_stack.initialize(current_dir)

        stack = shell.state.directory_stack

        # -n manipulates the stack WITHOUT changing directory (bash).
        if len(args) > 1 and args[1] == '-n':
            return self._pushd_no_cd(args[2:], stack, shell)

        if len(args) == 1:
            # No arguments - swap top two directories. TRANSACTIONAL: chdir to
            # the would-be new top FIRST, and only swap if that succeeds — a
            # failed chdir must leave stack[0] == cwd (the core invariant). The
            # old order swapped first, so a bad entry (e.g. planted by
            # `pushd -n /nonexistent`) ended up at stack[0] while cwd was
            # unchanged.
            if stack.size() < 2:
                self.error("no other directory", shell)
                return 1
            target = stack.stack[1]
            if not _chdir_or_error(self, target, shell):
                return 1
            stack.swap_top_two()
            self._update_pwd_vars(target, shell)
            self._print_stack(stack, shell)
            return 0

        arg = args[1]

        # Handle rotation arguments (+N, -N)
        if arg.startswith('+') or arg.startswith('-'):
            try:
                offset = int(arg)
            except ValueError:
                self.error(f"invalid rotation argument: {arg}", shell)
                return 1
            if stack.size() <= 1:
                # bash uses "directory stack empty" for the +N/-N rotate form
                # (and "no other directory" for the no-arg swap above).
                self.error("directory stack empty", shell)
                return 1
            if arg.startswith('-'):
                # Bash-verified: -N counts from the RIGHT, 0-based
                # (-0 is the bottom of the stack), so the left index
                # to rotate to the top is size-1-N.
                offset = stack.size() - 1 + offset
            # TRANSACTIONAL: the entry that would become the new top is
            # stack[offset % size]; chdir to it FIRST, rotate only on success.
            target = stack.stack[offset % stack.size()]
            if not _chdir_or_error(self, target, shell):
                return 1
            stack.rotate(offset)
            self._update_pwd_vars(target, shell)
            self._print_stack(stack, shell)
            return 0

        # Regular directory argument
        directory = arg

        # Expand tilde
        if directory.startswith('~'):
            if hasattr(shell.expansion_manager, 'expand_tilde'):
                directory = shell.expansion_manager.expand_tilde(directory)
            else:
                directory = os.path.expanduser(directory)

        # Convert to absolute path
        if not os.path.isabs(directory):
            directory = os.path.abspath(directory)

        try:
            # Get current directory from PWD to preserve logical path
            current_dir = shell.env.get('PWD', os.getcwd())

            # Change to directory first to validate it exists and is accessible
            os.chdir(directory)

            # Ensure current directory is on stack before pushing new one
            # In bash, stack[0] always represents the CWD
            if not stack.stack:
                stack.initialize(current_dir)

            # Push new directory onto stack (becomes new CWD at stack[0])
            stack.push(directory)

            # Update PWD variables
            self._update_pwd_vars(directory, shell)

            # Print the stack
            self._print_stack(stack, shell)

            return 0
        except FileNotFoundError:
            self.error(f"{directory}: No such file or directory", shell)
            return 1
        except NotADirectoryError:
            self.error(f"{directory}: Not a directory", shell)
            return 1
        except PermissionError:
            self.error(f"{directory}: Permission denied", shell)
            return 1
        except OSError as e:
            self.error(str(e), shell)
            return 1

    def _pushd_no_cd(self, args: List[str], stack: DirectoryStack,
                     shell: 'Shell') -> int:
        """``pushd -n``: manipulate the stack without changing directory.

        With a directory argument bash inserts it just BELOW the top of the
        stack (the current directory stays on top) and does NOT verify the
        path exists. With no argument the swap is suppressed (no change).
        A ``+N``/``-N`` rotates the stack; psh rotates cleanly and does not
        reproduce bash's duplicate-producing ``pushd -n +N`` quirk.
        """
        if not args:
            self._print_stack(stack, shell)
            return 0

        arg = args[0]
        if arg.startswith('+') or arg.startswith('-'):
            try:
                offset = int(arg)
            except ValueError:
                self.error(f"invalid rotation argument: {arg}", shell)
                return 1
            if arg.startswith('-'):
                offset = stack.size() - 1 + offset
            if stack.rotate(offset) is None:
                self.error("directory stack empty", shell)
                return 1
            self._print_stack(stack, shell)
            return 0

        directory = arg
        if directory.startswith('~'):
            if hasattr(shell.expansion_manager, 'expand_tilde'):
                directory = shell.expansion_manager.expand_tilde(directory)
            else:
                directory = os.path.expanduser(directory)
        if not os.path.isabs(directory):
            directory = os.path.abspath(directory)

        if not stack.stack:
            stack.initialize(shell.env.get('PWD', os.getcwd()))
        stack.stack.insert(1, directory)
        self._print_stack(stack, shell)
        return 0

    def _update_pwd_vars(self, directory: str, shell: 'Shell'):
        """Update PWD and OLDPWD environment variables."""
        old_pwd = shell.env.get('PWD', os.getcwd())

        # Update the exported PWD/OLDPWD shell variables (bash's declare -x
        # PWD/OLDPWD); export_variable's observer keeps shell.env in sync — the
        # single env interface, no direct poke (appraisal H3).
        shell.state.export_variable('OLDPWD', old_pwd)
        shell.state.export_variable('PWD', directory)

    def _print_stack(self, stack: DirectoryStack, shell: 'Shell'):
        """Print current directory stack."""
        output = ' '.join(format_directory_for_display(d) for d in stack.stack)
        self.write_line(output, shell)

    @property
    def help(self) -> str:
        return """pushd: pushd [-n] [dir | +N | -N]
    Add directories to stack and change directory.

    Arguments:
        dir     Change to DIR and add it to the directory stack
        +N      Rotate stack so Nth entry from left is on top
        -N      Rotate stack so Nth entry from right is on top

    With no arguments, exchanges the top two directories.

    The directory stack is displayed with the most recent directory first.

    Exit Status:
    Returns 0 unless an invalid argument is given or the directory
    change fails."""


@builtin
class PopdBuiltin(Builtin):
    """Pop directory from stack and change to it."""

    @property
    def name(self) -> str:
        return "popd"

    @property
    def synopsis(self) -> str:
        return "popd [-n] [+N | -N]"

    @property
    def description(self) -> str:
        return "Remove directories from stack and change directory"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute popd command."""
        # Initialize directory stack if not present
        if not hasattr(shell.state, 'directory_stack'):
            shell.state.directory_stack = DirectoryStack()
            # Use PWD if available to preserve logical path, otherwise use physical path
            current_dir = shell.env.get('PWD', os.getcwd())
            shell.state.directory_stack.initialize(current_dir)

        stack = shell.state.directory_stack

        # -n removes from the stack WITHOUT changing directory (bash).
        if len(args) > 1 and args[1] == '-n':
            return self._popd_no_cd(args[2:], stack, shell)

        if stack.size() <= 1:
            self.error("directory stack empty", shell)
            return 1

        if len(args) == 1:
            # No arguments - pop current directory. TRANSACTIONAL: the new top
            # would be stack[1]; chdir there FIRST and pop only on success, so a
            # failed chdir leaves the stack intact and stack[0] == cwd.
            target = stack.stack[1]
            if not _chdir_or_error(self, target, shell):
                return 1
            stack.pop()
            self._update_pwd_vars(target, shell)
            self._print_stack(stack, shell)
            return 0

        # Handle index arguments (+N, -N)
        arg = args[1]
        if not (arg.startswith('+') or arg.startswith('-')):
            self.error(f"invalid argument: {arg}", shell)
            return 1

        try:
            index = int(arg)
            if arg.startswith('-'):
                # Bash-verified: -N means Nth from the RIGHT, 0-based
                # (-0 is the bottom of the stack), so the left index is
                # size-1-N.
                index = stack.size() - 1 + index
            else:
                # +N means Nth from left
                index = index

            if index < 0 or index >= stack.size():
                self.error(f"directory stack index out of range: {arg}", shell)
                return 1

            if index == 0:
                # Popping the current directory - change to new top FIRST
                # (transactional): chdir to stack[1], pop only on success.
                target = stack.stack[1]
                if not _chdir_or_error(self, target, shell):
                    return 1
                stack.pop(0)
                self._update_pwd_vars(target, shell)
            else:
                # Popping non-current directory - don't change directories
                stack.pop(index)

            self._print_stack(stack, shell)
            return 0

        except ValueError:
            self.error(f"invalid index argument: {arg}", shell)
            return 1

    def _popd_no_cd(self, args: List[str], stack: DirectoryStack,
                    shell: 'Shell') -> int:
        """``popd -n``: remove from the stack without changing directory.

        With no argument bash removes the entry just below the top (index 1),
        leaving the current directory on top and performing no cd. ``+N``/
        ``-N`` remove the indexed entry (from the left / right) without a cd.
        """
        if not args:
            if stack.size() < 2:
                self.error("directory stack empty", shell)
                return 1
            stack.stack.pop(1)
            self._print_stack(stack, shell)
            return 0

        arg = args[0]
        if not (arg.startswith('+') or arg.startswith('-')):
            self.error(f"invalid argument: {arg}", shell)
            return 1
        try:
            index = int(arg)
        except ValueError:
            self.error(f"invalid index argument: {arg}", shell)
            return 1
        if arg.startswith('-'):
            index = stack.size() - 1 + index
        if index < 0 or index >= stack.size():
            self.error(f"directory stack index out of range: {arg}", shell)
            return 1
        stack.stack.pop(index)
        self._print_stack(stack, shell)
        return 0

    def _update_pwd_vars(self, directory: str, shell: 'Shell'):
        """Update PWD and OLDPWD environment variables."""
        old_pwd = shell.env.get('PWD', os.getcwd())

        # Update the exported PWD/OLDPWD shell variables (bash's declare -x
        # PWD/OLDPWD); export_variable's observer keeps shell.env in sync — the
        # single env interface, no direct poke (appraisal H3).
        shell.state.export_variable('OLDPWD', old_pwd)
        shell.state.export_variable('PWD', directory)

    def _print_stack(self, stack: DirectoryStack, shell: 'Shell'):
        """Print current directory stack."""
        output = ' '.join(format_directory_for_display(d) for d in stack.stack)
        self.write_line(output, shell)

    @property
    def help(self) -> str:
        return """popd: popd [-n] [+N | -N]
    Remove directories from stack and change directory.

    Arguments:
        +N      Remove Nth entry from left of stack (counting from 0)
        -N      Remove Nth entry from right of stack

    With no arguments, removes the top directory from the stack and
    changes to the new top directory.

    Exit Status:
    Returns 0 unless an invalid argument is given, the directory
    stack is empty, or the directory change fails."""


@builtin
class DirsBuiltin(Builtin):
    """Display directory stack."""

    @property
    def name(self) -> str:
        return "dirs"

    @property
    def synopsis(self) -> str:
        return "dirs [-clpv] [+N | -N]"

    @property
    def description(self) -> str:
        return "Display directory stack"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute dirs command."""
        # Initialize directory stack if not present
        if not hasattr(shell.state, 'directory_stack'):
            shell.state.directory_stack = DirectoryStack()
            # Use PWD if available to preserve logical path, otherwise use physical path
            current_dir = shell.env.get('PWD', os.getcwd())
            shell.state.directory_stack.initialize(current_dir)

        stack = shell.state.directory_stack

        # Parse options. NOTE: deliberately NOT parse_flags() — `-N` index
        # arguments (e.g. `dirs -1`) collide with single-dash flag syntax,
        # and bash itself rejects clustered flags here (`dirs -lv` is
        # "invalid number" in bash 5.2), so the shared clustering helper
        # would parse MORE than bash does.
        clear_stack = False
        vertical_format = False
        per_line = False
        no_tilde = False
        show_index = None

        i = 1
        while i < len(args):
            arg = args[i]
            if arg.startswith('-') and len(arg) > 1 and not arg[1:].isdigit():
                # Option flags
                for flag in arg[1:]:
                    if flag == 'c':
                        clear_stack = True
                    elif flag == 'v':
                        vertical_format = True
                    elif flag == 'p':
                        per_line = True
                    elif flag == 'l':
                        no_tilde = True
                    else:
                        self.error(f"invalid option: -{flag}", shell)
                        return 1
            elif arg.startswith('+') or arg.startswith('-'):
                # Index argument
                try:
                    show_index = int(arg)
                    if arg.startswith('-'):
                        # Bash-verified: -N means Nth from the RIGHT,
                        # 0-based (-0 is the bottom of the stack), so the
                        # left index is size-1-N.
                        show_index = stack.size() - 1 + show_index

                    if show_index < 0 or show_index >= stack.size():
                        self.error(f"directory stack index out of range: {arg}", shell)
                        return 1
                except ValueError:
                    self.error(f"invalid index argument: {arg}", shell)
                    return 1
            else:
                self.error(f"invalid argument: {arg}", shell)
                return 1
            i += 1

        # Handle clear operation
        if clear_stack:
            stack.clear()
            return 0

        # Handle index display
        if show_index is not None:
            directory = stack.get_directory(show_index)
            if directory is None:
                self.error(f"directory stack index out of range: {show_index}", shell)
                return 1

            formatted = format_directory_for_display(directory, no_tilde)
            self.write_line(formatted, shell)
            return 0

        # Display stack
        if vertical_format:
            # bash separates the index and path with two spaces, not a tab
            for i, directory in enumerate(stack.stack):
                formatted = format_directory_for_display(directory, no_tilde)
                self.write_line(f" {i}  {formatted}", shell)
        elif per_line:
            # -p: one entry per line, no indices (bash-verified)
            for directory in stack.stack:
                self.write_line(format_directory_for_display(directory, no_tilde), shell)
        else:
            # Horizontal format
            directories = [format_directory_for_display(d, no_tilde) for d in stack.stack]
            output = ' '.join(directories)
            self.write_line(output, shell)

        return 0

    @property
    def help(self) -> str:
        return """dirs: dirs [-clpv] [+N | -N]
    Display directory stack.

    Options:
        -c      Clear the directory stack by deleting all entries
        -l      List in long format; do not use ~ to indicate HOME
        -p      List one directory per line
        -v      List in vertical format with indices
        +N      Display Nth entry from left of stack (counting from 0)
        -N      Display Nth entry from right of stack

    With no options, displays the directory stack with the most recent
    directory first.

    Exit Status:
    Returns 0 unless an invalid option is given."""
