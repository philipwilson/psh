"""Operand mini-expansion for value/pattern/replacement operators.

Operands of ${var:-word}, ${var#pat}, ${var/pat/repl}, etc. get their
own expansion pass: quoted text and quoted expansion results are
protected (match literally / never field-split) while unquoted text
stays active — bash semantics pinned in v0.266.0 (patterns) and this
module's value walkers (v0.601). Mixed into VariableExpander
(variable.py).

**A value operand expands to a FIELD VECTOR, not a string.**
:class:`OperandValue` carries :class:`ExpandedField`s — the Word walker's
own currency — so field boundaries, explicit empties and per-run quote
protection all survive to ``word_expander``. bash keeps the positionals
of a ``"$@"`` inside an operand APART: ``unset x; set -- a b; printf
'<%s>' "${x:-"$@"}"`` prints ``<a><b>``, not ``<a b>``. The pre-field IR
(``OperandResult(str)``, carrying protection but no field dimension)
could not express that, and because it WAS a ``str`` every consumer
accepted it silently — which is how the scalar projection re-entered
unnamed. :class:`OperandValue` is deliberately NOT a ``str``: a consumer
that genuinely needs one string must NAME the projection
(:meth:`OperandValue.as_scalar`), and that call set is held closed by
``tests/unit/tooling/test_operand_projection_guard.py``.

Two facts the representation must keep distinct — they differ only in the
OUTER quoting, so no single string can satisfy both:

- ``set --; printf '<%s>' ${x:-"$@"}``   -> NO fields (the word elides)
- ``set --; printf '<%s>' "${x:-"$@"}"`` -> ONE EMPTY field

Value operands (${x:-w}, ${x:=w}, and the +/- families) expand
differently depending on the quoting context ENCLOSING the whole
``${...}`` — the ``quote_ctx`` parameter threaded through
VariableExpander (probed against bash 5.2, see
tmp/probes-r17t1-quoting/):

- ``None`` (unquoted ${...}): ordinary word semantics. One level of
  quotes is removed; single quotes keep text literal, double quotes
  expand without splitting, ``\\c`` escapes any character, ``$'...'``
  decodes, and a leading unquoted tilde prefix expands. Quoted/escaped
  regions are protected from later IFS splitting and globbing — the
  per-run protection of the emitted fields carries that to the Word
  walker.
- ``DQ_WORD`` / ``DQ_STRING`` (${...} inside double quotes): single
  quotes are LITERAL characters; an embedded ``"`` toggles the effective
  quote state (dquote backslash rules outside embedded quotes,
  backslash-escapes-anything inside them) and is removed; a simple
  ``$name`` scan runs ACROSS embedded quote marks (bash 3.2–5.2:
  ``"${x:-a"$y"c}"`` reads the variable ``yc`` — probed). ``$'...'``
  decodes only in DQ_WORD (lexed words); in DQ_STRING (heredoc bodies,
  ``$(( ))``, ``[[ ]]`` string operands) it stays literal, as bash never
  ANSI-C-decodes text that was not lexed as a word.
"""
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple, Union

from ..lexer.cmdsub_scanner import find_command_substitution_end
from ..lexer.pure_helpers import find_closing_delimiter
from ..lexer.recognizers.word_scanners import scan_inline_ansi_c
from .param_parser import parse_parameter_expansion
from .word_expansion_types import ExpandedField, FieldRun, Protection, Split

if TYPE_CHECKING:
    from ._protocols import VariableExpanderProtocol
    _Base = VariableExpanderProtocol
else:
    _Base = object

#: Enclosing-quote contexts for value-operand expansion (see module
#: docstring). ``None`` means the ``${...}`` itself is unquoted.
DQ_WORD = 'dquote-word'      # lexed double-quoted word: "${x:-w}"
DQ_STRING = 'dquote-string'  # dquote-like string data: heredocs, $(( )), [[ ]]

_PROTECTED = Protection.PROTECTED
_ACTIVE = Protection.ACTIVE
_NEVER = Split.NEVER
_ELIGIBLE = Split.IFS_ELIGIBLE


def _run(text: str, protected: bool) -> FieldRun:
    """One operand run. Protected (quoted/escaped) text never splits or globs;
    unprotected text is active and IFS-eligible like any unquoted expansion."""
    if protected:
        return FieldRun(text, _PROTECTED, _NEVER, 'operand')
    return FieldRun(text, _ACTIVE, _ELIGIBLE, 'operand')


class OperandValue:
    """A value-operand expansion: a vector of :class:`ExpandedField`.

    Deliberately NOT a ``str``. Consuming one as a string is a semantic
    decision — the shell has contexts that legitimately need a single
    string (an assignment value, a ``case`` selector, the ``:=`` store)
    and contexts that must keep the fields apart (a command argument, a
    ``for`` item list). Making that decision NAMEABLE is the point:
    :meth:`as_scalar` is the only projection, its call sites are the
    ruled terminal-consumer set, and :meth:`__str__` raises so an
    unnamed one cannot pass silently.

    ``fields`` distinguishes NO fields (the word elides) from one EMPTY
    field — see the module docstring; that distinction is unrepresentable
    in a string and is the reason this type exists.
    """
    __slots__ = ('fields',)

    def __init__(self, fields: Sequence[ExpandedField]) -> None:
        self.fields: List[ExpandedField] = list(fields)

    def as_scalar(self) -> str:
        """THE terminal scalar projection.

        bash joins an operand's ``$@`` fields with a literal SPACE and
        does NOT consult IFS (probed 5.2.26: with ``IFS=:``,
        ``v=${x:-"$@"}`` assigns ``a b`` while ``v=${x:-"$*"}`` assigns
        ``a:b`` — ``$*`` is a different mechanism that joins with IFS[0]
        BEFORE the operand IR ever sees it, yielding one field here).

        Call this ONLY from a ruled terminal consumer; the ruled set is
        enumerated and enforced in
        ``tests/unit/tooling/test_operand_projection_guard.py``.
        """
        return ' '.join(f.text for f in self.fields)

    def __str__(self) -> str:
        # TypeError, NOT a PshError: under the suite-wide PSH_STRICT_ERRORS
        # policy an unexpected TypeError is an INTERNAL DEFECT that fails
        # loudly, while shell-error types are swallowed to exit 1 and the
        # loudness would be lost (psh/core/CLAUDE.md expected-error taxonomy).
        raise TypeError(
            "OperandValue consumed as str — a value operand is a field "
            "vector; call .as_scalar() at a ruled terminal consumer "
            "(tests/unit/tooling/test_operand_projection_guard.py)")

    def __repr__(self) -> str:
        return f'OperandValue({self.fields!r})'


#: What an expansion application may yield: the FIELD VECTOR for the value
#: operators (:- := :+ :? and the non-colon twins), a plain ``str`` for every
#: other operator and for plain parameter resolution. Consumers that need one
#: string call :meth:`OperandValue.as_scalar` on the vector arm — that call is
#: the ruled terminal projection, never an implicit ``str()``.
OperandOrStr = Union[OperandValue, str]


class _OperandFieldBuilder:
    """Accumulates operand text into :class:`ExpandedField`s.

    ``emit`` extends the open field (merging into the previous run when the
    protection matches); ``splice_values``/``splice_fields`` apply the same
    boundary rule the Word walker uses for ``$@`` — the first value extends
    the open field and each further value starts a new one, while an EMPTY
    multi-field expansion is a no-op on boundaries (bash: ``pre"$@"post``
    with no positionals is the single field ``prepost``).
    """
    __slots__ = ('fields', 'emitted')

    def __init__(self) -> None:
        self.fields: List[ExpandedField] = [ExpandedField([])]
        #: False while the operand has contributed NOTHING — the flag that
        #: separates "no fields" from "one empty field" (see build()).
        self.emitted = False

    def emit(self, text: str, protected: bool) -> None:
        self.emitted = True
        runs = self.fields[-1].runs
        want = _PROTECTED if protected else _ACTIVE
        if runs and runs[-1].protection is want:
            runs[-1] = _run(runs[-1].text + text, protected)
        else:
            runs.append(_run(text, protected))

    def break_field(self) -> None:
        self.fields.append(ExpandedField([]))

    def splice_values(self, values: Sequence[str], protected: bool) -> None:
        """Splice a field-producing expansion's field TEXTS."""
        if not values:
            return
        self.emit(values[0], protected)
        for value in values[1:]:
            self.break_field()
            self.emit(value, protected)

    def splice_fields(self, fields: Sequence[ExpandedField]) -> None:
        """Splice a nested operand's own field vector, runs and all."""
        if not fields:
            return
        self.emitted = True
        for index, field in enumerate(fields):
            if index:
                self.break_field()
            self.fields[-1].runs.extend(field.runs)

    def build(self, empty_protected: bool) -> List[ExpandedField]:
        """Finish the vector.

        An operand that emitted NOTHING is one field holding one empty run,
        and that run's protection decides the two-cell representation test:
        PROTECTED (a DQ-context operand) survives as one empty field, while
        ACTIVE (an unquoted-context operand) is IFS-eligible, splits to
        nothing, and elides.
        """
        if not self.emitted:
            return [ExpandedField([_run('', empty_protected)])]
        return self.fields


class OperandOpsMixin(_Base):
    """Expansion of value/pattern/replacement operands with quote awareness."""

    @staticmethod
    def _inline_ansi_c(operand: str, i: int):
        """Decode an inline ANSI-C ``$'...'`` at ``operand[i]``.

        ``operand[i]`` is ``$`` and ``operand[i+1]`` is ``'``. Returns
        ``(decoded_text, new_index)`` using the single canonical scanner
        (``scan_inline_ansi_c`` → ``handle_ansi_c_escape``). If the quote never
        closes, the ``$`` is treated as a literal character. ANSI-C quoting is
        decoded in operand/word contexts but NOT by ``expand_string_variables``
        (which also serves double-quoted content, where ``$'...'`` is literal),
        so each operand walker decodes it explicitly.
        """
        res = scan_inline_ansi_c(operand, i)
        if res is None:
            return operand[i], i + 1
        return res

    def _expand_operand(self, operand: str,
                        quote_ctx: Optional[str] = None) -> OperandValue:
        """Expand a value-operator operand (${x:-OPERAND} and friends).

        Returns the operand's FIELD VECTOR. ``quote_ctx`` is the quoting
        context enclosing the whole ``${...}`` (see the module docstring)
        and decides run protection: in an unquoted context only the
        operand's own quoted/escaped regions are protected, while in a
        double-quote context the enclosing quotes protect everything. In
        BOTH contexts a ``$@``/``${a[@]}`` inside the operand still breaks
        fields — that is bash, and it is what the field vector exists to
        carry.
        """
        if quote_ctx is not None:
            return OperandValue(self._value_fields_dq(
                operand, decode_ansi=(quote_ctx == DQ_WORD)))
        return OperandValue(self._value_fields_unquoted(operand))

    def _operand_dollar_fields(self, text: str, i: int,
                               quote_ctx: Optional[str]):
        """``(field_texts, new_index)`` if the $-construct at ``text[i]`` is
        FIELD-PRODUCING, else ``(None, i)``.

        ``expand_to_fields`` is the existing discriminator and stays the
        single authority on what produces fields: it returns None for
        scalar semantics, which is why ``$*``/``${a[*]}`` (joined with
        IFS[0] before they get here) correctly stay one field.
        """
        if text.startswith('$@', i):
            return list(self.state.positional_params), i + 2
        if text.startswith('${', i):
            end, found = find_closing_delimiter(
                text, i + 2, '{', '}', track_quotes=True, track_escapes=True)
            if found:
                node = parse_parameter_expansion(text[i + 2:end - 1])
                fields = self.expand_to_fields(
                    node.parameter, node.operator, node.word,
                    quote_ctx=quote_ctx)
                if fields is not None:
                    # A view member may itself be a TRIGGERED value operand
                    # (${x:-${a[@]:-"$@"}}). Contribute its fields ONE PER
                    # ENTRY — projecting it to a scalar here would re-flatten
                    # exactly the structure this slot preserves.
                    values: List[str] = []
                    for f in fields:
                        if isinstance(f, OperandValue):
                            values.extend(inner.text for inner in f.fields)
                        else:
                            values.append(str(f))
                    return values, end
        return None, i

    def _emit_dollar(self, builder: '_OperandFieldBuilder', operand: str,
                     i: int, quote_ctx: Optional[str],
                     protected: bool, splice_producers: bool = True) -> int:
        """Expand the $-construct at ``operand[i]`` into ``builder``.

        Three shapes, in order: a field-producing expansion splices its
        fields; a nested value operand contributes its OWN field vector
        (bash: ``${x:-${y:-"$@"}}`` keeps the positionals apart, and
        ``${x:-${z:-'a b'}}`` keeps the nested quoting protected); anything
        else is ordinary scalar text.

        ``splice_producers`` is False for a BARE ``$@`` in an unquoted-context
        operand — :meth:`_value_fields_unquoted` records the measured reason.
        """
        if splice_producers:
            values, next_i = self._operand_dollar_fields(operand, i, quote_ctx)
            if values is not None:
                builder.splice_values(values, protected)
                return next_i
        expanded, next_i = self._expand_one_dollar(operand, i,
                                                   quote_ctx=quote_ctx)
        if isinstance(expanded, OperandValue):
            if protected:
                # An enclosing double quote protects the nested result's
                # runs, but never its field boundaries.
                builder.splice_fields([
                    ExpandedField([_run(f.text, True)])
                    for f in expanded.fields])
            else:
                builder.splice_fields(expanded.fields)
            return next_i
        builder.emit(expanded, protected)
        return next_i

    def _value_fields_unquoted(self, operand: str) -> List[ExpandedField]:
        """Walk an unquoted-context value operand into its field vector.

        Ordinary word semantics (bash): quotes group and are removed,
        ``\\c`` escapes any character, ``$'...'`` decodes, ``$"..."`` is a
        locale string, a leading tilde prefix expands, and $-constructs
        expand. Text from quotes/escapes (or a nested protected operand) is
        PROTECTED and never field-splits or globs; unquoted literal text and
        unquoted expansion results stay ACTIVE. A ``$@``/``${a[@]}`` breaks
        fields.
        """
        builder = _OperandFieldBuilder()
        i = 0
        n = len(operand)
        if n and operand[0] == '~':
            # bash expands only a LEADING tilde prefix in value operands
            # (no after-':' rule, unlike assignment values) and never
            # splits or globs the result.
            prefix, skip = self._tilde_prefix(operand)
            if skip:
                builder.emit(prefix, True)
                i = skip
        while i < n:
            c = operand[i]
            if c == "'":
                end = operand.find("'", i + 1)
                seg = operand[i + 1:] if end == -1 else operand[i + 1:end]
                i = n if end == -1 else end + 1
                builder.emit(seg, True)
            elif c == '"':
                i = self._dquote_region_fields(operand, i, builder)
            elif c == '\\' and i + 1 < n:
                builder.emit(operand[i + 1], True)
                i += 2
            elif c == '$' and i + 1 < n and operand[i + 1] == "'":
                seg, i = self._inline_ansi_c(operand, i)
                builder.emit(seg, True)
            elif c == '$' and i + 1 < n and operand[i + 1] == '"':
                # Locale string $"...": double-quoted content (untranslated).
                seg, i = self._inner_dquote_segment(operand, i)
                builder.emit(seg, True)
            elif c in '$`':
                # splice_producers=False: a BARE `$@` here is UNPROTECTED, and
                # bash does NOT give it plain field breaks. Measured 5.2.26
                # (`unset x; set -- aXq b`):
                #     IFS=X    ${x:-$@}  -> ONE field  [aXq b]
                #     IFS='X ' ${x:-$@}  -> TWO fields [aXq] [b]
                #     IFS=     ${x:-$@}  -> TWO fields [a] [b]
                # so the parameter CONTENT resists the very IFS char that the
                # joining separator splits on — a rule none of the obvious
                # models reproduces, and one this slot does NOT own. Keeping
                # the pre-field behaviour (join to one ACTIVE run, then let
                # ordinary IFS splitting act) reproduces bash wherever base
                # did and regresses nothing. The three cells where base ALREADY
                # diverged are reported to the integrator as a successor item,
                # not silently changed here. A `"$@"` — protected, the actual
                # HIGH-6 subject — DOES splice, via _dquote_region_fields.
                i = self._emit_dollar(builder, operand, i, None, False,
                                      splice_producers=False)
            else:
                builder.emit(c, False)
                i += 1
        return builder.build(empty_protected=False)

    def _dquote_region_fields(self, operand: str, i: int,
                              builder: '_OperandFieldBuilder') -> int:
        """Walk a ``"..."`` region inside an unquoted-context operand.

        The region's text is PROTECTED (its quotes protect it), but a
        field-producing expansion inside it STILL breaks fields — bash:
        ``${x:-"$@"}`` keeps the positionals apart AND unsplit, so
        ``set -- "a 1" b`` yields the two fields ``a 1`` and ``b``.
        Returns the index just past the closing quote.
        """
        start = i + 1
        end = self._skip_double_quote(operand, start)
        closed = end > start and operand[end - 1] == '"'
        body = operand[start:end - 1] if closed else operand[start:end]
        j = 0
        m = len(body)
        chunk: List[str] = []

        def flush() -> None:
            if chunk:
                builder.emit(self.expand_string_variables(
                    ''.join(chunk), quote_ctx=DQ_STRING), True)
                chunk.clear()

        saw_producer = False
        while j < m:
            ch = body[j]
            if ch == '\\' and j + 1 < m:
                chunk.append(body[j:j + 2])
                j += 2
                continue
            if ch == '$':
                values, nj = self._operand_dollar_fields(body, j, DQ_STRING)
                if values is not None:
                    flush()
                    builder.splice_values(values, True)
                    saw_producer = True
                    j = nj
                    continue
            chunk.append(ch)
            j += 1
        if chunk:
            flush()
        elif not saw_producer:
            # A literally empty "" is an EXPLICIT empty field, never elision.
            # But a region whose ONLY content was a field producer that yielded
            # ZERO fields contributes NOTHING — bash, probed:
            #     set --; unset x; printf '<%s>' ${x:-"$@"}   -> (no output)
            #     set --; unset x; printf '<%s>' ${x:-""}     -> <>
            # Both reach here with nothing emitted; only the producer flag
            # tells them apart, which is why it is tracked rather than
            # inferred from the accumulated text.
            builder.emit('', True)
        return end

    def _value_fields_dq(self, operand: str,
                         decode_ansi: bool) -> List[ExpandedField]:
        """Walk a value operand whose ``${...}`` sits inside double quotes.

        bash rules (probed 3.2–5.2, tmp/probes-r17t1-quoting/): single
        quotes are literal characters; an embedded ``"`` is removed and
        TOGGLES the effective quote state — outside embedded quotes the
        double-quote backslash rules apply (``\\$ \\" \\\\ \\``` processed,
        others kept), inside them a backslash escapes ANY character; a
        simple ``$name`` scan runs across embedded quote marks (consuming
        them), so ``"${x:-a"$y"c}"`` reads the variable ``yc``; ``$"..."``
        is a locale string; ``$'...'`` decodes only for lexed words
        (*decode_ansi*), never for heredoc-like string data.

        The enclosing quotes protect every run, so no run is ever
        split-eligible — but a ``$@``/``${a[@]}`` inside the operand STILL
        breaks fields (bash: ``"${x:-"$@"}"`` is ``<a><b>``). This is ONE
        walk: the ``inner`` quote state must survive across field breaks,
        and each $-construct must be expanded exactly ONCE (a speculative
        re-expansion would re-run command substitutions and re-assign
        ``:=``).
        """
        builder = _OperandFieldBuilder()
        ctx = DQ_WORD if decode_ansi else DQ_STRING
        i = 0
        n = len(operand)
        inner = False  # inside an embedded "..." region (escape rules invert)
        while i < n:
            c = operand[i]
            if c == '"':
                inner = not inner
                i += 1
            elif c == '\\' and i + 1 < n:
                nxt = operand[i + 1]
                if inner or nxt in '\\"$`':
                    builder.emit(nxt, True)
                    i += 2
                else:
                    builder.emit(c, True)
                    i += 1
            elif c == '$' and i + 1 < n and operand[i + 1] == "'" and decode_ansi:
                seg, i = self._inline_ansi_c(operand, i)
                builder.emit(seg, True)
            elif c == '$' and i + 1 < n and operand[i + 1] == '"':
                seg, i = self._inner_dquote_segment(operand, i)
                builder.emit(seg, True)
            elif c == '$' and i + 1 < n and (operand[i + 1].isalnum()
                                             or operand[i + 1] == '_'):
                expanded, i, inner = self._dq_name_scan(operand, i, inner)
                builder.emit(expanded, True)
            elif c in '$`':
                i = self._emit_dollar(builder, operand, i, ctx, True)
            else:
                builder.emit(c, True)
                i += 1
        return builder.build(empty_protected=True)

    def _inner_dquote_segment(self, operand: str, i: int) -> Tuple[str, int]:
        """Expand the ``"..."`` starting at operand[i] (``"`` or ``$"``).

        Returns (expanded_content, index_past_closing_quote). The content
        expands with double-quote rules; nested ``${...}`` operands see a
        double-quote context (bash: ``${x:-"${z:-'q'}"}`` keeps the single
        quotes).
        """
        start = i + (2 if operand[i] == '$' else 1)
        end = self._skip_double_quote(operand, start)
        closed = end > start and operand[end - 1] == '"'
        seg = operand[start:end - 1] if closed else operand[start:end]
        return self.expand_string_variables(seg, quote_ctx=DQ_STRING), end

    def _dq_name_scan(self, operand: str, i: int,
                      inner: bool) -> Tuple[str, int, bool]:
        """Scan-and-expand the ``$name`` at operand[i] in dquote context.

        The name scan consumes embedded ``"`` marks (each toggling the
        *inner* escape state) — the bash behavior that makes
        ``"${x:-a"$y"c}"`` expand the variable ``yc``. Digits fall through
        to the shared scanner first (``$1`` is single-character). Returns
        (expanded_text, new_index, new_inner_state).
        """
        if operand[i + 1].isdigit():
            # A positional (`$1`) carries no operator, so this is always a
            # string. Narrowed by assertion, matching the name branch below —
            # an as_scalar() here would be an unruled scalar re-entry.
            expanded, i = self._expand_one_dollar(operand, i)
            assert not isinstance(expanded, OperandValue)
            return expanded, i, inner
        j = i + 1
        name: List[str] = []
        while j < len(operand):
            ch = operand[j]
            if ch.isalnum() or ch == '_':
                name.append(ch)
                j += 1
            elif ch == '"':
                inner = not inner
                j += 1
            else:
                break
        if not name:
            # "$" directly before an embedded quote and no name: the quotes
            # were consumed (and toggled); the $ stays literal.
            return '$', j, inner
        # A bare `$name` carries no operator, so this is always a string; the
        # narrowing is asserted rather than projected (an as_scalar() here
        # would be an unruled scalar re-entry).
        scanned = self.expand_variable('$' + ''.join(name))
        assert not isinstance(scanned, OperandValue)
        return scanned, j, inner

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
            find_closing_delimiter,
        )
        if text.startswith('$((', i):
            end, found = find_balanced_double_parentheses(
                text, i + 3, track_quotes=True)
            if found:
                return end
        if text.startswith('$(', i):
            end, found = find_command_substitution_end(text, i + 2)
            return end if found else i + 2
        if text.startswith('${', i):
            end, found = find_closing_delimiter(
                text, i + 2, '{', '}', track_quotes=True, track_escapes=True)
            return end if found else i + 2
        return i + 1

    # Glob syntax that a quoted/escaped operand character must be protected
    # from. Besides the top-level metacharacters (``* ? [ ]`` and the extglob
    # prefixes ``( ) | @ ! +``), this includes the characters that are special
    # ONLY inside a bracket expression — ``-`` (range), ``^`` (negation at the
    # start) — because a quoted class-special char inside an ACTIVE bracket is a
    # literal member, not class syntax (bash: ``[a"-"c]`` is the set {a,-,c},
    # not the range a-c; #20 H7 carry-2). A backslash-escaped such char is a
    # literal member wherever it lands (the engine's ``_bracket_match`` reads
    # ``\c`` inside ``[...]`` as a member), so escaping them uniformly is safe.
    _GLOB_SPECIALS = set('\\*?[]()|@!+-^')

    @classmethod
    def glob_escape(cls, text: str) -> str:
        """Backslash-escape glob syntax so the text matches literally."""
        return ''.join('\\' + c if c in cls._GLOB_SPECIALS else c
                       for c in text)

    def _expand_one_dollar(self, text: str, i: int,
                           quote_ctx: Optional[str] = None):
        """Expand the single $-construct or `...` at text[i].

        Returns (expanded_text, index_past_construct); a '$' that starts
        nothing expandable stays literal. ``quote_ctx`` is the enclosing
        quote context, inherited by nested ``${...}`` operators (bash:
        the single quotes in ``"${x:-${z:-'q'}}"`` stay literal).
        """
        from ..lexer.pure_helpers import (
            find_balanced_double_parentheses,
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
            end, found = find_command_substitution_end(text, i + 2)
            if found:
                return self.shell.expansion_manager.command_sub.execute(text[i:end]), end
            return '$', i + 1
        if text.startswith('${', i):
            end, found = find_closing_delimiter(
                text, i + 2, '{', '}', track_quotes=True, track_escapes=True)
            if found:
                return self.expand_variable(text[i:end],
                                            quote_ctx=quote_ctx), end
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
        """Expand a leading unquoted tilde word of an operand.

        bash finds the tilde WORD — the raw text up to the first unquoted
        ``/``, or the whole operand — and tilde-expands it: the prefix
        proper is delimited at the first ``/`` or ``:``
        (TildeExpander.expand), and on success the REST of the tilde word
        is consumed verbatim with it, protected from further expansion
        (probed bash 5.2: ``${u:-~:$X}`` yields ``$HOME:$X`` with the
        ``$X`` literal and unsplit; ``${v#~root:x*}`` makes the ``x*``
        literal). A quote character inside the tilde word (``~'q'``,
        ``~\\:y``) or a failed expansion (unknown user, ``~$X``) yields
        ``('', 0)``: no tilde expansion, the walker processes the operand
        normally.

        Returns (expanded_text, chars_consumed).
        """
        end = len(operand)
        for i in range(1, len(operand)):
            ch = operand[i]
            if ch == '/':
                end = i
                break
            if ch in '\'"\\':
                return '', 0
        tilde_word = operand[:end]
        expanded = self.shell.expansion_manager.tilde_expander.expand(tilde_word)
        if expanded == tilde_word:
            return '', 0
        return expanded, end

    def _expand_pattern_operand(self, operand: str) -> str:
        """Expand a pattern operand (``${x#OP}``, ``${x/OP/...}``, case mods).

        Variables, command substitution and arithmetic are expanded and one
        level of quoting is removed (bash). Quoted text — and the results of
        expansions inside double quotes — matches literally, while unquoted
        text and unquoted-expansion results keep their glob power.

        RULED TERMINAL CONSUMER: a pattern is ONE string. A nested value
        operand is projected here, so the compiled-pattern side downstream
        never sees a field vector (probed: ``v="a b c"; "${v#${x:-"$@"}}"``
        is ``' c'`` in bash — the operand's fields are joined with a space
        before matching).
        """
        out = []
        i = 0
        n = len(operand)
        if n and operand[0] == '~':
            prefix, skip = self._tilde_prefix(operand)
            if skip:
                out.append(self.glob_escape(prefix))
                i = skip
        while i < n:
            c = operand[i]
            if c == "'":
                end = operand.find("'", i + 1)
                seg = operand[i + 1:] if end == -1 else operand[i + 1:end]
                i = n if end == -1 else end + 1
                out.append(self.glob_escape(seg))
            elif c == '"':
                end = self._skip_double_quote(operand, i + 1)
                closed = end > i + 1 and operand[end - 1] == '"'
                seg = operand[i + 1:end - 1] if closed else operand[i + 1:end]
                out.append(self.glob_escape(self.expand_string_variables(seg)))
                i = end
            elif c == '\\' and i + 1 < n:
                out.append(operand[i:i + 2])
                i += 2
            elif c == '$' and i + 1 < n and operand[i + 1] == "'":
                # Inline ANSI-C $'...': decoded content matches literally.
                seg, i = self._inline_ansi_c(operand, i)
                out.append(self.glob_escape(seg))
            elif c in '$`':
                expanded, i = self._expand_one_dollar(operand, i)
                out.append(expanded.as_scalar()
                           if isinstance(expanded, OperandValue) else expanded)
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
        parts: list = []
        buf: list = []

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
            elif c == '$' and i + 1 < n and operand[i + 1] == "'":
                # Inline ANSI-C $'...': decoded content is literal (a '&' inside
                # it is not the match placeholder).
                seg, i = self._inline_ansi_c(operand, i)
                buf.append(seg)
            elif c in '$`':
                expanded, i = self._expand_one_dollar(operand, i)
                add_active(expanded.as_scalar()
                           if isinstance(expanded, OperandValue) else expanded)
            else:
                buf.append(c)
                i += 1
        flush()
        return parts
