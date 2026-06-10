"""Batch 8: non-colon parameter operators, pattern deletion, null IFS.

Non-colon operators (${x-w}, ${x=w}, ${x+w}, ${x?w}) test only for *unset*,
unlike the colon variants which test unset-or-null. Also covers ${x//pat}
deletion (omitted replacement) and null vs unset IFS for $* joining.
"""



class TestNonColonDefault:
    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_unset_uses_default(self, shell, capsys):
        assert self._out(shell, capsys, 'unset x; echo "[${x-def}]"') == "[def]\n"

    def test_null_does_not_use_default(self, shell, capsys):
        assert self._out(shell, capsys, 'x=; echo "[${x-def}]"') == "[]\n"

    def test_set_uses_value(self, shell, capsys):
        assert self._out(shell, capsys, 'x=v; echo "[${x-def}]"') == "[v]\n"


class TestNonColonAlternative:
    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_set_yields_alt(self, shell, capsys):
        assert self._out(shell, capsys, 'x=v; echo "[${x+alt}]"') == "[alt]\n"

    def test_null_yields_alt(self, shell, capsys):
        # Plus operator: set (even empty) -> alt.
        assert self._out(shell, capsys, 'x=; echo "[${x+alt}]"') == "[alt]\n"

    def test_unset_yields_empty(self, shell, capsys):
        assert self._out(shell, capsys, 'unset x; echo "[${x+alt}]"') == "[]\n"


class TestNonColonAssign:
    def test_assign_when_unset(self, shell, capsys):
        assert shell.run_command('unset x; echo "[${x=val}]"; echo "[$x]"') == 0
        assert capsys.readouterr().out == "[val]\n[val]\n"

    def test_no_assign_when_null(self, shell, capsys):
        assert shell.run_command('x=; echo "[${x=val}]"; echo "[$x]"') == 0
        # null stays null (non-colon = does not assign to a set-but-empty var)
        assert capsys.readouterr().out == "[]\n[]\n"


class TestNonColonError:
    def test_unset_errors_127(self, shell, capsys):
        rc = shell.run_command('unset x; echo "${x?boom}"')
        assert rc == 127
        assert "boom" in capsys.readouterr().err

    def test_set_no_error(self, shell, capsys):
        assert shell.run_command('x=v; echo "${x?boom}"') == 0
        assert capsys.readouterr().out == "v\n"


class TestPatternDeletion:
    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_delete_all(self, shell, capsys):
        assert self._out(shell, capsys, 'x=hello; echo "${x//l}"') == "heo\n"

    def test_delete_first(self, shell, capsys):
        assert self._out(shell, capsys, 'x=hello; echo "${x/l}"') == "helo\n"


class TestNullIfsJoin:
    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_null_ifs_concatenates_star(self, shell, capsys):
        assert self._out(shell, capsys, 'IFS=; set -- a b c; echo "$*"') == "abc\n"

    def test_null_ifs_concatenates_array_star(self, shell, capsys):
        assert self._out(shell, capsys, 'IFS=; a=(x y z); echo "${a[*]}"') == "xyz\n"

    def test_unset_ifs_joins_with_space(self, shell, capsys):
        assert self._out(shell, capsys, 'unset IFS; set -- a b c; echo "$*"') == "a b c\n"


class TestNonColonRegression:
    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_colon_minus_still_works(self, shell, capsys):
        assert self._out(shell, capsys, 'x=; echo "[${x:-d}]"') == "[d]\n"

    def test_negative_array_index(self, shell, capsys):
        assert self._out(shell, capsys, 'a=(1 2 3); echo "${a[-1]}"') == "3\n"

    def test_array_case_mod_with_range(self, shell, capsys):
        assert self._out(shell, capsys,
                         'arr=("hello123" "WORLD456"); echo "${arr[@]^^[a-m]}"') == "HELLo123 WORLD456\n"
