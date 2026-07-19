"""Operand mini-expansion for value/pattern/replacement operators.

Operands of ${var:-word}, ${var#pat}, ${var/pat/repl}, etc. get their
own expansion pass: quoted text and quoted expansion results are
protected (match literally / never field-split) while unquoted text
stays active — bash semantics pinned in v0.266.0 (patterns) and this
module's value walkers (v0.601). Mixed into VariableExpander
(variable.py).

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
  ``OperandResult.segments`` carry that protection to the Word walker.
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
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..lexer.cmdsub_scanner import find_command_substitution_end
from ..lexer.recognizers.word_scanners import scan_inline_ansi_c

if TYPE_CHECKING:
    from ._protocols import VariableExpanderProtocol
    _Base = VariableExpanderProtocol
else:
    _Base = object

#: Enclosing-quote contexts for value-operand expansion (see module
#: docstring). ``None`` means the ``${...}`` itself is unquoted.
DQ_WORD = 'dquote-word'      # lexed double-quoted word: "${x:-w}"
DQ_STRING = 'dquote-string'  # dquote-like string data: heredocs, $(( )), [[ ]]


class OperandResult(str):
    """A joined value-operand expansion carrying per-segment quoting.

    Behaves as a plain str for every existing consumer; the Word walker
    (word_expander) additionally reads ``segments`` — ``(text,
    protected)`` pairs — to keep quoted/escaped regions of the operand
    safe from IFS splitting and globbing (bash: ``${x:-'a b'}`` stays
    one field while ``${x:-a b}`` splits into two).
    """
    __slots__ = ('segments',)
    segments: Tuple[Tuple[str, bool], ...]

    def __new__(cls, segments: List[Tuple[str, bool]]) -> 'OperandResult':
        obj = super().__new__(cls, ''.join(text for text, _ in segments))
        obj.segments = tuple(segments)
        return obj


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
                        quote_ctx: Optional[str] = None) -> str:
        """Expand a value-operator operand (${x:-OPERAND} and friends).

        ``quote_ctx`` is the quoting context enclosing the whole ``${...}``
        (see the module docstring). Unquoted context returns an
        :class:`OperandResult` whose segments record which regions were
        quoted/escaped, so the Word walker can protect them from IFS
        splitting and globbing; double-quote contexts return a plain str
        (the enclosing quotes already protect the whole result).
        """
        if quote_ctx is not None:
            return self._value_dq_text(operand,
                                       decode_ansi=(quote_ctx == DQ_WORD))
        return OperandResult(self._value_segments_unquoted(operand))

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

    def _value_segments_unquoted(self, operand: str) -> List[Tuple[str, bool]]:
        """Walk an unquoted-context value operand into (text, protected) runs.

        Ordinary word semantics (bash): quotes group and are removed,
        ``\\c`` escapes any character, ``$'...'`` decodes, ``$"..."`` is a
        locale string, a leading tilde prefix expands, and $-constructs
        expand. ``protected`` marks text that came from quotes/escapes
        (or a nested protected operand) and thus never field-splits or
        globs; unquoted literal text and unquoted expansion results stay
        active. Adjacent runs with equal protection are merged.
        """
        out: List[Tuple[str, bool]] = []

        def emit(text: str, protected: bool) -> None:
            if out and out[-1][1] == protected:
                out[-1] = (out[-1][0] + text, protected)
            else:
                out.append((text, protected))

        i = 0
        n = len(operand)
        if n and operand[0] == '~':
            # bash expands only a LEADING tilde prefix in value operands
            # (no after-':' rule, unlike assignment values) and never
            # splits or globs the result.
            prefix, skip = self._tilde_prefix(operand)
            if skip:
                emit(prefix, True)
                i = skip
        while i < n:
            c = operand[i]
            if c == "'":
                end = operand.find("'", i + 1)
                seg = operand[i + 1:] if end == -1 else operand[i + 1:end]
                i = n if end == -1 else end + 1
                emit(seg, True)
            elif c == '"':
                seg, i = self._inner_dquote_segment(operand, i)
                emit(seg, True)
            elif c == '\\' and i + 1 < n:
                emit(operand[i + 1], True)
                i += 2
            elif c == '$' and i + 1 < n and operand[i + 1] == "'":
                seg, i = self._inline_ansi_c(operand, i)
                emit(seg, True)
            elif c == '$' and i + 1 < n and operand[i + 1] == '"':
                # Locale string $"...": double-quoted content (untranslated).
                seg, i = self._inner_dquote_segment(operand, i)
                emit(seg, True)
            elif c in '$`':
                expanded, i = self._expand_one_dollar(operand, i)
                # A nested operand's protection propagates out (bash:
                # ${x:-${z:-'a b'}} stays one field).
                nested = getattr(expanded, 'segments', None)
                if nested is not None:
                    for text, protected in nested:
                        emit(text, protected)
                else:
                    emit(expanded, False)
            else:
                emit(c, False)
                i += 1
        return out

    def _value_dq_text(self, operand: str, decode_ansi: bool) -> str:
        """Expand a value operand whose ``${...}`` sits inside double quotes.

        bash rules (probed 3.2–5.2, tmp/probes-r17t1-quoting/): single
        quotes are literal characters; an embedded ``"`` is removed and
        TOGGLES the effective quote state — outside embedded quotes the
        double-quote backslash rules apply (``\\$ \\" \\\\ \\``` processed,
        others kept), inside them a backslash escapes ANY character; a
        simple ``$name`` scan runs across embedded quote marks (consuming
        them), so ``"${x:-a"$y"c}"`` reads the variable ``yc``; ``$"..."``
        is a locale string; ``$'...'`` decodes only for lexed words
        (*decode_ansi*), never for heredoc-like string data. No tilde
        expansion, no splitting/globbing (the enclosing quotes protect
        the result).
        """
        out: List[str] = []
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
                    out.append(nxt)
                    i += 2
                else:
                    out.append(c)
                    i += 1
            elif c == '$' and i + 1 < n and operand[i + 1] == "'" and decode_ansi:
                seg, i = self._inline_ansi_c(operand, i)
                out.append(seg)
            elif c == '$' and i + 1 < n and operand[i + 1] == '"':
                seg, i = self._inner_dquote_segment(operand, i)
                out.append(seg)
            elif c == '$' and i + 1 < n and (operand[i + 1].isalnum()
                                             or operand[i + 1] == '_'):
                expanded, i, inner = self._dq_name_scan(operand, i, inner)
                out.append(expanded)
            elif c in '$`':
                expanded, i = self._expand_one_dollar(
                    operand, i, quote_ctx=DQ_WORD if decode_ansi else DQ_STRING)
                out.append(str(expanded))
            else:
                out.append(c)
                i += 1
        return ''.join(out)

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
            expanded, i = self._expand_one_dollar(operand, i)
            return str(expanded), i, inner
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
        return self.expand_variable('$' + ''.join(name)), j, inner

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
                add_active(expanded)
            else:
                buf.append(c)
                i += 1
        flush()
        return parts
