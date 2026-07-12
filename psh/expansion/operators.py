"""Parameter-expansion operator application for VariableExpander.

The ``${var<op>operand}`` operators: defaults (:-, :=, :+, :?), pattern
removal (#, ##, %, %%), substitution (/, //), case modification (^, ,),
slicing (:off:len), and @-transforms. Mixed into VariableExpander
(variable.py).
"""

import sys
from typing import TYPE_CHECKING, NoReturn, Optional, cast

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
            raise ExpansionError(msg, exit_code=1) from None
        return offset, length

    def _slice_negative_length_error(self, length: int):
        """Report a negative element-slice length and abort (bash exit 1)."""
        from ..core import ExpansionError
        msg = f"{length}: substring expression < 0"
        print(f"{self.state.error_location_prefix()}{msg}", file=sys.stderr)
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
            selected = [el for el, i in zip(elements, indices, strict=False) if i >= start]
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
            print(f"{self.state.error_location_prefix()}{e}", file=sys.stderr)
            self.state.last_exit_code = 1
            raise ExpansionError(str(e), exit_code=1) from e

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
        if (parts := self.split_subscript(var_name)) is not None:
            from ..core import AssociativeArray, IndexedArray
            name = self._resolve_array_name(parts[0])
            index_expr = parts[1]
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

    @staticmethod
    def _nonassignable_subject(var_name: str) -> Optional[str]:
        """Error subject for :=/= on a target bash cannot assign through,
        else None. A positional ($1) or special ($@/$*/$#/...) parameter
        cannot be assigned: bash aborts with "$N: cannot assign in this way"
        instead of silently returning the default."""
        if var_name.isdigit():
            return f"${var_name}"
        if var_name in ('@', '*', '#', '?', '$', '!', '-'):
            return f"${var_name}"
        return None

    def _reject_nonassignable(self, var_name: str) -> None:
        """Abort a :=/= assignment to a positional/special parameter (bash)."""
        subject = self._nonassignable_subject(var_name)
        if subject is not None:
            from ..core import ExpansionError
            msg = f"{subject}: cannot assign in this way"
            print(f"{self.state.error_location_prefix()}{msg}", file=sys.stderr)
            self.state.last_exit_code = 1
            raise ExpansionError(msg, exit_code=1)

    def _view_conditional(self, operator: str, elements: list, joiner: str,
                          operand: Optional[str], qmark_subject: str,
                          assign_error: str,
                          quote_ctx: Optional[str] = None) -> list:
        """Apply a default/alternate/assign/error operator to a multi-element
        VIEW (``${a[@]}``, ``${a[*]}``, ``${@}``, ``${*}``), matching bash.

        The COLON variants (``:-``/``:+``/``:=``/``:?``) test whether the
        JOINED view is null; the non-colon variants test set-ness (any
        element present) — NOT the element count, which was psh's bug:

            a=("");     "${a[@]:+X}" -> ''   (joined view is null)
            a=("" "");  "${a[@]:+X}" -> X    (joined view is a single space)

        Returns the list of result fields.  ``:=``/``=`` and ``:?``/``?``
        raise bash's error when the view is null/unset (an @/* view can never
        be assigned, so ``:=`` never mutates; a set/non-null view keeps its
        elements).

        ``joiner`` is used only for the colon null-test (a space for @ views,
        IFS[0] for * views); ``qmark_subject`` is the ``:?``/``?`` error
        subject; ``assign_error`` is the full ``:=``/``=`` error text (bash's
        wording differs for array vs positional views).
        """
        from ..core import ExpansionError
        if operator.startswith(':'):
            triggered = joiner.join(elements) == ''
            base, empty_msg = operator[1], "parameter null or not set"
        else:
            triggered = len(elements) == 0
            base, empty_msg = operator, "parameter not set"

        if base == '-':
            return ([self._expand_operand(operand or '', quote_ctx)]
                    if triggered else list(elements))
        if base == '+':
            return ([] if triggered
                    else [self._expand_operand(operand or '', quote_ctx)])
        if base == '=':
            if triggered:
                print(f"{self.state.error_location_prefix()}{assign_error}", file=sys.stderr)
                self.state.last_exit_code = 1
                raise ExpansionError(assign_error, exit_code=1)
            return list(elements)
        # base == '?'
        if triggered:
            # bash renders the error word with UNQUOTED-context rules even
            # when the expansion sits inside double quotes (probed:
            # "${x:?'m'}" reports m, not 'm').
            msg = str(self._expand_operand(operand)) if operand else empty_msg
            print(f"{self.state.error_location_prefix()}{qmark_subject}: {msg}", file=sys.stderr)
            self.state.last_exit_code = 127
            from ..core import FatalExpansionError
            raise FatalExpansionError(f"{qmark_subject}: {msg}", exit_code=127)
        return list(elements)

    def _apply_operator(self, operator: str, value: str,
                        operand: Optional[str],
                        var_name: str = '', is_set: bool = True,
                        quote_ctx: Optional[str] = None) -> str:
        """Apply a parameter expansion operator to a resolved value.

        ``is_set`` distinguishes unset from set-but-empty and is only consulted
        by the non-colon operators (``-``, ``=``, ``+``, ``?``).
        ``quote_ctx`` is the quoting context enclosing the ``${...}``
        (operands.py) — it shapes how the default/alternate operators
        expand their value word.
        """
        # Every operator below carries a non-None operand (the parser emits
        # operand=None only for ${#var} length, handled in its own branch);
        # the asserts narrow Optional[str] -> str, matching variable.py.
        if operator == ':-':
            if not value:
                assert operand is not None
                return self._expand_operand(operand, quote_ctx)
            return value
        elif operator == '-':
            # Unset -> operand; set (even if empty) -> value.
            if not is_set:
                assert operand is not None
                return self._expand_operand(operand, quote_ctx)
            return value
        elif operator == '=':
            if not is_set:
                assert operand is not None
                return self._assign_default(var_name, operand, quote_ctx)
            return value
        elif operator == '+':
            # Set (even if empty) -> operand; unset -> empty.
            if is_set:
                assert operand is not None
                return self._expand_operand(operand, quote_ctx)
            return ''
        elif operator == '?':
            if not is_set:
                self._qmark_error(var_name, operand, "parameter not set")
            return value
        elif operator == ':=':
            if not value:
                assert operand is not None
                return self._assign_default(var_name, operand, quote_ctx)
            return value
        elif operator == ':?':
            if not value:
                self._qmark_error(var_name, operand,
                                  "parameter null or not set")
            return value
        elif operator == ':+':
            if value:
                assert operand is not None
                return self._expand_operand(operand, quote_ctx)
            return ''
        elif operator == '#' and operand is None:
            # ${#var} (no operand) is the length; ${var#} (empty pattern)
            # is prefix removal with a pattern that matches nothing.
            return self.param_expansion.get_length(value)
        elif operator in self._VALUE_OPERATORS:
            # Prefix/suffix removal, substitution and case-mod operators —
            # these have identical per-element semantics, so the single
            # _value_op table is the source of truth for both the scalar and
            # the "${arr[@]#pat}" per-element drivers.
            assert operand is not None
            result = self._value_op(operator, value, operand, var_name)
            assert result is not None
            return result
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
                print(f"{self.state.error_location_prefix()}{e}", file=sys.stderr)
                self.state.last_exit_code = 1
                raise ExpansionError(str(e), exit_code=1) from e
        elif operator == '!*':
            # ${!prefix*}: names joined with the first character of IFS
            names = self.param_expansion.match_variable_names(var_name)
            return self._ifs_star_separator().join(names)
        elif operator == '!@':
            # ${!prefix@}: names joined with spaces
            names = self.param_expansion.match_variable_names(var_name)
            return ' '.join(names)
        elif operator.startswith('@'):
            # An unset parameter transforms to nothing whatever the operand
            # (bash: ${unset@Q}, ${unset@ZZ}, ${unset@} are all '').
            if not is_set:
                return ''
            if len(operator) == 2:
                return self._apply_transform(operator[1], value, var_name)
            # Empty or multi-char operand on a SET parameter: fatal bad
            # substitution (bash — probe-verified: ${x@}, ${x@ZZ}, ${x@Q9}).
            self._bad_transform_error(operator[1:], var_name)
        # Unknown operator, return value unchanged
        return value

    def _assign_default(self, var_name: str, operand: str,
                        quote_ctx: Optional[str]) -> str:
        """Expand, STORE, and return a ``:=``/``=`` default (bash).

        The assigned value is the quote-removed word; the expansion then
        RESULTS in the variable's new value — plain value semantics, so
        an unquoted ``${x:=a\\ b}`` splits into two fields even though
        ``${x:-a\\ b}`` stays one (probed: bash stores "a b" and prints
        <a><b>). Hence the plain-str coercion: no operand segments (and
        their splitting protection) survive an assignment.
        """
        self._reject_nonassignable(var_name)
        expanded_default = str(self._expand_operand(operand, quote_ctx))
        if var_name:
            self.set_var_or_array_element(var_name, expanded_default)
        return expanded_default

    def _qmark_error(self, var_name: str, operand: Optional[str],
                     default_msg: str) -> NoReturn:
        """Report a ``:?``/``?`` failure and abort the command (bash).

        bash renders the error word with UNQUOTED-context value-operand
        rules regardless of the enclosing quotes (probed: both
        ``${x:?'m'}`` and ``"${x:?'m'}"`` report ``m``).
        """
        from ..core import FatalExpansionError
        msg = str(self._expand_operand(operand)) if operand else default_msg
        print(f"{self.state.error_location_prefix()}{var_name}: {msg}", file=sys.stderr)
        self.state.last_exit_code = 127
        raise FatalExpansionError(f"{var_name}: {msg}", exit_code=127)

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
        # @U/@L/@u case-transform through the locale service: length-safe
        # (ß stays ß, not "SS") and locale-gated (ASCII-only under C), exactly
        # like ^^ / ,, . Raw str.upper()/str.lower() grew ß -> "SS" and ignored
        # the locale — both wrong vs bash.
        loc = self.shell.state.locale
        if op == 'U':
            return loc.upper(value)
        if op == 'L':
            return loc.lower(value)
        if op == 'u':
            return loc.upper(value[:1]) + value[1:]
        if op == 'Q':
            return self._shell_quote(value)
        if op == 'E':
            return self._ansi_c_expand(value)
        if op == 'P':
            # Full prompt expansion (escapes + $-expansion), same as PS1/PS2 —
            # but @P yields a plain string, so \[ \] drop their readline
            # non-printing markers rather than emitting \001/\002 (bash).
            from ..interactive.prompt import PromptExpander
            return PromptExpander(self.shell).expand_full(value, readline_markers=False)
        if op == 'a':
            return self._var_attr_flags(self._transform_name(var_name))
        if op == 'A':
            name = self._transform_name(var_name)
            flags = self._var_attr_flags(name)
            assign = f"{name}={self._shell_quote(value)}"
            return f"declare -{flags} {assign}" if flags else assign
        if op in ('K', 'k'):
            # @K/@k on a scalar (or a single array element) behaves like @Q:
            # the value is shell-quoted. The whole-array key/value listing
            # form (${arr[@]@K}) is handled in the array branch of
            # variable.py / fields.py before reaching here.
            return self._shell_quote(value)
        # Unknown transform letter on a SET variable: runtime bad
        # substitution (bash). The unset case never reaches here — the
        # dispatch returns '' for unset parameters before applying the
        # transform, matching bash's quirk that ${unset@Z} is silently
        # empty while ${set@Z} is a fatal error.
        self._bad_transform_error(op, var_name)

    def _bad_transform_error(self, operand: str, var_name: str) -> NoReturn:
        """Fatal bad substitution for a ``${var@X}`` transform whose operand
        is unknown/empty/multi-char and the parameter IS set. Unlike the
        bad-NAME form (discard-line, BadSubstitutionError), this kind EXITS
        a non-interactive shell — 127 under ``-c`` (bash, probe-verified)."""
        from ..core.exceptions import FatalExpansionError
        content = f"{var_name}@{operand}" if var_name else f"@{operand}"
        print(f"{self.state.error_location_prefix()}${{{content}}}: bad substitution", file=sys.stderr)
        self.state.last_exit_code = 1
        raise FatalExpansionError(f"${{{content}}}: bad substitution",
                                  exit_code=127)

    @staticmethod
    def _shell_quote(s: str) -> str:
        """${var@Q} quoting — delegates to the shared implementation
        (psh/utils/escapes.py, which documents why ${var@Q} and
        printf %q formats differ)."""
        from ..utils.escapes import quote_at_q
        return quote_at_q(s)

    @staticmethod
    def _ansi_c_expand(s: str) -> str:
        """Expand backslash escapes as in $'...' (bash ${var@E}).

        Delegates to the single canonical ANSI-C decoder
        (``psh/lexer/pure_helpers.handle_ansi_c_escape``) so every escape form —
        ``\\n``/``\\t``/``\\r``, ``\\xHH``, octal ``\\NNN``, ``\\cX``,
        ``\\uHHHH``, ``\\UHHHHHHHH`` — matches ``$'...'`` and the lexer, instead
        of the previous partial reimplementation (which handled only the simple
        escapes and ``\\xHH``).
        """
        from ..lexer.pure_helpers import handle_ansi_c_escape
        out = []
        i = 0
        while i < len(s):
            if s[i] == '\\' and i + 1 < len(s):
                decoded, i = handle_ansi_c_escape(s, i)
                out.append(decoded)
            else:
                out.append(s[i])
                i += 1
        return ''.join(out)

    def _transform_name(self, var_name: str) -> str:
        """The variable NAME used by a ${var@A}/${var@a} transform.

        A single array element (``a[1]``, ``m[k]``) reports the whole
        array's name and attributes: bash's ``${a[1]@A}`` prints an
        assignment to the array NAME (``declare -a a='2'``) and ``${a[1]@a}``
        reports the array's flags, not the subscripted element.
        """
        subscript = self.split_subscript(var_name)
        if subscript is not None:
            return self._resolve_array_name(subscript[0])
        return var_name

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

    # Value-level operators that apply identically to a scalar and to each
    # element of "${arr[@]<op>...}". The single source of truth is _value_op;
    # both _apply_operator (scalar) and _apply_op_per_element consume it.
    _VALUE_OPERATORS = frozenset({
        '#', '##', '%', '%%', '/', '//', '/#', '/%',
        '^', '^^', ',', ',,', '~', '~~',
    })

    def _value_op(self, operator: str, value: str, operand: Optional[str],
                  var_name: str) -> Optional[str]:
        """Apply a value-level operator (prefix/suffix removal, substitution,
        case modification) to a single value. Returns None if *operator* is not
        a value-level operator."""
        if operator not in self._VALUE_OPERATORS:
            return None
        # Every value-level operator carries an operand (the operand-less
        # ${#var} length form is split off by the scalar caller before here).
        assert operand is not None
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
        # Case mods (^ ^^ upper, , ,, lower, ~ ~~ toggle): an absent pattern
        # (parser emits '') defaults to '?' — every character matches.
        if operator == '^':
            return pe.uppercase_first(value, self._expand_pattern_operand(operand) or '?')
        if operator == '^^':
            return pe.uppercase_all(value, self._expand_pattern_operand(operand) or '?')
        if operator == ',':
            return pe.lowercase_first(value, self._expand_pattern_operand(operand) or '?')
        if operator == ',,':
            return pe.lowercase_all(value, self._expand_pattern_operand(operand) or '?')
        if operator == '~':
            return pe.toggle_first(value, self._expand_pattern_operand(operand) or '?')
        if operator == '~~':
            return pe.toggle_all(value, self._expand_pattern_operand(operand) or '?')
        return None

    def _apply_op_per_element(self, operator, value, operand, var_name):
        """Apply one value-level operator to a single element. Returns None for
        operators without per-element semantics.

        Mirrors the scalar dispatch in expand_parameter_direct so quoted array
        expansion ("${a[@]#pat}") behaves like bash's per-element application.
        """
        result = self._value_op(operator, value, operand, var_name)
        if result is not None:
            return result
        if operator.startswith('@') and len(operator) > 1:
            if operator == '@A':
                # @A produces one whole-array assignment statement, not a
                # per-element transform — scalar path handles it.
                return None
            if len(operator) > 2:
                # Multi-char operand on a SET element: fatal bad
                # substitution, like the scalar path (bash).
                self._bad_transform_error(operator[1:], var_name)
            return self._apply_transform(operator[1], value, var_name)
        return None

    def _substitute(self, operator: str, value: str, operand: str) -> str:
        """Apply a ${x/pat/repl} family operator to one value."""
        raw_pattern, raw_replacement = self._split_pattern_replacement(operand)
        pattern = self._expand_pattern_operand(raw_pattern)
        if not pattern and operator in ('/', '//'):
            # ${x/} and ${x//y}: an unanchored empty pattern replaces nothing
            # (bash). The anchored forms /# and /% with an empty pattern DO
            # match the empty string at the start/end, so they fall through to
            # substitute_prefix/substitute_suffix and prepend/append.
            return value
        replacement = self._expand_replacement_operand(raw_replacement)
        fn = {'/': self.param_expansion.substitute_first,
              '//': self.param_expansion.substitute_all,
              '/#': self.param_expansion.substitute_prefix,
              '/%': self.param_expansion.substitute_suffix}[operator]
        return fn(value, pattern, replacement)
