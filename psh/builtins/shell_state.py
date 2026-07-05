"""Shell state related builtins (history, version, local)."""

from typing import TYPE_CHECKING, List

from .base import EMPTY_BUILTIN_CONTEXT, Builtin, BuiltinContext
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class HistoryBuiltin(Builtin):
    """Display command history."""

    @property
    def name(self) -> str:
        return "history"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Display command history."""
        # NOTE: deliberately NOT parse_flags(). This is a `[n] | -c` dispatch on
        # args[1], not a getopt loop: a numeric `n` operand (`history 5`) is not
        # a flag, and the bad-input messages/exit codes differ from the shared
        # helper's contract — `-5`/`-d`/`-w` yield "numeric argument required"
        # (or bare "invalid option") at exit 1, and `--` is itself "numeric
        # argument required", whereas parse_flags would emit "-X: invalid
        # option" + a usage line at exit 2 and treat `--` as end-of-options.
        if len(args) > 1:
            # Check for -c flag to clear history
            if args[1] == '-c':
                # Route through the HistoryManager so the file-sync marker
                # (_file_synced_len) is reset too. Clearing state.history
                # directly left the marker stale, so commands added AFTER the
                # clear were dropped from HISTFILE on save (data loss).
                hist_mgr = getattr(
                    getattr(shell, 'interactive_manager', None),
                    'history_manager', None)
                if hist_mgr is not None:
                    hist_mgr.clear_history()
                else:
                    shell.state.history.clear()
                return 0

            try:
                count = int(args[1])
                if count < 0:
                    self.error(f"{args[1]}: invalid option", shell)
                    return 1
            except ValueError:
                self.error(f"{args[1]}: numeric argument required", shell)
                return 1
        else:
            # Default to showing last 10 commands (bash behavior)
            count = 10

        # Calculate the starting index
        history = shell.state.history
        start = max(0, len(history) - count)
        history_slice = history[start:]

        # Print with line numbers
        start_num = len(history) - len(history_slice) + 1
        for i, cmd in enumerate(history_slice):
            self.write_line(f"{start_num + i:5d}  {cmd}", shell)

        return 0

    @property
    def help(self) -> str:
        return """history: history [n] | history -c

    Display the command history list with line numbers.

    Options:
      n     Show only the last n entries
      -c    Clear the history list

    Default is to show the last 10 commands."""


@builtin
class VersionBuiltin(Builtin):
    """Display version information."""

    @property
    def name(self) -> str:
        return "version"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Display version information."""
        from ..version import __version__, get_version_info

        if len(args) > 1 and args[1] == '--short':
            # Just print version number
            self.write_line(__version__, shell)
        else:
            # Full version info
            self.write_line(get_version_info(), shell)

        return 0

    @property
    def help(self) -> str:
        return """version: version [--short]

    Display version information for Python Shell (psh).
    With --short, display only the version number."""


@builtin
class LocalBuiltin(Builtin):
    """Create local variables within functions."""

    @property
    def name(self) -> str:
        return "local"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        return self.execute_in_context(args, shell, EMPTY_BUILTIN_CONTEXT)

    def execute_in_context(self, args: List[str], shell: 'Shell',
                           context: BuiltinContext) -> int:
        """Create local variables in function scope.

        ``context`` carries any structured array initializers for
        ``local name=(...)`` arguments (see BuiltinContext).
        """
        # Check if we're in a function
        if not shell.state.scope_manager.is_in_function():
            self.error("can only be used in a function", shell)
            return 1

        # Parse options and arguments
        options, positional = self._parse_options(args[1:], shell)
        if options is None:
            return 2  # invalid option (bash usage-error status)

        # If no arguments, just return success (bash behavior)
        if not positional:
            return 0

        # Build attributes from options
        from ..core import VarAttributes
        attributes = VarAttributes.NONE
        if options['readonly']:
            attributes |= VarAttributes.READONLY
        if options['export']:
            attributes |= VarAttributes.EXPORT
        if options['integer']:
            attributes |= VarAttributes.INTEGER
        if options['lowercase']:
            attributes |= VarAttributes.LOWERCASE
        if options['uppercase']:
            attributes |= VarAttributes.UPPERCASE
        if options['array']:
            attributes |= VarAttributes.ARRAY
        if options['assoc_array']:
            attributes |= VarAttributes.ASSOC_ARRAY
        if options['nameref']:
            attributes |= VarAttributes.NAMEREF
        if options['lowercase'] and options['uppercase']:
            # -l and -u together cancel: bash applies NEITHER transform and
            # records neither attribute (``local -ul x=Hello`` -> value
            # "Hello", ``declare -p`` shows ``declare --``). Matches the declare
            # builtin's _attributes_from_options.
            attributes &= ~(VarAttributes.LOWERCASE | VarAttributes.UPPERCASE)

        # Process each argument
        from ..lexer.unicode_support import is_valid_name
        posix_mode = shell.state.options.get('posix', False)
        for arg in positional:
            if arg == '-':
                # `local -`: save the shell's `set` options so they revert on
                # function return (bash). It is NOT a variable named '-'.
                self._save_dash_options(shell)
                continue
            # Validate the target NAME (bash: "not a valid identifier",
            # status 1). Same single identifier policy as declare — posix mode
            # restricts to ASCII; otherwise psh's lenient Unicode default
            # applies. A subscripted / append LHS validates its base name.
            name_part = arg.split('=', 1)[0]
            if name_part.endswith('+') and not options['nameref']:
                name_part = name_part[:-1]
            if not is_valid_name(name_part.split('[', 1)[0], posix_mode):
                self.error(f"`{arg}': not a valid identifier", shell)
                return 1
            if '=' in arg:
                # Variable with assignment: local var=value / var+=value
                var_name, var_value = arg.split('=', 1)
                append = var_name.endswith('+') and not options['nameref']
                if append:
                    var_name = var_name[:-1]

                # Name reference: store the target name verbatim (no expansion,
                # no array parsing) with the NAMEREF attribute.
                if options['nameref']:
                    if var_name == var_value:
                        self.error(f"{var_name}: nameref variable self references not allowed", shell)
                        return 1
                    shell.state.scope_manager.create_local(var_name, var_value, attributes)
                    continue

                # Array initialization is keyed STRICTLY on the parser having
                # seen literal ``var=(...)`` syntax: it attaches a structured
                # ArrayInitialization to the arg Word, delivered via the
                # shell's explicit pending-array-init handoff. We expand it
                # through the SAME structured path the bare ``a=(...)`` form uses (no
                # shlex reparse). A merely paren-shaped VALUE that did NOT
                # come from array syntax (``local "a=(1 2)"``) is a scalar in
                # bash, so it is NOT array-ified.
                array_init = context.array_init(arg)
                if array_init is not None:
                    # Parse array initialization; += appends to/merges with
                    # an existing array of the same kind (bash).
                    from ..core import AssociativeArray, IndexedArray
                    existing = (shell.state.scope_manager.get_variable_object(var_name)
                                if append else None)
                    into: object
                    if attributes & VarAttributes.ASSOC_ARRAY:
                        into = (existing.value
                                if existing is not None
                                and isinstance(existing.value, AssociativeArray)
                                else None)
                        array = self._build_assoc_array(array_init, into, shell)
                        shell.state.scope_manager.create_local(var_name, array, attributes | VarAttributes.ASSOC_ARRAY)
                    else:
                        into = (existing.value
                                if existing is not None
                                and isinstance(existing.value, IndexedArray)
                                else None)
                        array = self._build_indexed_array(array_init, into, shell)
                        shell.state.scope_manager.create_local(var_name, array, attributes | VarAttributes.ARRAY)
                else:
                    # Regular variable assignment. The executor has already
                    # expanded this argument; expanding again here would run
                    # single-quoted text like '$(cmd)' a second time.
                    if append:
                        from ..core import resolve_append_assignment
                        _, var_value = resolve_append_assignment(
                            shell.state.scope_manager, var_name + '+', var_value)

                    # Attribute transforms (-u/-l/-i) are applied by the single
                    # chokepoint in create_local -> ScopeManager._apply_attributes,
                    # NOT here: a second, divergent copy used to run first and
                    # mishandled -ul (it uppercased instead of applying neither).
                    shell.state.scope_manager.create_local(var_name, var_value, attributes)
            else:
                # Variable without assignment: local var
                if attributes & VarAttributes.ARRAY:
                    # Create empty indexed array
                    from ..core import IndexedArray
                    shell.state.scope_manager.create_local(arg, IndexedArray(), attributes)
                elif attributes & VarAttributes.ASSOC_ARRAY:
                    # Create empty associative array
                    from ..core import AssociativeArray
                    shell.state.scope_manager.create_local(arg, AssociativeArray(), attributes)
                else:
                    # Declared-but-unset local: shadows any outer variable
                    # but reads as unset (bash: ``local v; echo ${v-u}``
                    # prints ``u``). create_local(value=None) plants the
                    # UNSET-attributed variable.
                    shell.state.scope_manager.create_local(arg, None, attributes)

        return 0

    def _save_dash_options(self, shell: 'Shell') -> None:
        """Record the current `set` options for `local -` restore-on-return.

        Snapshots the SET-category options (what the `set` builtin changes;
        shopt/debug/internal are untouched by `local -`, per bash) plus the
        edit mode onto the current function scope. The function-return path
        (FunctionOperationExecutor) restores them. The first `local -` in a
        function wins — a second is a no-op, so options revert to their
        pre-`local -` values (bash).
        """
        from ..core.option_registry import OPTION_REGISTRY, OptionCategory
        scope = shell.state.scope_manager.current_scope
        if scope.dash_snapshot is not None:
            return
        snapshot = {name: shell.state.options[name]
                    for name, spec in OPTION_REGISTRY.items()
                    if spec.category is OptionCategory.SET}
        scope.dash_snapshot = (snapshot, shell.state.edit_mode)

    def _build_indexed_array(self, array_init, into, shell: 'Shell'):
        """Build an IndexedArray from the structured init via the shared
        ArrayOperationExecutor engine (the SAME path the bare ``a=(...)``
        form uses; no string reparse)."""
        from ..executor.array import ArrayOperationExecutor
        return ArrayOperationExecutor(shell).build_indexed_array(
            array_init.words, into=into)

    def _build_assoc_array(self, array_init, into, shell: 'Shell'):
        """Build an AssociativeArray from the structured init via the shared
        engine (see _build_indexed_array)."""
        from ..executor.array import ArrayOperationExecutor
        return ArrayOperationExecutor(shell).build_associative_array(
            array_init.words, into=into)

    def _parse_options(self, args: List[str], shell: 'Shell') -> tuple:
        """Parse local options and return (options_dict, positional_args)."""
        options = {
            'array': False,          # -a
            'assoc_array': False,    # -A
            'integer': False,        # -i
            'lowercase': False,      # -l
            'nameref': False,        # -n
            'readonly': False,       # -r
            'uppercase': False,      # -u
            'export': False,         # -x
        }
        positional = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == '--':  # End of options
                positional.extend(args[i+1:])
                break
            elif arg.startswith('-') and len(arg) > 1 and not arg[1].isdigit():
                # Process flags
                for flag in arg[1:]:
                    if flag == 'a':
                        options['array'] = True
                    elif flag == 'A':
                        options['assoc_array'] = True
                    elif flag == 'i':
                        options['integer'] = True
                    elif flag == 'l':
                        options['lowercase'] = True
                    elif flag == 'n':
                        options['nameref'] = True
                    elif flag == 'r':
                        options['readonly'] = True
                    elif flag == 'u':
                        options['uppercase'] = True
                    elif flag == 'x':
                        options['export'] = True
                    else:
                        self.error(f"invalid option: -{flag}", shell)
                        return None, []
            else:
                positional.append(arg)
            i += 1

        return options, positional

    @property
    def help(self) -> str:
        return """local: local [-aAilrux] [name[=value] ...]

    Create local variables within functions.

    Options:
      -a    Declare indexed array variables
      -A    Declare associative array variables
      -i    Make variables have the 'integer' attribute
      -l    Convert values to lowercase on assignment
      -r    Make variables readonly
      -u    Convert values to uppercase on assignment
      -x    Make variables export to the environment

    When used inside a function, creates variables that are only
    visible within that function. Without an assignment, the variable
    is created but unset.

    Examples:
        local var              # Create unset local variable
        local var=value        # Create local with value
        local -i num=42        # Create local integer variable
        local -u text=hello    # Create local uppercase variable
        local x=1 y=2 z        # Multiple variables

    Note: Using 'local' outside a function is an error."""
