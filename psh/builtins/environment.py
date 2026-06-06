"""Environment and variable management builtins (env, export, set, unset)."""

import io
import os
import shlex
import sys
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from ..core import ReadonlyVariableError
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class EnvBuiltin(Builtin):
    """Display or modify environment variables."""

    @property
    def name(self) -> str:
        return "env"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Display environment variables or run command with modified environment."""
        # Keep shell.env in sync with exported scope variables first.
        shell.state.scope_manager.sync_exports_to_environment(shell.env)

        if len(args) == 1:
            self._print_environment(shell.env, shell)
            return 0

        parsed = self._parse_invocation(args[1:], shell)
        if parsed is None:
            return 1
        clear_env, unset_names, assignments, command_args = parsed

        env_map = {} if clear_env else shell.env.copy()
        for name in unset_names:
            env_map.pop(name, None)
        env_map.update(assignments)

        # No command: print environment with temporary overrides.
        if not command_args:
            self._print_environment(env_map, shell)
            return 0

        # Command mode: run in isolated child shell so command-side effects
        # (e.g., export/unset/cd builtins) do not leak into parent shell state.
        command_text = " ".join(shlex.quote(arg) for arg in command_args)

        from ..core import VarAttributes
        from ..shell import Shell

        child_shell = Shell(parent_shell=shell)
        child_shell.state.options.update(shell.state.options)
        child_shell.stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
        child_shell.stderr = shell.stderr if hasattr(shell, 'stderr') else sys.stderr
        child_shell.stdin = shell.stdin if hasattr(shell, 'stdin') else sys.stdin

        self._configure_child_export_attributes(child_shell, clear_env, unset_names)
        child_shell.env.clear()
        child_shell.env.update(env_map)

        # Apply env overrides to child's exported environment only.
        for key, value in assignments.items():
            child_shell.state.scope_manager.set_variable(
                key, value, attributes=VarAttributes.EXPORT, local=False
            )
            child_shell.env[key] = value

        fd_backups = self._bind_process_fds_to_streams(child_shell)
        try:
            return child_shell.run_command(command_text, add_to_history=False)
        finally:
            self._restore_process_fds(fd_backups)

    def _parse_invocation(
        self, argv: List[str], shell: 'Shell'
    ) -> Optional[Tuple[bool, List[str], Dict[str, str], List[str]]]:
        """Parse env options, assignments, and command arguments."""
        clear_env = False
        unset_names: List[str] = []
        assignments: Dict[str, str] = {}
        idx = 0

        # Parse leading options.
        while idx < len(argv):
            arg = argv[idx]
            if arg == '--':
                idx += 1
                break
            if arg in ('-', '-i'):
                clear_env = True
                idx += 1
                continue
            if arg == '-u':
                if idx + 1 >= len(argv):
                    self.error("option requires an argument -- 'u'", shell)
                    return None
                unset_names.append(argv[idx + 1])
                idx += 2
                continue
            if arg.startswith('-u') and len(arg) > 2:
                unset_names.append(arg[2:])
                idx += 1
                continue
            if arg.startswith('-'):
                self.error(f"invalid option: {arg}", shell)
                return None
            break

        # Parse leading NAME=VALUE assignments after options.
        while idx < len(argv) and self._is_env_assignment(argv[idx]):
            key, value = argv[idx].split('=', 1)
            assignments[key] = value
            idx += 1

        return clear_env, unset_names, assignments, argv[idx:]

    def _configure_child_export_attributes(
        self, shell: 'Shell', clear_env: bool, unset_names: List[str]
    ) -> None:
        """Prevent child export sync from reintroducing env entries removed by env options."""
        from ..core import VarAttributes

        scope_manager = shell.state.scope_manager
        if clear_env:
            for var in scope_manager.all_variables_with_attributes():
                if var.is_exported:
                    scope_manager.remove_attribute(var.name, VarAttributes.EXPORT)

        for name in unset_names:
            scope_manager.remove_attribute(name, VarAttributes.EXPORT)

    def _is_env_assignment(self, arg: str) -> bool:
        """Check whether an argument is an env assignment token."""
        if '=' not in arg:
            return False
        name, _ = arg.split('=', 1)
        return bool(name)

    def _print_environment(self, env_map: Dict[str, str], shell: 'Shell') -> None:
        """Print environment mapping in a way that works in forked children."""
        if hasattr(shell.state, '_in_forked_child') and shell.state._in_forked_child:
            for key, value in sorted(env_map.items()):
                os.write(1, f"{key}={value}\n".encode('utf-8', errors='replace'))
            return

        out = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
        for key, value in sorted(env_map.items()):
            print(f"{key}={value}", file=out)

    def _bind_process_fds_to_streams(self, shell: 'Shell') -> List[Tuple[int, int]]:
        """Align process fds with shell streams so nested external commands obey redirections."""
        backups: List[Tuple[int, int]] = []
        stream_to_fd = (
            (shell.stdin if hasattr(shell, 'stdin') else sys.stdin, 0),
            (shell.stdout if hasattr(shell, 'stdout') else sys.stdout, 1),
            (shell.stderr if hasattr(shell, 'stderr') else sys.stderr, 2),
        )

        for stream, target_fd in stream_to_fd:
            try:
                stream_fd = stream.fileno()
            except (AttributeError, io.UnsupportedOperation, ValueError):
                continue

            if stream_fd == target_fd:
                continue

            backup_fd = os.dup(target_fd)
            os.dup2(stream_fd, target_fd)
            backups.append((target_fd, backup_fd))

        return backups

    def _restore_process_fds(self, backups: List[Tuple[int, int]]) -> None:
        """Restore fds previously redirected by _bind_process_fds_to_streams."""
        for target_fd, backup_fd in reversed(backups):
            os.dup2(backup_fd, target_fd)
            os.close(backup_fd)

    @property
    def help(self) -> str:
        return """env: env [OPTION]... [-] [name=value ...] [command [args ...]]

    Display environment variables or run a command with modified environment.
    With no arguments, print all environment variables.
    With -i (or -), start with an empty environment.
    With -u NAME, remove NAME from the environment for this invocation.
    With name=value pairs and no command, print the modified environment.
    With a command, run it with temporary environment overrides."""


@builtin
class ExportBuiltin(Builtin):
    """Export variables to environment."""

    @property
    def name(self) -> str:
        return "export"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Export variables to environment."""
        if len(args) == 1:
            # No arguments, print all exported variables in declare -x format
            for key, value in sorted(shell.env.items()):
                output_line = f'declare -x {key}="{value}"\n'
                # Check if we're in a child process (forked for pipeline/background)
                if hasattr(shell.state, '_in_forked_child') and shell.state._in_forked_child:
                    # In child process, write directly to fd 1
                    os.write(1, output_line.encode('utf-8', errors='replace'))
                else:
                    # In parent process, use shell.stdout to respect redirections
                    print(f'declare -x {key}="{value}"',
                          file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
        else:
            for arg in args[1:]:
                if '=' in arg:
                    # Variable assignment
                    key, value = arg.split('=', 1)
                    shell.state.export_variable(key, value)
                else:
                    # Export existing variable
                    value = shell.state.get_variable(arg)
                    if value is not None:
                        shell.state.export_variable(arg, value)
        return 0

    @property
    def help(self) -> str:
        return """export: export [name[=value] ...]

    Export variables to the environment.
    With no arguments, print all exported variables.
    With name=value, set the variable and export it.
    With just name, export an existing shell variable."""


@builtin
class SetBuiltin(Builtin):
    """Set shell options and positional parameters."""

    @property
    def name(self) -> str:
        return "set"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Set shell options and positional parameters."""
        if len(args) == 1:
            # No arguments, display all variables
            for var, value in sorted(shell.state.variables.items()):
                print(f"{var}={value}",
                      file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
            # Also show set options
            print(f"edit_mode={shell.edit_mode}",
                  file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
            return 0

        # Map short options to long names
        short_to_long = {
            'a': 'allexport',
            'b': 'notify',
            'C': 'noclobber',
            'e': 'errexit',
            'f': 'noglob',
            'h': 'hashcmds',
            'm': 'monitor',
            'n': 'noexec',
            'u': 'nounset',
            'v': 'verbose',
            'x': 'xtrace',
        }

        # Process arguments
        i = 1
        while i < len(args):
            arg = args[i]

            # Handle short options like -eux
            if arg.startswith('-') and not arg.startswith('-o') and len(arg) > 1 and not arg == '--':
                for opt_char in arg[1:]:
                    if opt_char in short_to_long:
                        shell.state.options[short_to_long[opt_char]] = True
                    else:
                        self.error(f"invalid option: -{opt_char}", shell)
                        return 1
                i += 1
                continue

            # Handle +eux to unset options
            elif arg.startswith('+') and not arg.startswith('+o') and len(arg) > 1:
                for opt_char in arg[1:]:
                    if opt_char in short_to_long:
                        shell.state.options[short_to_long[opt_char]] = False
                    else:
                        self.error(f"invalid option: +{opt_char}", shell)
                        return 1
                i += 1
                continue

            # Handle -o option with argument
            elif arg == '-o' and i + 1 < len(args):
                option = args[i + 1].lower().replace('_', '-')  # Allow debug_ast or debug-ast

                # Editor modes
                if option in ('vi', 'emacs'):
                    shell.edit_mode = option
                    # Set the corresponding option
                    shell.state.options['vi'] = (option == 'vi')
                    shell.state.options['emacs'] = (option == 'emacs')
                    print(f"Edit mode set to {option}",
                          file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                    return 0
                # Debug options and new shell options
                elif option in shell.state.options:
                    shell.state.options[option] = True
                    # Special handling for debug-scopes
                    if option == 'debug-scopes':
                        shell.state.scope_manager.enable_debug(True)
                    return 0
                else:
                    self.error(f"invalid option: {option}", shell)
                    valid_opts = ['vi', 'emacs'] + list(sorted(shell.state.options.keys()))
                    print(f"Valid options: {', '.join(valid_opts)}",
                          file=shell.stderr if hasattr(shell, 'stderr') else sys.stderr)
                    return 1

            # Handle -o without argument (show options)
            elif arg == '-o' and i + 1 == len(args):
                # Show current options with bash-compatible formatting
                self._show_all_options(shell)
                return 0

            # Handle +o without argument (show as set commands)
            elif arg == '+o' and i + 1 == len(args):
                # Show current options as set commands
                stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
                print(f"set {'+o' if shell.edit_mode == 'emacs' else '-o'} vi", file=stdout)
                # Show all shell options as set commands
                for opt_name, opt_value in sorted(shell.state.options.items()):
                    print(f"set {'-o' if opt_value else '+o'} {opt_name}", file=stdout)
                return 0

            # Handle +o with argument
            elif arg == '+o' and i + 1 < len(args):
                # Unset option
                option = args[i + 1].lower().replace('_', '-')
                if option == 'vi':
                    shell.edit_mode = 'emacs'
                    print("Edit mode set to emacs",
                          file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
                elif option in shell.state.options:
                    shell.state.options[option] = False
                    # Special handling for debug-scopes
                    if option == 'debug-scopes':
                        shell.state.scope_manager.enable_debug(False)
                return 0

            # Otherwise, treat as positional parameters
            else:
                # Handle -- to separate options from arguments
                if arg == '--':
                    shell.positional_params = args[i + 1:]
                else:
                    shell.positional_params = args[i:]
                return 0

        return 0

    @property
    def help(self) -> str:
        return """set: set [-abCefhmnuvx] [+abCefhmnuvx] [-o option] [arg ...]

    Set shell options and positional parameters.
    With no arguments, print all shell variables.

    Short options:
      -a                Enable allexport (auto-export all variables)
      -b                Enable notify (async job completion notifications)
      -C                Enable noclobber (prevent file overwriting with >)
      -e                Enable errexit (exit on command failure)
      -f                Enable noglob (disable pathname expansion)
      -h                Enable hashcmds (hash command locations)
      -m                Enable monitor (job control mode)
      -n                Enable noexec (read but don't execute commands)
      -u                Enable nounset (error on undefined variables)
      -v                Enable verbose (echo input lines as read)
      -x                Enable xtrace (print commands before execution)
      +<option>         Disable the specified option

    Long options:
      -o                Show current option settings
      -o vi             Set vi editing mode
      -o emacs          Set emacs editing mode (default)
      -o allexport      Auto-export all variables (same as -a)
      -o notify         Async job completion notifications (same as -b)
      -o noclobber      Prevent file overwriting with > (same as -C)
      -o errexit        Exit on command failure (same as -e)
      -o noglob         Disable pathname expansion (same as -f)
      -o hashcmds       Hash command locations (same as -h)
      -o monitor        Job control mode (same as -m)
      -o noexec         Read but don't execute commands (same as -n)
      -o nounset        Error on undefined variables (same as -u)
      -o verbose        Echo input lines as read (same as -v)
      -o xtrace         Print commands before execution (same as -x)
      -o pipefail       Pipeline fails if any command fails
      -o ignoreeof      Don't exit on EOF (Ctrl-D)
      -o nolog          Don't log function definitions to history
      -o debug-ast      Enable AST debug output
      -o enhanced-parser         Use enhanced parser features (default: on)
      -o validate-context        Validate token contexts during parsing
      -o validate-semantics      Validate semantic types during parsing
      -o analyze-semantics       Perform semantic analysis during parsing
      -o enhanced-error-recovery Use enhanced error recovery (default: on)
      -o enhanced-parser-mode    Set parser performance mode (performance/balanced/development)
      -o debug-tokens   Enable token debug output
      -o debug-scopes   Enable variable scope debug output
      -o debug-expansion Enable expansion debug output
      -o debug-exec     Enable executor debug output
      +o <option>       Disable the specified option

    With arguments, set positional parameters ($1, $2, etc.)."""

    def _show_all_options(self, shell: 'Shell'):
        """Show all shell options with bash-compatible formatting."""
        # Define standard POSIX/bash options to show (exclude PSH debug options for conformance)
        standard_options = {
            'allexport', 'braceexpand', 'emacs', 'errexit', 'errtrace', 'functrace',
            'hashall', 'histexpand', 'history', 'ignoreeof', 'interactive-comments',
            'keyword', 'monitor', 'noclobber', 'noexec', 'noglob', 'nolog',
            'notify', 'nounset', 'onecmd', 'physical', 'pipefail', 'posix',
            'privileged', 'verbose', 'vi', 'xtrace'
        }

        # If PSH_SHOW_ALL_OPTIONS environment variable is set, show all options including debug
        show_all = shell.state.env.get('PSH_SHOW_ALL_OPTIONS', '').lower() in ('1', 'true', 'yes')
        if show_all:
            # Show all options including PSH-specific debug options
            options_to_show = shell.state.options.keys()
        else:
            # Show only standard bash-compatible options for conformance
            options_to_show = [opt for opt in standard_options if opt in shell.state.options]

        # Check if we're in a child process (forked for pipeline/background)
        if hasattr(shell.state, '_in_forked_child') and shell.state._in_forked_child:
            # In child process, write directly to fd 1
            output_lines = []

            # Show options based on mode (standard vs all)
            for opt_name in sorted(options_to_show):
                opt_value = shell.state.options[opt_name]
                status = 'on' if opt_value else 'off'
                output_lines.append(f"{opt_name:<15}\t{status}\n")

            # Add edit mode info using standard option names
            if hasattr(shell, 'edit_mode'):
                if shell.edit_mode == 'emacs':
                    output_lines.append(f"{'emacs':<15}\ton\n")
                    output_lines.append(f"{'vi':<15}\toff\n")
                else:  # vi mode
                    output_lines.append(f"{'emacs':<15}\toff\n")
                    output_lines.append(f"{'vi':<15}\ton\n")

            # Write all lines to fd 1
            for line in output_lines:
                os.write(1, line.encode('utf-8', errors='replace'))
        else:
            # In parent process, use shell.stdout to respect redirections
            stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout

            # Show options based on mode (standard vs all)
            for opt_name in sorted(options_to_show):
                opt_value = shell.state.options[opt_name]
                status = 'on' if opt_value else 'off'
                print(f"{opt_name:<15}\t{status}", file=stdout)

            # Add edit mode info using standard option names
            if hasattr(shell, 'edit_mode'):
                if shell.edit_mode == 'emacs':
                    print(f"{'emacs':<15}\ton", file=stdout)
                    print(f"{'vi':<15}\toff", file=stdout)
                else:  # vi mode
                    print(f"{'emacs':<15}\toff", file=stdout)
                    print(f"{'vi':<15}\ton", file=stdout)


@builtin
class UnsetBuiltin(Builtin):
    """Unset variables and functions."""

    @property
    def name(self) -> str:
        return "unset"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Unset variables and functions."""
        if len(args) < 2:
            self.error("not enough arguments", shell)
            return 1

        # Check for -f flag
        if '-f' in args:
            # Remove functions
            exit_code = 0
            for arg in args[1:]:
                if arg != '-f':
                    if not shell.function_manager.undefine_function(arg):
                        self.error(f"{arg}: not a function", shell)
                        exit_code = 1
            return exit_code
        else:
            # Remove variables. `-n` unsets the nameref itself; otherwise a
            # nameref name is resolved to its target before unsetting (bash).
            nameref_mode = False
            names = []
            for arg in args[1:]:
                if arg == '-n':
                    nameref_mode = True
                elif arg == '-v':
                    pass  # explicit "variable" flag (the default)
                else:
                    names.append(arg)

            exit_code = 0
            for var in names:
                if not nameref_mode and '[' not in var:
                    var = shell.state.scope_manager.resolve_nameref_name(var)
                # Check if this is an array element syntax
                if '[' in var and var.endswith(']'):
                    # Array element unset: arr[index]
                    bracket_pos = var.find('[')
                    array_name = var[:bracket_pos]
                    index_expr = var[bracket_pos+1:-1]

                    # Get the array variable
                    from ..core import AssociativeArray, IndexedArray
                    var_obj = shell.state.scope_manager.get_variable_object(array_name)

                    if var_obj and isinstance(var_obj.value, IndexedArray):
                        # Evaluate the index
                        try:
                            # Expand variables in index
                            expanded_index = shell.expansion_manager.expand_string_variables(index_expr)

                            # Check if it's arithmetic
                            if any(op in expanded_index for op in ['+', '-', '*', '/', '%', '(', ')']):
                                from ..arithmetic import evaluate_arithmetic
                                index = evaluate_arithmetic(expanded_index, shell)
                            else:
                                index = int(expanded_index)

                            # Unset the element
                            var_obj.value.unset(index)
                        except (ValueError, KeyError, IndexError):
                            # Bash compatibility: treat string indices on indexed arrays as index 0
                            try:
                                var_obj.value.unset(0)
                            except (KeyError, IndexError):
                                self.error(f"{var}: bad array subscript", shell)
                                exit_code = 1
                    elif var_obj and isinstance(var_obj.value, AssociativeArray):
                        # For associative arrays
                        expanded_key = shell.expansion_manager.expand_string_variables(index_expr)
                        var_obj.value.unset(expanded_key)
                    else:
                        # Not an array
                        self.error(f"{array_name}: not an array", shell)
                        exit_code = 1
                else:
                    # Regular variable unset
                    try:
                        # Remove from both shell variables and environment
                        shell.state.scope_manager.unset_variable(var)
                        shell.env.pop(var, None)
                    except ReadonlyVariableError:
                        self.error(f"{var}: readonly variable", shell)
                        exit_code = 1
            return exit_code

    @property
    def help(self) -> str:
        return """unset: unset [-f] name [name ...]

    Unset variables or functions.

    Options:
      -f    Treat names as functions

    Without -f, remove the named variables from both shell
    variables and the environment."""
