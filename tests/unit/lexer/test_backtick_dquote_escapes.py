r"""Backtick escape handling by quote context (r17 H6).

Inside backticks a backslash quotes backslash, backtick, and dollar.
When the backtick substitution itself sits inside double quotes, bash
ALSO strips a backslash before a double quote: ``echo "`echo \"q\"`"``
prints ``q``. The rule is backtick-specific — a BARE backtick keeps
``\"`` and so does ``$(...)`` inside double quotes (both print ``"q"``).

Regression tests for reappraisal #17 finding H6: the unescape set in
``ExpansionParser.parse_backtick_substitution`` ignored the
``quote_context`` parameter that its double-quote caller already passed.
Pinned to bash 5.2 (probe battery in tmp/probes-r17t1-quoting/).
"""
from psh.lexer import tokenize


def token_values(src):
    return [(t.type.name, t.value) for t in tokenize(src)]


class TestLexerUnescapeSet:
    def test_dquoted_backtick_unescapes_dquote(self):
        # The token value carries the UNESCAPED body: \" -> ".
        values = [v for _, v in token_values(r'echo "`echo \"q\"`"')]
        assert '`echo "q"`' in values

    def test_bare_backtick_keeps_escaped_dquote(self):
        values = [v for _, v in token_values(r'echo `echo \"q\"`')]
        assert r'`echo \"q\"`' in values

    def test_dquoted_backtick_still_unescapes_dollar(self):
        values = [v for _, v in token_values(r'echo "`echo \$y`"')]
        assert '`echo $y`' in values

    def test_bare_backtick_unescapes_dollar(self):
        values = [v for _, v in token_values(r'echo `echo \$y`')]
        assert '`echo $y`' in values


class TestBacktickDquoteBehavior:
    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_report_case_simple(self, shell, capsys):
        assert self._out(shell, capsys, r'echo "`echo \"q\"`"') == "q\n"

    def test_report_case_variable(self, shell, capsys):
        assert self._out(shell, capsys,
                         r'x=hi; echo "`echo \"$x\"`"') == "hi\n"

    def test_report_case_embedded(self, shell, capsys):
        assert self._out(shell, capsys,
                         r'echo "pre `echo \"a b\"` post"') == "pre a b post\n"

    def test_contrast_bare_backtick_keeps_quotes(self, shell, capsys):
        assert self._out(shell, capsys, r'echo `echo \"q\"`') == '"q"\n'

    def test_contrast_dollar_paren_keeps_quotes(self, shell, capsys):
        assert self._out(shell, capsys, r'echo "$(echo \"q\")"') == '"q"\n'

    def test_nested_backticks_both_contexts(self, shell, capsys):
        assert self._out(shell, capsys, r'echo `echo \`echo hi\``') == "hi\n"
        assert self._out(shell, capsys, r'echo "`echo \`echo hi\``"') == "hi\n"

    def test_escaped_dollar_expands_in_body(self, shell, capsys):
        # \$ inside the body defers expansion to the child: `echo \$y`
        # runs `echo $y` in the substitution shell.
        assert self._out(shell, capsys, r'y=1; echo "`echo \$y`"') == "1\n"

    def test_heredoc_backtick_keeps_escaped_dquote(self):
        # The dquote rule does NOT apply to heredoc bodies (probed: bash
        # keeps \" -> "q" there). Subprocess: the heredoc feeds an
        # external cat, whose fd-level output capsys cannot see.
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'cat <<EOF\n`echo \\"q\\"`\nEOF'],
            capture_output=True, text=True)
        assert result.stdout == '"q"\n'

    def test_dquoted_operand_backtick_keeps_escaped_dquote(self, shell, capsys):
        # Backtick inside a dquoted parameter-expansion OPERAND (the
        # H5/H6 seam): bash does NOT apply the dquote unescape there —
        # the \" survives into the substitution (probed: bash prints "q").
        assert self._out(shell, capsys,
                         r'echo "${x:-`echo \"q\"`}"') == '"q"\n'
