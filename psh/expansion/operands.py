"""Operand mini-expansion for pattern/replacement operators.

Operands of ${var#pat}, ${var/pat/repl}, etc. get their own expansion
pass: quoted text and quoted expansion results are glob-escaped (match
literally) while unquoted text stays glob-active — bash semantics
pinned in v0.266.0. Mixed into VariableExpander (variable.py).
"""


class OperandOpsMixin:
    """Expansion of pattern/replacement operands with quote awareness."""

    def _expand_operand(self, operand: str) -> str:
        """Expand a conditional-operator operand (${x:-OPERAND}).

        One surrounding level of quotes is removed (bash): single quotes
        keep the text literal, double quotes expand without tilde.
        """
        if len(operand) >= 2 and operand[0] == "'" and operand[-1] == "'":
            return operand[1:-1]
        if len(operand) >= 2 and operand[0] == '"' and operand[-1] == '"':
            return self.expand_string_variables(operand[1:-1])
        return self._expand_tilde_in_operand(self.expand_string_variables(operand))

    def _expand_tilde_in_operand(self, text: str) -> str:
        """Apply tilde expansion to parameter expansion operand values."""
        if text.startswith('~'):
            return self.shell.expansion_manager.tilde_expander.expand(text)
        return text

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
        from ..lexer.cmdsub_scanner import find_command_substitution_end
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

    _GLOB_SPECIALS = set('\\*?[]()|@!+')

    @classmethod
    def glob_escape(cls, text: str) -> str:
        """Backslash-escape glob syntax so the text matches literally."""
        return ''.join('\\' + c if c in cls._GLOB_SPECIALS else c
                       for c in text)

    def _expand_one_dollar(self, text: str, i: int):
        """Expand the single $-construct or `...` at text[i].

        Returns (expanded_text, index_past_construct); a '$' that starts
        nothing expandable stays literal.
        """
        from ..lexer.cmdsub_scanner import find_command_substitution_end
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
                return self.expand_variable(text[i:end]), end
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
        """Expand a leading unquoted ~ or ~user prefix of an operand.

        Returns (expanded_prefix, chars_consumed); (``''``, 0) when the
        prefix isn't a plain tilde word.
        """
        end = operand.find('/')
        prefix = operand if end == -1 else operand[:end]
        if any(ch in prefix for ch in '\'"\\$`&'):
            return '', 0
        expanded = self.shell.expansion_manager.tilde_expander.expand(prefix)
        if expanded == prefix:
            return '', 0
        return expanded, len(prefix)

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
        parts = []
        buf = []

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
            elif c in '$`':
                expanded, i = self._expand_one_dollar(operand, i)
                add_active(expanded)
            else:
                buf.append(c)
                i += 1
        flush()
        return parts
