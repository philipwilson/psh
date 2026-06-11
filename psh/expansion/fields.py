"""Field-producing expansion: ${arr[@]...} and $@/$* with operators.

Expansions that yield multiple fields (one per element) rather than a
single string, including per-element operator application and field
slicing. Mixed into VariableExpander (variable.py).
"""

import sys


class FieldExpansionMixin:
    """Multi-field expansion of array/positional parameters."""

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
        from .arithmetic import ArithmeticError, evaluate_arithmetic
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
