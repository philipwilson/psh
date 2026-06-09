"""Command builtin for bypassing aliases and functions."""

import os
from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class CommandBuiltin(Builtin):
    """Execute a simple command or display information about commands."""

    @property
    def name(self) -> str:
        return "command"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute command with options or bypass functions/aliases."""
        # Default options
        use_default_path = False
        show_description = False
        verbose_description = False

        # Parse options
        i = 1
        while i < len(args):
            arg = args[i]
            if arg == '-p':
                use_default_path = True
                i += 1
            elif arg == '-v':
                show_description = True
                i += 1
            elif arg == '-V':
                verbose_description = True
                i += 1
            elif arg == '--':
                i += 1
                break
            elif arg.startswith('-'):
                self.error(f"invalid option: {arg}", shell)
                return 2
            else:
                break

        # Check if we have a command to process
        if i >= len(args):
            self.error("usage: command [-pVv] command [arg ...]", shell)
            return 2

        command_name = args[i]
        command_args = args[i:]

        # Handle description modes (-v and -V)
        if show_description or verbose_description:
            return self._show_command_info(command_name, verbose_description, shell)

        # Execute the command, bypassing aliases and functions
        if use_default_path:
            # Use a secure default PATH
            old_path = shell.env.get('PATH', '')
            shell.env['PATH'] = '/usr/bin:/bin'
            try:
                return self._execute_external_command(command_name, command_args, shell)
            finally:
                shell.env['PATH'] = old_path
        else:
            # Check if it's a builtin first
            if command_name in shell.builtin_registry:
                # Execute builtin directly
                builtin_obj = shell.builtin_registry[command_name]
                return builtin_obj.execute(command_args, shell)
            else:
                # Execute external command
                return self._execute_external_command(command_name, command_args, shell)

    def _show_command_info(self, command_name: str, verbose: bool, shell: 'Shell') -> int:
        """Display information about a command."""
        # Check if it's a builtin
        if command_name in shell.builtin_registry:
            if verbose:
                print(f"{command_name} is a shell builtin", file=shell.stdout)
            else:
                print(command_name, file=shell.stdout)
            return 0

        # Check if it's in PATH
        path_dirs = shell.env.get('PATH', '').split(':')
        for dir_path in path_dirs:
            if not dir_path:
                continue
            full_path = os.path.join(dir_path, command_name)
            if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                if verbose:
                    print(f"{command_name} is {full_path}", file=shell.stdout)
                else:
                    print(full_path, file=shell.stdout)
                return 0

        # Command not found
        if verbose:
            print(f"bash: type: {command_name}: not found", file=shell.stderr)
        return 1

    def _execute_external_command(self, command_name: str, args: List[str], shell: 'Shell') -> int:
        """Execute an external command using PSH's external execution strategy."""
        # Use PSH's existing external execution strategy which handles
        # process management, job control, and signal handling correctly
        from ..executor import ExecutionContext, ExternalExecutionStrategy

        # Create execution context
        context = ExecutionContext()

        # Create and use external strategy
        external_strategy = ExternalExecutionStrategy()

        # Execute using PSH's proven external command execution
        return external_strategy.execute(
            command_name, args[1:], shell, context,
            redirects=None, background=False
        )

    @property
    def synopsis(self) -> str:
        return "command [-pVv] command [arg ...]"

    @property
    def description(self) -> str:
        return "Execute a simple command or display information about commands"

    @property
    def help(self) -> str:
        return """command: command [-pVv] command [arg ...]
    Execute a simple command or display information about commands.

    Runs COMMAND with ARGS suppressing shell function lookup, or display
    information about the specified COMMANDs.  Can be used to invoke commands
    on disk when a function with the same name exists.

    Options:
      -p    use a default value for PATH that is guaranteed to find all of
            the standard utilities
      -v    print a description of COMMAND similar to the `type' builtin
      -V    print a more verbose description of each COMMAND

    Exit Status:
    Returns exit status of COMMAND, or failure if COMMAND is not found."""


@builtin
class BuiltinBuiltin(Builtin):
    """Run a shell builtin, bypassing function lookup."""

    @property
    def name(self) -> str:
        return "builtin"

    @property
    def synopsis(self) -> str:
        return "builtin [shell-builtin [arg ...]]"

    @property
    def description(self) -> str:
        return "Execute a shell builtin, bypassing functions with the same name"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        if len(args) < 2:
            return 0  # bash: bare `builtin` succeeds

        name = args[1]
        target = shell.builtin_registry.get(name)
        if target is None:
            self.error(f"{name}: not a shell builtin", shell)
            return 1
        # Run with the builtin's own name as argv[0]
        return target.execute(args[1:], shell)

    @property
    def help(self) -> str:
        return """builtin: builtin [shell-builtin [arg ...]]

    Execute SHELL-BUILTIN with the given arguments, without performing
    function lookup. Lets a function with the same name as a builtin
    call the builtin (e.g. a cd wrapper calling `builtin cd`).

    Exit Status:
    The exit status of SHELL-BUILTIN, or 1 if it is not a shell builtin."""
