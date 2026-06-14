"""Command builtin for bypassing aliases and functions."""

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

        # bash: bare `command` (or `command -v` with no names) succeeds
        if i >= len(args):
            return 0

        command_name = args[i]
        command_args = args[i:]

        # Handle description modes (-v and -V)
        if show_description or verbose_description:
            return self._show_command_info(args[i:], verbose_description, shell)

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
            builtin_obj = shell.builtin_registry.get(command_name)
            if builtin_obj is not None:
                # Execute builtin directly
                return builtin_obj.execute(command_args, shell)
            else:
                # Execute external command
                return self._execute_external_command(command_name, command_args, shell)

    def _show_command_info(self, names: List[str], verbose: bool, shell: 'Shell') -> int:
        """Display information about commands (bash `command -v` / `-V`).

        Lookup order follows `type`: alias > keyword > function > builtin >
        PATH. Returns 0 if at least one name was found, 1 otherwise (bash).
        """
        from .type_builtin import TypeBuiltin

        any_found = False
        for name in names:
            # Aliases (command -v prints the alias definition line)
            alias_value = shell.alias_manager.get_alias(name)
            if alias_value is not None:
                if verbose:
                    self.write_line(f"{name} is aliased to `{alias_value}'", shell)
                else:
                    escaped_value = alias_value.replace("'", "'\"'\"'")
                    self.write_line(f"alias {name}='{escaped_value}'", shell)
                any_found = True
                continue

            # Shell keywords
            if name in TypeBuiltin.SHELL_KEYWORDS:
                if verbose:
                    self.write_line(f"{name} is a shell keyword", shell)
                else:
                    self.write_line(name, shell)
                any_found = True
                continue

            # Functions (-V prints the definition, like `declare -f`)
            func = shell.function_manager.get_function(name)
            if func is not None:
                if verbose:
                    from ..utils.shell_formatter import ShellFormatter
                    self.write_line(f"{name} is a function", shell)
                    self.write_line(
                        f"{name} () " + ShellFormatter.format_function_body(func),
                        shell)
                else:
                    self.write_line(name, shell)
                any_found = True
                continue

            # Builtins
            if shell.builtin_registry.has(name):
                if verbose:
                    self.write_line(f"{name} is a shell builtin", shell)
                else:
                    self.write_line(name, shell)
                any_found = True
                continue

            # PATH search (also handles names containing a slash)
            paths = TypeBuiltin._find_in_path(name, shell.env.get('PATH', ''))
            if paths:
                if verbose:
                    self.write_line(f"{name} is {paths[0]}", shell)
                else:
                    self.write_line(paths[0], shell)
                any_found = True
                continue

            # Not found: -v is silent, -V prints an error (bash)
            if verbose:
                self.error(f"{name}: not found", shell)

        return 0 if any_found else 1

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
