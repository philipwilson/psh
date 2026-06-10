"""Executor/builtin correctness sweep (v0.268.0) — bash-pinned.

Covers: nameref circular-reference diagnostics, non-retroactive
declare -u/-l/-i, type -t keyword reporting, $"..." locale strings,
and $_ last-argument tracking.
"""

import pytest


def run(shell, cmd):
    shell.run_command(cmd)
    return shell.get_stdout()


class TestNamerefCycles:
    def test_write_through_cycle_fails(self, shell, capsys):
        # bash: "warning: a: circular name reference", assignment fails
        rc = shell.run_command('declare -n a=b; declare -n b=a; a=5')
        captured = capsys.readouterr()
        assert rc == 1
        assert "circular name reference" in captured.err

    def test_read_through_cycle_is_empty_and_warns(self, shell, capsys):
        rc = shell.run_command('declare -n a=b; declare -n b=a; echo "[${a}]"')
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out == "[]\n"
        assert "circular name reference" in captured.err

    def test_simple_read_through_cycle(self, shell, capsys):
        rc = shell.run_command('declare -n a=b; declare -n b=a; echo "[$a]"')
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out == "[]\n"
        assert "circular name reference" in captured.err

    def test_unset_through_cycle_succeeds(self, shell, capsys):
        rc = shell.run_command('declare -n a=b; declare -n b=a; unset a; echo "rc=$?"')
        captured = capsys.readouterr()
        assert rc == 0
        assert "rc=0" in captured.out
        assert "circular name reference" in captured.err

    def test_creating_cycle_is_not_an_error(self, shell, capsys):
        rc = shell.run_command('declare -n a=b; declare -n b=a; echo after')
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out == "after\n"

    def test_self_reference_rejected_at_declare(self, shell, capsys):
        shell.run_command('declare -n r=r; r=1; echo "rc=$?"')
        captured = capsys.readouterr()
        assert "r: nameref variable self references not allowed" in captured.err

    def test_normal_nameref_still_works(self, shell, capsys):
        shell.run_command('declare -n r=x; x=1; r=2; echo "$x"')
        assert capsys.readouterr().out == "2\n"

    def test_nameref_with_operator_still_works(self, shell, capsys):
        shell.run_command('declare -n r=x; x=hello; echo "${r%lo}"')
        assert capsys.readouterr().out == "hel\n"


class TestNonRetroactiveAttributes:
    """declare -u/-l/-i transform future assignments only (bash)."""

    def test_declare_u_keeps_existing_value(self, captured_shell):
        assert run(captured_shell, 'u=abc; declare -u u; echo "$u"') == "abc\n"

    def test_declare_u_transforms_next_assignment(self, captured_shell):
        assert run(captured_shell,
                   'u=abc; declare -u u; u=def; echo "$u"') == "DEF\n"

    def test_declare_l_keeps_existing_value(self, captured_shell):
        assert run(captured_shell, 'l=ABC; declare -l l; echo "$l"') == "ABC\n"

    def test_declare_i_keeps_existing_value(self, captured_shell):
        assert run(captured_shell, 'x="2+3"; declare -i x; echo "$x"') == "2+3\n"

    def test_declare_i_evaluates_next_assignment(self, captured_shell):
        assert run(captured_shell,
                   'x="2+3"; declare -i x; x=$x; echo "$x"') == "5\n"

    def test_declare_u_with_value_still_transforms(self, captured_shell):
        assert run(captured_shell, 'declare -u u=abc; echo "$u"') == "ABC\n"


class TestTypeKeywords:
    @pytest.mark.parametrize("kw", ["if", "while", "for", "case", "do",
                                    "done", "fi", "time", "in", "{", "[["])
    def test_type_t_keyword(self, captured_shell, kw):
        rc = captured_shell.run_command(f"type -t '{kw}'")
        assert rc == 0
        assert captured_shell.get_stdout() == "keyword\n"

    def test_type_long_form(self, captured_shell):
        captured_shell.run_command("type if")
        assert captured_shell.get_stdout() == "if is a shell keyword\n"

    def test_function_beats_nothing_but_keyword_beats_function(self, captured_shell):
        # A function named like a keyword: bash still reports keyword first
        captured_shell.run_command("type -t echo")
        assert captured_shell.get_stdout() == "builtin\n"


class TestLocaleStrings:
    """$"..." is treated as a plain double-quoted string."""

    def test_simple(self, captured_shell):
        assert run(captured_shell, 'echo $"hello world"') == "hello world\n"

    def test_in_assignment(self, captured_shell):
        assert run(captured_shell, 'x=$"loc"; echo "$x"') == "loc\n"

    def test_in_composite_word(self, captured_shell):
        assert run(captured_shell, 'echo pre$"mid"post') == "premidpost\n"

    def test_adjacent_locale_strings(self, captured_shell):
        assert run(captured_shell, 'echo $"a b"$"c"') == "a bc\n"

    def test_expansion_inside(self, captured_shell):
        assert run(captured_shell, 'u=we; echo $"hi $u"') == "hi we\n"

    def test_plain_dollar_still_literal(self, captured_shell):
        assert run(captured_shell, 'echo "$"') == "$\n"

    def test_trailing_dollar_still_literal(self, captured_shell):
        assert run(captured_shell, 'echo a$') == "a$\n"


class TestLastArgument:
    def test_underscore_is_previous_last_arg(self, captured_shell):
        assert run(captured_shell, 'true x y; echo "$_"') == "y\n"

    def test_underscore_with_no_args_is_command(self, captured_shell):
        assert run(captured_shell, 'true; echo "$_"') == "true\n"

    def test_underscore_updates_per_command(self, captured_shell):
        assert run(captured_shell, 'true one; true two; echo "$_"') == "two\n"

    def test_underscore_after_redirect(self, captured_shell):
        assert run(captured_shell, 'echo hi >/dev/null; echo "$_"') == "hi\n"
