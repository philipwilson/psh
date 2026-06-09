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
        """Print environment mapping (forked-child aware via Builtin.write)."""
        for key, value in sorted(env_map.items()):
            self.write_line(f"{key}={value}", shell)

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
        # Parse options: -p (print), -n (unexport), -- (end of options)
        print_mode = False
        unexport = False
        i = 1
        while i < len(args):
            arg = args[i]
            if arg == '--':
                i += 1
                break
            if arg.startswith('-') and len(arg) > 1:
                for ch in arg[1:]:
                    if ch == 'p':
                        print_mode = True
                    elif ch == 'n':
                        unexport = True
                    else:
                        self.error(f"-{ch}: invalid option", shell)
                        return 2
                i += 1
            else:
                break
        names = args[i:]

        if not names:
            # `export` / `export -p`: print all exported variables
            self._print_exports(shell)
            return 0

        status = 0
        for arg in names:
            if '=' in arg:
                key, value = arg.split('=', 1)
            else:
                key, value = arg, None

            # bash: invalid names are reported (rc 1) but the remaining
            # arguments are still processed.
            if not self._is_valid_identifier(key):
                self.error(f"`{arg}': not a valid identifier", shell)
                status = 1
                continue

            if print_mode:
                if key in shell.env:
                    self.write_line(f'declare -x {key}="{shell.env[key]}"', shell)
                continue

            if unexport:
                # export -n NAME[=value]: optionally assign, remove export attr
                if value is not None:
                    shell.state.set_variable(key, value)
                self._remove_export(key, shell)
            elif value is not None:
                shell.state.export_variable(key, value)
            else:
                # Export existing variable
                existing = shell.state.get_variable(key)
                if existing is not None:
                    shell.state.export_variable(key, existing)
        return status

    def _is_valid_identifier(self, name: str) -> bool:
        """Check if a name is a valid shell identifier."""
        if not name:
            return False
        if not (name[0].isalpha() or name[0] == '_'):
            return False
        return all(c.isalnum() or c == '_' for c in name[1:])

    def _print_exports(self, shell: 'Shell') -> None:
        """Print all exported variables in declare -x format."""
        for key, value in sorted(shell.env.items()):
            self.write_line(f'declare -x {key}="{value}"', shell)

    def _remove_export(self, name: str, shell: 'Shell') -> None:
        """Remove the export attribute from a variable (export -n)."""
        from ..core.variables import VarAttributes
        var = shell.state.scope_manager.get_variable_object(name)
        if var is not None and var.is_exported:
            var.attributes &= ~VarAttributes.EXPORT
        shell.state.env.pop(name, None)
        os.environ.pop(name, None)
        shell.state.scope_manager.sync_exports_to_environment(shell.state.env)

    @property
    def help(self) -> str:
        return """export: export [-n] [-p] [name[=value] ...]

    Export variables to the environment.
    With no arguments or -p, print all exported variables.
    With name=value, set the variable and export it.
    With just name, export an existing shell variable.

    Options:
      -n    Remove the export attribute from each name
      -p    Print exported variables in declare -x format"""


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

        # Process arguments. Option arguments do NOT stop processing — bash
        # accepts e.g. `set -o errexit -o pipefail -x`; the first non-option
        # argument starts the positional parameters.
        i = 1
        while i < len(args):
            arg = args[i]

            # -- separates options from positional parameters
            if arg == '--':
                shell.positional_params = args[i + 1:]
                return 0

            # Bare -o / +o without a following name: display options
            if arg in ('-o', '+o') and i + 1 == len(args):
                if arg == '-o':
                    # Show current options with bash-compatible formatting
                    self._show_all_options(shell)
                else:
                    # Show current options as set commands
                    stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
                    for opt_name, opt_value in sorted(shell.state.options.items()):
                        print(f"set {'-o' if opt_value else '+o'} {opt_name}", file=stdout)
                return 0

            # Short option clusters like -eux / +eux. A trailing 'o' consumes
            # the next argument as a long option name, so `set -euo pipefail`
            # works like bash.
            if arg[0] in '-+' and len(arg) > 1:
                enable = arg.startswith('-')
                sign = arg[0]
                cluster = arg[1:]
                for pos, opt_char in enumerate(cluster):
                    if opt_char == 'o' and pos == len(cluster) - 1:
                        if i + 1 < len(args):
                            i += 1
                            rc = self._set_long_option(shell, args[i], enable)
                            if rc != 0:
                                return rc
                        elif enable:
                            self._show_all_options(shell)
                    elif opt_char in short_to_long:
                        shell.state.options[short_to_long[opt_char]] = enable
                    else:
                        self.error(f"invalid option: {sign}{opt_char}", shell)
                        return 2
                i += 1
                continue

            # First non-option argument: the rest are positional parameters
            shell.positional_params = args[i:]
            return 0

        return 0

    def _set_long_option(self, shell: 'Shell', name: str, enable: bool) -> int:
        """Set or unset one -o/+o long option. Returns 0 or an error status."""
        option = name.lower().replace('_', '-')  # Allow debug_ast or debug-ast

        # Editor modes (silent, like bash)
        if option in ('vi', 'emacs'):
            if enable:
                shell.edit_mode = option
                shell.state.options['vi'] = (option == 'vi')
                shell.state.options['emacs'] = (option == 'emacs')
            elif option == 'vi':
                shell.edit_mode = 'emacs'
                shell.state.options['vi'] = False
            else:
                shell.state.options['emacs'] = False
            return 0

        # Debug options and shell options
        if option in shell.state.options:
            shell.state.options[option] = enable
            # Special handling for debug-scopes
            if option == 'debug-scopes':
                shell.state.scope_manager.enable_debug(enable)
            return 0

        self.error(f"{name}: invalid option name", shell)
        if enable:
            valid_opts = ['vi', 'emacs'] + list(sorted(shell.state.options.keys()))
            print(f"Valid options: {', '.join(valid_opts)}",
                  file=shell.stderr if hasattr(shell, 'stderr') else sys.stderr)
        return 2

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

        # Show options based on mode (standard vs all); Builtin.write_line
        # handles forked-child fd semantics.
        for opt_name in sorted(options_to_show):
            opt_value = shell.state.options[opt_name]
            status = 'on' if opt_value else 'off'
            self.write_line(f"{opt_name:<15}\t{status}", shell)

        # Add edit mode info using standard option names
        if hasattr(shell, 'edit_mode'):
            if shell.edit_mode == 'emacs':
                self.write_line(f"{'emacs':<15}\ton", shell)
                self.write_line(f"{'vi':<15}\toff", shell)
            else:  # vi mode
                self.write_line(f"{'emacs':<15}\toff", shell)
                self.write_line(f"{'vi':<15}\ton", shell)


@builtin
class UnsetBuiltin(Builtin):
    """Unset variables and functions."""

    @property
    def name(self) -> str:
        return "unset"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Unset variables and functions."""
        opts, names = self.parse_flags(args, shell, flags='fvn')
        if opts is None:
            return 2  # invalid option (bash usage-error status)
        if not names:
            return 0  # bash: unset with no operands succeeds silently

        if opts['f']:
            # Remove functions
            exit_code = 0
            for arg in names:
                if not shell.function_manager.undefine_function(arg):
                    self.error(f"{arg}: not a function", shell)
                    exit_code = 1
            return exit_code
        else:
            # Remove variables. `-n` unsets the nameref itself; otherwise a
            # nameref name is resolved to its target before unsetting (bash).
            nameref_mode = opts['n']

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
