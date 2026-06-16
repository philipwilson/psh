"""Array expansion operations for VariableExpander.

Subscript/index/slice/length access on indexed and associative arrays,
plus array-aware assignment. Mixed into VariableExpander (variable.py);
methods use ``self.shell`` / ``self.state`` from the host class.
"""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ._protocols import VariableExpanderProtocol
    _Base = VariableExpanderProtocol
else:
    _Base = object


class ArrayOpsMixin(_Base):
    """Array subscript, slice, length, and assignment operations."""

    def _resolve_array_name(self, array_name: str) -> str:
        """Resolve the array-name part of a subscript through namerefs.

        ``declare -n r=arr; ${r[1]}`` must access ``arr[1]``: the array-read
        paths split ``r[1]`` into name ``r`` + subscript ``1``, but the name
        ``r`` is a nameref and must be followed to its target ``arr`` BEFORE
        the array lookup (``get_variable_object`` does not follow namerefs).
        This is the single nameref-aware resolution point every array-read
        site funnels through.

        A nameref whose target is itself an element reference (``declare -n
        r=arr[1]``) resolves to that subscripted target name (``arr[1]``); a
        further array lookup on it finds no variable, yielding empty —
        matching bash, where ``${r[@]}`` of an element nameref is empty. A
        cyclic chain resolves to the original name (read as unset).
        """
        from ..core import NamerefCycleError
        try:
            return self.state.scope_manager.resolve_nameref_name(array_name)
        except NamerefCycleError as e:
            self.state.scope_manager.warn_nameref_cycle(e.name)
            return array_name

    def _eval_array_index(self, index_expr: str) -> int:
        """Expand and arithmetically evaluate an indexed-array subscript.

        This is THE canonical subscript evaluation (every indexed-array
        access funnels through it): variables expand first, then the
        result is evaluated as arithmetic; an unevaluable subscript
        counts as 0, matching bash (``a[junk]`` addresses ``a[0]``).
        """
        from .arithmetic import ArithmeticError, evaluate_arithmetic
        expanded = self.expand_array_index(index_expr)
        try:
            return evaluate_arithmetic(expanded, self.shell)
        except ArithmeticError:
            return 0

    def _expand_array_indices(self, subscripted: str) -> str:
        """Handle ${!arr[@]} and ${!arr[*]} — *subscripted* is ``arr[@]``.

        Joined with spaces for both @ and * (historical behavior).
        """
        from ..core import AssociativeArray, IndexedArray

        bracket_pos = subscripted.find('[')
        array_name = self._resolve_array_name(subscripted[:bracket_pos])

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

    def _expand_array_subscript(self, var_content: str,
                                check_nounset: bool = False) -> str:
        """Handle ${arr[index]}, ${arr[@]}, ${arr[*]}.

        Returns the result string, or None if this is not a subscript
        expansion (so the caller can fall through).

        ``check_nounset`` is True only for the BARE ``${arr[i]}`` form (so an
        absent element errors under ``set -u``); the operator path
        (``${arr[i]:-d}``, ``${#arr[i]}``) reuses this to fetch the base value
        and must stay exempt, so it leaves it False.
        """
        from ..core import AssociativeArray, IndexedArray

        bracket_pos = var_content.find('[')
        array_name = self._resolve_array_name(var_content[:bracket_pos])
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
            idx = self._eval_array_index(index_expr)
            if var.value.negative_out_of_range(idx):
                # bash warns on an out-of-range negative READ subscript and
                # expands to empty (the exit status is unaffected).
                print(f"psh: {array_name}: bad array subscript",
                      file=self.state.stderr)
                return ''
            result = var.value.get(idx)
            if result is None:
                self._check_nounset_element(array_name, index_expr, check_nounset)
                return ''
            return result
        elif var and isinstance(var.value, AssociativeArray):
            expanded_key = self.expand_assoc_key(index_expr)
            result = var.value.get(expanded_key)
            if result is None:
                self._check_nounset_element(array_name, index_expr, check_nounset)
                return ''
            return result
        elif var and var.value:
            expanded_index = self.expand_array_index(index_expr)
            try:
                index = int(expanded_index)
                if index == 0:
                    return str(var.value)
            except ValueError:
                return ''
            self._check_nounset_element(array_name, index_expr, check_nounset)
            return ''
        # No such array variable at all (unset / tombstone).
        self._check_nounset_element(array_name, index_expr, check_nounset)
        return ''

    def _check_nounset_element(self, array_name: str, index_expr: str,
                               check_nounset: bool) -> None:
        """Under ``set -u``, reading an absent array element is an error.

        Mirrors the scalar nounset check for the bare ``${arr[i]}`` /
        ``${arr[key]}`` forms only (``check_nounset`` is False for the operator
        path, which is exempt; ``${arr[@]}``/``${arr[*]}`` returned earlier).
        bash's message names the full subscript, e.g. ``a[5]: unbound variable``.
        """
        if check_nounset and self.state.options.get('nounset', False):
            from ..core import UnboundVariableError
            raise UnboundVariableError(
                f"{array_name}[{index_expr}]: unbound variable")

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
            array_name = self._resolve_array_name(var_name[:bracket_pos])
            index_expr = var_name[bracket_pos + 1:-1]

            from ..core import AssociativeArray, IndexedArray
            var = self.state.scope_manager.get_variable_object(array_name)

            # A readonly array forbids element writes too (bash: ``a=(1 2);
            # readonly a; a[0]=X`` errors). The gate is the array variable,
            # not the subscript, so report the array name.
            if var is not None and var.is_readonly:
                from ..core import ReadonlyVariableError
                raise ReadonlyVariableError(array_name)

            if var and isinstance(var.value, IndexedArray):
                var.value.set(self._eval_array_index(index_expr), value)
            elif var and isinstance(var.value, AssociativeArray):
                expanded_key = self.expand_assoc_key(index_expr)
                var.value.set(expanded_key, value)
            else:
                # Array doesn't exist yet; create an indexed array
                arr = IndexedArray()
                arr.set(self._eval_array_index(index_expr), value)
                from ..core import VarAttributes
                self.state.scope_manager.set_variable(
                    array_name, arr,
                    attributes=VarAttributes.ARRAY,
                )
        else:
            self.state.set_variable(var_name, value)

    @staticmethod
    def _at_a_quote(s: Optional[str]) -> str:
        """Double-quote a value the way bash's @A/@K declare-form does
        (escape backslash, double-quote, ``$`` and backtick)."""
        s = (s or '')
        s = (s.replace('\\', '\\\\').replace('"', '\\"')
             .replace('$', '\\$').replace('`', '\\`'))
        return f'"{s}"'

    def _array_assignment_form(self, array_name: str, var) -> str:
        """Build the ${arr[@]@A} declare statement (values double-quoted)."""
        from ..core import AssociativeArray, IndexedArray
        flags = self._var_attr_flags(array_name)
        dq = self._at_a_quote

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

    def _array_keyvalue_pairs(self, var):
        """Yield (key, value) pairs for a variable's @K/@k transform.

        Indexed arrays use their (string) indices as keys; associative
        arrays use their keys; a scalar yields a single ('0', value) pair
        (bash treats ${scalar@K} like a one-element array indexed at 0).
        """
        from ..core import AssociativeArray, IndexedArray
        if var and isinstance(var.value, AssociativeArray):
            return list(var.value.items())
        if var and isinstance(var.value, IndexedArray):
            return [(str(i), var.value.get(i) or '') for i in var.value.indices()]
        if var and var.value is not None:
            return [('0', str(var.value))]
        return []

    def _array_keyvalue_form(self, op: str, var) -> str:
        """Build the ${arr[@]@K} string: key "value" key "value" ...

        Values are double-quoted with bash's @A/@K declare-form escaping.
        Associative arrays get a trailing space (matching bash formatting).
        """
        from ..core import AssociativeArray
        pairs = self._array_keyvalue_pairs(var)
        body = ' '.join(f'{k} {self._at_a_quote(v)}' for k, v in pairs)
        if var and isinstance(var.value, AssociativeArray) and body:
            body += ' '
        return body

    def _array_keyvalue_fields(self, var):
        """Build the ${arr[@]@k} field list: [key, value, key, value, ...].

        Each key and each (unquoted) value is a SEPARATE field (bash).
        """
        fields = []
        for k, v in self._array_keyvalue_pairs(var):
            fields.append(k)
            fields.append(v)
        return fields

    def expand_assoc_key(self, index_expr: str) -> str:
        """Expand an associative-array subscript and apply quote removal.

        bash applies quote removal to assoc subscripts: ``${h["k 1"]}`` and
        ``${h['k 1']}`` address the key ``k 1``. This mirrors the assignment
        side (executor/array.py), which strips one fully-wrapping quote pair
        after expansion — keeping lookups symmetric with assignments.
        """
        expanded = self.expand_array_index(index_expr)
        if (len(expanded) >= 2 and expanded[0] == expanded[-1]
                and expanded[0] in ('"', "'")):
            return expanded[1:-1]
        return expanded

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
                array_name = self._resolve_array_name(array_part[:bracket_pos])
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
                array_name = self._resolve_array_name(var_content[:bracket_pos])
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
