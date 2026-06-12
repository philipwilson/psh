"""Directory stack builtin commands (pushd, popd, dirs)."""

import os
from typing import TYPE_CHECKING, List, Optional

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


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
        return "pushd [dir | +N | -N]"

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

        if len(args) == 1:
            # No arguments - swap top two directories
            new_dir = stack.swap_top_two()
            if new_dir is None:
                self.error("directory stack empty", shell)
                return 1

            try:
                os.chdir(new_dir)
                self._update_pwd_vars(new_dir, shell)
                self._print_stack(stack, shell)
                return 0
            except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
                self.error(str(e), shell)
                return 1

        arg = args[1]

        # Handle rotation arguments (+N, -N)
        if arg.startswith('+') or arg.startswith('-'):
            try:
                offset = int(arg)
                if arg.startswith('-'):
                    # Bash-verified: -N counts from the RIGHT, 0-based
                    # (-0 is the bottom of the stack), so the left index
                    # to rotate to the top is size-1-N.
                    offset = stack.size() - 1 + offset
                new_dir = stack.rotate(offset)
                if new_dir is None:
                    self.error("directory stack empty", shell)
                    return 1

                try:
                    os.chdir(new_dir)
                    self._update_pwd_vars(new_dir, shell)
                    self._print_stack(stack, shell)
                    return 0
                except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
                    self.error(str(e), shell)
                    return 1
            except ValueError:
                self.error(f"invalid rotation argument: {arg}", shell)
                return 1

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

    def _update_pwd_vars(self, directory: str, shell: 'Shell'):
        """Update PWD and OLDPWD environment variables."""
        old_pwd = shell.env.get('PWD', os.getcwd())
        shell.env['OLDPWD'] = old_pwd
        shell.env['PWD'] = directory

        # Also update shell state variables
        try:
            shell.state.set_variable('OLDPWD', old_pwd)
            shell.state.set_variable('PWD', directory)
        except (AttributeError, TypeError):
            pass

    def _print_stack(self, stack: DirectoryStack, shell: 'Shell'):
        """Print current directory stack."""
        output = ' '.join(format_directory_for_display(d) for d in stack.stack)
        self.write_line(output, shell)

    @property
    def help(self) -> str:
        return """pushd: pushd [dir | +N | -N]
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
        return "popd [+N | -N]"

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

        if stack.size() <= 1:
            self.error("directory stack empty", shell)
            return 1

        if len(args) == 1:
            # No arguments - pop current directory
            new_dir = stack.pop()
            if new_dir is None:
                self.error("directory stack empty", shell)
                return 1

            try:
                os.chdir(new_dir)
                self._update_pwd_vars(new_dir, shell)
                self._print_stack(stack, shell)
                return 0
            except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
                self.error(str(e), shell)
                return 1

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
                # Popping current directory - change to new top
                new_dir = stack.pop(0)
                if new_dir is None:
                    self.error("directory stack empty", shell)
                    return 1

                try:
                    os.chdir(new_dir)
                    self._update_pwd_vars(new_dir, shell)
                except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
                    self.error(str(e), shell)
                    return 1
            else:
                # Popping non-current directory - don't change directories
                stack.pop(index)

            self._print_stack(stack, shell)
            return 0

        except ValueError:
            self.error(f"invalid index argument: {arg}", shell)
            return 1

    def _update_pwd_vars(self, directory: str, shell: 'Shell'):
        """Update PWD and OLDPWD environment variables."""
        old_pwd = shell.env.get('PWD', os.getcwd())
        shell.env['OLDPWD'] = old_pwd
        shell.env['PWD'] = directory

        # Also update shell state variables
        try:
            shell.state.set_variable('OLDPWD', old_pwd)
            shell.state.set_variable('PWD', directory)
        except (AttributeError, TypeError):
            pass

    def _print_stack(self, stack: DirectoryStack, shell: 'Shell'):
        """Print current directory stack."""
        output = ' '.join(format_directory_for_display(d) for d in stack.stack)
        self.write_line(output, shell)

    @property
    def help(self) -> str:
        return """popd: popd [+N | -N]
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
