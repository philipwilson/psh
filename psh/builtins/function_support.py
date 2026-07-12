"""Function-related builtin commands."""
from typing import TYPE_CHECKING, Any, List, Optional, cast

from ..core import (
    AssociativeArray,
    IndexedArray,
    ReadonlyVariableError,
    SpecialBuiltinUsageError,
    TargetScope,
    VarAttributes,
    Variable,
    special_builtin_usage_discard,
)

# FunctionReturn now lives with its control-flow siblings in
# core/exceptions.py; re-exported here because many call sites
# historically import it from this module.
from ..core.exceptions import FunctionReturn  # noqa: F401
from ..lexer.unicode_support import is_valid_name
from ..visitor import format_function_definition
from .base import EMPTY_BUILTIN_CONTEXT, Builtin, BuiltinContext
from .declare_format import format_declaration, matches_filter
from .registry import builtin, registry

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class DeclareBuiltin(Builtin):
    """Declare variables and functions with attributes."""

    @property
    def name(self) -> str:
        return "declare"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        return self.execute_in_context(args, shell, EMPTY_BUILTIN_CONTEXT)

    def execute_in_context(self, args: List[str], shell: 'Shell',
                           context: BuiltinContext) -> int:
        """Execute the declare builtin.

        ``context`` carries the structured array initializers the executor
        collected for any ``name=(...)`` argument (see BuiltinContext).
        """
        return self.run_as(args, shell, context, invoked_as=self.name,
                           special=False)

    def run_as(self, args: List[str], shell: 'Shell', context: BuiltinContext,
               *, invoked_as: str, special: bool,
               catch_readonly: bool = True) -> int:
        """``execute_in_context`` with an explicit diagnostic label + POSIX
        special-builtin policy, so ``typeset``/``readonly`` can delegate here and
        get correctly-labeled, correctly-fatal diagnostics (H5).

        - ``invoked_as`` — the builtin name used to label the variable-path
          diagnostics (``declare``/``typeset``/``readonly``).
        - ``special`` — True for ``readonly``: a readonly-assignment error emits
          BARE and (after processing every operand) raises
          :class:`SpecialBuiltinUsageError` so a posix non-interactive shell
          exits.
        - ``catch_readonly`` — False lets a readonly error propagate to the
          caller (``export``'s array-init delegation renders its own message).
        """
        # Parse options
        options, positional = self._parse_options(args[1:], shell)
        if options is None:
            return 2  # invalid option (bash usage-error status)

        # Validate exclusive options
        if options['array'] and options['assoc_array']:
            self.error("cannot use both -a and -A options", shell)
            return 1

        # Handle different modes
        if options['functions'] or options['function_names']:
            return self._handle_functions(options, positional, shell)
        elif options['nameref'] and not positional:
            # `declare -n` / `declare -pn` / `declare -p -n` with no names lists
            # ONLY nameref variables (bash). The old paths omitted nameref from
            # the listing filter and dumped every variable (builtins appraisal
            # finding 3). Named forms (`declare -pn r`) still print the named
            # variable's own declaration through _print_variables below.
            return self._list_namerefs(shell)
        elif options['print']:
            return self._print_variables(options, positional, shell)
        elif not positional and any([
            options['readonly'], options['export'], options['integer'],
            options['lowercase'], options['uppercase'], options['array'],
            options['assoc_array'], options['trace']
        ]):
            # When attribute flags are specified without arguments, list matching variables
            # This handles cases like "declare -r" (list readonly vars)
            return self._print_variables(options, positional, shell)
        else:
            return self._declare_variables(options, positional, shell, context,
                                           invoked_as=invoked_as, special=special,
                                           catch_readonly=catch_readonly)

    # Flag char → option key (set with `-c`; `+c` sets 'remove_' + key for
    # the chars in _REMOVABLE_FLAGS). declare cannot use Builtin.parse_flags
    # because of the `+x` attribute-removal syntax.
    _FLAG_OPTIONS = {
        'a': 'array',
        'A': 'assoc_array',
        'f': 'functions',
        'F': 'function_names',
        'g': 'global',
        'i': 'integer',
        'l': 'lowercase',
        'n': 'nameref',
        'p': 'print',
        'r': 'readonly',
        't': 'trace',
        'u': 'uppercase',
        'x': 'export',
    }
    _REMOVABLE_FLAGS = frozenset('aAilnrtux')

    def _parse_options(self, args: List[str], shell: 'Shell') -> tuple[Optional[dict], List[str]]:
        """Parse declare options and return (options_dict, positional_args)."""
        options: dict[str, Any] = {key: False for key in self._FLAG_OPTIONS.values()}
        options.update({f'remove_{self._FLAG_OPTIONS[c]}': False
                        for c in self._REMOVABLE_FLAGS})
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
                    if flag not in self._REMOVABLE_FLAGS:
                        self.error(f"invalid option: +{flag}", shell)
                        return None, []
                    options[f'remove_{self._FLAG_OPTIONS[flag]}'] = True
            else:
                positional.append(arg)
            i += 1

        return options, positional

    def _handle_functions(self, options: dict, names: List[str], shell: 'Shell') -> int:
        """Handle function-related options (-f, -F)."""
        show_names_only = options['function_names']
        fm = shell.function_manager

        # Attribute flags combined with -f/-F APPLY the attribute to the
        # named functions rather than printing them (bash: `declare -fx f`
        # exports f, `declare -fr f` makes it readonly, `declare -ft f`
        # sets the trace attribute so f inherits the RETURN trap; an
        # undefined name is silent with status 1, like `declare -f NAME`).
        if names and (options['export'] or options['remove_export']
                      or options['readonly']
                      or options['trace'] or options['remove_trace']):
            exit_code = 0
            for name in names:
                if fm.get_function(name) is None:
                    exit_code = 1
                    continue
                if options['export'] or options['remove_export']:
                    fm.set_function_exported(name, options['export'])
                if options['readonly']:
                    fm.set_function_readonly(name)
                if options['trace'] or options['remove_trace']:
                    fm.set_function_trace(name, options['trace'])
            return exit_code

        if not names:
            # List all functions; `declare -fx`/-Fr etc. filter on the attribute.
            functions = sorted(fm.list_functions())
            if options['export']:
                functions = [(n, f) for n, f in functions if f.exported]
            if options['readonly']:
                functions = [(n, f) for n, f in functions if f.readonly]
            for name, func in functions:
                if show_names_only:
                    # -F flag: names only, with each function's attribute flags
                    self.write_line(f"declare -{self._function_flags(func)} {name}",
                                    shell)
                else:
                    # -f flag: full definitions; readonly/exported functions get
                    # a `declare -fr/-fx NAME` attribute line after the body (bash)
                    self._print_function_definition(name, func, shell)
                    if func.readonly or func.exported:
                        self.write_line(
                            f"declare -{self._function_flags(func)} {name}", shell)
        else:
            # List specific functions
            exit_code = 0
            for name in names:
                named_func = fm.get_function(name)
                if named_func:
                    if show_names_only:
                        # bash: `declare -F NAME` prints just the bare name
                        # (the no-name listing form prints `declare -f NAME`
                        # lines instead — handled in the no-names branch above).
                        self.write_line(name, shell)
                    else:
                        self._print_function_definition(name, named_func, shell)
                else:
                    # bash: `declare -f/-F NAME` for an undefined function is
                    # SILENT — exit status 1, no error message on stderr.
                    exit_code = 1
            return exit_code
        return 0

    @staticmethod
    def _function_flags(func) -> str:
        """The flag string for a function's attribute line (f, fr, ft, fx, ...)."""
        return ('f' + ('r' if func.readonly else '')
                + ('t' if getattr(func, 'trace', False) else '')
                + ('x' if func.exported else ''))

    def _is_valid_identifier(self, name: str, posix_mode: bool = False) -> bool:
        """Check if a name is a valid shell identifier.

        Delegates to the shell's single authoritative identifier policy
        (``unicode_support.is_valid_name``). ``posix_mode`` (``set -o posix``)
        restricts names to ASCII ``[A-Za-z_][A-Za-z0-9_]*`` as bash does;
        otherwise psh's lenient Unicode-letter rule applies.
        """
        return is_valid_name(name, posix_mode)

    # Nameref target-SHAPE validation + the -flag→VarAttributes mapping now
    # live in the shared declaration engine (H5: local -n reuses the same
    # check; the -l/-u cancel rule is defined once). Thin delegators keep the
    # call sites readable.
    def _is_valid_nameref_target(self, value: str, posix_mode: bool = False) -> bool:
        from .declaration_engine import is_valid_nameref_target
        return is_valid_nameref_target(value, posix_mode)

    def _attributes_from_options(self, options: dict) -> VarAttributes:
        from .declaration_engine import attributes_from_options
        return attributes_from_options(options)

    def _removed_attributes_from_options(self, options: dict) -> VarAttributes:
        from .declaration_engine import removed_attributes_from_options
        return removed_attributes_from_options(options)

    def _diag(self, invoked_as: str, message: str, shell: 'Shell') -> None:
        """Emit ``<$0>: line N: <invoked_as>: <message>`` — like ``error()`` but
        with an EXPLICIT builtin-name label, so ``readonly`` (which delegates
        through ``declare``) labels its diagnostics ``readonly:`` rather than
        ``declare:`` (H5 carry). ``report_error`` adds only the location prefix.
        """
        self.report_error(f"{invoked_as}: {message}", shell)

    def _declare_variables(self, options: dict, args: List[str], shell: 'Shell',
                           context: BuiltinContext, *, invoked_as: str,
                           special: bool, catch_readonly: bool = True) -> int:
        """Handle variable declarations (list, assignment, or bare-name forms).

        bash's declaration arg loop is CONTINUE-ON-ERROR: every operand is
        processed even after one fails (a readonly-value redeclare OR an invalid
        identifier is reported and skipped, good operands are still created, and
        the builtin returns 1). ``invoked_as`` labels the per-arg diagnostics
        (``declare``/``typeset``/``readonly``); ``special`` (``readonly``) emits
        the readonly-assignment error BARE (no builtin name) and, after the whole
        loop, raises :class:`SpecialBuiltinUsageError` so a POSIX-mode
        non-interactive shell exits (the special-builtin contract). When
        ``catch_readonly`` is False (``export``'s array-init delegation) a
        readonly error PROPAGATES so the delegating builtin can render its own
        (bare) message.
        """
        attributes = self._attributes_from_options(options)
        remove_attrs = self._removed_attributes_from_options(options)

        # If no arguments, list all shell variables (not environment)
        if not args:
            return self._declare_list_all(options, shell)

        failed = False
        saw_readonly = False
        for arg in args:
            try:
                if '=' in arg:
                    rc = self._declare_assignment(arg, options, attributes,
                                                  remove_attrs, shell, context,
                                                  invoked_as)
                else:
                    rc = self._declare_bare_name(arg, options, attributes,
                                                 remove_attrs, shell, invoked_as)
                if rc != 0:
                    failed = True
            except ReadonlyVariableError as e:
                if not catch_readonly:
                    raise
                if special:
                    # readonly: bash labels the assignment error BARE.
                    self.report_error(f"{e.name}: readonly variable", shell)
                    saw_readonly = True
                else:
                    # declare/typeset: byte-identical to the builtin guard's
                    # former `<$0>: line N: declare: NAME: readonly variable`.
                    self._diag(invoked_as, str(e), shell)
                failed = True
        if special and saw_readonly:
            # readonly is a POSIX special builtin: a readonly-assignment error
            # makes a posix-mode non-interactive shell EXIT rc1 (default and
            # interactive shells simply fail with rc1, list continues).
            raise SpecialBuiltinUsageError(1)
        return 1 if failed else 0

    def _declare_list_all(self, options: dict, shell: 'Shell') -> int:
        """List all shell variables (the no-argument `declare` form)."""
        # Get all variables with their attributes
        variables = self._get_all_variables_with_attributes(shell)

        # If no special options were given, use simple format
        simple_format = not any([
            options['array'], options['assoc_array'], options['export'],
            options['integer'], options['lowercase'], options['uppercase'],
            options['readonly'], options['trace'], options['print']
        ])

        for var in sorted(variables, key=lambda v: v.name):
            if simple_format:
                # Simple format: NAME=value
                self._print_simple_declaration(var, shell)
            else:
                # Full format: declare -flags NAME="value"
                self._print_declaration(var, shell)
        return 0

    def _list_namerefs(self, shell: 'Shell') -> int:
        """List only nameref variables in reusable ``declare -n`` form.

        The no-name listing filter for ``declare -n`` / ``declare -pn`` /
        ``declare -p -n`` (bash lists namerefs only). Uses the shared declaration
        formatter so a nameref prints its OWN target (``declare -n r="a"``)
        without dereferencing.
        """
        from .declare_format import format_declaration
        for var in sorted(shell.state.scope_manager.all_variables_with_attributes(),
                          key=lambda v: v.name):
            if var.is_nameref:
                self.write_line(format_declaration(var), shell)
        return 0

    def _declare_assignment(self, arg: str, options: dict, attributes: VarAttributes,
                            remove_attrs: VarAttributes, shell: 'Shell',
                            context: BuiltinContext, invoked_as: str) -> int:
        """Apply one `NAME=value` / `NAME+=value` declaration argument.

        ``invoked_as`` labels the per-arg diagnostics (``declare``/``typeset``/
        ``readonly``); ``remove_attrs`` are the ``+flags`` to clear.
        """
        # Variable assignment (NAME=value or NAME+=value append).
        # Namerefs take the text verbatim, so '+' stays part of
        # the (invalid) name there, as in bash.
        name, value = arg.split('=', 1)
        append = name.endswith('+') and not options['nameref']
        if append:
            name = name[:-1]

        # Validate variable name
        posix_mode = shell.state.options.get('posix', False)
        if not self._is_valid_identifier(name, posix_mode):
            self._diag(invoked_as, f"`{arg}': not a valid identifier", shell)
            return 1

        # Name reference: store the target name as the value with the
        # NAMEREF attribute (set_variable writes it raw to `name`).
        if options['nameref']:
            if name == value:
                self._diag(invoked_as,
                           f"{name}: nameref variable self references not allowed",
                           shell)
                return 1
            # bash validates the target's SHAPE at declare time (the target
            # need not exist). An empty target gets bash's plain-identifier
            # message; any other invalid shape gets the nameref-specific one.
            if not value:
                self._diag(invoked_as, "`': not a valid identifier", shell)
                return 1
            if not self._is_valid_nameref_target(value, posix_mode):
                self._diag(invoked_as,
                           f"`{value}': invalid variable name for name reference",
                           shell)
                return 1
            self._set_variable_with_attributes(shell, name, value, attributes, options['global'])
            return 0

        # Handle array initialization syntax. A parenthesized value
        # makes an indexed array even WITHOUT -a (bash: ``declare -x
        # ARR=(a b)`` creates an array — and arrays are never
        # exported to the environment). -A, or an existing
        # associative variable, selects the associative form.
        #
        # Array initialization is keyed STRICTLY on the parser having
        # seen literal ``name=(...)`` syntax: it attaches a structured
        # ArrayInitialization (element Words with full quote context)
        # to the argument Word, delivered via the shell's explicit
        # pending-array-init handoff. We expand it through the
        # SAME structured path the bare ``a=(...)`` form uses (the shared
        # engine's build_array_init) — no shlex reparse. A merely
        # paren-shaped VALUE that did NOT come from array syntax
        # (``declare "a=(1 2)"``, ``declare a=$x`` with x="(1 2)") is a
        # scalar in bash, so it is NOT array-ified.
        from .declaration_engine import (
            DeclarationAssignment,
            DeclarationEngine,
            DeclarationRequest,
        )
        engine = DeclarationEngine(shell)
        array_init = context.array_init(arg)
        is_array_init = array_init is not None

        # bash: a SCALAR value combined with -a/-A still creates an
        # array, storing the value at index 0 (or key "0" for -A).
        # ``declare -a v=5`` -> ``([0]="5")``; ``declare -A m=foo`` ->
        # ``([0]="foo")``.
        scalar_into_array = (
            not is_array_init
            and (options['array'] or options['assoc_array']))

        as_assoc = False
        if (is_array_init or scalar_into_array) and not options['array']:
            existing = self._get_variable_with_attributes(shell, name)
            as_assoc = options['assoc_array'] or (
                existing is not None and existing.is_assoc_array)

        if is_array_init:
            assert array_init is not None  # narrowed by is_array_init
            # Array initialization; += merges into a COPY of the same-kind
            # existing array (the ONE engine home for the copy-then-build
            # snapshot — a readonly commit leaves the live array intact, C2/P1.2).
            existing = (self._get_variable_with_attributes(shell, name)
                        if append else None)
            array: Any = engine.build_array_init(
                array_init, assoc=as_assoc, append=append, existing=existing)
            self._transform_array_elements(array, attributes, shell)
            kind_attr = (VarAttributes.ASSOC_ARRAY if as_assoc
                         else VarAttributes.ARRAY)
            self._set_variable_with_attributes(
                shell, name, array, attributes | kind_attr, options['global'])

        elif scalar_into_array and append:
            # ``declare -a a+=10`` / ``declare -Ai h+=10``: append the scalar
            # onto element 0 through the ONE append engine, preserving the rest
            # of the array — NOT the old clobber-to-scalar (appraisal H5 carry).
            existing = self._existing_in_target_scope(shell, name, options['global'])
            kind_attr = (VarAttributes.ASSOC_ARRAY if as_assoc
                         else VarAttributes.ARRAY)
            in_function = (bool(shell.state.function_stack)
                           and not options['global'])
            engine.scalar_append_into_array(
                name, value, assoc=as_assoc,
                add_attributes=attributes | kind_attr, existing=existing,
                local=in_function, global_scope=options['global'])

        elif scalar_into_array and as_assoc:
            array = AssociativeArray()
            array.set("0", self._transform_element(value, attributes, shell))
            self._set_variable_with_attributes(
                shell, name, array,
                attributes | VarAttributes.ASSOC_ARRAY, options['global'])

        elif scalar_into_array:
            array = IndexedArray()
            array.set(0, self._transform_element(value, attributes, shell))
            self._set_variable_with_attributes(
                shell, name, array,
                attributes | VarAttributes.ARRAY, options['global'])

        else:
            # Regular scalar assignment / append — routed through the single
            # declaration-engine chokepoint (store.assign / store.append). This
            # makes ``declare -g x+=A`` read the append base from the GLOBAL
            # target (not the local shadow) and honor the target's integer
            # attribute (builtins appraisal finding 3). Attribute transforms are
            # applied by the store; a readonly target raises ReadonlyVariableError.
            if remove_attrs:
                # ``declare +x v=bye`` / ``declare +i n=2+3``: clear the +attrs
                # on the existing target BEFORE the assignment, so the value is
                # transformed with the POST-removal attributes (bash removes the
                # attribute first — the value is NOT integer-evaluated). A ``+r``
                # on a readonly target raises (the loop reports it).
                existing_scalar = self._declared_in_target_scope(
                    shell, name, options['global'])
                if existing_scalar is not None:
                    shell.state.scope_manager.remove_attribute(
                        name, remove_attrs, global_scope=options['global'])
            request = DeclarationRequest(
                target_scope=(TargetScope.GLOBAL if options['global']
                              else TargetScope.DEFAULT),
                add_attributes=attributes)
            engine.commit_request_scalar(
                request, DeclarationAssignment(name, value, append=append))
        return 0

    def _declare_bare_name(self, arg: str, options: dict, attributes: VarAttributes,
                           remove_attrs: VarAttributes, shell: 'Shell',
                           invoked_as: str) -> int:
        """Declare/modify a variable by NAME only (no assignment).

        ``invoked_as`` labels the per-arg diagnostics (declare/typeset/readonly).
        """
        # Just declaring with attributes, no assignment
        # Validate variable name
        if not self._is_valid_identifier(arg, shell.state.options.get('posix', False)):
            self._diag(invoked_as, f"`{arg}': not a valid identifier", shell)
            return 1

        from .declaration_engine import ArrayKind, DeclarationEngine
        if options['array']:
            # Check for array type conflict first. Use the scope declare writes
            # to, so a local `declare -a` in a function doesn't convert an
            # outer-scope scalar.
            existing = self._existing_in_target_scope(shell, arg, options['global'])
            # An incompatible conversion (associative -> indexed) fails with
            # status 1 and PRESERVES the existing array (shared engine check).
            conv_err = DeclarationEngine.array_conversion_error(existing, ArrayKind.INDEXED)
            if conv_err:
                self._diag(invoked_as, f"{arg}: {conv_err}", shell)
                return 1
            if existing and existing.is_indexed_array:
                # Re-declaring an existing indexed array keeps its elements (bash).
                value: Any = existing.value
            elif (existing is not None
                  and not self._declare_target_is_local(shell, options['global'])):
                # Converting a GLOBAL scalar to an indexed array preserves the
                # old value at index 0 (bash: `x=foo; declare -a x` ->
                # ([0]="foo")). A LOCAL scalar is NOT preserved — bash empties
                # it (`f(){ local x=hi; declare -a x; }` -> ()).
                value = IndexedArray()
                value.set(0, existing.as_string())
            else:
                value = IndexedArray()
            self._set_variable_with_attributes(shell, arg, value, attributes, options['global'])
        elif options['assoc_array']:
            # Check for array type conflict first (scope declare writes to).
            existing = self._existing_in_target_scope(shell, arg, options['global'])
            # An incompatible conversion (indexed -> associative) FAILS with
            # status 1 and PRESERVES the indexed array — bash does NOT convert
            # (builtins appraisal finding 3; the old code's convert-and-continue
            # was wrong, and applied even to an empty indexed array).
            conv_err = DeclarationEngine.array_conversion_error(existing, ArrayKind.ASSOC)
            if conv_err:
                self._diag(invoked_as, f"{arg}: {conv_err}", shell)
                return 1
            if existing and existing.is_assoc_array:
                # Re-declaring an existing associative array keeps its keys (bash).
                self._set_variable_with_attributes(shell, arg, existing.value, attributes, options['global'])
            elif (existing is not None
                  and not self._declare_target_is_local(shell, options['global'])):
                # Converting a GLOBAL scalar to an associative array preserves
                # the old value at key "0" (bash). A LOCAL scalar is not
                # preserved (bash empties it).
                new_assoc = AssociativeArray()
                new_assoc.set("0", existing.as_string())
                self._set_variable_with_attributes(shell, arg, new_assoc, attributes, options['global'])
            else:
                # Create empty associative array
                self._set_variable_with_attributes(shell, arg, AssociativeArray(), attributes, options['global'])
        else:
            # Apply attributes to existing variable or create new one
            # (attribute changes fire the scope manager's observer,
            # which keeps state.env in sync — no manual export sync).
            # A declared-but-unset name (``declare -u y``) reads as unset
            # but must still accept later attribute changes (``declare -l
            # y`` flips its case), so route those through the mutators too.
            # Look only in the scope declare WRITES to: inside a function a
            # bare ``declare NAME`` is local (== ``local NAME``), so an
            # outer-scope variable is invisible and must not be mutated — a
            # fresh local shadow is created instead (bash).
            existing = self._declared_in_target_scope(shell, arg, options['global'])
            if existing:
                if remove_attrs:
                    shell.state.scope_manager.remove_attribute(
                        arg, remove_attrs, global_scope=options['global'])
                if attributes:
                    shell.state.scope_manager.apply_attribute(
                        arg, attributes, global_scope=options['global'])
            else:
                # Create the variable in the target scope (a local shadow
                # inside a function). Declared-but-unset: the name reads as
                # unset and (for -x) gains no environment entry until assigned
                # (bash: ``declare -x FOO`` then ``${FOO-u}`` is ``u``, printenv
                # fails; assignment makes both appear).
                self._set_variable_with_attributes(
                    shell, arg, "",
                    attributes | VarAttributes.UNSET, options['global'])
        return 0
    def _print_variables(self, options: dict, names: List[str], shell: 'Shell') -> int:
        """Print variables with attributes using declare -p format."""
        if names:
            # Print specific variables. The declared-aware lookup also
            # finds declared-but-unset variables (``export FOO`` shows as
            # ``declare -x FOO``, like bash).
            exit_code = 0
            for name in names:
                var = shell.state.scope_manager.get_declared_variable_object(name)
                if var:
                    self._print_declaration(var, shell)
                else:
                    self.error(f"{name}: not found", shell)
                    exit_code = 1
            return exit_code
        else:
            # Print all variables that match filter criteria
            variables = self._get_all_variables_with_attributes(shell)
            for var in sorted(variables, key=lambda v: v.name):
                if matches_filter(var, options):
                    self._print_declaration(var, shell)
            return 0

    def _print_simple_declaration(self, var: Variable, shell: 'Shell'):
        """Print variable in bash's plain-``declare`` (no-arg) form.

        Identical to the ``set`` listing: ``name=value`` with a single-quoted
        scalar (``$'...'`` for control chars) and the bare ``([0]="..")`` array
        form — no ``declare`` prefix and no attribute flags (those belong to
        ``declare -p``). The old code emitted unquoted scalars and prefixed
        arrays with ``declare -a``/``-A``, neither of which matches bash."""
        from .declare_format import format_assignment_reuse
        self.write_line(format_assignment_reuse(var), shell)

    def _print_declaration(self, var: Variable, shell: 'Shell'):
        """Print variable declaration in reusable format
        (shared formatter: declare_format.format_declaration)."""
        self.write_line(format_declaration(var), shell)

    def _transform_element(self, value: str, attributes: VarAttributes,
                           shell: 'Shell') -> str:
        """Apply the integer/case-fold attributes to one array ELEMENT value.

        bash applies -i (arithmetic-evaluate) and -l/-u (case-fold) to the
        elements of an array, not just to scalar variables. We reuse the
        scope manager's scalar transformer so the rules stay identical.
        """
        if not (attributes & (VarAttributes.INTEGER | VarAttributes.LOWERCASE
                              | VarAttributes.UPPERCASE)):
            return value
        return str(shell.state.scope_manager._apply_attributes(value, attributes))

    def _transform_array_elements(self, array: Any, attributes: VarAttributes,
                                  shell: 'Shell') -> None:
        """In-place: apply integer/case-fold attributes to every element."""
        if not (attributes & (VarAttributes.INTEGER | VarAttributes.LOWERCASE
                              | VarAttributes.UPPERCASE)):
            return
        if isinstance(array, IndexedArray):
            for index in array.indices():
                array.set(index, self._transform_element(
                    array.get(index) or "", attributes, shell))
        elif isinstance(array, AssociativeArray):
            for key in array.keys():
                array.set(key, self._transform_element(
                    array.get(key) or "", attributes, shell))

    # Methods to interact with shell's enhanced variable storage

    def _get_variable_with_attributes(self, shell: 'Shell', name: str) -> Optional[Variable]:
        """Get variable with its attributes."""
        return shell.state.scope_manager.get_variable_object(name)

    def _declare_target_is_local(self, shell: 'Shell', global_flag: bool) -> bool:
        """True if a bare `declare` here writes a function-local variable."""
        return bool(shell.state.function_stack) and not global_flag

    def _existing_in_target_scope(self, shell: 'Shell', name: str,
                                  global_flag: bool) -> Optional[Variable]:
        """The variable `declare` would modify, looked up in the scope it
        writes to. A bare `declare -a/-A` inside a function creates a LOCAL
        variable, so it must NOT pull in / convert an outer-scope scalar
        (bash); at global scope (or with -g) it sees the global. Tombstones
        (declared-unset) count as absent.
        """
        sm = shell.state.scope_manager
        if self._declare_target_is_local(shell, global_flag):
            var = sm.current_scope.variables.get(name)
            return var if (var is not None and not var.is_unset) else None
        return sm.get_variable_object(name)

    def _declared_in_target_scope(self, shell: 'Shell', name: str,
                                  global_flag: bool) -> Optional[Variable]:
        """Like ``_existing_in_target_scope`` but INCLUDING a declared-but-unset
        tombstone, so repeated attribute-only declares accumulate (``declare -u
        y; declare -l y``). Inside a function (no -g) only the current scope is
        consulted — an outer-scope variable is invisible, so ``declare NAME``
        creates a fresh LOCAL shadow rather than mutating the outer (bash).
        """
        sm = shell.state.scope_manager
        if global_flag:
            # declare -g targets the global instance, past any local shadow.
            return sm.global_scope.variables.get(name)
        if self._declare_target_is_local(shell, global_flag):
            return sm.current_scope.variables.get(name)
        return sm.get_declared_variable_object(name)

    def _get_all_variables_with_attributes(self, shell: 'Shell') -> List[Variable]:
        """Get all variables with their attributes."""
        return shell.state.scope_manager.all_variables_with_attributes()

    def _set_variable_with_attributes(self, shell: 'Shell', name: str,
                                     value: Any, attributes: VarAttributes, global_flag: bool = False):
        """Set variable with attributes.

        With -g the write is forced to the global scope (past any local of
        the same name — bash). Otherwise, inside a function, ``declare``
        creates a local (== ``local``); at top level it writes the global.

        A ReadonlyVariableError propagates UNWRAPPED: the builtin guard
        (execute_builtin_guarded → report_internal_defect) prints one clean
        ``psh: declare: NAME: readonly variable`` line. The former re-wrap
        here produced a triple-nested message.
        """
        # (set_variable fires the scope manager's observer, which keeps
        # state.env in sync for export-attributed variables)
        if global_flag:
            shell.state.scope_manager.set_variable(
                name, value, attributes=attributes, global_scope=True)
        else:
            shell.state.scope_manager.set_variable(
                name, value, attributes=attributes,
                local=bool(shell.state.function_stack))

    def _print_function_definition(self, name, func, shell: 'Shell'):
        """Print a function definition in a format that can be re-executed."""
        self.write_line(format_function_definition(name, func), shell)

    @property
    def help(self) -> str:
        return """declare: declare [-aAfFgilnprtux] [name[=value] ...]

    Declare variables and give them attributes.

    Options:
      -a    Declare indexed array variables
      -A    Declare associative array variables
      -f    Restrict action to function names and definitions
      -F    Display function names only (no definitions)
      -g    Create global variables when used in a function
      -i    Make variables have the 'integer' attribute
      -l    Convert values to lowercase on assignment
      -n    Make NAME a name reference to the variable named by its value
      -p    Display the attributes and value of each variable
      -r    Make variables readonly
      -t    Give variables the 'trace' attribute (functions only)
      -u    Convert values to uppercase on assignment
      -x    Make variables export to the environment
      +x    Remove export attribute
      +r    Remove readonly attribute (if possible)

    Using '+' instead of '-' turns off the given attribute.

    With no arguments, display all variables and their values.
    With -p, display variables in a reusable format.
    With -f, display all function definitions.
    With -F, display all function names."""


@builtin
class TypesetBuiltin(DeclareBuiltin):
    """Typeset builtin - alias for declare (ksh compatibility)."""

    @property
    def name(self) -> str:
        return "typeset"

    @property
    def help(self) -> str:
        return """typeset: typeset [-aAfFgilnprtux] [name[=value] ...]

    Declare variables and give them attributes (alias for declare).

    Options:
      -a    Declare indexed array variables
      -A    Declare associative array variables
      -f    Restrict action to function names and definitions
      -F    Display function names only (no definitions)
      -g    Create global variables when used in a function
      -i    Make variables have the 'integer' attribute
      -l    Convert values to lowercase on assignment
      -n    Make NAME a name reference to the variable named by its value
      -p    Display the attributes and value of each variable
      -r    Make variables readonly
      -t    Give variables the 'trace' attribute (functions only)
      -u    Convert values to uppercase on assignment
      -x    Make variables export to the environment
      +x    Remove export attribute
      +r    Remove readonly attribute (if possible)

    Using '+' instead of '-' turns off the given attribute.

    With no arguments, display all variables and their values.
    With -p, display variables in a reusable format.
    With -f, display all function definitions.
    With -F, display all function names.

    Note: typeset is supplied for compatibility with the Korn shell.
    It is exactly equivalent to declare."""


@builtin
class ReadonlyBuiltin(Builtin):
    """Make variables readonly."""

    @property
    def name(self) -> str:
        return "readonly"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        return self.execute_in_context(args, shell, EMPTY_BUILTIN_CONTEXT)

    def execute_in_context(self, args: List[str], shell: 'Shell',
                           context: BuiltinContext) -> int:
        """Execute the readonly builtin.

        ``context`` carries any structured array initializers for
        ``readonly name=(...)`` arguments; they are forwarded to ``declare -r``.
        """
        # Parse options
        options, names = self._parse_readonly_options(args[1:], shell)
        if options is None:
            # Invalid option: special-builtin usage error (rc 2; exits a
            # POSIX-mode non-interactive shell). The `1bad=x` identifier
            # error stays a plain rc-1 operand error inside declare.
            raise SpecialBuiltinUsageError(2, suppressible=True)

        if options['functions']:
            return self._handle_readonly_functions(names, shell)
        elif options['print'] or not names:
            # `readonly -p` / bare `readonly`: list all readonly variables
            # in reusable declare format (same output as `declare -pr`,
            # via the shared formatter).
            for var in sorted(shell.state.scope_manager.all_variables_with_attributes(),
                              key=lambda v: v.name):
                if var.is_readonly:
                    self.write_line(format_declaration(var), shell)
            return 0
        else:
            # readonly NAME[=value]... is declare -r NAME[=value]...;
            # delegate to the registered declare singleton, forwarding the
            # same context so an array-init argument resolves. Attribute flags
            # (-a/-A) are passed through to declare so `readonly -a arr=(...)`
            # creates a readonly array. ``invoked_as='readonly'`` labels the
            # per-arg diagnostics `readonly:` (not `declare:`), and
            # ``special=True`` makes declare's shared loop emit a readonly
            # ASSIGNMENT error BARE (`x: readonly variable`, no builtin name —
            # bash) and, after processing every operand (bash's
            # continue-on-error arg loop), raise SpecialBuiltinUsageError(1):
            # default mode fails non-fatally rc1, a POSIX-mode non-interactive
            # shell exits rc1 (readonly is a special builtin; probe tmp/posixexit).
            declare_builtin = registry.get('declare')
            assert declare_builtin is not None
            return cast(DeclareBuiltin, declare_builtin).run_as(
                ['declare', '-r'] + options['declare_flags'] + names,
                shell, context, invoked_as='readonly', special=True)

    # readonly attribute flags forwarded to `declare -r` (bash accepts -aA).
    _READONLY_FORWARD_FLAGS = {'a': '-a', 'A': '-A'}

    def _parse_readonly_options(self, args: List[str], shell: 'Shell') -> tuple[Optional[dict], List[str]]:
        """Parse readonly options and return (options_dict, function_names)."""
        options: dict = {
            'functions': False,    # -f
            'print': False,        # -p
            'declare_flags': [],   # -a/-A forwarded to declare -r
        }
        names = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == '--':  # End of options
                names.extend(args[i+1:])
                break
            elif arg.startswith('-') and len(arg) > 1:
                # Process flags
                for flag in arg[1:]:
                    if flag == 'f':
                        options['functions'] = True
                    elif flag == 'p':
                        options['print'] = True
                    elif flag in self._READONLY_FORWARD_FLAGS:
                        options['declare_flags'].append(
                            self._READONLY_FORWARD_FLAGS[flag])
                    else:
                        self.error(f"invalid option: -{flag}", shell)
                        return None, []
            else:
                names.append(arg)
            i += 1

        return options, names

    def _handle_readonly_functions(self, names: List[str], shell: 'Shell') -> int:
        """Handle readonly -f for functions."""
        if not names:
            # List all readonly functions
            functions = shell.function_manager.list_functions()
            readonly_funcs = [(name, func) for name, func in functions if func.readonly]

            for name, _func in readonly_funcs:
                self.write_line(f"readonly -f {name}", shell)
            return 0

        # Set specified functions as readonly
        exit_code = 0
        for name in names:
            if shell.function_manager.get_function(name):
                shell.function_manager.set_function_readonly(name)
            else:
                self.error(f"{name}: not found", shell)
                exit_code = 1

        return exit_code

    @property
    def help(self) -> str:
        return """readonly: readonly [-aAf] [-p] [name[=value] ...]

    Mark variables or functions as readonly.

    Mark each name as readonly; the values of these names may not be changed
    by subsequent assignment. If value is supplied, assign value before
    marking as readonly.

    Options:
      -a    Refer to indexed arrays
      -A    Refer to associative arrays
      -f    Mark functions as readonly (cannot be redefined)
      -p    Display all readonly variables in declare format

    With no arguments, display all readonly variables.
    With -f and no names, display all readonly functions.

    Exit Status:
    Returns success unless an invalid option is given or name is invalid."""


@builtin
class ReturnBuiltin(Builtin):
    """Return from a function with optional exit code."""

    @property
    def name(self) -> str:
        return "return"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the return builtin."""
        if len(args) > 2:
            # bash checks this before the in-function check. `return 3 4`
            # is the same too-many-arguments family as `exit 7 8`/`shift
            # 1 2` (probe-verified, bash 5.2, tmp/posixexit): the error is
            # reported and the CURRENT INPUT UNIT is discarded — it does
            # NOT return from the function (the rest of the body on this
            # line dies too) and does NOT exit the shell, in default AND
            # POSIX mode; the next input line runs with $? = 1. (The old
            # sys.exit(1) here made a non-interactive psh exit — bash
            # survives.)
            self.error("too many arguments", shell)
            special_builtin_usage_discard(shell.state, 1)

        # Validate the numeric argument FIRST — bash reports a bad numeric
        # argument ("numeric argument required") BEFORE the can-only-return
        # context check, so `return abc` OUTSIDE a function prints BOTH lines
        # (both location-prefixed). Inside a function it prints only this line.
        numeric_error = False
        exit_code = shell.state.last_exit_code
        if len(args) > 1:
            try:
                # Wrap return value to 0-255 range like bash does
                exit_code = int(args[1]) % 256
            except ValueError:
                self.error(f"{args[1]}: numeric argument required", shell)
                numeric_error = True
                exit_code = 2

        if not shell.state.function_stack and shell.state.source_depth == 0:
            # Usage error rc 2 (bash); a POSIX-mode non-interactive shell
            # exits with 2 (typed outcome, resolved at the builtin guard). The
            # numeric error (if any) has already printed above.
            self.error("can only `return' from a function or sourced script", shell)
            raise SpecialBuiltinUsageError(2, suppressible=True)

        # We can't actually "return" from the middle of execution in Python,
        # so we'll use an exception for control flow. A bad numeric argument
        # still returns from the function/sourced file, with status 2 (bash).
        raise FunctionReturn(2 if numeric_error else exit_code)
