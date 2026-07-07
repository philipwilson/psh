"""Shell state related builtins (history, version, local)."""

import re
from typing import TYPE_CHECKING, List, Optional

from .base import EMPTY_BUILTIN_CONTEXT, Builtin, BuiltinContext
from .registry import builtin

if TYPE_CHECKING:
    from ..interactive.history_manager import HistoryManager
    from ..shell import Shell


_HISTORY_USAGE = ("usage: history [-c] [-d offset] [n] or history -anrw "
                  "[filename] or history -ps arg [arg...]")


@builtin
class HistoryBuiltin(Builtin):
    """Display or manipulate the command history list."""

    @property
    def name(self) -> str:
        return "history"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Display or manipulate command history.

        NOTE: deliberately NOT parse_flags(). This is a hand dispatch because
        bash's ``history`` conflates a numeric ``n`` operand (``history 5``,
        show the last 5) with option letters, and its bad-input messages/exit
        codes (``abc: numeric argument required`` at 1, ``-5: invalid option``
        at 2, ``5: history position out of range`` for ``-d``) diverge from the
        shared helper's contract.
        """
        if len(args) <= 1:
            return self._display(shell, None)

        first = args[1]
        # Anything beginning with '-' (other than a bare '-') is an option;
        # bash even rejects '-5' as an invalid option rather than a count.
        if first.startswith('-') and first != '-':
            return self._dispatch_flag(first, args[2:], shell)

        # Otherwise a numeric operand: show the last N entries.
        try:
            count = int(first)
        except ValueError:
            self.error(f"{first}: numeric argument required", shell)
            return 1
        return self._display(shell, count)

    # -- display ------------------------------------------------------------

    def _display(self, shell: 'Shell', count: Optional[int]) -> int:
        history = shell.state.history
        if count is None:
            entries = history           # bash lists the WHOLE history
        else:
            entries = history[max(0, len(history) - count):]
        start_num = len(history) - len(entries) + 1
        for i, cmd in enumerate(entries):
            self.write_line(f"{start_num + i:5d}  {cmd}", shell)
        return 0

    # -- option dispatch ----------------------------------------------------

    def _dispatch_flag(self, flag: str, rest: List[str], shell: 'Shell') -> int:
        hist_mgr = self._history_manager(shell)
        if hist_mgr is None:
            # No interactive history manager available (unexpected); the only
            # thing we can still honor without one is clearing the raw list.
            if flag == '-c':
                shell.state.history.clear()
                return 0
            return 0

        if flag == '-c':
            # Route through the manager so the file-sync markers reset too —
            # clearing state.history directly left them stale and dropped
            # post-clear commands from HISTFILE on save (data loss).
            hist_mgr.clear_history()
            return 0

        if flag in ('-w', '-r', '-a', '-n'):
            path = rest[0] if rest else None
            method = {
                '-w': hist_mgr.write_history,
                '-r': hist_mgr.read_history,
                '-a': hist_mgr.append_history,
                '-n': hist_mgr.read_new_history,
            }[flag]
            if not method(path):
                target = path or shell.state.history_file
                self.error(f"{target}: cannot access history file", shell)
                return 1
            return 0

        if flag == '-d':
            return self._delete(rest, shell, hist_mgr)

        if flag == '-s':
            # Store the args as one entry, without executing them.
            if rest:
                hist_mgr.store_entry(' '.join(rest))
            return 0

        if flag == '-p':
            # Perform history expansion on args and print without storing.
            # Implementing this needs the interactive '!' expansion engine;
            # be honest rather than echo a misleadingly-unexpanded result.
            self.error("-p: history expansion not supported by psh", shell)
            return 2

        return self._usage_error(f"{flag}: invalid option", shell)

    def _delete(self, rest: List[str], shell: 'Shell',
                hist_mgr: 'HistoryManager') -> int:
        if not rest:
            return self._usage_error("-d: option requires an argument", shell)
        spec = rest[0]
        n = len(shell.state.history)

        # Single offset (a positive position, or negative from the end).
        try:
            idx = self._resolve_offset(int(spec), n)
        except ValueError:
            idx = None
        else:
            if idx is None:
                self.error(f"{spec}: history position out of range", shell)
                return 1
            hist_mgr.delete_entry(idx + 1, idx + 1)
            return 0

        # Range form: start-end (both 1-based, inclusive).
        m = re.fullmatch(r'(\d+)-(\d+)', spec)
        if m:
            lo = self._resolve_offset(int(m.group(1)), n)
            hi = self._resolve_offset(int(m.group(2)), n)
            if lo is None or hi is None or lo > hi:
                self.error(f"{spec}: history position out of range", shell)
                return 1
            hist_mgr.delete_entry(lo + 1, hi + 1)
            return 0

        # Non-numeric argument — bash reports it as out of range, not a
        # "numeric argument required".
        self.error(f"{spec}: history position out of range", shell)
        return 1

    @staticmethod
    def _resolve_offset(offset: int, n: int) -> Optional[int]:
        """Map a 1-based history position (negative = from the end) to a 0-based
        index, or None when out of range."""
        if offset > 0:
            idx = offset - 1
        elif offset < 0:
            idx = n + offset
        else:
            return None
        return idx if 0 <= idx < n else None

    def _usage_error(self, message: str, shell: 'Shell') -> int:
        self.error(message, shell)
        self.error(_HISTORY_USAGE, shell)
        return 2

    @staticmethod
    def _history_manager(shell: 'Shell') -> 'Optional[HistoryManager]':
        return getattr(getattr(shell, 'interactive_manager', None),
                       'history_manager', None)

    @property
    def help(self) -> str:
        return """history: history [n] | history -c | history -d offset[-end]
       history -anrw [filename] | history -s arg [arg...]

    Display or manipulate the command history list.

    With no options, list the whole history with line numbers; a numeric N
    lists only the last N entries.

    Options:
      -c           Clear the history list
      -d offset    Delete the entry at OFFSET (negative counts from the end;
                   OFFSET-END deletes a range)
      -a [file]    Append new history since the last write/append to FILE
                   (default: $HISTFILE)
      -n [file]    Read history lines from FILE not already read into memory
      -r [file]    Read (append) FILE's contents into the history list
      -w [file]    Write the whole history list to FILE
      -s arg ...   Store ARGs as a single entry, without executing them

    The -p (expand-and-print) option is not supported.

    Default is to show the entire history."""


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
                    # Build += into a COPY, not the live array: if the target
                    # is readonly, create_local rejects the assignment and the
                    # live array must stay untouched (C2/P1.2 — a failed
                    # operation does not mutate a readonly value).
                    if attributes & VarAttributes.ASSOC_ARRAY:
                        into = (existing.value.copy()
                                if existing is not None
                                and isinstance(existing.value, AssociativeArray)
                                else None)
                        array = self._build_assoc_array(array_init, into, shell)
                        shell.state.scope_manager.create_local(var_name, array, attributes | VarAttributes.ASSOC_ARRAY)
                    else:
                        into = (existing.value.copy()
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
                        # ``local x+=v`` appends only to an x ALREADY local in
                        # THIS scope; a fresh local starts from empty even when
                        # an outer scope has x (bash: g(){ local x+=INNER;}
                        # called under f's ``local x=out`` yields ``INNER``, not
                        # ``outINNER``). resolve_append_assignment reads the
                        # innermost instance, so gate it on the current scope.
                        cur = shell.state.scope_manager.current_scope.variables.get(var_name)
                        if cur is not None and not cur.is_unset:
                            from ..core import resolve_append_assignment
                            _, var_value = resolve_append_assignment(
                                shell.state.scope_manager, var_name + '+', var_value)
                        # else: fresh local — the raw RHS IS the value (an -i
                        # flag, if any, is applied by create_local's transform).

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
