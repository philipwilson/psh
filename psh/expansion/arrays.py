"""Array expansion operations for VariableExpander.

Subscript/index/slice/length access on indexed and associative arrays,
plus array-aware assignment. Mixed into VariableExpander (variable.py);
methods use ``self.shell`` / ``self.state`` from the host class.
"""


class ArrayOpsMixin:
    """Array subscript, slice, length, and assignment operations."""

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
            element = var.value.get(self._eval_array_index(index_expr))
            return str(len(element)) if element else '0'
        elif var and isinstance(var.value, AssociativeArray):
            expanded_key = self.expand_assoc_key(index_expr)
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
        what = f"{array_name}[{index_expr}]"
        sep = ' ' if index_expr == '@' else self._ifs_star_separator()

        if var and isinstance(var.value, IndexedArray):
            # bash slices indexed arrays by INDEX (matters for sparse arrays)
            sliced = self._slice_sequence(var.value.all_elements(), slice_part[1:],
                                          what=what, indices=var.value.indices())
            return sep.join(sliced)
        elif var and var.value:
            # Scalar with an [@]/[*] subscript: bash substring semantics.
            offset, length = self._parse_slice_operand(slice_part[1:], what)
            return sep.join(self._slice_scalar_subscript(str(var.value),
                                                         offset, length))
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
            result = var.value.get(self._eval_array_index(index_expr))
            return result if result is not None else ''
        elif var and isinstance(var.value, AssociativeArray):
            expanded_key = self.expand_assoc_key(index_expr)
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
