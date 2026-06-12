"""Behavior fixes that rode along with the one-parameter-parser unification.

The four legacy ``${...}`` parser copies disagreed on these forms, so psh's
behavior depended on the path (command argument vs heredoc/string context
vs quoted array expansion). Each divergence was adjudicated against
bash 5.2 (see the fix families F1-F5 in test_param_parser_differential.py);
every expected value below is the probed bash output.

Heredoc cases run psh in a subprocess: the heredoc body is expanded on the
string path, and ``cat`` writes at fd level (invisible to capsys).
"""

import subprocess
import sys


def psh_out(script: str) -> str:
    result = subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


class TestConditionalAfterAtSubscript:
    """F1: ':-'/':+'/':='/':?' after [@]/[*] are conditional operators."""

    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_default_unset_unquoted(self, shell, capsys):
        assert self._out(shell, capsys,
                         'unset a; echo "[${a[@]:-def}]"') == "[def]\n"

    def test_default_set(self, shell, capsys):
        assert self._out(shell, capsys,
                         'a=(1 2); echo "[${a[@]:-def}]"') == "[1 2]\n"

    def test_default_unset_heredoc(self):
        # The string path used to misparse this as a slice with offset -def.
        assert psh_out('unset a; cat <<EOF\n${a[@]:-def}\nEOF') == "def\n"

    def test_alt_set_heredoc(self):
        assert psh_out('a=(1 2); cat <<EOF\n${a[@]:+y}\nEOF') == "y\n"

    def test_assign_set_heredoc(self):
        # Used to abort with 'invalid offset or length' on the string path.
        assert psh_out('a=(1 2); cat <<EOF\n${a[@]:=d}\nEOF') == "1 2\n"

    def test_slice_still_slices(self, shell, capsys):
        assert self._out(shell, capsys,
                         'a=(1 2 3); echo "${a[@]: -2}"') == "2 3\n"
        assert self._out(shell, capsys,
                         'a=(1 2 3 4); echo "${a[@]:1:2}"') == "2 3\n"


class TestNonColonAfterSubscript:
    """F2: '-'/'='/'+'/'?' after a closed ']' are operators (bash)."""

    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_element_minus_set(self, shell, capsys):
        assert self._out(shell, capsys,
                         'arr=(hi yo); echo "[${arr[0]-d}]"') == "[hi]\n"

    def test_element_minus_unset(self, shell, capsys):
        assert self._out(shell, capsys,
                         'arr=(hi yo); echo "[${arr[5]-d}]"') == "[d]\n"

    def test_scalar_subscript_plus(self, shell, capsys):
        # x[0] of a scalar x is set (bash); x[9] is not.
        assert self._out(shell, capsys,
                         'x=hello; echo "[${x[0]+s}][${x[9]+s}]"') == "[s][]\n"

    def test_whole_array_minus(self, shell, capsys):
        assert self._out(shell, capsys,
                         'unset a; echo "[${a[@]-def}]"') == "[def]\n"
        assert self._out(shell, capsys,
                         'a=(1 2); echo "[${a[@]-def}]"') == "[1 2]\n"

    def test_arith_subscript_plus(self, shell, capsys):
        assert self._out(shell, capsys,
                         'a=(p q r); i=0; echo "[${a[i+1]+x}]"') == "[x]\n"


class TestScalarSubscriptResolution:
    """${x[0]} of a scalar resolves to $x on every path (bash)."""

    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_length_of_scalar_element(self, shell, capsys):
        # Was '0' on the AST path, '5' in heredocs.
        assert self._out(shell, capsys,
                         'x=hello; echo "${#x[0]}"') == "5\n"

    def test_default_on_scalar_element(self, shell, capsys):
        assert self._out(shell, capsys,
                         'x=hello; echo "${x[0]:-d}"') == "hello\n"
        assert self._out(shell, capsys,
                         'x=hello; echo "${x[1]:-d}"') == "d\n"

    def test_case_mod_on_scalar_element(self, shell, capsys):
        assert self._out(shell, capsys,
                         'x=hello; echo "${x[0]^^}"') == "HELLO\n"

    def test_substring_on_scalar_element(self, shell, capsys):
        assert self._out(shell, capsys,
                         'x=hello; echo "${x[0]:1:3}"') == "ell\n"


class TestOperandWithTransformLetters:
    """F3: ${v:-x@Q} is ':-' with literal operand 'x@Q' (scan order)."""

    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_unset_yields_operand(self, shell, capsys):
        assert self._out(shell, capsys,
                         'unset v; echo "${v:-x@Q}"') == "x@Q\n"

    def test_set_yields_value(self, shell, capsys):
        assert self._out(shell, capsys, 'v=hi; echo "${v:-x@Q}"') == "hi\n"


class TestHashDisambiguation:
    """F4: ${#rest} is a length form only when rest is a parameter spec."""

    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_length_of_dash(self, shell, capsys):
        # ${#-} == length of $- (was the '-' operator on '#').
        out = self._out(shell, capsys, 'echo "${#-}"; echo "$-"')
        length, flags = out.splitlines()
        assert int(length) == len(flags)

    def test_hash_with_default_in_heredoc(self):
        # The string path used to expand a plain (unset) name '#:-default'.
        assert psh_out('set -- 1 2; cat <<EOF\n${#:-default}\nEOF') == "2\n"

    def test_hash_with_minus_default(self, shell, capsys):
        assert self._out(shell, capsys,
                         'set -- a b; echo "${#-d}"') == "2\n"


class TestElementIndirection:
    """F5: ${!arr[idx]} (non-@/*) is indirection through the element."""

    def _out(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out

    def test_indexed_element(self, shell, capsys):
        assert self._out(shell, capsys,
                         't=hello; a=(t); echo "${!a[0]}"') == "hello\n"

    def test_assoc_element(self, shell, capsys):
        assert self._out(
            shell, capsys,
            'declare -A h=([x]=t); t=val; echo "${!h[x]}"') == "val\n"

    def test_keys_still_keys(self, shell, capsys):
        assert self._out(shell, capsys,
                         'a=(x y z); echo "${!a[@]}"') == "0 1 2\n"


class TestAssocSliceStringPath:
    """Heredoc ${h[@]:0:1} slices elements (was substring of a repr)."""

    def test_assoc_slice_heredoc(self):
        assert psh_out(
            'declare -A h=([a]=1); cat <<EOF\n${h[@]:0:1}\nEOF') == "1\n"
