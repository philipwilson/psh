"""Function-related builtin commands."""
import shlex
import sys
from typing import TYPE_CHECKING, Any, List, Optional

from ..core import AssociativeArray, IndexedArray, ReadonlyVariableError, VarAttributes, Variable
from ..utils import ShellFormatter
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


class FunctionReturn(Exception):
    """Exception used to implement the return builtin."""
    def __init__(self, exit_code: int):
        self.exit_code = exit_code
        super().__init__()


@builtin
class DeclareBuiltin(Builtin):
    """Declare variables and functions with attributes."""

    @property
    def name(self) -> str:
        return "declare"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the declare builtin."""
        # Parse options
        options, positional = self._parse_options(args[1:], shell)
        if options is None:
            return 1  # Error already printed

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
            return self._declare_variables(options, positional, shell, args[1:])

    def _parse_options(self, args: List[str], shell: 'Shell') -> tuple[Optional[dict], List[str]]:
        """Parse declare options and return (options_dict, positional_args)."""
        options = {
            'array': False,          # -a
            'assoc_array': False,    # -A
            'functions': False,      # -f
            'function_names': False, # -F
            'global': False,         # -g
            'integer': False,        # -i
            'lowercase': False,      # -l
            'nameref': False,        # -n
            'print': False,          # -p
            'readonly': False,       # -r
            'trace': False,          # -t
            'uppercase': False,      # -u
            'export': False,         # -x
            'remove_nameref': False, # +n
            'remove_export': False,  # +x
            'remove_readonly': False,# +r
            'remove_integer': False, # +i
            'remove_lowercase': False,# +l
            'remove_uppercase': False,# +u
            'remove_array': False,   # +a
            'remove_assoc_array': False,# +A
            'remove_trace': False,   # +t
            'last_case_attr': None,  # Track last case attribute for "last wins" behavior
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
                    elif flag == 'f':
                        options['functions'] = True
                    elif flag == 'F':
                        options['function_names'] = True
                    elif flag == 'g':
                        options['global'] = True
                    elif flag == 'i':
                        options['integer'] = True
                    elif flag == 'l':
                        options['lowercase'] = True
                        options['last_case_attr'] = 'lowercase'
                    elif flag == 'n':
                        options['nameref'] = True
                    elif flag == 'p':
                        options['print'] = True
                    elif flag == 'r':
                        options['readonly'] = True
                    elif flag == 't':
                        options['trace'] = True
                    elif flag == 'u':
                        options['uppercase'] = True
                        options['last_case_attr'] = 'uppercase'
                    elif flag == 'x':
                        options['export'] = True
                    else:
                        self.error(f"invalid option: -{flag}", shell)
                        return None, []
            elif arg.startswith('+') and len(arg) > 1:
                # Process attribute removal flags
                for flag in arg[1:]:
                    if flag == 'x':
                        options['remove_export'] = True
                    elif flag == 'n':
                        options['remove_nameref'] = True
                    elif flag == 'r':
                        options['remove_readonly'] = True
                    elif flag == 'i':
                        options['remove_integer'] = True
                    elif flag == 'l':
                        options['remove_lowercase'] = True
                    elif flag == 'u':
                        options['remove_uppercase'] = True
                    elif flag == 'a':
                        options['remove_array'] = True
                    elif flag == 'A':
                        options['remove_assoc_array'] = True
                    elif flag == 't':
                        options['remove_trace'] = True
                    else:
                        self.error(f"invalid option: +{flag}", shell)
                        return None, []
            else:
                positional.append(arg)
            i += 1

        return options, positional

    def _handle_functions(self, options: dict, names: List[str], shell: 'Shell') -> int:
        """Handle function-related options (-f, -F)."""
        stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
        show_names_only = options['function_names']

        if not names:
            # List all functions
            functions = shell.function_manager.list_functions()
            if show_names_only:
                # -F flag: show only function names
                for name, _ in sorted(functions):
                    print(f"declare -f {name}", file=stdout)
            else:
                # -f flag: show full definitions
                for name, func in sorted(functions):
                    self._print_function_definition(name, func, stdout)
        else:
            # List specific functions
            exit_code = 0
            for name in names:
                func = shell.function_manager.get_function(name)
                if func:
                    if show_names_only:
                        print(f"declare -f {name}", file=stdout)
                    else:
                        self._print_function_definition(name, func, stdout)
                else:
                    self.error(f"{name}: not found", shell)
                    exit_code = 1
            return exit_code
        return 0

    def _is_valid_identifier(self, name: str) -> bool:
        """Check if a name is a valid shell identifier."""
        if not name:
            return False
        # Must start with letter or underscore
        if not (name[0].isalpha() or name[0] == '_'):
            return False
        # Rest must be alphanumeric or underscore
        return all(c.isalnum() or c == '_' for c in name[1:])

    def _declare_variables(self, options: dict, args: List[str], shell: 'Shell', _original_args=None) -> int:
        """Handle variable declarations."""
        # Build attributes from options
        attributes = VarAttributes.NONE
        if options['readonly']:
            attributes |= VarAttributes.READONLY
        if options['export']:
            attributes |= VarAttributes.EXPORT
        if options['integer']:
            attributes |= VarAttributes.INTEGER
        # Handle mutually exclusive -l and -u (bash uses "last wins" behavior)
        if options['lowercase'] and options['uppercase']:
            # When both -l and -u are specified, apply the last one seen
            if options['last_case_attr'] == 'lowercase':
                attributes |= VarAttributes.LOWERCASE
            elif options['last_case_attr'] == 'uppercase':
                attributes |= VarAttributes.UPPERCASE
            # If somehow last_case_attr is None, ignore both (fallback)
        elif options['lowercase']:
            attributes |= VarAttributes.LOWERCASE
        elif options['uppercase']:
            attributes |= VarAttributes.UPPERCASE
        if options['array']:
            attributes |= VarAttributes.ARRAY
        if options['assoc_array']:
            attributes |= VarAttributes.ASSOC_ARRAY
        if options['trace']:
            attributes |= VarAttributes.TRACE
        if options['nameref']:
            attributes |= VarAttributes.NAMEREF

        # Handle attribute removal
        remove_attrs = VarAttributes.NONE
        if options['remove_nameref']:
            remove_attrs |= VarAttributes.NAMEREF
        if options['remove_export']:
            remove_attrs |= VarAttributes.EXPORT
        if options['remove_readonly']:
            remove_attrs |= VarAttributes.READONLY
        if options['remove_integer']:
            remove_attrs |= VarAttributes.INTEGER
        if options['remove_lowercase']:
            remove_attrs |= VarAttributes.LOWERCASE
        if options['remove_uppercase']:
            remove_attrs |= VarAttributes.UPPERCASE
        if options['remove_array']:
            remove_attrs |= VarAttributes.ARRAY
        if options['remove_assoc_array']:
            remove_attrs |= VarAttributes.ASSOC_ARRAY
        if options['remove_trace']:
            remove_attrs |= VarAttributes.TRACE

        # If no arguments, list all shell variables (not environment)
        if not args:
            stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
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
                    self._print_simple_declaration(var, stdout)
                else:
                    # Full format: declare -flags NAME="value"
                    self._print_declaration(var, stdout)
            return 0

        # Process each argument
        for arg in args:
            if '=' in arg:
                # Variable assignment
                name, value = arg.split('=', 1)

                # Validate variable name
                if not self._is_valid_identifier(name):
                    self.error(f"`{arg}': not a valid identifier", shell)
                    return 1

                # Name reference: store the target name as the value with the
                # NAMEREF attribute (set_variable writes it raw to `name`).
                if options['nameref']:
                    if name == value:
                        self.error("nameref variable self references not allowed", shell)
                        return 1
                    self._set_variable_with_attributes(shell, name, value, attributes, options['global'])
                    continue

                # Handle array initialization syntax
                if options['array'] and value.startswith('(') and value.endswith(')'):
                    # Parse indexed array initialization
                    array = IndexedArray()
                    array_values = self._parse_array_init(value)
                    for i, val in enumerate(array_values):
                        array.set(i, val)
                    self._set_variable_with_attributes(shell, name, array, attributes, options['global'])

                elif options['assoc_array'] and value.startswith('(') and value.endswith(')'):
                    # Parse associative array initialization
                    array = AssociativeArray()
                    assoc_values = self._parse_assoc_array_init(value)
                    for key, val in assoc_values:
                        array.set(key, val)
                    self._set_variable_with_attributes(shell, name, array, attributes, options['global'])

                else:
                    # Regular variable assignment
                    # The enhanced scope manager will apply attribute transformations
                    self._set_variable_with_attributes(shell, name, value, attributes, options['global'])

            else:
                # Just declaring with attributes, no assignment
                # Validate variable name
                if not self._is_valid_identifier(arg):
                    self.error(f"`{arg}': not a valid identifier", shell)
                    return 1

                if options['array']:
                    # Check for array type conflict first
                    existing = self._get_variable_with_attributes(shell, arg)
                    if existing and existing.is_assoc_array:
                        self.error(f"{arg}: cannot convert associative to indexed array", shell)
                        return 1
                    # Create empty indexed array
                    self._set_variable_with_attributes(shell, arg, IndexedArray(), attributes, options['global'])
                elif options['assoc_array']:
                    # Check for array type conflict first
                    existing = self._get_variable_with_attributes(shell, arg)
                    if existing and existing.is_indexed_array:
                        # Bash behavior: print error but continue, convert to associative array
                        self.error(f"{arg}: cannot convert indexed to associative array", shell)
                        # Convert indexed array content to associative array
                        new_assoc = AssociativeArray()
                        if hasattr(existing.value, '_elements'):
                            # Copy indexed array elements as string keys
                            for index, value in existing.value._elements.items():
                                new_assoc.set(str(index), value)
                        # Completely replace the variable with new associative array
                        # Remove old attributes and set only the new ones
                        shell.state.scope_manager.unset_variable(arg)
                        self._set_variable_with_attributes(shell, arg, new_assoc, attributes, options['global'])
                    else:
                        # Create empty associative array
                        self._set_variable_with_attributes(shell, arg, AssociativeArray(), attributes, options['global'])
                else:
                    # Apply attributes to existing variable or create new one
                    existing = self._get_variable_with_attributes(shell, arg)
                    if existing:
                        # Apply or remove attributes
                        if remove_attrs:
                            shell.state.scope_manager.remove_attribute(arg, remove_attrs)
                            # If removing export, sync to remove from environment
                            if remove_attrs & VarAttributes.EXPORT:
                                shell.state.scope_manager.sync_exports_to_environment(shell.state.env)
                        if attributes:
                            shell.state.scope_manager.apply_attribute(arg, attributes)
                            # Sync exports if needed
                            if attributes & VarAttributes.EXPORT:
                                shell.state.scope_manager.sync_exports_to_environment(shell.state.env)
                    else:
                        # Create new variable with empty value
                        self._set_variable_with_attributes(shell, arg, "", attributes, options['global'])

        return 0

    def _print_variables(self, options: dict, names: List[str], shell: 'Shell') -> int:
        """Print variables with attributes using declare -p format."""
        if names:
            # Print specific variables
            exit_code = 0
            for name in names:
                var = self._get_variable_with_attributes(shell, name)
                if var:
                    self._print_declaration_with_pipeline_support(var, shell)
                else:
                    self.error(f"{name}: not found", shell)
                    exit_code = 1
            return exit_code
        else:
            # Print all variables that match filter criteria
            variables = self._get_all_variables_with_attributes(shell)
            for var in sorted(variables, key=lambda v: v.name):
                if self._matches_filter(var, options):
                    self._print_declaration_with_pipeline_support(var, shell)
            return 0

    def _print_simple_declaration(self, var: Variable, file):
        """Print variable in simple format (NAME=value)."""
        if isinstance(var.value, (IndexedArray, AssociativeArray)):
            # Arrays can't be shown in simple format, use declare format
            self._print_declaration(var, file)
        else:
            # Simple format without quotes or escaping
            print(f"{var.name}={var.value}", file=file)

    def _print_declaration_with_pipeline_support(self, var: Variable, shell: 'Shell'):
        """Print variable declaration with pipeline support."""
        # Build the declaration string
        declaration_str = self._format_declaration(var)

        # Use pipeline-aware output (like echo builtin)
        import os
        if shell.state.in_forked_child:
            # In child process (pipeline), write directly to fd 1
            output_bytes = (declaration_str + '\n').encode('utf-8', errors='replace')
            os.write(1, output_bytes)
        else:
            # In parent process, use shell.stdout to respect redirections
            stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
            print(declaration_str, file=stdout)

    def _print_declaration(self, var: Variable, file):
        """Print variable declaration in reusable format."""
        declaration_str = self._format_declaration(var)
        print(declaration_str, file=file)

    def _format_declaration(self, var: Variable) -> str:
        """Format variable declaration string."""
        # Build flags string
        flags = []
        if var.attributes & VarAttributes.ARRAY:
            flags.append('a')
        if var.attributes & VarAttributes.ASSOC_ARRAY:
            flags.append('A')
        if var.attributes & VarAttributes.READONLY:
            flags.append('r')
        if var.attributes & VarAttributes.EXPORT:
            flags.append('x')
        if var.attributes & VarAttributes.INTEGER:
            flags.append('i')
        if var.attributes & VarAttributes.LOWERCASE:
            flags.append('l')
        if var.attributes & VarAttributes.UPPERCASE:
            flags.append('u')
        if var.attributes & VarAttributes.NAMEREF:
            flags.append('n')
        if var.attributes & VarAttributes.TRACE:
            flags.append('t')

        flag_str = f"-{''.join(flags)}" if flags else "--"

        # Format value
        if isinstance(var.value, IndexedArray):
            # declare -a name=([0]="val" [1]="val")
            elements = []
            for idx in var.value.indices():
                val = var.value.get(idx)
                elements.append(f'[{idx}]="{self._escape_value(val)}"')
            if elements:
                value_str = f"=({' '.join(elements)})"
            else:
                value_str = "=()"

        elif isinstance(var.value, AssociativeArray):
            # declare -A name=([key]="val" [key2]="val2")
            elements = []
            for key, val in sorted(var.value.items()):
                elements.append(f'[{key}]="{self._escape_value(val)}"')
            if elements:
                value_str = f"=({' '.join(elements)})"
            else:
                value_str = "=()"

        else:
            # Regular variable
            value_str = f'="{self._escape_value(str(var.value))}"'

        return f"declare {flag_str} {var.name}{value_str}"

    def _escape_value(self, value: str) -> str:
        """Escape special characters in value for shell output."""
        # Escape backslashes first, then double quotes, dollar signs, and backticks
        value = value.replace('\\', '\\\\')
        value = value.replace('"', '\\"')
        value = value.replace('$', '\\$')
        value = value.replace('`', '\\`')
        return value

    def _parse_array_init(self, value: str) -> List[str]:
        """Parse array initialization: (val1 val2 val3)"""
        # Remove parentheses
        content = value[1:-1].strip()
        if not content:
            return []

        # Simple word splitting with quote handling
        parts = content.split()
        result = []
        for part in parts:
            # Remove surrounding quotes if present
            if (part.startswith('"') and part.endswith('"')) or \
               (part.startswith("'") and part.endswith("'")):
                result.append(part[1:-1])
            else:
                result.append(part)
        return result

    def _parse_assoc_array_init(self, value: str) -> List[tuple[str, str]]:
        """Parse associative array initialization: ([key]=val [key2]=val2)"""
        # Remove parentheses
        content = value[1:-1].strip()
        if not content:
            return []

        # Use shell-like splitting so quoted keys/values with spaces are preserved.
        try:
            parts = shlex.split(content, posix=True)
        except ValueError:
            # Fall back to conservative splitting on malformed quoting.
            parts = content.split()

        result = []
        for part in parts:
            parsed = self._parse_assoc_array_entry(part)
            if parsed is not None:
                result.append(parsed)
        return result

    def _parse_assoc_array_entry(self, token: str) -> Optional[tuple[str, str]]:
        """Parse one associative array entry token in the form [key]=value."""
        if not token.startswith('['):
            return None

        sep_idx = token.find(']=', 1)
        if sep_idx == -1:
            return None

        key = token[1:sep_idx]
        value = token[sep_idx + 2:]
        return key, value

    def _apply_attributes(self, value: Any, attributes: VarAttributes, shell: 'Shell') -> Any:
        """Apply attribute transformations to value."""
        if isinstance(value, (IndexedArray, AssociativeArray)):
            return value  # Arrays aren't transformed

        str_value = str(value)

        if attributes & VarAttributes.UPPERCASE:
            return str_value.upper()
        elif attributes & VarAttributes.LOWERCASE:
            return str_value.lower()
        elif attributes & VarAttributes.INTEGER:
            # Evaluate arithmetic expression
            try:
                from ..arithmetic import evaluate_arithmetic
                result = evaluate_arithmetic(str_value, shell)
                return str(result)
            except (ValueError, ArithmeticError):
                try:
                    return str(int(str_value))
                except (ValueError, TypeError):
                    return "0"
        return str_value

    def _matches_filter(self, var: Variable, options: dict) -> bool:
        """Check if variable matches filter criteria."""
        from ..core import VarAttributes

        # If no specific attribute options are set, show all variables
        has_attribute_filter = any([
            options.get('readonly', False),
            options.get('export', False),
            options.get('integer', False),
            options.get('lowercase', False),
            options.get('uppercase', False),
            options.get('array', False),
            options.get('assoc_array', False),
            options.get('trace', False),
        ])

        if not has_attribute_filter:
            return True

        # Check specific attributes
        if options.get('readonly', False) and not (var.attributes & VarAttributes.READONLY):
            return False
        if options.get('export', False) and not (var.attributes & VarAttributes.EXPORT):
            return False
        if options.get('integer', False) and not (var.attributes & VarAttributes.INTEGER):
            return False
        if options.get('lowercase', False) and not (var.attributes & VarAttributes.LOWERCASE):
            return False
        if options.get('uppercase', False) and not (var.attributes & VarAttributes.UPPERCASE):
            return False
        if options.get('array', False) and not (var.attributes & VarAttributes.ARRAY):
            return False
        if options.get('assoc_array', False) and not (var.attributes & VarAttributes.ASSOC_ARRAY):
            return False
        if options.get('trace', False) and not (var.attributes & VarAttributes.TRACE):
            return False

        return True

    # Methods to interact with shell's enhanced variable storage

    def _get_variable_with_attributes(self, shell: 'Shell', name: str) -> Optional[Variable]:
        """Get variable with its attributes."""
        return shell.state.scope_manager.get_variable_object(name)

    def _get_all_variables_with_attributes(self, shell: 'Shell') -> List[Variable]:
        """Get all variables with their attributes."""
        return shell.state.scope_manager.all_variables_with_attributes()

    def _set_variable_with_attributes(self, shell: 'Shell', name: str,
                                     value: Any, attributes: VarAttributes, global_flag: bool = False):
        """Set variable with attributes."""
        try:
            # When in a function, declare creates local variables by default
            # Unless -g flag is used to force global scope
            # This matches bash behavior where 'declare' in a function is local
            if global_flag:
                local_scope = False  # Force global scope
            else:
                local_scope = bool(shell.function_stack)  # Local if in function

            shell.state.scope_manager.set_variable(name, value, attributes=attributes, local=local_scope)

            # Handle export - sync to environment
            if attributes & VarAttributes.EXPORT:
                shell.state.scope_manager.sync_exports_to_environment(shell.state.env)
        except ReadonlyVariableError:
            raise ReadonlyVariableError(f"{self.name}: {name}: readonly variable")

    def _print_function_definition(self, name, func, stdout):
        """Print a function definition in a format that can be re-executed."""
        print(f"{name} () ", file=stdout, end='')
        print(ShellFormatter.format_function_body(func), file=stdout)

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
        """Execute the readonly builtin."""
        # Parse options
        options, names = self._parse_readonly_options(args[1:], shell)
        if options is None:
            return 1

        if options['functions']:
            return self._handle_readonly_functions(names, shell)
        elif options['print']:
            # List readonly variables in declare format
            declare_builtin = DeclareBuiltin()
            return declare_builtin.execute(['declare', '-pr'], shell)
        elif not names:
            # No arguments - list all readonly variables (same as declare -pr)
            declare_builtin = DeclareBuiltin()
            return declare_builtin.execute(['declare', '-pr'], shell)
        else:
            # Process arguments - readonly is equivalent to declare -r
            declare_args = ['declare', '-r'] + names
            declare_builtin = DeclareBuiltin()
            return declare_builtin.execute(declare_args, shell)

    def _parse_readonly_options(self, args: List[str], shell: 'Shell') -> tuple[Optional[dict], List[str]]:
        """Parse readonly options and return (options_dict, function_names)."""
        options = {
            'functions': False,  # -f
            'print': False,      # -p
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

            stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
            for name, func in readonly_funcs:
                print(f"readonly -f {name}", file=stdout)
            return 0

        # Set specified functions as readonly
        exit_code = 0
        for name in names:
            func = shell.function_manager.get_function(name)
            if func:
                shell.function_manager.set_function_readonly(name)
            else:
                self.error(f"{name}: not found", shell)
                exit_code = 1

        return exit_code

    @property
    def help(self) -> str:
        return """readonly: readonly [-f] [-p] [name[=value] ...]

    Mark variables or functions as readonly.

    Mark each name as readonly; the values of these names may not be changed
    by subsequent assignment. If value is supplied, assign value before
    marking as readonly.

    Options:
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
        if not shell.function_stack:
            print("return: can only `return' from a function or sourced script", file=sys.stderr)
            return 1

        # Get return value
        if len(args) > 1:
            try:
                exit_code = int(args[1])
                # Wrap return value to 0-255 range like bash does
                exit_code = exit_code % 256
            except ValueError:
                print(f"return: {args[1]}: numeric argument required", file=sys.stderr)
                return 1
        else:
            # With no arguments, return the current value of $?
            exit_code = shell.state.last_exit_code

        # We can't actually "return" from the middle of execution in Python,
        # so we'll use an exception for control flow
        raise FunctionReturn(exit_code)
