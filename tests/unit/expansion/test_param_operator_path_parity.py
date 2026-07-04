"""Colon operators work through the collapsed string-expansion path.

The dual engines were collapsed so that string-context parameter expansion
(inside double quotes / assignment values) delegates to the same
expand_parameter_direct/_apply_operator path as the AST path, instead of a
separate inline copy. These tests exercise the colon operators in a quoted
(string-path) context with explicit expected values.
"""



class TestColonOperatorsStringPath:
    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_default_unset(self, shell, capsys):
        assert self._out(shell, capsys, 'unset x; echo "[${x:-d}]"') == "[d]\n"

    def test_default_null(self, shell, capsys):
        assert self._out(shell, capsys, 'x=; echo "[${x:-d}]"') == "[d]\n"

    def test_default_set(self, shell, capsys):
        assert self._out(shell, capsys, 'x=v; echo "[${x:-d}]"') == "[v]\n"

    def test_default_nested_expansion(self, shell, capsys):
        assert self._out(shell, capsys, 'unset x; y=Y; echo "[${x:-pre$y}]"') == "[preY]\n"

    def test_alt_set(self, shell, capsys):
        assert self._out(shell, capsys, 'x=v; echo "[${x:+a}]"') == "[a]\n"

    def test_alt_null(self, shell, capsys):
        assert self._out(shell, capsys, 'x=; echo "[${x:+a}]"') == "[]\n"

    def test_assign_unset(self, shell, capsys):
        assert self._out(shell, capsys, 'unset x; echo "${x:=v}"; echo "$x"') == "v\nv\n"

    def test_assign_in_quoted_value(self, shell, capsys):
        # Assignment happens even when the expansion is in a quoted RHS.
        assert self._out(shell, capsys, 'unset x; y="${x:=assigned}"; echo "$x/$y"') == "assigned/assigned\n"

    def test_error_set_ok(self, shell, capsys):
        assert self._out(shell, capsys, 'x=v; echo "[${x:?msg}]"') == "[v]\n"

    def test_error_unset_discards_line(self, shell, capsys):
        # ${x:?msg} on unset: fatal expansion error. An interactive/embedded
        # shell discards the line with status 1 (bash -i: $? is 1; the 127
        # -c exit status is pinned by the subprocess tests in
        # tests/integration/test_fatal_expansion_model.py).
        rc = shell.run_command('unset x; echo "${x:?boom}"')
        assert rc == 1
        assert "boom" in capsys.readouterr().err

    def test_colon_ops_on_array_element(self, shell, capsys):
        assert self._out(shell, capsys, 'a=(x y); echo "[${a[5]:-d}]"') == "[d]\n"
        assert self._out(shell, capsys, 'a=(x y); echo "[${a[0]:-d}]"') == "[x]\n"

    def test_substring_unaffected(self, shell, capsys):
        assert self._out(shell, capsys, 'x=hello; echo "[${x:1:3}]"') == "[ell]\n"
