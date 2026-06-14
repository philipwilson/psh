"""Parameter-expansion operator application for VariableExpander.

The ``${var<op>operand}`` operators: defaults (:-, :=, :+, :?), pattern
removal (#, ##, %, %%), substitution (/, //), case modification (^, ,),
slicing (:off:len), and @-transforms. Mixed into VariableExpander
(variable.py).
"""

import sys
from typing import TYPE_CHECKING, Optional, cast

if TYPE_CHECKING:
    from ._protocols import VariableExpanderProtocol
    _Base = VariableExpanderProtocol
else:
    _Base = object

# Sentinel distinguishing an unset variable from one set to the empty
# string (used by the non-colon operators ${x-}, ${x+}, ...).
_UNSET = object()


class OperatorOpsMixin(_Base):
    """Application of ${var...} operators to resolved values."""

    def _positional_slice_elements(self) -> list:
        """Element sequence for ``${@:off:len}`` / ``${*:off:len}`` slicing.

        bash indexes positional slices as ``[$0, $1, $2, ...]``: ``${@:0}``
        includes ``$0`` and a negative offset is taken relative to one past
        the last positional parameter.  Prepending ``$0`` makes plain Python
        list slicing match those semantics.
        """
        return [self.state.get_special_variable('0')] + list(self.state.positional_params)

    # === Canonical ${...:offset:length} slice parsing/evaluation ===
    #
    # ALL slice forms — scalar ${v:o:l}, positional ${@:o:l}/${*:o:l},
    # and array ${a[@]:o:l}/${a[*]:o:l}, quoted or not — share the
    # helpers below (operand parsing, arithmetic evaluation, and element
    # slicing).  The bash semantics they implement, probe-verified:
    #
    # * offset/length are arithmetic expressions; a failed evaluation
    #   aborts the command with status 1.
    # * an absent length means "to the end"; an EMPTY length (``${v:1:}``)
    #   means 0.
    # * bounds are checked before the length: an out-of-range start
    #   yields an empty result even with a negative length
    #   (``${a[@]:9:-1}`` is empty, ``${a[@]:1:-1}`` is an error).
    # * a negative offset counts back from one past the last element (or
    #   string char); if still negative the result is empty (no clamping
    #   to 0 — ``${@: -99}`` is empty, not everything).
    # * sparse indexed arrays slice by INDEX, not element position;
    #   length is always a count of elements.
    # * a scalar subscripted ``${s[@]:o:l}`` gets STRING substring
    #   semantics: one field when the start is within the string
    #   (0 <= start <= len), no field otherwise.

    def _parse_slice_operand(self, operand: str, what: str) -> tuple:
        """Parse and arithmetic-evaluate a ``offset[:length]`` slice operand.

        Returns ``(offset, length)``; ``length`` is None when absent.
        Raises ExpansionError (status 1) when evaluation fails, as bash
        aborts the whole command for a bad slice expression.
        """
        from ..core import ExpansionError
        from .arithmetic import ArithmeticError, evaluate_arithmetic

        if ':' in operand:
            offset_str, length_str = operand.split(':', 1)
        else:
            offset_str, length_str = operand, None

        try:
            offset = evaluate_arithmetic(offset_str, self.shell) if offset_str.strip() else 0
            if length_str is None:
                length = None
            elif length_str.strip():
                length = evaluate_arithmetic(length_str, self.shell)
            else:
                length = 0
        except (ValueError, ArithmeticError):
            msg = f"{what}: {operand}: invalid offset or length"
            print(f"psh: {msg}", file=sys.stderr)
            self.state.last_exit_code = 1
            raise ExpansionError(msg, exit_code=1)
        return offset, length

    def _slice_negative_length_error(self, length: int):
        """Report a negative element-slice length and abort (bash exit 1)."""
        from ..core import ExpansionError
        msg = f"{length}: substring expression < 0"
        print(f"psh: {msg}", file=sys.stderr)
        self.state.last_exit_code = 1
        raise ExpansionError(msg, exit_code=1)

    def _slice_elements(self, elements: list, offset: int,
                        length, indices=None) -> list:
        """Slice an element list with bash semantics (see block comment).

        ``indices``: the elements' array indices, for sparse indexed
        arrays (selection is by index, not position); None for positional
        slicing.
        """
        if indices is not None:
            top = indices[-1] + 1 if indices else 0
            start = offset if offset >= 0 else top + offset
            if start < 0 or start >= top:
                return []
            selected = [el for el, i in zip(elements, indices) if i >= start]
        else:
            n = len(elements)
            start = offset if offset >= 0 else n + offset
            if start < 0 or start >= n:
                return []
            selected = elements[start:]

        if length is None:
            return selected
        if length < 0:
            self._slice_negative_length_error(length)
        return selected[:length]

    def _slice_scalar_subscript(self, value: str, offset: int, length) -> list:
        """Fields for ``${scalar[@]:o:l}`` — bash applies STRING substring
        semantics when the subscripted variable is a plain scalar.

        Returns one field (possibly empty) when the start lies within the
        string, no field when it is out of range.
        """
        from ..core import ExpansionError
        n = len(value)
        start = offset if offset >= 0 else n + offset
        if start < 0 or start > n:
            return []
        try:
            return [self.param_expansion.extract_substring(value, offset, length)]
        except ValueError as e:
            print(f"psh: {e}", file=sys.stderr)
            self.state.last_exit_code = 1
            raise ExpansionError(str(e), exit_code=1)

    def _slice_sequence(self, elements: list, operand: str,
                        what: str = 'seq', indices=None) -> list:
        """Parse a slice operand and slice ``elements`` (canonical entry
        combining _parse_slice_operand + _slice_elements)."""
        offset, length = self._parse_slice_operand(operand, what)
        return self._slice_elements(elements, offset, length, indices=indices)

    def _ifs_star_separator(self) -> str:
        """Separator for joining $* / ${arr[*]} (delegates to the one
        source on ShellState — see state.ifs_star_separator)."""
        return self.state.ifs_star_separator()

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
            name = self._resolve_array_name(var_name[:bracket])
            index_expr = var_name[bracket + 1:-1]
            var = self.state.scope_manager.get_variable_object(name)
            if var is None:
                return False
            if isinstance(var.value, IndexedArray):
                return var.value.get(self._eval_array_index(index_expr)) is not None
            if isinstance(var.value, AssociativeArray):
                return var.value.get(self.expand_array_index(index_expr)) is not None
            # Scalar with a subscript: bash treats x[0] as set iff x is set
            # (a scalar acts as an array with one element at index 0).
            if index_expr in ('@', '*'):
                return var.value is not None
            return var.value is not None and self._eval_array_index(index_expr) == 0
        # _UNSET is an identity sentinel for "variable absent"; the cast is
        # type-only (get_variable's default is typed str), the `is not`
        # identity check is unchanged.
        return self.state.get_variable(var_name, cast(str, _UNSET)) is not _UNSET

    def _apply_operator(self, operator: str, value: str,
                        operand: Optional[str],
                        var_name: str = '', is_set: bool = True) -> str:
        """Apply a parameter expansion operator to a resolved value.

        ``is_set`` distinguishes unset from set-but-empty and is only consulted
        by the non-colon operators (``-``, ``=``, ``+``, ``?``).
        """
        # Every operator below carries a non-None operand (the parser emits
        # operand=None only for ${#var} length, handled in its own branch);
        # the asserts narrow Optional[str] -> str, matching variable.py.
        if operator == ':-':
            if not value:
                assert operand is not None
                return self._expand_operand(operand)
            return value
        elif operator == '-':
            # Unset -> operand; set (even if empty) -> value.
            if not is_set:
                assert operand is not None
                return self._expand_operand(operand)
            return value
        elif operator == '=':
            if not is_set:
                assert operand is not None
                expanded_default = self._expand_operand(operand)
                if var_name and not var_name.isdigit():
                    self.set_var_or_array_element(var_name, expanded_default)
                return expanded_default
            return value
        elif operator == '+':
            # Set (even if empty) -> operand; unset -> empty.
            if is_set:
                assert operand is not None
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
                assert operand is not None
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
                assert operand is not None
                return self._expand_operand(operand)
            return ''
        elif operator == '#' and operand is None:
            # ${#var} (no operand) is the length; ${var#} (empty pattern)
            # is prefix removal with a pattern that matches nothing.
            return self.param_expansion.get_length(value)
        elif operator == '#':
            assert operand is not None
            return self.param_expansion.remove_shortest_prefix(
                value, self._expand_pattern_operand(operand))
        elif operator == '##':
            assert operand is not None
            return self.param_expansion.remove_longest_prefix(
                value, self._expand_pattern_operand(operand))
        elif operator == '%%':
            assert operand is not None
            return self.param_expansion.remove_longest_suffix(
                value, self._expand_pattern_operand(operand))
        elif operator == '%':
            assert operand is not None
            return self.param_expansion.remove_shortest_suffix(
                value, self._expand_pattern_operand(operand))
        elif operator in ('/', '//', '/#', '/%'):
            assert operand is not None
            return self._substitute(operator, value, operand)
        elif operator == ':':
            # Substring extraction. Offset and length are arithmetic
            # expressions (bash), so support ${x:1+1:2}, ${x:(-3):2}, etc.
            from ..core import ExpansionError

            assert operand is not None
            offset, length = self._parse_slice_operand(operand, var_name or 'var')
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
            # Case mods: an absent pattern (parser emits '') defaults to '?'
            # — every character matches.
            assert operand is not None
            return self.param_expansion.uppercase_first(
                value, self._expand_pattern_operand(operand) or '?')
        elif operator == '^^':
            assert operand is not None
            return self.param_expansion.uppercase_all(
                value, self._expand_pattern_operand(operand) or '?')
        elif operator == ',':
            assert operand is not None
            return self.param_expansion.lowercase_first(
                value, self._expand_pattern_operand(operand) or '?')
        elif operator == ',,':
            assert operand is not None
            return self.param_expansion.lowercase_all(
                value, self._expand_pattern_operand(operand) or '?')
        elif len(operator) == 2 and operator[0] == '@':
            # An unset parameter transforms to nothing (bash: ${unset@Q} -> '').
            if not is_set:
                return ''
            return self._apply_transform(operator[1], value, var_name)
        # Unknown operator, return value unchanged
        return value

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
            from ..interactive.prompt import PromptExpander
            return PromptExpander(self.shell).expand_prompt(value)
        if op == 'a':
            return self._var_attr_flags(var_name)
        if op == 'A':
            flags = self._var_attr_flags(var_name)
            assign = f"{var_name}={self._shell_quote(value)}"
            return f"declare -{flags} {assign}" if flags else assign
        if op in ('K', 'k'):
            # @K/@k on a scalar (or a single array element) behaves like @Q:
            # the value is shell-quoted. The whole-array key/value listing
            # form (${arr[@]@K}) is handled in the array branch of
            # variable.py / fields.py before reaching here.
            return self._shell_quote(value)
        return value

    @staticmethod
    def _shell_quote(s: str) -> str:
        """${var@Q} quoting — delegates to the shared implementation
        (psh/utils/escapes.py, which documents why ${var@Q} and
        printf %q formats differ)."""
        from ..utils.escapes import quote_at_q
        return quote_at_q(s)

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
