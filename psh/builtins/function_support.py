"""Function-related builtin commands."""
import sys
from typing import TYPE_CHECKING, Any, List, Optional

from ..core import AssociativeArray, IndexedArray, ReadonlyVariableError, VarAttributes, Variable

# FunctionReturn now lives with its control-flow siblings in
# core/exceptions.py; re-exported here because many call sites
# historically import it from this module.
from ..core.exceptions import FunctionReturn  # noqa: F401
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
            # Pass original args for mutually exclusive attribute handling
            return self._declare_variables(options, positional, shell, context, args[1:])

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
        # exports f, `declare -fr f` makes it readonly; an undefined name is
        # silent with status 1, like `declare -f NAME`).
        if names and (options['export'] or options['remove_export']
                      or options['readonly']):
            exit_code = 0
            for name in names:
                if fm.get_function(name) is None:
                    exit_code = 1
                    continue
                if options['export'] or options['remove_export']:
                    fm.set_function_exported(name, options['export'])
                if options['readonly']:
                    fm.set_function_readonly(name)
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
        """The flag string for a function's attribute line (f, fr, fx, frx)."""
        return 'f' + ('r' if func.readonly else '') + ('x' if func.exported else '')

    def _is_valid_identifier(self, name: str) -> bool:
        """Check if a name is a valid shell identifier."""
        if not name:
            return False
        # Must start with letter or underscore
        if not (name[0].isalpha() or name[0] == '_'):
            return False
        # Rest must be alphanumeric or underscore
        return all(c.isalnum() or c == '_' for c in name[1:])

    def _is_valid_nameref_target(self, value: str) -> bool:
        """Check a nameref target: an identifier, optionally followed by ONE
        balanced ``[subscript]`` spanning to the end of the string.

        Mirrors bash's valid_nameref_value/valid_array_reference (pinned
        against bash 5.2): ``a``, ``a[0]``, ``a[$i]``, ``a[b[c]]`` are valid;
        ``1``, ``a b``, ``a-b``, ``a[``, ``a[]``, ``a[0]x``, ``a[0][1]`` are
        not. The subscript is NOT evaluated here — only its shape is checked.
        """
        bracket = value.find('[')
        name = value if bracket == -1 else value[:bracket]
        if not self._is_valid_identifier(name):
            return False
        if bracket == -1:
            return True
        subscript = value[bracket:]
        if len(subscript) < 3 or not subscript.endswith(']'):
            return False  # needs a non-empty, closed [subscript]
        depth = 0
        for i, ch in enumerate(subscript):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    # The first [ must close exactly at the end (a[0][1] is
                    # invalid, a[b[c]] valid).
                    return i == len(subscript) - 1
        return False

    # Option key → variable attribute, for both the -set and +remove
    # directions of _declare_variables.
    _OPTION_ATTRIBUTES = {
        'readonly': VarAttributes.READONLY,
        'export': VarAttributes.EXPORT,
        'integer': VarAttributes.INTEGER,
        'lowercase': VarAttributes.LOWERCASE,
        'uppercase': VarAttributes.UPPERCASE,
        'array': VarAttributes.ARRAY,
        'assoc_array': VarAttributes.ASSOC_ARRAY,
        'trace': VarAttributes.TRACE,
        'nameref': VarAttributes.NAMEREF,
    }

    def _attributes_from_options(self, options: dict) -> VarAttributes:
        """Attributes the -flags select.

        -l and -u are mutually exclusive; when BOTH appear in a single
        declaration bash applies NEITHER (``declare -ul y; y=HeLLo`` leaves
        $y unfolded). Set no case bit here — _removed_attributes_from_options
        also clears any pre-existing case attribute so the cancellation
        applies even when the name was already -u/-l.
        """
        attributes = VarAttributes.NONE
        for key, attr in self._OPTION_ATTRIBUTES.items():
            if options[key]:
                attributes |= attr
        if options['lowercase'] and options['uppercase']:
            attributes &= ~(VarAttributes.LOWERCASE | VarAttributes.UPPERCASE)
        return attributes

    def _removed_attributes_from_options(self, options: dict) -> VarAttributes:
        """Attributes the +flags remove (plus the -u/-l mutual cancellation)."""
        removed = VarAttributes.NONE
        for key, attr in self._OPTION_ATTRIBUTES.items():
            if options.get(f'remove_{key}', False):
                removed |= attr
        if options['lowercase'] and options['uppercase']:
            # Both case flags in one declaration cancel — and clear any
            # case attribute the name already carried (bash).
            removed |= VarAttributes.LOWERCASE | VarAttributes.UPPERCASE
        return removed

    def _declare_variables(self, options: dict, args: List[str], shell: 'Shell',
                           context: BuiltinContext, _original_args=None) -> int:
        """Handle variable declarations (list, assignment, or bare-name forms)."""
        attributes = self._attributes_from_options(options)
        remove_attrs = self._removed_attributes_from_options(options)

        # If no arguments, list all shell variables (not environment)
        if not args:
            return self._declare_list_all(options, shell)

        # Process each argument; an invalid name (or nameref self-ref)
        # stops immediately with exit 1, matching bash.
        for arg in args:
            if '=' in arg:
                rc = self._declare_assignment(arg, options, attributes, shell, context)
            else:
                rc = self._declare_bare_name(arg, options, attributes, remove_attrs, shell)
            if rc != 0:
                return rc
        return 0

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

    def _declare_assignment(self, arg: str, options: dict, attributes: VarAttributes,
                            shell: 'Shell', context: BuiltinContext) -> int:
        """Apply one `NAME=value` / `NAME+=value` declaration argument."""
        # Variable assignment (NAME=value or NAME+=value append).
        # Namerefs take the text verbatim, so '+' stays part of
        # the (invalid) name there, as in bash.
        name, value = arg.split('=', 1)
        append = name.endswith('+') and not options['nameref']
        if append:
            name = name[:-1]

        # Validate variable name
        if not self._is_valid_identifier(name):
            self.error(f"`{arg}': not a valid identifier", shell)
            return 1

        # Name reference: store the target name as the value with the
        # NAMEREF attribute (set_variable writes it raw to `name`).
        if options['nameref']:
            if name == value:
                self.error(f"{name}: nameref variable self references not allowed", shell)
                return 1
            # bash validates the target's SHAPE at declare time (the target
            # need not exist). An empty target gets bash's plain-identifier
            # message; any other invalid shape gets the nameref-specific one.
            if not value:
                self.error("`': not a valid identifier", shell)
                return 1
            if not self._is_valid_nameref_target(value):
                self.error(f"`{value}': invalid variable name for name reference", shell)
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
        # SAME structured path the bare ``a=(...)`` form uses
        # (build_indexed_array / build_associative_array) — no shlex
        # reparse. A merely paren-shaped VALUE that did NOT come from
        # array syntax (``declare "a=(1 2)"``, ``declare a=$x`` with
        # x="(1 2)") is a scalar in bash, so it is NOT array-ified.
        array_init = context.array_init(arg)
        is_array_init = array_init is not None

        # bash: a SCALAR value combined with -a/-A still creates an
        # array, storing the value at index 0 (or key "0" for -A).
        # ``declare -a v=5`` -> ``([0]="5")``; ``declare -A m=foo`` ->
        # ``([0]="foo")``. The integer/case attrs then apply to the
        # element (handled by _transform_array_elements below).
        scalar_into_array = (
            not is_array_init
            and (options['array'] or options['assoc_array']))

        as_assoc = False
        if (is_array_init or scalar_into_array) and not options['array']:
            existing = self._get_variable_with_attributes(shell, name)
            as_assoc = options['assoc_array'] or (
                existing is not None and existing.is_assoc_array)

        if is_array_init and as_assoc:
            # Associative array initialization; += merges into the
            # existing array (bash).
            existing = (self._get_variable_with_attributes(shell, name)
                        if append else None)
            into: Any = (existing.value
                         if existing is not None
                         and isinstance(existing.value, AssociativeArray)
                         else None)
            array: Any = self._build_assoc_array(array_init, into, shell)
            self._transform_array_elements(array, attributes, shell)
            self._set_variable_with_attributes(
                shell, name, array,
                attributes | VarAttributes.ASSOC_ARRAY, options['global'])

        elif is_array_init:
            # Indexed array initialization; += appends after the
            # existing array's highest index (bash).
            existing = (self._get_variable_with_attributes(shell, name)
                        if append else None)
            into = (existing.value
                    if existing is not None
                    and isinstance(existing.value, IndexedArray)
                    else None)
            array = self._build_indexed_array(array_init, into, shell)
            self._transform_array_elements(array, attributes, shell)
            self._set_variable_with_attributes(
                shell, name, array,
                attributes | VarAttributes.ARRAY, options['global'])

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
            # Regular variable assignment
            # The enhanced scope manager will apply attribute transformations
            final_value: object = value
            if append:
                from ..core import resolve_append_assignment
                _, final_value = resolve_append_assignment(
                    shell.state.scope_manager, name + '+', value)
            self._set_variable_with_attributes(shell, name, final_value, attributes, options['global'])
        return 0

    def _declare_bare_name(self, arg: str, options: dict, attributes: VarAttributes,
                           remove_attrs: VarAttributes, shell: 'Shell') -> int:
        """Declare/modify a variable by NAME only (no assignment)."""
        # Just declaring with attributes, no assignment
        # Validate variable name
        if not self._is_valid_identifier(arg):
            self.error(f"`{arg}': not a valid identifier", shell)
            return 1

        if options['array']:
            # Check for array type conflict first. Use the scope declare writes
            # to, so a local `declare -a` in a function doesn't convert an
            # outer-scope scalar.
            existing = self._existing_in_target_scope(shell, arg, options['global'])
            if existing and existing.is_assoc_array:
                self.error(f"{arg}: cannot convert associative to indexed array", shell)
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
            if existing and existing.is_indexed_array:
                # Bash behavior: print error but continue, convert to associative array
                self.error(f"{arg}: cannot convert indexed to associative array", shell)
                # Convert indexed array content to associative array
                new_assoc = AssociativeArray()
                if isinstance(existing.value, IndexedArray):
                    # Copy indexed array elements as string keys
                    for index in existing.value.indices():
                        new_assoc.set(str(index), existing.value.get(index) or "")
                # Completely replace the variable with new associative array
                # Remove old attributes and set only the new ones
                shell.state.scope_manager.unset_variable(arg)
                self._set_variable_with_attributes(shell, arg, new_assoc, attributes, options['global'])
            elif existing and existing.is_assoc_array:
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
        """Print variable in simple format (NAME=value)."""
        if isinstance(var.value, (IndexedArray, AssociativeArray)):
            # Arrays can't be shown in simple format, use declare format
            self._print_declaration(var, shell)
        else:
            # Simple format without quotes or escaping
            self.write_line(f"{var.name}={var.value}", shell)

    def _print_declaration(self, var: Variable, shell: 'Shell'):
        """Print variable declaration in reusable format
        (shared formatter: declare_format.format_declaration)."""
        self.write_line(format_declaration(var), shell)

    def _build_indexed_array(self, array_init, into, shell: 'Shell') -> IndexedArray:
        """Build an IndexedArray from the structured init via the shared
        ArrayOperationExecutor engine — the SAME path the bare ``a=(...)``
        form uses (no string reparse). ``into`` is the existing array for
        ``+=`` append, else None."""
        from ..executor.array import ArrayOperationExecutor
        return ArrayOperationExecutor(shell).build_indexed_array(
            array_init.words, into=into)

    def _build_assoc_array(self, array_init, into, shell: 'Shell') -> AssociativeArray:
        """Build an AssociativeArray from the structured init via the shared
        engine (see _build_indexed_array)."""
        from ..executor.array import ArrayOperationExecutor
        return ArrayOperationExecutor(shell).build_associative_array(
            array_init.words, into=into)

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
        return """declare: declare [-aAfFgilprtux] [name[=value] ...]

    Declare variables and give them attributes.

    Options:
      -a    Declare indexed array variables
      -A    Declare associative array variables
      -f    Restrict action to function names and definitions
      -F    Display function names only (no definitions)
      -g    Create global variables when used in a function
      -i    Make variables have the 'integer' attribute
      -l    Convert values to lowercase on assignment
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
        return """typeset: typeset [-aAfFgilprtux] [name[=value] ...]

    Declare variables and give them attributes (alias for declare).

    Options:
      -a    Declare indexed array variables
      -A    Declare associative array variables
      -f    Restrict action to function names and definitions
      -F    Display function names only (no definitions)
      -g    Create global variables when used in a function
      -i    Make variables have the 'integer' attribute
      -l    Convert values to lowercase on assignment
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
            return 2  # invalid option (bash usage-error status)

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
            # creates a readonly array.
            declare_builtin = registry.get('declare')
            assert declare_builtin is not None
            try:
                return declare_builtin.execute_in_context(
                    ['declare', '-r'] + options['declare_flags'] + names,
                    shell, context)
            except ReadonlyVariableError as e:
                # bash prints the assignment error for `readonly x=2` WITHOUT
                # the builtin name (unlike `declare`): just `x: readonly
                # variable`. Emit that (via the psh assignment convention) and
                # fail non-fatally — the rest of the command list continues.
                self.write_error_line(
                    f"psh: {e.name}: readonly variable", shell)
                return 1

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

            for name, func in readonly_funcs:
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
            # bash checks this before the in-function check: the error does
            # NOT return, and a non-interactive shell aborts with status 1
            # (return is a POSIX special builtin).
            self.error("too many arguments", shell)
            shell.state.last_exit_code = 1
            if shell.state.is_script_mode:
                sys.exit(1)
            return 1

        if not shell.state.function_stack and shell.state.source_depth == 0:
            self.error("can only `return' from a function or sourced script", shell)
            return 2  # bash usage-error status

        # Get return value
        if len(args) > 1:
            try:
                exit_code = int(args[1])
                # Wrap return value to 0-255 range like bash does
                exit_code = exit_code % 256
            except ValueError:
                # bash: the error still returns from the function/sourced
                # file, with the usage-error status 2.
                self.error(f"{args[1]}: numeric argument required", shell)
                raise FunctionReturn(2)
        else:
            # With no arguments, return the current value of $?
            exit_code = shell.state.last_exit_code

        # We can't actually "return" from the middle of execution in Python,
        # so we'll use an exception for control flow
        raise FunctionReturn(exit_code)
