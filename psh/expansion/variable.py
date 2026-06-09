"""Variable expansion implementation."""
import os
import sys
from typing import TYPE_CHECKING

from .parameter_expansion import ParameterExpansion

if TYPE_CHECKING:
    from ..shell import Shell

# Sentinel for distinguishing an unset variable from one set to the empty
# string (used by the non-colon parameter operators ${x-}, ${x+}, ...).
_UNSET = object()


class VariableExpander:
    """Handles variable and parameter expansion."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state
        self.param_expansion = ParameterExpansion(shell)

    def expand_variable(self, var_expr: str) -> str:
        """Expand a variable expression starting with $."""

        if not var_expr.startswith('$'):
            return var_expr

        var_expr = var_expr[1:]  # Remove $

        # Handle ${var} syntax
        if var_expr.startswith('{') and var_expr.endswith('}'):
            var_content = var_expr[1:-1]

            # ${#arr[@]} or ${#arr[index]} — array/element length
            if var_content.startswith('#') and '[' in var_content and var_content.endswith(']'):
                return self._expand_array_length(var_content)

            # ${!arr[@]} — array indices/keys
            if var_content.startswith('\\!'):
                var_content = var_content[1:]  # Remove the backslash
            if var_content.startswith('!') and '[' in var_content and var_content.endswith(']'):
                result = self._expand_array_indices(var_content)
                if result is not None:
                    return result

            # ${arr[@]:start:length} — array slicing
            if ':' in var_content and '[' in var_content and ']' in var_content:
                result = self._expand_array_slice(var_content)
                if result is not None:
                    return result

            # ${arr[index]} — array subscript (exclude case modification)
            if ('[' in var_content and var_content.endswith(']') and
                not any(op in var_content for op in ['^^', ',,', '^', ','])):
                result = self._expand_array_subscript(var_content)
                if result is not None:
                    return result

            # All parameter-expansion operators (colon and non-colon) go
            # through the single application path in expand_parameter_direct.
            try:
                operator, var_name, operand = self.param_expansion.parse_expansion('${' + var_content + '}')
                if operator:
                    return self.expand_parameter_direct(operator, var_name, operand)
            except (ValueError, AttributeError):
                pass

            # No operator: a plain ${var}. Honor nounset. The error already
            # carries bash's message format; do not re-wrap (a "psh: " prefix
            # here doubled up with the printing handler's prefix).
            var_name = var_content
            if self.state.options.get('nounset', False):
                from ..core import OptionHandler
                OptionHandler.check_unset_variable(self.state, var_name)
        else:
            var_name = var_expr

        return self._expand_special_variable(var_name)

    # ------------------------------------------------------------------
    # Helpers extracted from expand_variable()
    # ------------------------------------------------------------------

    def _expand_array_length(self, var_content: str) -> str:
        """Handle ${#arr[@]}, ${#arr[*]}, and ${#arr[index]}."""
        from ..core import AssociativeArray, IndexedArray

        array_part = var_content[1:]  # Remove the #
        bracket_pos = array_part.find('[')
        array_name = array_part[:bracket_pos]
        index_expr = array_part[bracket_pos + 1:-1]

        if index_expr in ('@', '*'):
            var = self.state.scope_manager.get_variable_object(array_name)
            if var and isinstance(var.value, (IndexedArray, AssociativeArray)):
                return str(var.value.length())
            elif var and var.value:
                return '1'
            return '0'

        # ${#arr[index]} — length of specific element
        var = self.state.scope_manager.get_variable_object(array_name)

        if var and isinstance(var.value, IndexedArray):
            expanded_index = self.expand_array_index(index_expr)
            try:
                from ..arithmetic import ArithmeticError, evaluate_arithmetic
                try:
                    index = evaluate_arithmetic(expanded_index, self.shell)
                except ArithmeticError:
                    index = 0
                element = var.value.get(index)
                return str(len(element)) if element else '0'
            except (ValueError, TypeError):
                return '0'
        elif var and isinstance(var.value, AssociativeArray):
            expanded_key = self.expand_array_index(index_expr)
            element = var.value.get(expanded_key)
            return str(len(element)) if element else '0'
        elif var and var.value:
            try:
                index = int(self.expand_array_index(index_expr))
                if index == 0:
                    return str(len(str(var.value)))
                return '0'
            except (ValueError, TypeError):
                return '0'
        return '0'

    def _expand_array_indices(self, var_content: str) -> str:
        """Handle ${!arr[@]} and ${!arr[*]}.

        Returns the result string, or None if this is not a matching
        expansion (so the caller can fall through).
        """
        from ..core import AssociativeArray, IndexedArray

        array_part = var_content[1:]  # Remove the !
        bracket_pos = array_part.find('[')
        array_name = array_part[:bracket_pos]
        index_expr = array_part[bracket_pos + 1:-1]

        if index_expr not in ('@', '*'):
            return None

        var = self.state.scope_manager.get_variable_object(array_name)

        if var and isinstance(var.value, IndexedArray):
            indices = var.value.indices()
            return ' '.join(str(i) for i in indices)
        elif var and isinstance(var.value, AssociativeArray):
            keys = var.value.keys()
            return ' '.join(keys)
        elif var and var.value:
            return '0'
        return ''

    def _expand_array_slice(self, var_content: str) -> str:
        """Handle ${arr[@]:start:length}.

        Returns the result string, or None if this is not a slice
        expansion (so the caller can fall through).
        """
        from ..core import IndexedArray

        bracket_pos = var_content.find('[')
        close_bracket_pos = var_content.find(']')

        if not (bracket_pos < close_bracket_pos and close_bracket_pos < var_content.find(':')):
            return None

        array_name = var_content[:bracket_pos]
        index_expr = var_content[bracket_pos + 1:close_bracket_pos]
        slice_part = var_content[close_bracket_pos + 1:]

        if not (slice_part.startswith(':') and index_expr in ('@', '*')):
            return None

        var = self.state.scope_manager.get_variable_object(array_name)
        slice_params = slice_part[1:].split(':', 1)

        if var and isinstance(var.value, IndexedArray):
            try:
                sliced = self._slice_sequence(var.value.all_elements(), slice_part[1:])
                if index_expr == '@':
                    return ' '.join(sliced)
                return self._ifs_star_separator().join(sliced)
            except (ValueError, TypeError):
                return ''
        elif var and var.value:
            try:
                start = int(self.expand_string_variables(slice_params[0]))
                if start == 0:
                    if len(slice_params) > 1:
                        length = int(self.expand_string_variables(slice_params[1]))
                        if length > 0:
                            return str(var.value)
                        return ''
                    return str(var.value)
                return ''
            except (ValueError, TypeError):
                return ''
        return ''

    def _expand_array_subscript(self, var_content: str) -> str:
        """Handle ${arr[index]}, ${arr[@]}, ${arr[*]}.

        Returns the result string, or None if this is not a subscript
        expansion (so the caller can fall through).
        """
        from ..core import AssociativeArray, IndexedArray

        bracket_pos = var_content.find('[')
        array_name = var_content[:bracket_pos]
        index_expr = var_content[bracket_pos + 1:-1]

        var = self.state.scope_manager.get_variable_object(array_name)

        # ${arr[@]} or ${arr[*]}
        if index_expr in ('@', '*'):
            if var and isinstance(var.value, (IndexedArray, AssociativeArray)):
                elements = var.value.all_elements()
                if index_expr == '@':
                    return ' '.join(elements)
                return self._ifs_star_separator().join(elements)
            elif var and var.value:
                return str(var.value)
            return ''

        # Regular indexed access
        if var and isinstance(var.value, IndexedArray):
            expanded_index = self.expand_array_index(index_expr)
            try:
                from ..arithmetic import ArithmeticError, evaluate_arithmetic
                try:
                    index = evaluate_arithmetic(expanded_index, self.shell)
                except ArithmeticError:
                    index = 0
                result = var.value.get(index)
                return result if result is not None else ''
            except ValueError:
                result = var.value.get(0)
                return result if result is not None else ''
        elif var and isinstance(var.value, AssociativeArray):
            expanded_key = self.expand_array_index(index_expr)
            result = var.value.get(expanded_key)
            return result if result is not None else ''
        elif var and var.value:
            expanded_index = self.expand_array_index(index_expr)
            try:
                index = int(expanded_index)
                if index == 0:
                    return str(var.value)
                return ''
            except ValueError:
                return ''
        return ''

    def _expand_special_variable(self, var_name: str) -> str:
        """Expand special variables ($?, $$, $!, etc.) and regular variables."""
        if var_name == '?':
            return str(self.state.last_exit_code)
        elif var_name == '$':
            return str(os.getpid())
        elif var_name == '!':
            return str(self.state.last_bg_pid) if self.state.last_bg_pid else ''
        elif var_name == '#':
            return str(len(self.state.positional_params))
        elif var_name == '-':
            return self.state.get_option_string()
        elif var_name == '0':
            if self.state.function_stack:
                return self.state.function_stack[-1]
            return self.state.script_name
        elif var_name == '@':
            return ' '.join(self.state.positional_params)
        elif var_name == '*':
            return self._ifs_star_separator().join(self.state.positional_params)
        elif var_name.isdigit():
            index = int(var_name) - 1
            if 0 <= index < len(self.state.positional_params):
                return self.state.positional_params[index]
            if self.state.options.get('nounset', False):
                from ..core import OptionHandler
                OptionHandler.check_unset_variable(self.state, var_name)
            return ''

        # Regular variables. Route through _get_var_or_positional so a nameref
        # to an array element (declare -n e=arr[1]) reads the element value.
        result = self._get_var_or_positional(var_name)

        if self.state.options.get('nounset', False):
            # The error carries bash's message format; no "psh: " re-wrap here
            # (the printing handler adds the prefix exactly once).
            from ..core import OptionHandler
            OptionHandler.check_unset_variable(self.state, var_name)

        return result

    def _get_var_or_positional(self, var_name: str) -> str:
        """Get value of a variable or positional parameter."""
        # Follow a nameref to its target name; an array-element target (arr[1])
        # then flows into the array branch below.
        var_name = self.state.scope_manager.resolve_nameref_name(var_name)
        if var_name.isdigit():
            index = int(var_name) - 1
            if 0 <= index < len(self.state.positional_params):
                return self.state.positional_params[index]
            return ''
        elif var_name in ['#', '?', '$', '!', '@', '*', '0', '-']:
            # Special variables
            return self.state.get_special_variable(var_name)
        elif '[' in var_name and var_name.endswith(']'):
            # Array element: arr[index]
            bracket_pos = var_name.find('[')
            array_name = var_name[:bracket_pos]
            index_expr = var_name[bracket_pos + 1:-1]

            from ..core import AssociativeArray, IndexedArray
            var = self.state.scope_manager.get_variable_object(array_name)

            if var and isinstance(var.value, IndexedArray):
                expanded_index = self.expand_array_index(index_expr)
                try:
                    from ..arithmetic import ArithmeticError, evaluate_arithmetic
                    index = evaluate_arithmetic(expanded_index, self.shell)
                except ArithmeticError:
                    index = 0
                result = var.value.get(index)
                return result if result is not None else ''
            elif var and isinstance(var.value, AssociativeArray):
                expanded_key = self.expand_array_index(index_expr)
                result = var.value.get(expanded_key)
                return result if result is not None else ''
            else:
                return ''
        else:
            return self.state.get_variable(var_name, '')

    def set_var_or_array_element(self, var_name: str, value: str):
        """Set a variable or array element (public).

        Handles both plain variables (``var_name="foo"``) and array
        subscript syntax (``arr[5]="foo"``). Exposed as public API so other
        layers (e.g. the scope manager resolving a nameref whose target is an
        array element) can route subscripted writes here without reaching into
        a private method.
        """
        if '[' in var_name and var_name.endswith(']'):
            bracket_pos = var_name.find('[')
            array_name = var_name[:bracket_pos]
            index_expr = var_name[bracket_pos + 1:-1]

            from ..core import AssociativeArray, IndexedArray
            var = self.state.scope_manager.get_variable_object(array_name)

            if var and isinstance(var.value, IndexedArray):
                expanded_index = self.expand_array_index(index_expr)
                try:
                    from ..arithmetic import ArithmeticError, evaluate_arithmetic
                    index = evaluate_arithmetic(expanded_index, self.shell)
                except ArithmeticError:
                    index = 0
                var.value.set(index, value)
            elif var and isinstance(var.value, AssociativeArray):
                expanded_key = self.expand_array_index(index_expr)
                var.value.set(expanded_key, value)
            else:
                # Array doesn't exist yet; create an indexed array
                arr = IndexedArray()
                expanded_index = self.expand_array_index(index_expr)
                try:
                    from ..arithmetic import ArithmeticError, evaluate_arithmetic
                    idx = evaluate_arithmetic(expanded_index, self.shell)
                except ArithmeticError:
                    idx = 0
                arr.set(idx, value)
                from ..core import VarAttributes
                self.state.scope_manager.set_variable(
                    array_name, arr,
                    attributes=VarAttributes.ARRAY,
                )
        else:
            self.state.set_variable(var_name, value)

    def expand_parameter_direct(self, operator: str, var_name: str, operand: str) -> str:
        """Expand a parameter expansion from pre-parsed components.

        Called by ExpansionEvaluator for Word AST nodes and by
        expand_variable() for string-based expansions.

        Args:
            operator: The expansion operator ('#', '##', '%', '%%', '/', '//', etc.)
            var_name: The variable name (may include array subscript like 'arr[0]')
            operand: The pattern/replacement/offset operand
        """
        # Indirect / nameref-name expansion: ${!name}
        if operator == '!' and var_name and not operand:
            return self._expand_indirect(var_name)

        # Follow a nameref to its target name so ${ref...} operators apply to
        # the target (including an array-element target like arr[1]).
        var_name = self.state.scope_manager.resolve_nameref_name(var_name)

        # Resolve the variable value
        if var_name in ('', '#') and operator == '#' and not operand:
            # Special case: ${#} is number of positional params
            # Parser AST uses parameter='', operator='#'; parse_expansion uses var_name='#'
            return str(len(self.state.positional_params))
        elif var_name == '*':
            if operator == '#':
                return str(len(self.state.positional_params))
            if operator == ':':
                return self._ifs_star_separator().join(
                    self._slice_sequence(self._positional_slice_elements(), operand))
            if len(operator) == 2 and operator[0] == '@':
                return self._ifs_star_separator().join(
                    self._apply_transform(operator[1], p, var_name)
                    for p in self.state.positional_params)
            value = ' '.join(self.state.positional_params)
        elif var_name == '@':
            if operator == '#':
                return str(len(self.state.positional_params))
            if operator == ':':
                return ' '.join(
                    self._slice_sequence(self._positional_slice_elements(), operand))
            if len(operator) == 2 and operator[0] == '@':
                return ' '.join(
                    self._apply_transform(operator[1], p, var_name)
                    for p in self.state.positional_params)
            value = ' '.join(self.state.positional_params)
        elif var_name.isdigit():
            index = int(var_name) - 1
            value = self.state.positional_params[index] if 0 <= index < len(self.state.positional_params) else ''
        elif '[' in var_name and var_name.endswith(']'):
            # Array element with parameter expansion
            bracket_pos = var_name.find('[')
            array_name = var_name[:bracket_pos]
            index_expr = var_name[bracket_pos+1:-1]

            from ..core import AssociativeArray, IndexedArray
            var = self.state.scope_manager.get_variable_object(array_name)

            # Handle special indices @ and * for whole-array operations
            if index_expr in ('@', '*'):
                # ${#arr[@]} / ${#arr[*]} — array element count
                if operator == '#' and not operand:
                    if var and isinstance(var.value, (IndexedArray, AssociativeArray)):
                        return str(var.value.length())
                    elif var and var.value:
                        return '1'
                    else:
                        return '0'

                if var and isinstance(var.value, (IndexedArray, AssociativeArray)):
                    elements = var.value.all_elements()
                elif var and var.value:
                    elements = [str(var.value)]
                else:
                    elements = []

                # ${arr[@]:offset:length} — array slice (select elements),
                # distinct from per-element substring.
                if operator == ':':
                    sliced = self._slice_sequence(elements, operand)
                    if index_expr == '@':
                        return ' '.join(sliced)
                    return self._ifs_star_separator().join(sliced)

                # Whole-array transform: ${arr[@]@A} -> a `declare` statement.
                if operator == '@A':
                    return self._array_assignment_form(array_name, var)

                # Per-element transforms (@Q/@U/@u/@L/@E/@P/@a) apply to each
                # element; the @-operators need the array *name* (not the
                # subscripted form) so e.g. ${arr[@]@a} reports the array flag.
                op_var = array_name if (len(operator) == 2 and operator[0] == '@') else var_name
                results = []
                for element in elements:
                    results.append(self._apply_operator(operator, element, operand,
                                                        var_name=op_var))

                if index_expr == '@':
                    return ' '.join(results)
                else:
                    return self._ifs_star_separator().join(results)

            # Handle regular indexed/associative array access
            elif var and isinstance(var.value, IndexedArray):
                expanded_index = self.expand_array_index(index_expr)
                try:
                    from ..arithmetic import ArithmeticError, evaluate_arithmetic
                    try:
                        index = evaluate_arithmetic(expanded_index, self.shell)
                    except ArithmeticError:
                        index = 0
                    value = var.value.get(index) or ''
                except (ValueError, TypeError):
                    value = ''
            elif var and isinstance(var.value, AssociativeArray):
                expanded_key = self.expand_array_index(index_expr)
                value = var.value.get(expanded_key) or ''
            else:
                value = ''
        else:
            # Use _get_var_or_positional to handle special variables (#, ?, $, etc.)
            value = self._get_var_or_positional(var_name)

        needs_is_set = (operator in ('-', '=', '+', '?')
                        or (len(operator) == 2 and operator[0] == '@'))
        is_set = self._param_is_set(var_name) if needs_is_set else True
        return self._apply_operator(operator, value, operand, var_name=var_name, is_set=is_set)

    def _expand_indirect(self, name: str) -> str:
        """Expand ${!name}.

        If *name* is a nameref, yield its target *name* (bash treats namerefs
        specially here). Otherwise treat the value of *name* as the name of
        another variable and yield that variable's value (classic indirect
        expansion). Resolution of the final lookup follows namerefs.
        """
        var = self.state.scope_manager.get_variable_object(name)  # raw, no deref
        if var is None:
            return ''
        if var.is_nameref:
            return str(var.value) if var.value else ''
        indirect_name = var.as_string()
        if not indirect_name:
            return ''
        return self.state.get_variable(indirect_name, '') or ''

    def _expand_operand(self, operand: str) -> str:
        """Expand a conditional-operator operand (${x:-OPERAND}).

        One surrounding level of quotes is removed (bash): single quotes
        keep the text literal, double quotes expand without tilde.
        """
        if len(operand) >= 2 and operand[0] == "'" and operand[-1] == "'":
            return operand[1:-1]
        if len(operand) >= 2 and operand[0] == '"' and operand[-1] == '"':
            return self.expand_string_variables(operand[1:-1])
        return self._expand_tilde_in_operand(self.expand_string_variables(operand))

    def _expand_tilde_in_operand(self, text: str) -> str:
        """Apply tilde expansion to parameter expansion operand values."""
        if text.startswith('~'):
            return self.shell.expansion_manager.tilde_expander.expand(text)
        return text

    def _positional_slice_elements(self) -> list:
        """Element sequence for ``${@:off:len}`` / ``${*:off:len}`` slicing.

        bash indexes positional slices as ``[$0, $1, $2, ...]``: ``${@:0}``
        includes ``$0`` and a negative offset is taken relative to one past
        the last positional parameter.  Prepending ``$0`` makes plain Python
        list slicing match those semantics.
        """
        return [self.state.get_special_variable('0')] + list(self.state.positional_params)

    def _slice_sequence(self, elements: list, operand: str) -> list:
        """Slice a list of words for ``${seq[@]:offset:length}`` expansions.

        Offset and length are arithmetic expressions.  A negative offset
        counts from the end; a negative length is an error (matching bash,
        which only allows from-the-end lengths for scalar substrings, not
        for ``@``/``*``/array slices).
        """
        from ..arithmetic import ArithmeticError, evaluate_arithmetic
        from ..core import ExpansionError

        if ':' in operand:
            offset_str, length_str = operand.split(':', 1)
        else:
            offset_str, length_str = operand, None

        try:
            offset = evaluate_arithmetic(offset_str, self.shell) if offset_str.strip() else 0
            length = (evaluate_arithmetic(length_str, self.shell)
                      if length_str is not None and length_str.strip() else None)
        except (ValueError, ArithmeticError):
            print(f"psh: ${{seq:{operand}}}: invalid offset or length", file=sys.stderr)
            return []

        n = len(elements)
        start = n + offset if offset < 0 else offset
        if start < 0:
            start = 0

        if length is None:
            return elements[start:]
        if length < 0:
            print(f"psh: {length}: substring expression < 0", file=sys.stderr)
            self.state.last_exit_code = 1
            raise ExpansionError(f"{length}: substring expression < 0", exit_code=1)
        return elements[start:start + length]

    def _ifs_star_separator(self) -> str:
        """Separator for joining $* / ${arr[*]}.

        bash distinguishes unset IFS (join with a space) from a null IFS
        (``IFS=``, join with no separator); only the first char is used
        otherwise.
        """
        ifs = self.state.get_variable('IFS', None)
        if ifs is None:
            return ' '
        return ifs[0] if ifs else ''

    def _param_is_set(self, var_name: str) -> bool:
        """Whether a parameter is set (distinct from set-but-empty).

        Used by the non-colon operators ${x-w}/${x=w}/${x+w}/${x?w}, which
        test only for "unset" (the colon variants test "unset or null").
        """
        if var_name == '':
            return False
        if var_name in ('?', '$', '!', '#', '-', '0'):
            return True
        if var_name in ('@', '*'):
            return len(self.state.positional_params) > 0
        if var_name.isdigit():
            return 0 <= int(var_name) - 1 < len(self.state.positional_params)
        if '[' in var_name and var_name.endswith(']'):
            from ..core import AssociativeArray, IndexedArray
            bracket = var_name.find('[')
            name = var_name[:bracket]
            index_expr = var_name[bracket + 1:-1]
            var = self.state.scope_manager.get_variable_object(name)
            if var is None:
                return False
            if isinstance(var.value, IndexedArray):
                try:
                    from ..arithmetic import ArithmeticError, evaluate_arithmetic
                    index = evaluate_arithmetic(self.expand_array_index(index_expr), self.shell)
                except ArithmeticError:
                    index = 0
                return var.value.get(index) is not None
            if isinstance(var.value, AssociativeArray):
                return var.value.get(self.expand_array_index(index_expr)) is not None
            return False
        return self.state.get_variable(var_name, _UNSET) is not _UNSET

    def _apply_operator(self, operator: str, value: str, operand: str,
                        var_name: str = '', is_set: bool = True) -> str:
        """Apply a parameter expansion operator to a resolved value.

        ``is_set`` distinguishes unset from set-but-empty and is only consulted
        by the non-colon operators (``-``, ``=``, ``+``, ``?``).
        """
        if operator == ':-':
            if not value:
                return self._expand_operand(operand)
            return value
        elif operator == '-':
            # Unset -> operand; set (even if empty) -> value.
            if not is_set:
                return self._expand_operand(operand)
            return value
        elif operator == '=':
            if not is_set:
                expanded_default = self._expand_operand(operand)
                if var_name and not var_name.isdigit():
                    self.set_var_or_array_element(var_name, expanded_default)
                return expanded_default
            return value
        elif operator == '+':
            # Set (even if empty) -> operand; unset -> empty.
            if is_set:
                return self._expand_operand(operand)
            return ''
        elif operator == '?':
            if not is_set:
                expanded_message = self.expand_string_variables(operand) if operand else "parameter not set"
                print(f"psh: {var_name}: {expanded_message}", file=sys.stderr)
                self.state.last_exit_code = 127
                from ..core import ExpansionError
                raise ExpansionError(f"{var_name}: {expanded_message}", exit_code=127)
            return value
        elif operator == ':=':
            if not value:
                expanded_default = self._expand_operand(operand)
                if var_name and not var_name.isdigit():
                    self.set_var_or_array_element(var_name, expanded_default)
                return expanded_default
            return value
        elif operator == ':?':
            if not value:
                expanded_message = self.expand_string_variables(operand) if operand else "parameter null or not set"
                print(f"psh: {var_name}: {expanded_message}", file=sys.stderr)
                self.state.last_exit_code = 127
                from ..core import ExpansionError
                raise ExpansionError(f"{var_name}: {expanded_message}", exit_code=127)
            return value
        elif operator == ':+':
            if value:
                return self._expand_operand(operand)
            return ''
        elif operator == '#' and not operand:
            return self.param_expansion.get_length(value)
        elif operator == '#' and operand:
            return self.param_expansion.remove_shortest_prefix(
                value, self._expand_pattern_operand(operand))
        elif operator == '##':
            return self.param_expansion.remove_longest_prefix(
                value, self._expand_pattern_operand(operand))
        elif operator == '%%':
            return self.param_expansion.remove_longest_suffix(
                value, self._expand_pattern_operand(operand))
        elif operator == '%':
            return self.param_expansion.remove_shortest_suffix(
                value, self._expand_pattern_operand(operand))
        elif operator in ('/', '//', '/#', '/%'):
            return self._substitute(operator, value, operand)
        elif operator == ':':
            # Substring extraction. Offset and length are arithmetic
            # expressions (bash), so support ${x:1+1:2}, ${x:(-3):2}, etc.
            from ..arithmetic import ArithmeticError, evaluate_arithmetic
            from ..core import ExpansionError

            if ':' in operand:
                offset_str, length_str = operand.split(':', 1)
            else:
                offset_str, length_str = operand, None

            try:
                offset = evaluate_arithmetic(offset_str, self.shell) if offset_str.strip() else 0
                length = (evaluate_arithmetic(length_str, self.shell)
                          if length_str is not None and length_str.strip() else
                          (0 if length_str is not None else None))
            except (ValueError, ArithmeticError):
                print(f"psh: ${{var:{operand}}}: invalid offset or length", file=sys.stderr)
                return ''

            try:
                return self.param_expansion.extract_substring(value, offset, length)
            except ValueError as e:
                # Out-of-range negative length: bash reports an error and a
                # non-zero exit status.
                print(f"psh: {e}", file=sys.stderr)
                self.state.last_exit_code = 1
                raise ExpansionError(str(e), exit_code=1)
        elif operator == '!*':
            # ${!prefix*}: names joined with the first character of IFS
            names = self.param_expansion.match_variable_names(var_name)
            return self._ifs_star_separator().join(names)
        elif operator == '!@':
            # ${!prefix@}: names joined with spaces
            names = self.param_expansion.match_variable_names(var_name)
            return ' '.join(names)
        elif operator == '^':
            return self.param_expansion.uppercase_first(
                value, self._expand_pattern_operand(operand) if operand else operand)
        elif operator == '^^':
            return self.param_expansion.uppercase_all(
                value, self._expand_pattern_operand(operand) if operand else operand)
        elif operator == ',':
            return self.param_expansion.lowercase_first(
                value, self._expand_pattern_operand(operand) if operand else operand)
        elif operator == ',,':
            return self.param_expansion.lowercase_all(
                value, self._expand_pattern_operand(operand) if operand else operand)
        elif len(operator) == 2 and operator[0] == '@':
            # An unset parameter transforms to nothing (bash: ${unset@Q} -> '').
            if not is_set:
                return ''
            return self._apply_transform(operator[1], value, var_name)
        # Unknown operator, return value unchanged
        return value

    # Attribute-flag order used by ${var@a} (matches bash, e.g. -airx -> "airx").
    _ATTR_FLAG_ORDER = (
        ('ARRAY', 'a'), ('ASSOC_ARRAY', 'A'), ('INTEGER', 'i'),
        ('LOWERCASE', 'l'), ('UPPERCASE', 'u'), ('NAMEREF', 'n'),
        ('READONLY', 'r'), ('TRACE', 't'), ('EXPORT', 'x'),
    )

    def _apply_transform(self, op: str, value: str, var_name: str) -> str:
        """Apply a ${var@OP} transformation operator to a resolved value.

        Per-element operators (Q/U/u/L/E/P/a) are also invoked once per element
        for ``${arr[@]@OP}`` by the array branch of expand_parameter_direct.
        """
        if op == 'U':
            return value.upper()
        if op == 'L':
            return value.lower()
        if op == 'u':
            return value[:1].upper() + value[1:]
        if op == 'Q':
            return self._shell_quote(value)
        if op == 'E':
            return self._ansi_c_expand(value)
        if op == 'P':
            from ..prompt import PromptExpander
            return PromptExpander(self.shell).expand_prompt(value)
        if op == 'a':
            return self._var_attr_flags(var_name)
        if op == 'A':
            flags = self._var_attr_flags(var_name)
            assign = f"{var_name}={self._shell_quote(value)}"
            return f"declare -{flags} {assign}" if flags else assign
        # K/k (associative key/value display) are not implemented.
        return value

    @staticmethod
    def _shell_quote(s: str) -> str:
        """Quote a string so it can be reused as shell input (bash ${var@Q}).

        Empty -> ''. Strings with control characters use the $'...' ANSI-C
        form; otherwise a single-quoted form with embedded quotes escaped as
        '\\''.
        """
        if s == '':
            return "''"
        if any(ord(c) < 32 or ord(c) == 127 for c in s):
            out = []
            simple = {'\n': '\\n', '\t': '\\t', '\r': '\\r', '\\': '\\\\',
                      "'": "\\'", '\a': '\\a', '\b': '\\b', '\f': '\\f',
                      '\v': '\\v'}
            for c in s:
                if c in simple:
                    out.append(simple[c])
                elif ord(c) < 32 or ord(c) == 127:
                    out.append('\\%03o' % ord(c))
                else:
                    out.append(c)
            return "$'" + ''.join(out) + "'"
        return "'" + s.replace("'", "'\\''") + "'"

    @staticmethod
    def _ansi_c_expand(s: str) -> str:
        """Expand backslash escapes as in $'...' (bash ${var@E})."""
        simple = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', "'": "'",
                  '"': '"', 'a': '\a', 'b': '\b', 'f': '\f', 'v': '\v',
                  'e': '\x1b', 'E': '\x1b', '0': '\0'}
        out = []
        i = 0
        while i < len(s):
            if s[i] == '\\' and i + 1 < len(s):
                nxt = s[i + 1]
                if nxt in simple:
                    out.append(simple[nxt])
                    i += 2
                    continue
                if nxt == 'x':
                    j = i + 2
                    hexd = ''
                    while j < len(s) and len(hexd) < 2 and s[j] in '0123456789abcdefABCDEF':
                        hexd += s[j]
                        j += 1
                    if hexd:
                        out.append(chr(int(hexd, 16)))
                        i = j
                        continue
                out.append(s[i])
                i += 1
            else:
                out.append(s[i])
                i += 1
        return ''.join(out)

    def _var_attr_flags(self, var_name: str) -> str:
        """Return the attribute-flag letters for ${var@a} (e.g. 'rx', '')."""
        from ..core.variables import VarAttributes
        var = self.state.scope_manager.get_variable_object(var_name)
        if var is None:
            return ''
        flags = []
        for attr_name, letter in self._ATTR_FLAG_ORDER:
            if var.attributes & getattr(VarAttributes, attr_name):
                flags.append(letter)
        return ''.join(flags)

    def _array_assignment_form(self, array_name: str, var) -> str:
        """Build the ${arr[@]@A} declare statement (values double-quoted)."""
        from ..core import AssociativeArray, IndexedArray
        flags = self._var_attr_flags(array_name)

        def dq(s: str) -> str:
            s = (s.replace('\\', '\\\\').replace('"', '\\"')
                 .replace('$', '\\$').replace('`', '\\`'))
            return f'"{s}"'

        if var and isinstance(var.value, AssociativeArray):
            # bash emits a trailing space before ')' for associative arrays.
            items = ' '.join(f'[{k}]={dq(v)}' for k, v in var.value.items())
            body = f'{items} ' if items else ''
            return f"declare -{flags} {array_name}=({body})"
        elif var and isinstance(var.value, IndexedArray):
            body = ' '.join(f'[{i}]={dq(var.value.get(i))}' for i in var.value.indices())
        else:
            # Not actually an array — fall back to the scalar assignment form.
            assign = f"{array_name}={self._shell_quote(str(var.value) if var else '')}"
            return f"declare -{flags} {assign}" if flags else assign
        return f"declare -{flags} {array_name}=({body})"

    def expand_array_index(self, index_expr: str) -> str:
        """Expand variables in array index expressions.

        In array subscripts, bare variable names should be expanded as variables.
        For example, in ${arr[i]}, 'i' should be expanded to its value.
        """
        # First try normal variable expansion in case it has $
        expanded = self.expand_string_variables(index_expr)

        # If no $ was found in the index, check if the whole thing is a variable name
        if expanded == index_expr:
            # Check if it's a valid variable name (letters, digits, underscore)
            if index_expr and (index_expr[0].isalpha() or index_expr[0] == '_'):
                if all(c.isalnum() or c == '_' for c in index_expr):
                    # It's a valid variable name, expand it
                    var_value = self.state.get_variable(index_expr, '')
                    if var_value:
                        return var_value

        return expanded

    def expand_string_variables(self, text: str) -> str:
        """Expand variables and arithmetic in a string (for here strings and quoted strings)."""
        from ..lexer.pure_helpers import (
            find_balanced_double_parentheses,
            find_balanced_parentheses,
            find_closing_delimiter,
        )

        result = []
        i = 0
        while i < len(text):
            if text[i] == '$' and i + 1 < len(text):
                if text[i + 1] == '(' and i + 2 < len(text) and text[i + 2] == '(':
                    # $((...)) arithmetic expansion — quote-aware scanner
                    end_pos, found = find_balanced_double_parentheses(
                        text, i + 3, track_quotes=True)
                    if found:
                        arith_expr = text[i:end_pos]
                        arith_result = self.shell.expansion_manager.execute_arithmetic_expansion(arith_expr)
                        result.append(str(arith_result))
                        i = end_pos
                    else:
                        result.append(text[i])
                        i += 1
                    continue
                elif text[i + 1] == '(':
                    # $(...) command substitution — quote-aware scanner
                    end_pos, found = find_balanced_parentheses(
                        text, i + 2, track_quotes=True)
                    if found:
                        cmd_sub = text[i:end_pos]
                        output = self.shell.expansion_manager.command_sub.execute(cmd_sub)
                        result.append(output)
                        i = end_pos
                    else:
                        result.append(text[i])
                        i += 1
                    continue
                elif text[i + 1] == '{':
                    # ${var} or ${var:-default} — quote-aware scanner
                    end_pos, found = find_closing_delimiter(
                        text, i + 2, '{', '}',
                        track_quotes=True, track_escapes=True)
                    if found:
                        var_expr = text[i:end_pos]
                        expanded = self.expand_variable(var_expr)
                        result.append(expanded)
                        i = end_pos
                    else:
                        result.append(text[i])
                        i += 1
                    continue
                else:
                    # Simple variable like $var
                    j = i + 1
                    # Special single-char variables
                    if j < len(text) and text[j] in '?$!#@*-0123456789':
                        var_expr = text[i:j + 1]
                        result.append(self.expand_variable(var_expr))
                        i = j + 1
                        continue
                    # Regular variable name
                    while j < len(text) and (text[j].isalnum() or text[j] == '_'):
                        j += 1
                    if j > i + 1:
                        var_expr = text[i:j]
                        result.append(self.expand_variable(var_expr))
                        i = j
                        continue
            elif text[i] == '`':
                # Backtick command substitution
                j = i + 1
                while j < len(text) and text[j] != '`':
                    if text[j] == '\\' and j + 1 < len(text):
                        j += 2  # Skip escaped character
                    else:
                        j += 1
                if j < len(text) and text[j] == '`':
                    cmd_sub = text[i:j + 1]  # Include `...`
                    output = self.shell.expansion_manager.command_sub.execute(cmd_sub)
                    result.append(output)
                    i = j + 1
                    continue
            elif text[i] == '\\' and i + 1 < len(text):
                # Handle escape sequences
                next_char = text[i + 1]
                # Note: Standard C escape sequences like \n, \t are NOT processed in shell strings
                # They remain as literal \n, \t for compatibility with prompt expansion
                # Only backslash before special shell characters is processed
                if next_char == '\\':
                    result.append('\\')
                    i += 2
                    continue
                elif next_char in '"$`':
                    # In double quotes, these characters can be escaped
                    # But for $ and `, we need to check if they're actually escaping something
                    if next_char == '$':
                        # Check if this is escaping a variable expansion
                        if i + 2 < len(text) and (text[i + 2].isalnum() or text[i + 2] in '_${(@#*!?'):
                            # This is escaping a variable expansion, remove the backslash
                            result.append(next_char)
                            i += 2
                            continue
                        else:
                            # Not escaping a variable, keep the backslash (for PS1 compatibility)
                            result.append(text[i])
                            i += 1
                            continue
                    else:
                        # For " and `, always remove the backslash
                        result.append(next_char)
                        i += 2
                        continue

            result.append(text[i])
            i += 1

        return ''.join(result)

    def is_array_expansion(self, var_expr: str) -> bool:
        """Check if this is an array expansion that produces multiple words."""
        if not var_expr.startswith('$'):
            return False

        var_expr = var_expr[1:]  # Remove $

        # Check for $@ (positional parameters expansion)
        if var_expr == '@':
            return True

        # Check for ${arr[@]} syntax
        if var_expr.startswith('{') and var_expr.endswith('}'):
            var_content = var_expr[1:-1]

            # Special expansions that don't produce multiple words
            if var_content.startswith('#'):
                # ${#arr[@]} produces single word
                return False

            # ${!arr[@]} produces multiple words (array indices)
            # Handle escaped ! if present
            check_content = var_content
            if check_content.startswith('\\!'):
                check_content = check_content[1:]  # Remove the backslash

            if check_content.startswith('!') and '[' in check_content and check_content.endswith(']'):
                bracket_pos = check_content.find('[')
                index_expr = check_content[bracket_pos+1:-1]
                if index_expr == '@' or index_expr == '*':
                    return True  # This is array indices expansion
                return False  # Other ! expansions are single words

            # Check for array subscript with @
            if '[' in var_content and var_content.endswith(']'):
                bracket_pos = var_content.find('[')
                index_expr = var_content[bracket_pos+1:-1]
                return index_expr == '@'

        return False

    def expand_array_to_list(self, var_expr: str) -> list:
        """Expand an array variable to a list of words for ${arr[@]} syntax."""
        if not var_expr.startswith('$'):
            return [var_expr]

        var_expr = var_expr[1:]  # Remove $

        # Handle $@ (positional parameters)
        if var_expr == '@':
            return list(self.state.positional_params)

        # Handle ${var} syntax
        if var_expr.startswith('{') and var_expr.endswith('}'):
            var_content = var_expr[1:-1]

            # Check for array indices expansion: ${!arr[@]}
            # Handle escaped ! if present
            check_content = var_content
            if check_content.startswith('\\!'):
                check_content = check_content[1:]  # Remove the backslash

            if check_content.startswith('!') and '[' in check_content and check_content.endswith(']'):
                array_part = check_content[1:]  # Remove the !
                bracket_pos = array_part.find('[')
                array_name = array_part[:bracket_pos]
                index_expr = array_part[bracket_pos+1:-1]  # Remove [ and ]

                if index_expr == '@' or index_expr == '*':
                    # Get the array variable
                    from ..core import AssociativeArray, IndexedArray
                    var = self.state.scope_manager.get_variable_object(array_name)

                    if var and isinstance(var.value, IndexedArray):
                        # Return the indices as list of strings
                        indices = var.value.indices()
                        return [str(i) for i in indices]
                    elif var and isinstance(var.value, AssociativeArray):
                        # Return the keys as list
                        return var.value.keys()
                    elif var and var.value:
                        # Regular variable - has index 0
                        return ['0']
                    else:
                        # Not an array or no value, return empty
                        return []

            # Check for array subscript syntax: ${arr[index]}
            if '[' in var_content and var_content.endswith(']'):
                bracket_pos = var_content.find('[')
                array_name = var_content[:bracket_pos]
                index_expr = var_content[bracket_pos+1:-1]  # Remove [ and ]

                if index_expr == '@':
                    # Get the array variable
                    from ..core import AssociativeArray, IndexedArray
                    var = self.state.scope_manager.get_variable_object(array_name)

                    if var and isinstance(var.value, (IndexedArray, AssociativeArray)):
                        # Return elements as list
                        return var.value.all_elements()
                    elif var and var.value:
                        # Regular variable - return as single element list
                        return [str(var.value)]
                    else:
                        return []

        # Not an array expansion, return single element
        return [self.expand_variable('$' + var_expr)]

    def expand_to_fields(self, parameter: str, operator, operand):
        """Expand an @-subscripted parameter expansion to a list of fields.

        Returns None when the expansion has scalar semantics (anything not
        subscripted by @, plus length ``${#a[@]}``), so the caller falls
        back to the scalar path. Implements bash's quoted multi-field
        behaviour for ``"${a[@]}"``, ``"${@:2}"``, ``"${a[@]:1:2}"``,
        ``"${a[@]@Q}"``, ``"${a[@]#pat}"`` and friends.
        """
        # ${#a[@]} / ${#@}: length — scalar
        if operator == '#' and not operand:
            return None

        param = parameter
        # The parser bakes operators into the parameter text for bracketed
        # names ('a[@]:1:2', 'a[@]#pat'); positional-parameter operators
        # arrive separately ("${@:2}" → parameter '@', operator ':').
        if param != '@' and '[@]' in param and not param.endswith('[@]'):
            name_part, rest = param.split('[@]', 1)
            param = name_part + '[@]'
            operator, operand = self._parse_trailing_op(rest)
            if operator is None:
                return None

        slice_operand = operand if operator == ':' else None

        # Resolve the base fields
        if param == '@':
            base = list(self.state.positional_params)
        elif param.startswith('!') and param.endswith('[@]'):
            # ${!a[@]}: indices/keys (no further per-element operators)
            if operator is None and slice_operand is None:
                return self.expand_array_to_list('${' + param + '}')
            return None
        elif param.endswith('[@]') and not param.startswith('#'):
            base = self.expand_array_to_list('${' + param + '}')
        else:
            return None

        if slice_operand is not None:
            return self._slice_fields(param, base, slice_operand)

        if operator is None:
            return base

        # Conditional operators (bash): a non-empty base keeps its fields;
        # otherwise the default text becomes a single field.
        if operator in (':-', '-'):
            if base:
                return base
            return [self._expand_operand(operand or '')]
        if operator in (':+', '+'):
            if not base:
                return []
            return [self._expand_operand(operand or '')]
        if operator in (':=', '=', ':?', '?'):
            # Assignment/error semantics on @-subscripts: keep the fields
            # when non-empty, else fall back to the scalar path.
            return base if base else None

        # Per-element value operators (bash applies them to each element)
        array_name = '@' if param == '@' else param[:-3]
        out = []
        for value in base:
            new = self._apply_op_per_element(operator, value, operand or '', array_name)
            if new is None:
                return None  # unsupported per-element → scalar fallback
            out.append(new)
        return out

    @staticmethod
    def _parse_trailing_op(rest: str):
        """Split the operator+operand text that follows ``name[@]`` inside a
        baked parameter string ('a[@]#pat' → ('#', 'pat')).

        ``:-`` ``:=`` ``:?`` ``:+`` are checked before bare ``:`` so
        ``${a[@]:-default}`` is the conditional operator, not a slice with a
        negative offset (matching bash's disambiguation).
        """
        if not rest:
            return None, None
        two = rest[:2]
        if two in (':-', ':=', ':?', ':+'):
            return two, rest[2:]
        if rest[0] == ':':
            return ':', rest[1:]
        if two in ('##', '%%', '//', '/#', '/%', '^^', ',,'):
            return two, rest[2:]
        if rest[0] in '#%/^,':
            return rest[0], rest[1:]
        if rest[0] == '@' and len(rest) == 2:
            return rest, ''
        return None, None

    def _slice_fields(self, param, base, slice_operand):
        """Slice positional params or array elements: ${@:o:l}, ${a[@]:o:l}."""
        from ..arithmetic import ArithmeticError, evaluate_arithmetic
        if ':' in slice_operand:
            offset_str, length_str = slice_operand.split(':', 1)
        else:
            offset_str, length_str = slice_operand, None
        try:
            offset = evaluate_arithmetic(offset_str, self.shell) if offset_str.strip() else 0
            length = (evaluate_arithmetic(length_str, self.shell)
                      if length_str is not None and length_str.strip() else None)
        except (ValueError, ArithmeticError):
            print(f"psh: ${{{param}:{slice_operand}}}: invalid offset or length",
                  file=sys.stderr)
            return []

        if param == '@':
            # bash: index 0 is $0; the parameters start at offset 1, and a
            # negative offset counts back from one past the last parameter.
            seq = [self.state.script_name] + base
            start = len(seq) + offset if offset < 0 else offset
            sliced = seq[max(0, start):]
        else:
            # bash slices indexed arrays by INDEX, not by element position
            # (matters for sparse arrays).
            from ..core import IndexedArray
            name = param[:-3]
            var = self.state.scope_manager.get_variable_object(name)
            if var is not None and isinstance(var.value, IndexedArray):
                indices = var.value.indices()
                if offset < 0:
                    offset = (max(indices) + 1 + offset) if indices else 0
                sliced = [var.value.get(i) for i in indices if i >= offset]
            else:
                start = len(base) + offset if offset < 0 else offset
                sliced = base[max(0, start):]

        if length is not None:
            if length < 0:
                print(f"psh: {param}: substring expression < 0", file=sys.stderr)
                self.state.last_exit_code = 1
                return []
            sliced = sliced[:length]
        return sliced

    def _apply_op_per_element(self, operator, value, operand, var_name):
        """Apply one value-level parameter-expansion operator to a single
        element. Returns None for operators without per-element semantics.

        Mirrors the scalar dispatch in expand_parameter_direct so quoted
        array expansion ("${a[@]#pat}") behaves like bash's per-element
        application.
        """
        pe = self.param_expansion
        if operator == '#':
            return pe.remove_shortest_prefix(value, self._expand_pattern_operand(operand))
        if operator == '##':
            return pe.remove_longest_prefix(value, self._expand_pattern_operand(operand))
        if operator == '%':
            return pe.remove_shortest_suffix(value, self._expand_pattern_operand(operand))
        if operator == '%%':
            return pe.remove_longest_suffix(value, self._expand_pattern_operand(operand))
        if operator in ('/', '//', '/#', '/%'):
            return self._substitute(operator, value, operand)
        if operator == '^':
            return pe.uppercase_first(value, self._expand_pattern_operand(operand) or '?')
        if operator == '^^':
            return pe.uppercase_all(value, self._expand_pattern_operand(operand) or '?')
        if operator == ',':
            return pe.lowercase_first(value, self._expand_pattern_operand(operand) or '?')
        if operator == ',,':
            return pe.lowercase_all(value, self._expand_pattern_operand(operand) or '?')
        if len(operator) == 2 and operator[0] == '@':
            if operator[1] == 'A':
                # @A produces one whole-array assignment statement, not a
                # per-element transform — scalar path handles it.
                return None
            return self._apply_transform(operator[1], value, var_name)
        return None

    def _split_pattern_replacement(self, operand: str):
        """Split a substitution operand into (pattern, replacement).

        The separator is the first '/' that is not backslash-escaped,
        not inside quotes, and not inside a $-construct (so division in
        ``${x/$((4/2))/y}`` and nested expansions don't split early).
        With no separator the replacement is empty (deletion, bash).
        """
        i = 0
        n = len(operand)
        while i < n:
            c = operand[i]
            if c == '\\' and i + 1 < n:
                i += 2
            elif c == "'":
                end = operand.find("'", i + 1)
                i = n if end == -1 else end + 1
            elif c == '"':
                i = self._skip_double_quote(operand, i + 1)
            elif c == '$' and i + 1 < n and operand[i + 1] in '{(':
                i = self._skip_dollar_construct(operand, i)
            elif c == '/':
                return operand[:i], operand[i + 1:]
            else:
                i += 1
        return operand, ''

    @staticmethod
    def _skip_double_quote(text: str, i: int) -> int:
        """Index just past the '"' closing a double quote opened before i."""
        n = len(text)
        while i < n:
            if text[i] == '\\' and i + 1 < n:
                i += 2
            elif text[i] == '"':
                return i + 1
            else:
                i += 1
        return n

    @staticmethod
    def _skip_dollar_construct(text: str, i: int) -> int:
        """Index just past the ${...}, $(...) or $((...)) at text[i]."""
        from ..lexer.pure_helpers import (
            find_balanced_double_parentheses,
            find_balanced_parentheses,
            find_closing_delimiter,
        )
        if text.startswith('$((', i):
            end, found = find_balanced_double_parentheses(
                text, i + 3, track_quotes=True)
            if found:
                return end
        if text.startswith('$(', i):
            end, found = find_balanced_parentheses(text, i + 2, track_quotes=True)
            return end if found else i + 2
        if text.startswith('${', i):
            end, found = find_closing_delimiter(
                text, i + 2, '{', '}', track_quotes=True, track_escapes=True)
            return end if found else i + 2
        return i + 1

    # Characters with glob (and extglob) meaning in pattern operands.
    _GLOB_SPECIALS = set('\\*?[]()|@!+')

    @classmethod
    def _glob_escape(cls, text: str) -> str:
        """Backslash-escape glob syntax so the text matches literally."""
        return ''.join('\\' + c if c in cls._GLOB_SPECIALS else c
                       for c in text)

    def _expand_one_dollar(self, text: str, i: int):
        """Expand the single $-construct or `...` at text[i].

        Returns (expanded_text, index_past_construct); a '$' that starts
        nothing expandable stays literal.
        """
        from ..lexer.pure_helpers import (
            find_balanced_double_parentheses,
            find_balanced_parentheses,
            find_closing_delimiter,
        )
        n = len(text)
        if text[i] == '`':
            j = i + 1
            while j < n and text[j] != '`':
                j += 2 if text[j] == '\\' and j + 1 < n else 1
            if j < n:
                output = self.shell.expansion_manager.command_sub.execute(text[i:j + 1])
                return output, j + 1
            return '`', i + 1
        if text.startswith('$((', i):
            end, found = find_balanced_double_parentheses(
                text, i + 3, track_quotes=True)
            if found:
                result = self.shell.expansion_manager.execute_arithmetic_expansion(text[i:end])
                return str(result), end
        if text.startswith('$(', i):
            end, found = find_balanced_parentheses(text, i + 2, track_quotes=True)
            if found:
                return self.shell.expansion_manager.command_sub.execute(text[i:end]), end
            return '$', i + 1
        if text.startswith('${', i):
            end, found = find_closing_delimiter(
                text, i + 2, '{', '}', track_quotes=True, track_escapes=True)
            if found:
                return self.expand_variable(text[i:end]), end
            return '$', i + 1
        j = i + 1
        if j < n and text[j] in '?$!#@*-0123456789':
            return self.expand_variable(text[i:j + 1]), j + 1
        while j < n and (text[j].isalnum() or text[j] == '_'):
            j += 1
        if j > i + 1:
            return self.expand_variable(text[i:j]), j
        return '$', i + 1

    def _tilde_prefix(self, operand: str):
        """Expand a leading unquoted ~ or ~user prefix of an operand.

        Returns (expanded_prefix, chars_consumed); (``''``, 0) when the
        prefix isn't a plain tilde word.
        """
        end = operand.find('/')
        prefix = operand if end == -1 else operand[:end]
        if any(ch in prefix for ch in '\'"\\$`&'):
            return '', 0
        expanded = self.shell.expansion_manager.tilde_expander.expand(prefix)
        if expanded == prefix:
            return '', 0
        return expanded, len(prefix)

    def _expand_pattern_operand(self, operand: str) -> str:
        """Expand a pattern operand (``${x#OP}``, ``${x/OP/...}``, case mods).

        Variables, command substitution and arithmetic are expanded and one
        level of quoting is removed (bash). Quoted text — and the results of
        expansions inside double quotes — matches literally, while unquoted
        text and unquoted-expansion results keep their glob power.
        """
        out = []
        i = 0
        n = len(operand)
        if n and operand[0] == '~':
            prefix, skip = self._tilde_prefix(operand)
            if skip:
                out.append(self._glob_escape(prefix))
                i = skip
        while i < n:
            c = operand[i]
            if c == "'":
                end = operand.find("'", i + 1)
                seg = operand[i + 1:] if end == -1 else operand[i + 1:end]
                i = n if end == -1 else end + 1
                out.append(self._glob_escape(seg))
            elif c == '"':
                end = self._skip_double_quote(operand, i + 1)
                closed = end > i + 1 and operand[end - 1] == '"'
                seg = operand[i + 1:end - 1] if closed else operand[i + 1:end]
                out.append(self._glob_escape(self.expand_string_variables(seg)))
                i = end
            elif c == '\\' and i + 1 < n:
                out.append(operand[i:i + 2])
                i += 2
            elif c in '$`':
                expanded, i = self._expand_one_dollar(operand, i)
                out.append(expanded)
            else:
                out.append(c)
                i += 1
        return ''.join(out)

    def _expand_replacement_operand(self, operand: str) -> list:
        """Prepare a substitution replacement as a template list.

        Entries are literal strings or PATSUB_MATCH (the matched text).
        Bash 5.2 patsub_replacement: an unquoted & — even one produced by
        an expansion — stands for the match; ``\\&`` and quoted & are
        literal; an unquoted backslash escapes the next character (and is
        removed); backslashes inside expansion results stay literal.
        """
        from .parameter_expansion import PATSUB_MATCH
        parts = []
        buf = []

        def flush():
            if buf:
                parts.append(''.join(buf))
                buf.clear()

        def add_active(text):
            pieces = text.split('&')
            for k, piece in enumerate(pieces):
                if k:
                    flush()
                    parts.append(PATSUB_MATCH)
                buf.append(piece)

        i = 0
        n = len(operand)
        if n and operand[0] == '~':
            prefix, skip = self._tilde_prefix(operand)
            if skip:
                buf.append(prefix)
                i = skip
        while i < n:
            c = operand[i]
            if c == "'":
                end = operand.find("'", i + 1)
                buf.append(operand[i + 1:] if end == -1 else operand[i + 1:end])
                i = n if end == -1 else end + 1
            elif c == '"':
                end = self._skip_double_quote(operand, i + 1)
                closed = end > i + 1 and operand[end - 1] == '"'
                seg = operand[i + 1:end - 1] if closed else operand[i + 1:end]
                buf.append(self.expand_string_variables(seg))
                i = end
            elif c == '\\' and i + 1 < n:
                buf.append(operand[i + 1])
                i += 2
            elif c == '&':
                flush()
                parts.append(PATSUB_MATCH)
                i += 1
            elif c in '$`':
                expanded, i = self._expand_one_dollar(operand, i)
                add_active(expanded)
            else:
                buf.append(c)
                i += 1
        flush()
        return parts

    def _substitute(self, operator: str, value: str, operand: str) -> str:
        """Apply a ${x/pat/repl} family operator to one value."""
        raw_pattern, raw_replacement = self._split_pattern_replacement(operand)
        pattern = self._expand_pattern_operand(raw_pattern)
        if not pattern:
            # ${x//} and ${x///y}: an empty pattern replaces nothing (bash).
            return value
        replacement = self._expand_replacement_operand(raw_replacement)
        fn = {'/': self.param_expansion.substitute_first,
              '//': self.param_expansion.substitute_all,
              '/#': self.param_expansion.substitute_prefix,
              '/%': self.param_expansion.substitute_suffix}[operator]
        return fn(value, pattern, replacement)
