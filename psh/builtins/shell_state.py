"""Shell state related builtins (history, version, local)."""
import re
from typing import TYPE_CHECKING, List, Optional

from ..core import AssociativeArray, IndexedArray, ReadonlyVariableError, VarAttributes, resolve_append_assignment
from ..core.option_registry import OPTION_REGISTRY, OptionCategory
from ..lexer.unicode_support import is_valid_name
from .base import EMPTY_BUILTIN_CONTEXT, Builtin, BuiltinContext
from .registry import builtin

if TYPE_CHECKING:
    from ..core import VarAttributes
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
            # Store the args as one entry, without executing them. bash strips
            # the `history -s ...` invocation itself first, so the stored line
            # REPLACES it rather than lingering beside it (CV3).
            if rest:
                self._strip_own_invocation(shell)
                hist_mgr.store_entry(' '.join(rest))
            return 0

        if flag == '-p':
            return self._expand_print(rest, shell)

        return self._usage_error(f"{flag}: invalid option", shell)

    @staticmethod
    def _strip_own_invocation(shell: 'Shell') -> None:
        """Remove the `history -p`/`-s` invocation's OWN just-recorded history
        entry (bash) — so a `!!` operand refers to the command BEFORE the
        `history` call and the invocation does not linger. Interactive-family
        only, and ONLY the verified invocation: the source processor records the
        line it added (``_last_recorded_history_line``); a HISTCONTROL/HISTIGNORE
        -filtered or non-recorded line leaves the marker None, so no prior entry
        is stripped by mistake (the ignorespace/ignoredups edge — probed vs bash
        5.2). The list is mutated in place, preserving the editor list-alias
        contract. Called only when there are operands (bash: `history -p`/`-s`
        with no operands strips nothing)."""
        state = shell.state
        line = getattr(state, '_last_recorded_history_line', None)
        if line is not None and state.history and state.history[-1] == line:
            del state.history[-1]
            state._last_recorded_history_line = None

    def _expand_print(self, rest: List[str], shell: 'Shell') -> int:
        """``history -p arg...``: history-expand each ARG and print the result
        to STDOUT without storing it (bash). This is the SECOND consumer of the
        typed HistoryExpansionResult (campaign I4): the outcome ``kind`` drives
        printing vs the error path — no re-derivation. A leading ``--`` ends
        option processing (bash)."""
        expander = getattr(shell, 'history_expander', None)
        if expander is None:  # pragma: no cover - every Shell builds one
            self.error("-p: history expansion unavailable", shell)
            return 2
        if rest and rest[0] == '--':
            rest = rest[1:]
        # bash strips the `history -p ...` invocation from history BEFORE
        # expanding (only WITH operands), so a `!!` operand refers to the
        # command before this `history -p`, not to the invocation itself.
        if rest:
            self._strip_own_invocation(shell)
        status = 0
        for arg in rest:
            # force=True: `history -p` expands regardless of `set +H` (bash).
            result = expander.expand_history(arg, force=True)
            if result.is_error:
                # bash reports a `history -p` failure and returns nonzero.
                self.error(result.error, shell)
                status = 1
            else:
                # NONE / EXPANDED / PRINT_ONLY all print their resulting text;
                # `history -p` never executes and never records.
                self.write_line(result.text, shell)
        return status

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
      -p arg ...   History-expand each ARG and print the result, without
                   storing or executing

    Default is to show the entire history."""


@builtin
class VersionBuiltin(Builtin):
    """Display version information."""

    @property
    def name(self) -> str:
        return "version"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Display version information."""
        # Lazy so tests can patch psh.version.__version__ (late binding).
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

        # Build the add/remove attribute sets through the SHARED declaration
        # engine (same table + -l/-u cancellation rule declare uses; H5).
        from .declaration_engine import (
            attributes_from_options,
            removed_attributes_from_options,
        )
        attributes = attributes_from_options(options)
        remove_attrs = removed_attributes_from_options(options)

        # Process each argument. bash's `local` arg loop is CONTINUE-ON-ERROR:
        # every argument is processed even after one fails. A per-arg failure —
        # an invalid identifier OR a value redeclare onto a readonly local —
        # is reported and that argument is skipped, but the good arguments are
        # still created and `local` returns 1 (probes: `local -r x=1; local x=2
        # y=3` -> error on x, y=3 still set, rc 1; `local 1bad x=2` -> error on
        # 1bad, x=2 still set, rc 1). Only an OPTION-parse error (handled above)
        # aborts the whole builtin.
        failed = False
        for arg in positional:
            try:
                if not self._declare_one_local(arg, shell, context,
                                               attributes, remove_attrs, options):
                    failed = True
            except ReadonlyVariableError as e:
                # A value redeclare onto a readonly local: create_local raises,
                # we report in bash's shape and keep going. self.error() renders
                # the SAME `<$0>: line N: local: NAME: readonly variable` line
                # the last-resort builtin guard printed when this used to
                # propagate, so the single-arg output is byte-identical.
                self.error(str(e), shell)
                failed = True
        return 1 if failed else 0

    def _declare_one_local(self, arg: str, shell: 'Shell',
                           context: BuiltinContext, attributes: 'VarAttributes',
                           remove_attrs: 'VarAttributes', options: dict) -> bool:
        """Create ONE ``local`` binding for *arg*.

        Returns True on success, False if a per-arg error was already reported
        (invalid identifier / nameref self-reference / invalid nameref target —
        the caller then makes the builtin return 1). Raises
        :class:`ReadonlyVariableError` for a value redeclare onto a readonly
        local OR a ``+r`` that would clear readonly, which the CALLER catches so
        it can report and continue with the remaining arguments (bash's
        continue-on-error arg loop). ``remove_attrs`` are the ``+flag``
        attributes to clear (H5 carry).
        """
        posix_mode = shell.state.options.get('posix', False)
        if arg == '-':
            # `local -`: save the shell's `set` options so they revert on
            # function return (bash). It is NOT a variable named '-'.
            self._save_dash_options(shell)
            return True
        # Validate the target NAME (bash: "not a valid identifier",
        # status 1). Same single identifier policy as declare — posix mode
        # restricts to ASCII; otherwise psh's lenient Unicode default
        # applies. A subscripted / append LHS validates its base name.
        name_part = arg.split('=', 1)[0]
        if name_part.endswith('+') and not options['nameref']:
            name_part = name_part[:-1]
        if not is_valid_name(name_part.split('[', 1)[0], posix_mode):
            self.error(f"`{arg}': not a valid identifier", shell)
            return False
        if '=' in arg:
            # Variable with assignment: local var=value / var+=value
            var_name, var_value = arg.split('=', 1)
            append = var_name.endswith('+') and not options['nameref']
            if append:
                var_name = var_name[:-1]

            # Name reference: store the target name verbatim (no expansion,
            # no array parsing) with the NAMEREF attribute. bash validates the
            # target's SHAPE at `local -n` time exactly like `declare -n`
            # (H5): shared engine check (an empty target gets bash's
            # plain-identifier message; any other invalid shape the
            # nameref-specific one).
            if options['nameref']:
                from .declaration_engine import is_valid_nameref_target
                if var_name == var_value:
                    self.error(f"{var_name}: nameref variable self references not allowed", shell)
                    return False
                if not var_value:
                    self.error("`': not a valid identifier", shell)
                    return False
                if not is_valid_nameref_target(var_value, posix_mode):
                    self.error(f"`{var_value}': invalid variable name for name reference", shell)
                    return False
                shell.state.scope_manager.create_local(var_name, var_value, attributes)
                return True

            # Array initialization is keyed STRICTLY on the parser having
            # seen literal ``var=(...)`` syntax: it attaches a structured
            # ArrayInitialization to the arg Word, delivered via the
            # shell's explicit pending-array-init handoff. We expand it
            # through the SAME shared engine home as declare (build_array_init;
            # no shlex reparse; the copy-then-build += snapshot lives there). A
            # merely paren-shaped VALUE that did NOT come from array syntax
            # (``local "a=(1 2)"``) is a scalar in bash, so it is NOT array-ified.
            array_init = context.array_init(arg)
            if array_init is not None:
                from .declaration_engine import DeclarationEngine
                assoc = bool(attributes & VarAttributes.ASSOC_ARRAY)
                existing = (shell.state.scope_manager.get_variable_object(var_name)
                            if append else None)
                array = DeclarationEngine(shell).build_array_init(
                    array_init, assoc=assoc, append=append, existing=existing)
                kind_attr = (VarAttributes.ASSOC_ARRAY if assoc
                             else VarAttributes.ARRAY)
                shell.state.scope_manager.create_local(
                    var_name, array, attributes | kind_attr)
            else:
                # Regular variable assignment. The executor has already
                # expanded this argument; expanding again here would run
                # single-quoted text like '$(cmd)' a second time.
                value_to_set: object = var_value
                if append:
                    # ``local x+=v`` appends only to an x ALREADY local in
                    # THIS scope; a fresh local starts from empty even when
                    # an outer scope has x (bash: g(){ local x+=INNER;}
                    # called under f's ``local x=out`` yields ``INNER``, not
                    # ``outINNER``). resolve_append_assignment reads the
                    # innermost instance, so gate it on the current scope. It
                    # may return an array object (scalar += onto an array), so
                    # the value handed to create_local is wider than str.
                    cur = shell.state.scope_manager.current_scope.variables.get(var_name)
                    if cur is not None and not cur.is_unset:
                        # Pass the local's being-added flags (``local -i n+=3``)
                        # so a fresh -i makes the append arithmetic (bash), even
                        # when the existing local is not yet integer.
                        _, value_to_set = resolve_append_assignment(
                            shell.state.scope_manager, var_name + '+', var_value,
                            extra_attrs=attributes)
                    # else: fresh local — the raw RHS IS the value (an -i
                    # flag, if any, is applied by create_local's transform).

                # Attribute transforms (-u/-l/-i) are applied by the single
                # chokepoint in create_local -> ScopeManager._apply_attributes,
                # NOT here: a second, divergent copy used to run first and
                # mishandled -ul (it uppercased instead of applying neither).
                self._create_local_with_removal(
                    shell, var_name, value_to_set, attributes, remove_attrs)
        else:
            # Variable without assignment: local var
            if attributes & VarAttributes.ARRAY:
                # Create empty indexed array
                shell.state.scope_manager.create_local(arg, IndexedArray(), attributes)
            elif attributes & VarAttributes.ASSOC_ARRAY:
                # Create empty associative array
                shell.state.scope_manager.create_local(arg, AssociativeArray(), attributes)
            else:
                # Declared-but-unset local: shadows any outer variable
                # but reads as unset (bash: ``local v; echo ${v-u}``
                # prints ``u``). create_local(value=None) plants the
                # UNSET-attributed variable. ``local +x v`` clears the +attrs.
                self._create_local_with_removal(
                    shell, arg, None, attributes, remove_attrs)
        return True

    def _create_local_with_removal(self, shell: 'Shell', name: str,
                                   value: object, add_attrs: 'VarAttributes',
                                   remove_attrs: 'VarAttributes') -> None:
        """``create_local(name, value, add_attrs)`` then clear ``remove_attrs``
        from the resulting LOCAL (bash's ``local +x``/``+i``/``+n``/... removal).

        The removal targets the local: if ``name`` is ALREADY local in this
        scope — INCLUDING a declared-but-unset tombstone (``local -r v``), which
        IS a local and keeps its attributes — we strip FIRST, so ``+r`` on a
        readonly local raises :class:`ReadonlyVariableError` BEFORE anything can
        mutate (bash: rc 1, readonly and value intact). The r19-T2 bounce
        blocker: tombstones used to route down the fresh-local path, where
        create_local clobbered the attributes before the removal ran, silently
        STRIPPING readonly (``local -r v; local +r v`` must instead report
        ``local: v: readonly variable``). Strip-first also means a value is
        transformed with the POST-removal attributes (bash removes the
        attribute before assigning — ``local +i n=2+3`` stores ``2+3``
        literally, not the evaluated ``5``).

        A tombstone ATTRS-ONLY redeclare (no value) is mutated IN PLACE
        (remove + apply): create_local's fresh path (a tombstone is not a
        ``redeclare``) would REPLACE the cell and drop its remaining attributes
        (``local -rx e; local +x e`` must keep readonly — bash ``declare -r e``).

        A FRESH name is established first (inheriting only EXPORT from the
        variable it shadows), then the inherited attribute is stripped
        (``export G=g; f(){ local +x G=z; }`` gives a non-exported local
        shadow).
        """
        sm = shell.state.scope_manager
        if not remove_attrs:
            sm.create_local(name, value, add_attrs)
            return
        cur = sm.current_scope.variables.get(name)
        if cur is not None:
            sm.remove_attribute(name, remove_attrs)  # may raise (+r on readonly)
            if value is None and cur.is_unset:
                # Tombstone attrs-only: mutate in place, keep remaining attrs.
                if add_attrs:
                    sm.apply_attribute(name, add_attrs)
                return
            sm.create_local(name, value, add_attrs)
            return
        sm.create_local(name, value, add_attrs)
        sm.remove_attribute(name, remove_attrs)

    def _save_dash_options(self, shell: 'Shell') -> None:
        """Record the current `set` options for `local -` restore-on-return.

        Snapshots the SET-category options (what the `set` builtin changes;
        shopt/debug/internal are untouched by `local -`, per bash) plus the
        edit mode onto the current function scope. The function-return path
        (FunctionOperationExecutor) restores them. The first `local -` in a
        function wins — a second is a no-op, so options revert to their
        pre-`local -` values (bash).
        """
        scope = shell.state.scope_manager.current_scope
        if scope.dash_snapshot is not None:
            return
        snapshot = {name: shell.state.options[name]
                    for name, spec in OPTION_REGISTRY.items()
                    if spec.category is OptionCategory.SET}
        scope.dash_snapshot = (snapshot, shell.state.edit_mode)

    # Flag char → option key. ``-c`` sets the key; ``+c`` sets ``remove_``+key
    # (attribute removal, bash's `local +x`/`+i`/... — H5 carry). Shared shape
    # with declare's option parser.
    _FLAG_OPTIONS = {
        'a': 'array', 'A': 'assoc_array', 'i': 'integer', 'l': 'lowercase',
        'n': 'nameref', 'r': 'readonly', 'u': 'uppercase', 'x': 'export',
    }

    def _parse_options(self, args: List[str], shell: 'Shell') -> tuple:
        """Parse local options and return (options_dict, positional_args).

        Accepts both ``-flag`` (set an attribute) and ``+flag`` (remove an
        attribute) clusters, like ``declare`` — ``local +x v`` clears export
        (H5 carry: this closes the ``local +r``/``+attr`` parse gap).
        """
        options: dict = {key: False for key in self._FLAG_OPTIONS.values()}
        options.update({f'remove_{key}': False
                        for key in self._FLAG_OPTIONS.values()})
        positional = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == '--':  # End of options
                positional.extend(args[i+1:])
                break
            elif arg.startswith('-') and len(arg) > 1 and not arg[1].isdigit():
                # Attribute-setting flags (clusterable: -aix)
                for flag in arg[1:]:
                    key = self._FLAG_OPTIONS.get(flag)
                    if key is None:
                        self.error(f"invalid option: -{flag}", shell)
                        return None, []
                    options[key] = True
            elif arg.startswith('+') and len(arg) > 1:
                # Attribute-removal flags (clusterable: +ix)
                for flag in arg[1:]:
                    key = self._FLAG_OPTIONS.get(flag)
                    if key is None:
                        self.error(f"invalid option: +{flag}", shell)
                        return None, []
                    options[f'remove_{key}'] = True
            else:
                positional.append(arg)
            i += 1

        return options, positional

    @property
    def help(self) -> str:
        return """local: local [-aAilnrux] [name[=value] ...]

    Create local variables within functions.

    Options:
      -a    Declare indexed array variables
      -A    Declare associative array variables
      -i    Make variables have the 'integer' attribute
      -l    Convert values to lowercase on assignment
      -n    Make NAME a name reference to the variable named by its value
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
