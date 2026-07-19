"""Array expansion operations for VariableExpander.

Subscript/index/slice/length access on indexed and associative arrays,
plus array-aware assignment. Mixed into VariableExpander (variable.py);
methods use ``self.shell`` / ``self.state`` from the host class.
"""
from typing import TYPE_CHECKING, Optional, Tuple

from ..core import AssociativeArray, IndexedArray, NamerefCycleError, UnboundVariableError
from ..utils.escapes import format_assoc_key

if TYPE_CHECKING:
    from ._protocols import VariableExpanderProtocol
    _Base = VariableExpanderProtocol
else:
    _Base = object


class ArrayOpsMixin(_Base):
    """Array subscript, slice, length, and assignment operations."""

    @staticmethod
    def split_subscript(name: str) -> Optional[Tuple[str, str]]:
        """Split ``base[subscript]`` into ``(base, subscript)``, or None.

        THE one home for the ``NAME[...]`` shape rule ("``[`` present AND the
        string ends with ``]``"): every array-read/write site that needs to
        separate an array name from its subscript funnels through here instead
        of re-deriving ``find('[')`` + slicing. Returns the RAW base name
        (nameref resolution is a separate step via ``_resolve_array_name``) and
        the raw subscript text (``@``/``*`` or an arithmetic/key expression).
        A non-subscripted name (or one not ending in ``]``) returns None; an
        empty base (``[i]``) returns ``('', 'i')`` — callers that reject an
        empty base test ``base`` truthiness.

        The parser's own subscript scanning (param_parser.py) stays separate:
        it is the grammar producer, not a read-time consumer.
        """
        if '[' in name and name.endswith(']'):
            bracket = name.find('[')
            return name[:bracket], name[bracket + 1:-1]
        return None

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
        try:
            return self.state.scope_manager.resolve_nameref_name(array_name)
        except NamerefCycleError as e:
            self.state.scope_manager.warn_nameref_cycle(e.name)
            return array_name

    def _eval_array_index(self, index_expr: str) -> int:
        """Evaluate an indexed-array subscript to an int (thin adapter).

        Delegates to the ONE subscript authority
        (``ExpansionManager.subscript.indexed_index`` — campaign W2), which
        expands then arithmetic-evaluates: ``a[i]`` with ``i=3`` addresses
        ``a[3]`` (bare names are variable references in arithmetic), while a
        subscript that fails to EVALUATE (``a[08]``, ``a[1//]``) is a fatal
        expansion error aborting the whole command (bash), not a silent 0.
        """
        return self.shell.expansion_manager.subscript.indexed_index(index_expr)

    def _expand_array_indices(self, subscripted: str) -> str:
        """Handle ${!arr[@]} and ${!arr[*]} — *subscripted* is ``arr[@]``.

        Joined with spaces for both @ and * (historical behavior).
        """

        parts = self.split_subscript(subscripted)
        assert parts is not None  # caller passes a NAME[...] form
        array_name = self._resolve_array_name(parts[0])

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

        Always returns a result string (empty for an absent element).

        ``check_nounset`` is True only for the BARE ``${arr[i]}`` form (so an
        absent element errors under ``set -u``); the operator path
        (``${arr[i]:-d}``, ``${#arr[i]}``) reuses this to fetch the base value
        and must stay exempt, so it leaves it False.
        """

        parts = self.split_subscript(var_content)
        assert parts is not None  # caller passes a NAME[...] form
        array_name = self._resolve_array_name(parts[0])
        index_expr = parts[1]

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
            expanded_key = self.shell.expansion_manager.subscript.associative_key(index_expr)
            result = var.value.get(expanded_key)
            if result is None:
                self._check_nounset_element(array_name, index_expr, check_nounset)
                return ''
            return result
        elif var and var.value:
            # Scalar: the subscript is ARITHMETIC (bash), so index 0 addresses
            # the value and any other index is unset. Evaluate — and thereby
            # VALIDATE — it: ${x[1-1]} is $x (index 0), while ${x[1//]} is a
            # fatal subscript error that discards the line, not a silent empty.
            idx = self._eval_array_index(index_expr)
            if idx == 0:
                return str(var.value)
            self._check_nounset_element(array_name, index_expr, check_nounset)
            return ''
        # No such array variable at all (unset / tombstone). bash still
        # arithmetic-evaluates the subscript here (an undeclared name is
        # treated as indexed): a bad subscript (${a[1//]}, ${a[08]}) is a
        # fatal expansion error that discards the line, not a silent empty.
        # (${#name[sub]} on an unset name is the one exception — 0 without
        # evaluating the subscript — and is short-circuited earlier in
        # _expand_array_parameter.)
        self._eval_array_index(index_expr)
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
        parts = self.split_subscript(var_name)
        if parts is not None:
            array_name = self._resolve_array_name(parts[0])
            index_expr = parts[1]

            var = self.state.scope_manager.get_variable_object(array_name)

            # An associative array keys on the expanded literal subscript; an
            # indexed array (or a not-yet-created one) keys on the arithmetic
            # value. The store then owns the readonly guard, negative-index
            # resolution, create-if-absent, and observer notification — this
            # write never touches ``.value.set`` directly (core-state C2).
            key: "int | str"
            subscript = self.shell.expansion_manager.subscript
            if var is not None and isinstance(var.value, AssociativeArray):
                key = subscript.associative_key(index_expr)
            else:
                key = subscript.indexed_index(index_expr)
            self.state.scope_manager.store.set_element(array_name, key, value)
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
        flags = self._var_attr_flags(array_name)
        dq = self._at_a_quote

        if var and isinstance(var.value, AssociativeArray):
            # bash emits a trailing space before ')' for associative arrays.
            # Keys render through THE one rule (utils/escapes.format_assoc_key),
            # identically to declare -p (campaign W2).
            items = ' '.join(f'[{format_assoc_key(k)}]={dq(v)}'
                             for k, v in var.value.items())
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
        pairs = self._array_keyvalue_pairs(var)
        body = ' '.join(f'{format_assoc_key(k)} {self._at_a_quote(v)}'
                        for k, v in pairs)
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

    def array_fields(self, array_name: str, keys: bool = False) -> list:
        """Fields of an ``@``-subscripted array, from its NAME component.

        The component form of the retired ``expand_array_to_list``: the callers
        in fields.py already hold the array NAME (they used to build a
        ``'${...}'`` string only to have it re-parsed back into name+subscript
        here — the string round-trip M3 flagged). ``keys`` selects the
        ``${!arr[@]}`` view (indexed: indices as strings; associative: keys) vs
        the default ``${arr[@]}`` view (all element values). ``array_name`` is
        resolved through namerefs. A scalar yields ``['0']`` (keys) /
        ``[value]`` (elements); an unset/absent name yields ``[]``.
        """
        name = self._resolve_array_name(array_name)
        var = self.state.scope_manager.get_variable_object(name)
        if var and isinstance(var.value, (IndexedArray, AssociativeArray)):
            if not keys:
                return var.value.all_elements()
            if isinstance(var.value, IndexedArray):
                return [str(i) for i in var.value.indices()]
            return var.value.keys()
        if var and var.value:
            return ['0'] if keys else [str(var.value)]
        return []
