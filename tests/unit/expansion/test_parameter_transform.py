"""Tests for ${parameter@OP} transformation operators.

Operators implemented (verified against bash 5.2):
  @Q  quote for reuse as input        @U  uppercase all
  @E  expand ANSI-C backslash escapes @u  uppercase first
  @P  prompt-string expansion         @L  lowercase all
  @a  attribute-flag letters          @A  assignment/declare form

Not implemented: @K / @k (associative key/value display).
"""

import pytest


class TestQuoteTransform:
    """${var@Q} - quote so the value can be reused as shell input."""

    def test_simple_word_is_single_quoted(self, shell, capsys):
        shell.run_command('x=abc; echo "${x@Q}"')
        assert capsys.readouterr().out.strip() == "'abc'"

    def test_spaces(self, shell, capsys):
        shell.run_command('x="a b"; echo "${x@Q}"')
        assert capsys.readouterr().out.strip() == "'a b'"

    def test_embedded_single_quote(self, shell, capsys):
        shell.run_command("""x="a'b"; echo "${x@Q}" """)
        assert capsys.readouterr().out.strip() == "'a'\\''b'"

    def test_empty_set_value(self, shell, capsys):
        shell.run_command('x=""; echo "[${x@Q}]"')
        assert capsys.readouterr().out.strip() == "['']"

    def test_unset_yields_nothing(self, shell, capsys):
        shell.run_command('unset u; echo "[${u@Q}]"')
        # bash: an unset parameter transforms to the empty string (no '').
        assert capsys.readouterr().out.strip() == "[]"

    def test_control_char_uses_ansi_c_form(self, shell, capsys):
        shell.run_command("x=$'a\\tb'; printf '%s' \"${x@Q}\"")
        assert capsys.readouterr().out == "$'a\\tb'"


class TestCaseTransforms:
    """${var@U}, ${var@u}, ${var@L}."""

    def test_upper_all(self, shell, capsys):
        shell.run_command('x=aBc; echo "${x@U}"')
        assert capsys.readouterr().out.strip() == "ABC"

    def test_upper_first(self, shell, capsys):
        shell.run_command('x=aBc; echo "${x@u}"')
        assert capsys.readouterr().out.strip() == "ABc"

    def test_lower_all(self, shell, capsys):
        shell.run_command('x=aBc; echo "${x@L}"')
        assert capsys.readouterr().out.strip() == "abc"


class TestEscapeTransform:
    """${var@E} - expand backslash escapes as in $'...'."""

    def test_tab_and_newline(self, shell, capsys):
        shell.run_command(r'x="a\tb\nc"; printf "%s" "${x@E}"')
        assert capsys.readouterr().out == "a\tb\nc"

    def test_hex_escape(self, shell, capsys):
        shell.run_command(r'x="\x41\x42"; echo "${x@E}"')
        assert capsys.readouterr().out.strip() == "AB"


class TestPromptTransform:
    """${var@P} - expand prompt escapes."""

    def test_username_escape(self, shell, capsys):
        import getpass
        shell.run_command(r'x="\u"; echo "${x@P}"')
        assert capsys.readouterr().out.strip() == getpass.getuser()


class TestAttributeTransforms:
    """${var@a} (flags) and ${var@A} (assignment form)."""

    def test_attr_integer(self, shell, capsys):
        shell.run_command('declare -i n=5; echo "${n@a}"')
        assert capsys.readouterr().out.strip() == "i"

    def test_attr_readonly_export(self, shell, capsys):
        shell.run_command('declare -rx C=1; echo "${C@a}"')
        assert capsys.readouterr().out.strip() == "rx"

    def test_attr_order_airx(self, shell, capsys):
        shell.run_command('declare -airx z=5; echo "${z@a}"')
        assert capsys.readouterr().out.strip() == "airx"

    def test_attr_none_is_empty(self, shell, capsys):
        shell.run_command('p=1; echo "[${p@a}]"')
        assert capsys.readouterr().out.strip() == "[]"

    def test_assignment_scalar(self, shell, capsys):
        shell.run_command('x="a b"; echo "${x@A}"')
        assert capsys.readouterr().out.strip() == "x='a b'"

    def test_assignment_integer(self, shell, capsys):
        shell.run_command('declare -i n=5; echo "${n@A}"')
        assert capsys.readouterr().out.strip() == "declare -i n='5'"


class TestArrayTransforms:
    """${arr[@]@OP} - per-element transforms and the @A declare form."""

    def test_array_quote_each_element(self, shell, capsys):
        shell.run_command('a=(x "y z"); echo "${a[@]@Q}"')
        assert capsys.readouterr().out.strip() == "'x' 'y z'"

    def test_array_uppercase_each(self, shell, capsys):
        shell.run_command('a=(ab cd); echo "${a[@]@U}"')
        assert capsys.readouterr().out.strip() == "AB CD"

    def test_array_attr_per_element(self, shell, capsys):
        shell.run_command('a=(x y); echo "${a[@]@a}"')
        assert capsys.readouterr().out.strip() == "a a"

    def test_array_assignment_form(self, shell, capsys):
        shell.run_command('a=(x "y z"); echo "${a[@]@A}"')
        assert capsys.readouterr().out.strip() == 'declare -a a=([0]="x" [1]="y z")'

    def test_positional_quote_each(self, shell, capsys):
        shell.run_command('set -- a "b c"; echo "${@@Q}"')
        assert capsys.readouterr().out.strip() == "'a' 'b c'"


class TestBashParity:
    """Compare a representative set directly against bash via subprocess."""

    @pytest.mark.parametrize("script", [
        'x=abc; echo "${x@Q}"',
        'x="a b c"; echo "${x@Q}"',
        'x=Hello; echo "${x@U}${x@L}${x@u}"',
        r'x="a\tb"; printf "%s" "${x@E}"',
        'x="key val"; echo "${x@A}"',
        'declare -i n=42; echo "${n@A} ${n@a}"',
        'a=(one "two three"); echo "${a[@]@Q}"',
        'set -- p "q r"; echo "${@@Q}"',
    ])
    def test_matches_bash(self, script):
        import subprocess
        import sys
        psh = subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                             capture_output=True, text=True)
        bash = subprocess.run(['bash', '-c', script],
                              capture_output=True, text=True)
        assert psh.stdout == bash.stdout
        assert psh.returncode == bash.returncode
