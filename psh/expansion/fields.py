"""Field-producing expansion: ${arr[@]...} and $@/$* with operators.

Expansions that yield multiple fields (one per element) rather than a
single string, including per-element operator application and field
slicing. Mixed into VariableExpander (variable.py).
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._protocols import VariableExpanderProtocol
    _Base = VariableExpanderProtocol
else:
    _Base = object


class FieldExpansionMixin(_Base):
    """Multi-field expansion of array/positional parameters."""

    def expand_to_fields(self, parameter: str, operator, operand):
        """Expand an @-subscripted parameter expansion to a list of fields.

        Returns None when the expansion has scalar semantics (anything not
        subscripted by @, plus length ``${#a[@]}``), so the caller falls
        back to the scalar path. Implements bash's quoted multi-field
        behaviour for ``"${a[@]}"``, ``"${@:2}"``, ``"${a[@]:1:2}"``,
        ``"${a[@]@Q}"``, ``"${a[@]#pat}"`` and friends.
        """
        # ${#a[@]} / ${#@}: length — scalar. operand is None only for the
        # length form; ${a[@]#} (empty removal pattern) has operand '' and
        # must produce per-element fields below.
        if operator == '#' and operand is None:
            return None

        param = parameter

        # ${!prefix@}: one field per matching variable name (like "$@").
        # The *-form (!*) keeps scalar IFS-joined semantics, so it is NOT
        # handled here and falls through to the scalar path.
        if operator == '!@':
            return self.param_expansion.match_variable_names(param)

        # ${!a[@]}: indices/keys, one field per key (no further operators).
        if operator == '!' and param.endswith('[@]'):
            return self.expand_array_to_list('${!' + param + '}')

        # ${!ref}: plain indirection. If ref is a plain variable whose VALUE
        # names an [@]-subscripted array (ref="a[@]"), the indirection produces
        # that array's fields ("${!ref}" -> one field per element), like bash.
        # Everything else (scalar/[*] target, positional/special source, an
        # invalid name like ${!1abc}, an unset ref) returns None so the scalar
        # path handles it AND reports any error exactly as before — we must not
        # call the error-raising resolver here (it would mis-report and could
        # double-print). (param can't end in [@] here — keys form returned above.)
        if operator == '!':
            if param.isidentifier():
                target = self.state.get_variable(param)
                if (target is not None and target.endswith('[@]')
                        and not target.startswith(('!', '#'))):
                    return self.expand_array_to_list('${' + target + '}')
            return None

        slice_operand = operand if operator == ':' else None

        # Resolve the base fields
        if param == '@':
            base = list(self.state.positional_params)
        elif param.endswith('[@]') and not param.startswith(('!', '#')):
            base = self.expand_array_to_list('${' + param + '}')
        else:
            return None

        if slice_operand is not None:
            return self._slice_fields(param, base, slice_operand)

        if operator is None:
            return base

        # Conditional/default/assign/error operators. bash tests the JOINED
        # view for null (colon) or set-ness (non-colon), NOT the field count
        # — see OperatorOpsMixin._view_conditional. The @-subscript views
        # reaching here (param '@' and 'name[@]') join with a space; :=/= and
        # :?/? raise bash's error when null/unset.
        if operator in (':-', '-', ':+', '+', ':=', '=', ':?', '?'):
            if param == '@':
                subject, assign_error = '@', '$@: cannot assign in this way'
            else:
                name = self._resolve_array_name(param[:-3])
                subject = f'{name}[@]'
                assign_error = f'{subject}: bad array subscript'
            return self._view_conditional(operator, base, ' ', operand,
                                          qmark_subject=subject,
                                          assign_error=assign_error)

        # Whole-array key/value transforms (bash):
        #   @K -> ONE field: key "value" key "value" ... (values @Q-quoted)
        #   @k -> SEPARATE fields: key, value, key, value, ... (unquoted)
        if operator in ('@K', '@k') and param != '@':
            name = self._resolve_array_name(param[:-3])
            var = self.state.scope_manager.get_variable_object(name)
            if operator == '@K':
                return [self._array_keyvalue_form('K', var)]
            return self._array_keyvalue_fields(var)

        # Per-element value operators (bash applies them to each element)
        array_name = '@' if param == '@' else self._resolve_array_name(param[:-3])
        out = []
        for value in base:
            new = self._apply_op_per_element(operator, value, operand or '', array_name)
            if new is None:
                return None  # unsupported per-element → scalar fallback
            out.append(new)
        return out

    def _slice_fields(self, param, base, slice_operand):
        """Slice positional params or array elements: ${@:o:l}, ${a[@]:o:l}.

        Thin dispatcher over the canonical slice helpers in operators.py
        (_parse_slice_operand / _slice_elements / _slice_scalar_subscript),
        which document the shared bash semantics.
        """
        offset, length = self._parse_slice_operand(slice_operand, param)

        if param == '@':
            # bash: index 0 is $0; the parameters start at offset 1, and a
            # negative offset counts back from one past the last parameter.
            return self._slice_elements(
                self._positional_slice_elements(), offset, length)

        from ..core import AssociativeArray, IndexedArray
        name = self._resolve_array_name(param[:-3])
        var = self.state.scope_manager.get_variable_object(name)
        if var is not None and isinstance(var.value, IndexedArray):
            # bash slices indexed arrays by INDEX, not by element position
            # (matters for sparse arrays).
            return self._slice_elements(var.value.all_elements(), offset,
                                        length, indices=var.value.indices())
        if (var is not None and var.value is not None
                and not isinstance(var.value, AssociativeArray)):
            # Scalar with an [@] subscript: bash substring semantics
            # (a set-but-empty scalar still yields one field for ":0").
            return self._slice_scalar_subscript(str(var.value), offset, length)
        return self._slice_elements(base, offset, length)
