"""Variable expansion implementation.

``VariableExpander`` is the facade for all ``$var`` / ``${...}``
expansion. The implementation is decomposed by concern:

- arrays.py    — subscripts, slices, lengths, array assignment
- operators.py — ${var<op>operand} operator application
- operands.py  — pattern/replacement operand mini-expansion
- fields.py    — multi-field expansion (${arr[@]}, $@ with operators)

This module keeps the entry points (string scanning, name resolution,
special variables, ${!name} indirection) and dispatch.
"""
import sys
from typing import TYPE_CHECKING

from .arrays import ArrayOpsMixin
from .fields import FieldExpansionMixin
from .operands import OperandOpsMixin
from .operators import OperatorOpsMixin
from .parameter_expansion import ParameterExpansion

if TYPE_CHECKING:
    from ..shell import Shell


class VariableExpander(ArrayOpsMixin, OperatorOpsMixin, OperandOpsMixin,
                       FieldExpansionMixin):
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

    def _expand_special_variable(self, var_name: str) -> str:
        """Expand special variables ($?, $$, $!, etc.) and regular variables."""
        if var_name == '?':
            return str(self.state.last_exit_code)
        elif var_name == '$':
            return str(self.state.shell_pid)
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
        # then flows into the array branch below. A cyclic chain warns and
        # reads as unset (bash).
        from ..core import NamerefCycleError
        try:
            var_name = self.state.scope_manager.resolve_nameref_name(var_name)
        except NamerefCycleError as e:
            self.state.scope_manager.warn_nameref_cycle(e.name)
            return ''
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
                result = var.value.get(self._eval_array_index(index_expr))
                return result if result is not None else ''
            elif var and isinstance(var.value, AssociativeArray):
                expanded_key = self.expand_array_index(index_expr)
                result = var.value.get(expanded_key)
                return result if result is not None else ''
            else:
                return ''
        else:
            return self.state.get_variable(var_name, '')

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

        # ${!name<op>...}: resolve the indirection first, then apply the
        # operator to the target parameter (bash). The ${!arr[@]} keys form
        # never reaches here (handled before operator parsing).
        if (var_name.startswith('!') and len(var_name) > 1
                and not var_name.endswith(('[@]', '[*]'))):
            var_name = self._resolve_indirect_target(var_name[1:])

        # Follow a nameref to its target name so ${ref...} operators apply to
        # the target (including an array-element target like arr[1]). A
        # cyclic chain warns and reads as unset (bash).
        from ..core import NamerefCycleError
        try:
            var_name = self.state.scope_manager.resolve_nameref_name(var_name)
        except NamerefCycleError as e:
            self.state.scope_manager.warn_nameref_cycle(e.name)
            var_name = ''

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
            if int(var_name) == 0:
                # $0 is the script/shell name, not a positional parameter.
                value = self.state.get_special_variable('0')
            else:
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
                value = var.value.get(self._eval_array_index(index_expr)) or ''
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
        another parameter — a variable, array element (``a[1]``, ``a[@]``),
        positional or special parameter — and yield that parameter's value.
        """
        var = self.state.scope_manager.get_variable_object(name)  # raw, no deref
        if var is not None and var.is_nameref:
            return str(var.value) if var.value else ''
        target = self._resolve_indirect_target(name)
        if not target:
            return ''
        return self.expand_variable('${' + target + '}')

    def _resolve_indirect_target(self, source: str) -> str:
        """Resolve the target parameter name for ``${!source}``.

        Raises ExpansionError with bash's diagnostics: an unset source is
        an "invalid indirect expansion" and a target that isn't a valid
        parameter name is an "invalid variable name" (both exit status 1).
        """
        from ..core import ExpansionError

        if source.isdigit():
            idx = int(source) - 1
            params = self.state.positional_params
            if not (0 <= idx < len(params)):
                # An out-of-range positional source is just an unset
                # parameter (bash), not an indirection error.
                return ''
            target = params[idx]
        elif len(source) == 1 and source in '#?$!-0':
            target = self.state.get_special_variable(source) or None
        elif '[' in source and source.endswith(']'):
            target = self.expand_variable('${' + source + '}') or None
        else:
            var = self.state.scope_manager.get_variable_object(source)
            target = None if var is None else var.as_string()

        if target is None:
            print(f"psh: {source}: invalid indirect expansion", file=sys.stderr)
            self.state.last_exit_code = 1
            raise ExpansionError(f"{source}: invalid indirect expansion",
                                 exit_code=1)
        if not self._valid_indirect_target(target):
            print(f"psh: {target}: invalid variable name", file=sys.stderr)
            self.state.last_exit_code = 1
            raise ExpansionError(f"{target}: invalid variable name",
                                 exit_code=1)
        return target

    @staticmethod
    def _valid_indirect_target(target: str) -> bool:
        """Whether text can serve as an indirection target parameter name."""
        if not target:
            return False
        if target.isdigit():
            return True
        if len(target) == 1 and target in '@*#?$!-':
            return True
        name = target
        if '[' in target:
            if not target.endswith(']'):
                return False
            name = target[:target.find('[')]
        if not name or not (name[0].isalpha() or name[0] == '_'):
            return False
        return all(c.isalnum() or c == '_' for c in name)

    def expand_string_variables(self, text: str) -> str:
        """Expand variables, command substitution, and arithmetic in a string
        (here strings/documents, double-quoted content, redirect targets).

        The per-construct work is delegated to ``_expand_one_dollar`` —
        the shared $-scanner also used for operator operands — so the
        recognized constructs can't drift between contexts. This wrapper
        adds only the double-quote escape rules (``\\\\``, ``\\"``,
        ``\\$``, ``\\```).
        """
        result = []
        i = 0
        n = len(text)
        while i < n:
            if (text[i] == '$' and i + 1 < n) or text[i] == '`':
                expanded, i = self._expand_one_dollar(text, i)
                result.append(expanded)
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
