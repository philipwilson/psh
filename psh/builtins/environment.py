"""Environment and variable management builtins (export, set, unset).

The ``env`` builtin lives in its own module (``env_command.py``) because it
runs a command in a nested in-process child Shell and carries its own
process-fd binding helpers.
"""

from typing import TYPE_CHECKING, List

from ..core import ReadonlyVariableError, SpecialBuiltinUsageError, VarAttributes
from ..core.option_registry import (
    OPTION_REGISTRY,
    SET_O_OPTION_NAMES,
    SHORT_TO_LONG,
    OptionCategory,
)
from .base import EMPTY_BUILTIN_CONTEXT, Builtin, BuiltinContext
from .declare_format import escape_value
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


def apply_set_o_option(shell: 'Shell', option: str, enable: bool) -> None:
    """Apply one VALIDATED long-option toggle with its couplings.

    The single toggle engine behind ``set -o/+o NAME`` and
    ``shopt -so/-uo NAME`` (bash keeps the two surfaces exactly equivalent).
    ``option`` must already be a real key of ``shell.state.options``; the
    callers own name resolution and their differing unknown-name errors.
    """
    # Editor modes (silent, like bash): vi/emacs couple to edit_mode.
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
        return

    # ignoreeof couples to the IGNOREEOF variable exactly like bash's
    # set_ignoreeof(): enabling binds IGNOREEOF=10, disabling unbinds it.
    # The variable observer (ShellState's _sync_exported_variable, playing
    # sv_ignoreeof) keeps the option flag tracking the variable's existence,
    # so `IGNOREEOF=n` / `unset IGNOREEOF` flip it too; the explicit
    # assignment below covers the variable-absent direction.
    if option == 'ignoreeof':
        if enable:
            shell.state.set_variable('IGNOREEOF', '10')
        else:
            shell.state.scope_manager.unset_variable('IGNOREEOF')
        shell.state.options['ignoreeof'] = enable
        return

    shell.state.options[option] = enable
    # Special handling for debug-scopes
    if option == 'debug-scopes':
        shell.state.scope_manager.enable_debug(enable)


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
                        # Usage error of a POSIX special builtin (see
                        # SpecialBuiltinUsageError): POSIX-mode
                        # non-interactive shells exit with 2.
                        self.error(f"-{ch}: invalid option", shell)
                        raise SpecialBuiltinUsageError(2, suppressible=True)
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
        # Tracks a readonly ASSIGNMENT error (vs an identifier error, which
        # is a plain rc-1 operand error): POSIX-mode non-interactive shells
        # exit on it (probe: `set -o posix; readonly r=1; export r=2` exits
        # rc 1 in bash 5.2). Deferred to the end so the remaining names are
        # still processed exactly as before in every mode.
        assignment_error = False
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
            if not self._is_valid_identifier(key, shell.state.options.get('posix', False)):
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
                    try:
                        rc = declare_builtin.execute_in_context(
                            ['declare', '-x', arg], shell, context)
                    except ReadonlyVariableError as e:
                        self.report_error(f"{e.name}: readonly variable", shell)
                        status = 1
                        assignment_error = True
                        continue
                    if rc != 0:
                        status = rc
                    continue

            if print_mode:
                if key in shell.env:
                    self.write_line(
                        f'declare -x {key}="{escape_value(shell.env[key])}"', shell)
                continue

            try:
                if unexport:
                    # export -n NAME[=value]: optionally assign, remove export attr
                    if value is not None:
                        if append:
                            value = (shell.state.get_variable(key) or '') + value
                        shell.state.set_variable(key, value)
                    self._remove_export(key, shell)
                elif value is not None:
                    # export NAME[+]=value through the single declaration-engine
                    # chokepoint. FIX1: an append reads the export target's base
                    # (past a temp-env layer) and honors its integer attribute,
                    # so `declare -i n=2; export n+=3` is 5, not a textual "23".
                    from .declaration_engine import DeclarationEngine
                    DeclarationEngine(shell).commit_scalar(
                        key, value, append=append,
                        add_attributes=VarAttributes.EXPORT,
                        local=False, skip_temp_env=True)
                else:
                    self._export_existing(key, shell)
            except ReadonlyVariableError as e:
                # bash reports `export x=2` on a readonly var WITHOUT the
                # builtin name (like a plain assignment error), non-fatally
                # in default mode.
                self.report_error(f"{e.name}: readonly variable", shell)
                status = 1
                assignment_error = True
        if assignment_error:
            # Typed usage/assignment outcome: the guard returns 1 in default
            # mode (byte-identical to the old `return 1`) and exits a
            # POSIX-mode non-interactive shell.
            raise SpecialBuiltinUsageError(1)
        return status

    def _export_existing(self, key: str, shell: 'Shell') -> None:
        """Valueless ``export NAME``: add the EXPORT attribute.

        An existing variable keeps its value (readonly included — bash:
        ``readonly R=1; export R`` succeeds). An UNSET name records the
        attribute on a declared-but-unset variable: no environment entry
        appears until it is assigned (bash: ``export FOO; printenv FOO``
        fails, then ``FOO=now`` makes it visible to children).
        """
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

        With no names, lists each exported function as its full definition
        followed by a ``declare -fx`` line (bash). With names, marks (or with
        -n unmarks) each named function; a name that is not a function is a
        bash usage error (status 1). psh does not serialise functions into the
        environment for EXTERNAL children, so the attribute is observable via
        this listing rather than in subprocesses.
        """
        from ..visitor import format_function_definition
        fm = shell.function_manager
        if not names:
            for name, func in fm.list_functions():
                if func.exported:
                    self.write_line(format_function_definition(name, func), shell)
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

    def _is_valid_identifier(self, name: str, posix_mode: bool = False) -> bool:
        """Check if a name is a valid shell identifier.

        Delegates to the shell's single authoritative identifier policy
        (``unicode_support.is_valid_name``); ``posix_mode`` (``set -o posix``)
        restricts to the ASCII set as bash does.
        """
        from ..lexer.unicode_support import is_valid_name
        return is_valid_name(name, posix_mode)

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
        var = shell.state.scope_manager.get_variable_object(name)
        if var is not None and var.is_exported:
            # Route through the store (no direct .attributes write, C2); its
            # observer re-derives the live-environment entry (removing it, since
            # the variable is no longer exported) — the single env interface, no
            # direct env poke (appraisal H3). A name that is only an inherited
            # OPAQUE env entry cannot reach here: `export -n` rejects invalid
            # identifiers, and every valid-identifier env entry is a variable.
            shell.state.scope_manager.store.remove_attributes(
                name, VarAttributes.EXPORT)

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
            # No arguments: display all variables in bash's reusable
            # single-quote form (`x='a b'`, `$'a\nb'`, arrays as
            # `a=([0]="..")`), identical to plain `declare`. The old
            # `f"{var}={value}"` emitted unquoted values and str()'d arrays to
            # a single space-joined word — not re-parseable.
            from .declare_format import format_assignment_reuse
            for var in sorted(shell.state.scope_manager.all_variables_with_attributes(),
                              key=lambda v: v.name):
                self.write_line(format_assignment_reuse(var), shell)
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

            # A lone '-' or '+' ends option processing WITHOUT becoming a
            # positional parameter (bash/POSIX). '-' additionally resets -v/-x.
            # Any following words become the positional parameters; with NO
            # following word the parameters are left unchanged — unlike '--',
            # which clears them. (Probe-verified against bash 5.2: `set a b c;
            # set -` leaves $# at 3, `set - x` sets $1=x, `set -x; set -` clears
            # xtrace.)
            if arg in ('-', '+'):
                if arg == '-':
                    shell.state.options['verbose'] = False
                    shell.state.options['xtrace'] = False
                if i + 1 < len(args):
                    shell.state.positional_params = args[i + 1:]
                return 0

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
                    # Show current options as reusable `set` commands. Only
                    # `set -o`-settable options belong here: emitting shopt/
                    # debug/internal names (dotglob, stdin_mode, ...) made
                    # `eval "$(set +o)"` spew "invalid option name" for each,
                    # since `set -o NAME` rejects them. Restrict to the SET
                    # category (bash's set-vs-shopt split); str-valued options
                    # (parser-mode) have no on/off form and are skipped.
                    for opt_name in sorted(self._reusable_option_names()):
                        opt_value = shell.state.options[opt_name]
                        self.write_line(
                            f"set {'-o' if opt_value else '+o'} {opt_name}", shell)
                return 0

            # Short option clusters like -eux / +eux. A trailing 'o' consumes
            # the next argument as a long option name, so `set -euo pipefail`
            # works like bash. ``arg[:1]`` (not ``arg[0]``) so an EMPTY operand
            # (`set ""`) falls through to the positional-parameter branch below
            # instead of raising IndexError.
            if arg[:1] in ('-', '+') and len(arg) > 1:
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
                        # Usage error of a POSIX special builtin: report,
                        # then raise the typed outcome — in POSIX mode a
                        # non-interactive shell exits with 2, otherwise the
                        # guard turns it back into plain status 2.
                        self.error(f"invalid option: {sign}{opt_char}", shell)
                        raise SpecialBuiltinUsageError(2, suppressible=True)
                i += 1
                continue

            # First non-option argument: the rest are positional parameters
            shell.state.positional_params = args[i:]
            return 0

        return 0

    def _set_long_option(self, shell: 'Shell', name: str, enable: bool) -> int:
        """Set or unset one -o/+o long option. Returns 0 or an error status."""
        # Resolve to a real option key, accepting both spellings: registry
        # keys use dashes for debug-* / strict-errors but underscores for
        # stdin_mode / command_mode. Trying the raw name first keeps underscore
        # options settable — so `eval "$(set +o)"` round-trips instead of
        # erroring on an underscore name.
        raw = name.lower()
        option = raw if raw in shell.state.options else raw.replace('_', '-')

        # INTERNAL-category options (interactive, stdin_mode, command_mode) are
        # set by the shell itself and are NOT user-settable by name — bash:
        # `set -o interactive` → "interactive: invalid option name". Letting
        # them through corrupted $- (a spurious `i`). psh's `set -o` otherwise
        # stays a deliberate superset of bash's (it also accepts shopt/debug
        # names); only the INTERNAL ones are rejected.
        spec = OPTION_REGISTRY.get(option)
        if spec is not None and spec.category is OptionCategory.INTERNAL:
            self.error(f"{name}: invalid option name", shell)
            raise SpecialBuiltinUsageError(2, suppressible=True)

        # Debug options and shell options (vi/emacs/ignoreeof couplings live
        # in the shared toggle engine, also used by `shopt -so/-uo`).
        if option in shell.state.options:
            apply_set_o_option(shell, option, enable)
            return 0

        # Unknown -o/+o name: a usage error (bash: rc 2; POSIX-mode
        # non-interactive shells exit — probe `set -o nosuchoption`). bash
        # prints ONLY this one line — the old `Valid options: <45 names>`
        # dump that used to follow (enable path only) had no bash analogue
        # (probe-pinned vs bash 5.2: `set -o nosuchopt` is a single line).
        self.error(f"{name}: invalid option name", shell)
        raise SpecialBuiltinUsageError(2, suppressible=True)

    @property
    def help(self) -> str:
        return """set: set [-abBCefhmnuvx] [+abBCefhmnuvx] [-o option] [arg ...]

    Set shell options and positional parameters.
    With no arguments, print all shell variables.

    Short options:
      -a                Enable allexport (auto-export all variables)
      -b                Enable notify (async job completion notifications)
      -B                Enable braceexpand (brace expansion, on by default)
      -C                Enable noclobber (prevent file overwriting with >)
      -e                Enable errexit (exit on command failure)
      -f                Enable noglob (disable pathname expansion)
      -h                Enable hashall (hash command locations)
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
      -o hashall        Hash command locations (same as -h)
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
        """Show all shell options with bash-compatible formatting.

        The names come from the registry's SET_O_OPTION_NAMES — the SAME
        table behind `set +o`, `shopt -o` and $SHELLOPTS (bash keeps all of
        these identical; `diff <(set -o) <(shopt -o)` is empty). A hardcoded
        bash-name list used to live here, exactly the parallel map the
        option registry exists to eliminate.
        """
        # If PSH_SHOW_ALL_OPTIONS environment variable is set, show all options including debug
        show_all = shell.state.env.get('PSH_SHOW_ALL_OPTIONS', '').lower() in ('1', 'true', 'yes')
        if show_all:
            # Show all options including PSH-specific debug options
            options_to_show = list(shell.state.options.keys())
        else:
            options_to_show = list(SET_O_OPTION_NAMES)

        # Show options based on mode (standard vs all); Builtin.write_line
        # handles forked-child fd semantics. emacs/vi are printed from the
        # options dict like every other option (one line each): the option
        # values already track the edit mode — `set -o vi` sets both — and
        # match bash (both `off` in a non-interactive shell). A separate
        # edit_mode-driven block used to print them a SECOND time with a
        # contradictory value.
        for opt_name in sorted(options_to_show):
            opt_value = shell.state.options[opt_name]
            status = 'on' if opt_value else 'off'
            self.write_line(f"{opt_name:<15}\t{status}", shell)

    @staticmethod
    def _reusable_option_names() -> list:
        """Option names emitted by bare `set +o` (the reusable form).

        Only `set -o`-settable on/off options qualify: the SET category with a
        boolean value type (SET_O_OPTION_NAMES). shopt/debug/internal names
        are excluded so `eval "$(set +o)"` round-trips cleanly.
        """
        return list(SET_O_OPTION_NAMES)


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
            # Invalid option: a special-builtin usage error (rc 2; exits a
            # POSIX-mode non-interactive shell). The -f/-v conflict and
            # readonly/unset failures below stay plain operand errors.
            raise SpecialBuiltinUsageError(2, suppressible=True)
        if opts['f'] and opts['v']:
            # bash rejects -f and -v together regardless of operands.
            self.error(
                "cannot simultaneously unset a function and a variable", shell)
            return 1
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
                    # Regular variable unset. The scope manager's
                    # variable_changed observer re-derives the environment
                    # entry — it disappears, or REAPPEARS when removing a
                    # variable from a deeper scope reveals an exported outer
                    # instance (bash: unsetting an exported local restores the
                    # exported global's entry). This deeper-scope reveal is the
                    # only reappearance case — an own-scope `local x; unset x`
                    # plants a tombstone and reveals nothing. Either way there
                    # is no explicit env.pop here.
                    try:
                        shell.state.scope_manager.unset_variable(var)
                    except ReadonlyVariableError:
                        self.error(f"{var}: cannot unset: readonly variable", shell)
                        exit_code = 1
            return exit_code

    def _unset_array_element(self, var: str, shell: 'Shell') -> bool:
        """Unset one array element (``unset 'arr[index]'``).

        Subscript evaluation delegates to the expansion subsystem's
        canonical evaluators (VariableExpander._eval_array_index /
        expand_array_index) rather than re-implementing them here.
        Returns True on success, False on error (caller sets status 1).
        """
        from ..core import AssociativeArray, IndexedArray, NamerefCycleError

        bracket_pos = var.find('[')
        array_name = var[:bracket_pos]
        index_expr = var[bracket_pos+1:-1]
        # Resolve a nameref target: `declare -n r=a; unset "r[1]"` unsets a[1]
        # (bash). The main loop skips its nameref resolution for a subscripted
        # name (`'[' in var`), so it happens here on the array-name part.
        try:
            array_name = shell.state.scope_manager.resolve_nameref_name(array_name)
        except NamerefCycleError as e:
            shell.state.scope_manager.warn_nameref_cycle(e.name)
            return True
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
                except ReadonlyVariableError:
                    self.error(f"{array_name}: cannot unset: readonly variable", shell)
                    return False
                return True
            if not isinstance(value, AssociativeArray):
                if var_obj is not None:
                    self.error(f"{array_name}: not an array variable", shell)
                return True

        if var_obj is None:
            # bash: unsetting an element of a nonexistent variable succeeds
            return True

        # A readonly array/assoc forbids element removal too — check BEFORE
        # mutating so a failed unset never changes the value (bash: `readonly
        # a; unset 'a[0]'` -> "a: cannot unset: readonly variable", rc=1, array
        # intact). The whole-array (@/*) and scalar paths route through
        # scope_manager.unset_variable, which already enforces this.
        if var_obj.is_readonly and isinstance(
                var_obj.value, (IndexedArray, AssociativeArray)):
            self.error(f"{array_name}: cannot unset: readonly variable", shell)
            return False

        if isinstance(var_obj.value, (IndexedArray, AssociativeArray)):
            # Route through the store's element-unset transaction: it owns the
            # negative-index resolution (the SAME one-past-the-top formula as
            # read/write, so sparse `unset 'a[-2]'` matches bash) and the
            # observer, so this never touches `.value.unset` directly (C2). An
            # associative array keys on the expanded literal subscript; an
            # indexed array keys on the arithmetic value. An out-of-range
            # negative subscript is "bad array subscript" (rc=1), like bash.
            from ..core import ArraySubscriptError
            key: "int | str"
            if isinstance(var_obj.value, AssociativeArray):
                key = expander.expand_array_index(index_expr)
            else:
                key = expander._eval_array_index(index_expr)
            try:
                shell.state.scope_manager.store.unset_element(array_name, key)
            except ArraySubscriptError:
                self.error(f"[{index_expr}]: bad array subscript", shell)
                return False
            return True

        # Scalar variable: bash treats it as a one-element array, so
        # `unset 'x[0]'` unsets x and any other subscript is an error.
        if expander._eval_array_index(index_expr) == 0:
            try:
                shell.state.scope_manager.unset_variable(array_name)
            except ReadonlyVariableError:
                self.error(f"{array_name}: cannot unset: readonly variable", shell)
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
