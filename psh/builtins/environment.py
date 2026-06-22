"""Environment and variable management builtins (export, set, unset).

The ``env`` builtin lives in its own module (``env_command.py``) because it
runs a command in a nested in-process child Shell and carries its own
process-fd binding helpers.
"""

from typing import TYPE_CHECKING, List

from ..core import ReadonlyVariableError
from ..core.option_registry import SHORT_TO_LONG
from .base import EMPTY_BUILTIN_CONTEXT, Builtin, BuiltinContext
from .declare_format import escape_value
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class ExportBuiltin(Builtin):
    """Export variables to environment."""

    @property
    def name(self) -> str:
        return "export"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        return self.execute_in_context(args, shell, EMPTY_BUILTIN_CONTEXT)

    def execute_in_context(self, args: List[str], shell: 'Shell',
                           context: BuiltinContext) -> int:
        """Export variables to environment.

        ``context`` carries any structured array initializers for
        ``export name=(...)`` arguments (see BuiltinContext); they are
        forwarded to ``declare -x`` so the array logic stays in one place.
        """
        # Parse options: -p (print), -n (unexport), -f (functions),
        # -- (end of options)
        print_mode = False
        unexport = False
        functions = False
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
                    elif ch == 'f':
                        functions = True
                    else:
                        self.error(f"-{ch}: invalid option", shell)
                        return 2
                i += 1
            else:
                break
        names = args[i:]

        if functions:
            return self._export_functions(names, shell, unexport=unexport)

        if not names:
            # `export` / `export -p`: print all exported variables
            self._print_exports(shell)
            return 0

        status = 0
        for arg in names:
            if '=' in arg:
                key, value = arg.split('=', 1)
                append = key.endswith('+')
                if append:
                    # export NAME+=value appends (bash)
                    key = key[:-1]
            else:
                key, value = arg, None
                append = False

            # bash: invalid names are reported (rc 1) but the remaining
            # arguments are still processed.
            if not self._is_valid_identifier(key):
                self.error(f"`{arg}': not a valid identifier", shell)
                status = 1
                continue

            # ``export NAME=(...)`` makes an indexed array with the export
            # attribute (bash; arrays are never written to the environment).
            # The parser attaches a structured ArrayInitialization to the arg
            # Word, delivered via the BuiltinContext the executor passed in;
            # expand it through the SAME structured path the bare ``a=(...)``
            # form uses (no shlex reparse). Delegating to declare keeps the
            # array attribute logic in one place — we forward the same context
            # so declare resolves the same structured init.
            if not print_mode and not unexport:
                if context.array_init(arg) is not None:
                    from .registry import registry
                    declare_builtin = registry.get('declare')
                    assert declare_builtin is not None
                    # Forward the SAME context so declare sees the structured
                    # init for this argument (it reads context.array_init(arg)).
                    rc = declare_builtin.execute_in_context(
                        ['declare', '-x', arg], shell, context)
                    if rc != 0:
                        status = rc
                    continue

            if append and value is not None:
                value = (shell.state.get_variable(key) or '') + value

            if print_mode:
                if key in shell.env:
                    self.write_line(
                        f'declare -x {key}="{escape_value(shell.env[key])}"', shell)
                continue

            if unexport:
                # export -n NAME[=value]: optionally assign, remove export attr
                if value is not None:
                    shell.state.set_variable(key, value)
                self._remove_export(key, shell)
            elif value is not None:
                shell.state.export_variable(key, value)
            else:
                self._export_existing(key, shell)
        return status

    def _export_existing(self, key: str, shell: 'Shell') -> None:
        """Valueless ``export NAME``: add the EXPORT attribute.

        An existing variable keeps its value (readonly included — bash:
        ``readonly R=1; export R`` succeeds). An UNSET name records the
        attribute on a declared-but-unset variable: no environment entry
        appears until it is assigned (bash: ``export FOO; printenv FOO``
        fails, then ``FOO=now`` makes it visible to children).
        """
        from ..core.variables import VarAttributes
        scope_manager = shell.state.scope_manager
        if scope_manager.get_variable_object(key) is not None:
            scope_manager.apply_attribute(key, VarAttributes.EXPORT)
        else:
            scope_manager.set_variable(
                key, "", attributes=VarAttributes.EXPORT | VarAttributes.UNSET,
                local=False)

    def _export_functions(self, names: List[str], shell: 'Shell', *,
                          unexport: bool) -> int:
        """Handle ``export -f`` / ``export -fn`` (function export attribute).

        With no names, lists the exported functions in ``declare -fx`` form.
        With names, marks (or with -n unmarks) each named function; a name that
        is not a function is a bash usage error (status 1). psh does not
        serialise functions into the environment for EXTERNAL children, so the
        attribute is observable via this listing rather than in subprocesses.
        """
        fm = shell.function_manager
        if not names:
            for name, func in fm.list_functions():
                if func.exported:
                    self.write_line(f'declare -fx {name}', shell)
            return 0

        status = 0
        for name in names:
            if fm.get_function(name) is None:
                self.error(f"{name}: not a function", shell)
                status = 1
                continue
            fm.set_function_exported(name, not unexport)
        return status

    def _is_valid_identifier(self, name: str) -> bool:
        """Check if a name is a valid shell identifier."""
        if not name:
            return False
        if not (name[0].isalpha() or name[0] == '_'):
            return False
        return all(c.isalnum() or c == '_' for c in name[1:])

    def _print_exports(self, shell: 'Shell') -> None:
        """Print all exported variables in ``declare -x`` format.

        Iterates exported VARIABLE OBJECTS (not the live env dict) so a
        declared-but-unset export (``export FOO``) is shown as ``declare -x FOO``
        with no ``=value`` — bash does, and the old env-dict iteration dropped it
        (it has no env entry). Uses the shared ``format_declaration`` so the full
        attribute set is shown (``declare -ix N="5"``) and values are escaped,
        matching ``declare -p``."""
        from .declare_format import format_declaration
        exported = shell.state.scope_manager.all_exported_variables()
        for var in sorted(exported, key=lambda v: v.name):
            self.write_line(format_declaration(var), shell)

    def _remove_export(self, name: str, shell: 'Shell') -> None:
        """Remove the export attribute from a variable (export -n)."""
        from ..core.variables import VarAttributes
        var = shell.state.scope_manager.get_variable_object(name)
        if var is not None and var.is_exported:
            var.attributes &= ~VarAttributes.EXPORT
        # state.env is the live environment; os.environ is read-once at
        # startup and never written.
        shell.state.env.pop(name, None)
        shell.state.scope_manager.sync_exports_to_environment(shell.state.env)

    @property
    def help(self) -> str:
        return """export: export [-fn] [-p] [name[=value] ...]

    Export variables to the environment.
    With no arguments or -p, print all exported variables.
    With name=value, set the variable and export it.
    With just name, export an existing shell variable.

    Options:
      -f    Refer to shell functions
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
                self.write_line(f"{var}={value}", shell)
            return 0

        # Short option (-e, -u, ...) → long name, from the option registry
        # (the single source of truth; see psh/core/option_registry.py).
        short_to_long = SHORT_TO_LONG

        # Process arguments. Option arguments do NOT stop processing — bash
        # accepts e.g. `set -o errexit -o pipefail -x`; the first non-option
        # argument starts the positional parameters.
        i = 1
        while i < len(args):
            arg = args[i]

            # -- separates options from positional parameters
            if arg == '--':
                shell.state.positional_params = args[i + 1:]
                return 0

            # Bare -o / +o without a following name: display options
            if arg in ('-o', '+o') and i + 1 == len(args):
                if arg == '-o':
                    # Show current options with bash-compatible formatting
                    self._show_all_options(shell)
                else:
                    # Show current options as set commands
                    for opt_name, opt_value in sorted(shell.state.options.items()):
                        self.write_line(f"set {'-o' if opt_value else '+o'} {opt_name}", shell)
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
            shell.state.positional_params = args[i:]
            return 0

        return 0

    def _set_long_option(self, shell: 'Shell', name: str, enable: bool) -> int:
        """Set or unset one -o/+o long option. Returns 0 or an error status."""
        option = name.lower().replace('_', '-')  # Allow debug_ast or debug-ast

        # Editor modes (silent, like bash)
        if option in ('vi', 'emacs'):
            if enable:
                shell.state.edit_mode = option
                shell.state.options['vi'] = (option == 'vi')
                shell.state.options['emacs'] = (option == 'emacs')
            elif option == 'vi':
                shell.state.edit_mode = 'emacs'
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
            self.write_error_line(f"Valid options: {', '.join(valid_opts)}", shell)
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
            options_to_show = list(shell.state.options.keys())
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
        if shell.state.edit_mode == 'emacs':
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
            # Remove functions. bash: unsetting a non-existent function is a
            # silent no-op returning 0 (matches `unset -v` on a missing var).
            for arg in names:
                shell.function_manager.undefine_function(arg)
            return 0
        else:
            # Remove variables. `-n` unsets the nameref itself; otherwise a
            # nameref name is resolved to its target before unsetting (bash).
            nameref_mode = opts['n']

            exit_code = 0
            for var in names:
                if not nameref_mode and '[' not in var:
                    from ..core import NamerefCycleError
                    try:
                        var = shell.state.scope_manager.resolve_nameref_name(var)
                    except NamerefCycleError as e:
                        # bash warns but unset still succeeds (status 0)
                        shell.state.scope_manager.warn_nameref_cycle(e.name)
                        continue
                # Check if this is an array element syntax
                if '[' in var and var.endswith(']'):
                    if not self._unset_array_element(var, shell):
                        exit_code = 1
                elif (not opts['v']
                      and shell.state.scope_manager.get_variable_object(var) is None
                      and var not in shell.env
                      and shell.function_manager.get_function(var) is not None):
                    # Bash: a bare `unset NAME` (no -v/-f) unsets the variable if
                    # one exists, else falls back to unsetting a FUNCTION of that
                    # name. With both present the variable wins (handled by the
                    # variable branch below, which runs when a variable exists);
                    # an explicit `-v` restricts to variables and never falls back.
                    shell.function_manager.undefine_function(var)
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

    def _unset_array_element(self, var: str, shell: 'Shell') -> bool:
        """Unset one array element (``unset 'arr[index]'``).

        Subscript evaluation delegates to the expansion subsystem's
        canonical evaluators (VariableExpander._eval_array_index /
        expand_array_index) rather than re-implementing them here.
        Returns True on success, False on error (caller sets status 1).
        """
        from ..core import AssociativeArray, IndexedArray

        bracket_pos = var.find('[')
        array_name = var[:bracket_pos]
        index_expr = var[bracket_pos+1:-1]
        var_obj = shell.state.scope_manager.get_variable_object(array_name)
        expander = shell.expansion_manager.variable_expander

        if index_expr in ('@', '*'):
            # `unset 'arr[@]'` / `'arr[*]'` removes the ENTIRE array — but only
            # for an INDEXED array (bash). For an associative array @/* is a
            # literal key (fall through); for a scalar bash reports "not an
            # array variable"; for an absent name it is a silent no-op success.
            value = getattr(var_obj, 'value', None)
            if isinstance(value, IndexedArray):
                try:
                    shell.state.scope_manager.unset_variable(array_name)
                    shell.env.pop(array_name, None)
                except ReadonlyVariableError:
                    self.error(f"{array_name}: readonly variable", shell)
                    return False
                return True
            if not isinstance(value, AssociativeArray):
                if var_obj is not None:
                    self.error(f"{array_name}: not an array variable", shell)
                return True

        if var_obj is None:
            # bash: unsetting an element of a nonexistent variable succeeds
            return True

        if isinstance(var_obj.value, AssociativeArray):
            var_obj.value.unset(expander.expand_array_index(index_expr))
            return True

        if isinstance(var_obj.value, IndexedArray):
            index = expander._eval_array_index(index_expr)
            if index < 0:
                # Negative subscripts count back from the end (bash)
                indices = var_obj.value.indices()
                if -index > len(indices):
                    self.error(f"[{index_expr}]: bad array subscript", shell)
                    return False
                index = indices[index]
            var_obj.value.unset(index)
            return True

        # Scalar variable: bash treats it as a one-element array, so
        # `unset 'x[0]'` unsets x and any other subscript is an error.
        if expander._eval_array_index(index_expr) == 0:
            try:
                shell.state.scope_manager.unset_variable(array_name)
                shell.env.pop(array_name, None)
            except ReadonlyVariableError:
                self.error(f"{array_name}: readonly variable", shell)
                return False
            return True
        self.error(f"{array_name}: not an array variable", shell)
        return False

    @property
    def help(self) -> str:
        return """unset: unset [-f] name [name ...]

    Unset variables or functions.

    Options:
      -f    Treat names as functions

    Without -f, remove the named variables from both shell
    variables and the environment."""
