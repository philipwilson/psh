"""Batch 7: empty-field handling and for-loop word-splitting/glob consolidation.

Covers: an unquoted empty/unset expansion contributing zero fields (#1), the
for/select loop preserving empty fields from a non-whitespace IFS (#2), and the
for-loop honoring nullglob (#23).
"""



class TestEmptyUnquotedExpansion:
    def _eval(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_unset_yields_no_field(self, shell, capsys):
        assert self._eval(shell, capsys, 'set -- $emptyvar; echo "count=$#"') == "count=0\n"

    def test_unset_then_word(self, shell, capsys):
        out = self._eval(shell, capsys, 'set -- $emptyvar foo; echo "count=$# first=[$1]"')
        assert out == "count=1 first=[foo]\n"

    def test_quoted_empty_still_a_field(self, shell, capsys):
        # Quoted empty string is a genuine (empty) field.
        assert self._eval(shell, capsys, 'set -- "$emptyvar"; echo "count=$#"') == "count=1\n"


class TestForLoopEmptyFields:
    def _lines(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_interior_empty_field(self, shell, capsys):
        out = self._lines(shell, capsys, 'IFS=:; v="a::b"; for x in $v; do echo "[$x]"; done')
        assert out == "[a]\n[]\n[b]\n"

    def test_leading_empty_field(self, shell, capsys):
        out = self._lines(shell, capsys, 'IFS=:; v=":a:b"; for x in $v; do echo "[$x]"; done')
        assert out == "[]\n[a]\n[b]\n"


class TestForLoopNullglob:
    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_nullglob_no_iterations(self, shell, capsys):
        out = self._out(shell, capsys,
                        'shopt -s nullglob; for f in zzz_nomatch*; do echo "iter=$f"; done; echo done')
        assert out == "done\n"

    def test_without_nullglob_literal(self, shell, capsys):
        out = self._out(shell, capsys,
                        'for f in zzz_nomatch*; do echo "iter=$f"; done')
        assert out == "iter=zzz_nomatch*\n"
