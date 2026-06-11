"""Bash-pinned tests for ${...:offset:length} slicing (all forms).

Slice parsing/evaluation is unified in the canonical helpers in
psh/expansion/operators.py (_parse_slice_operand / _slice_elements /
_slice_scalar_subscript), shared by the scalar substring operator, the
joined positional/array paths, and quoted multi-field slicing.

Every expectation here was probe-verified against bash 5.2, including
the previously divergent edges:

* empty-but-present length is 0 everywhere (``${a[@]:1:}`` is empty);
* sparse indexed arrays slice by INDEX in every context (including
  assignment, ``x=${b[@]:3}``);
* a negative offset that resolves before the start yields an empty
  result (no clamping to 0: ``${@: -99}`` is empty);
* bounds are checked before the negative-length error
  (``${a[@]:9:-1}`` is empty, ``${a[@]:1:-1}`` aborts with status 1);
* a negative length or invalid arithmetic aborts the command (bash
  exits 1; previously psh printed a warning and continued);
* a scalar subscripted ``${s[@]:o:l}`` gets string substring semantics
  (one field when the start is in range, none otherwise).
"""


import subprocess
import sys


def run(shell, cmd):
    shell.run_command(cmd)
    return shell.get_stdout()


def run_script(cmd):
    """Run a command in a non-interactive psh (expansion errors are fatal
    in script mode, as in bash -c)."""
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestScalarSubstring:
    def test_offset(self, captured_shell):
        assert run(captured_shell, 'v=hello; echo "[${v:2}]"') == "[llo]\n"

    def test_offset_length(self, captured_shell):
        assert run(captured_shell, 'v=hello; echo "[${v:2:2}]"') == "[ll]\n"

    def test_negative_offset(self, captured_shell):
        assert run(captured_shell, 'v=hello; echo "[${v: -3}]"') == "[llo]\n"

    def test_negative_offset_parens(self, captured_shell):
        assert run(captured_shell, 'v=hello; echo "[${v:(-3):2}]"') == "[ll]\n"

    def test_negative_length(self, captured_shell):
        assert run(captured_shell, 'v=hello; echo "[${v:1:-1}]"') == "[ell]\n"

    def test_offset_past_end(self, captured_shell):
        assert run(captured_shell, 'v=hello; echo "[${v:10}]"') == "[]\n"

    def test_empty_length_is_zero(self, captured_shell):
        assert run(captured_shell, 'v=hello; echo "[${v:1:}]"') == "[]\n"

    def test_empty_offset(self, captured_shell):
        assert run(captured_shell, 'v=hello; echo "[${v::2}]"') == "[he]\n"

    def test_arithmetic_offset(self, captured_shell):
        assert run(captured_shell, 'v=hello; echo "[${v:1+1:2}]"') == "[ll]\n"

    def test_unset_var_in_length_is_zero(self, captured_shell):
        assert run(captured_shell,
                   'unset x; v=hello; echo "[${v:$((1+1)):x}]"') == "[]\n"

    def test_negative_offset_before_start_empty(self, captured_shell):
        assert run(captured_shell, 'v=hello; echo "[${v: -10}]"') == "[]\n"

    def test_bounds_checked_before_negative_length(self, captured_shell):
        # Out-of-range offset: empty, NO error (bash)
        assert run(captured_shell,
                   'v=hi; echo "[${v:9:-1}]"; echo after') == "[]\nafter\n"

    def test_negative_length_out_of_range_aborts(self):
        r = run_script('v=hello; echo "${v:0:-10}"; echo after')
        assert r.returncode == 1
        assert r.stdout == ""
        assert "substring expression < 0" in r.stderr

    def test_invalid_arithmetic_aborts(self):
        r = run_script('v=hello; echo "${v:bad@:2}"; echo after')
        assert r.returncode == 1
        assert r.stdout == ""


class TestArraySlicing:
    def test_basic(self, captured_shell):
        assert run(captured_shell,
                   'a=(1 2 3 4); echo "[${a[@]:1:2}]"') == "[2 3]\n"

    def test_negative_offset(self, captured_shell):
        assert run(captured_shell,
                   'a=(1 2 3 4); echo "[${a[@]: -2}]"') == "[3 4]\n"

    def test_negative_offset_before_start_empty(self, captured_shell):
        assert run(captured_shell,
                   'a=(1 2 3); echo "[${a[@]: -5}]"') == "[]\n"

    def test_empty_length_is_zero(self, captured_shell):
        assert run(captured_shell,
                   'a=(1 2 3 4); echo "[${a[@]:1:}]"') == "[]\n"

    def test_empty_length_in_assignment(self, captured_shell):
        assert run(captured_shell,
                   'a=(1 2 3 4); x=${a[@]:1:}; echo "[$x]"') == "[]\n"

    def test_star_subscript_joins(self, captured_shell):
        assert run(captured_shell,
                   'a=(q r s); IFS=-; echo "[${a[*]:1}]"') == "[r-s]\n"

    def test_star_negative_offset_before_start_empty(self, captured_shell):
        assert run(captured_shell,
                   'a=(1 2 3); echo "[${a[*]: -5}]"') == "[]\n"

    def test_quoted_fields(self, captured_shell):
        assert run(captured_shell,
                   'a=(1 2 3 4); printf "(%s)" "${a[@]:1:2}"; echo') == "(2)(3)\n"

    def test_arithmetic_length(self, captured_shell):
        assert run(captured_shell,
                   'a=(1 2 3 4); echo "[${a[@]:1:1+1}]"') == "[2 3]\n"

    def test_negative_length_aborts(self):
        r = run_script('a=(1 2 3); echo "${a[@]:1:-1}"; echo after')
        assert r.returncode == 1
        assert r.stdout == ""
        assert "substring expression < 0" in r.stderr

    def test_bounds_checked_before_negative_length(self, captured_shell):
        assert run(captured_shell,
                   'a=(1 2 3); echo "[${a[@]:9:-1}]"; echo after') == "[]\nafter\n"
        captured_shell.clear_output()
        assert run(captured_shell,
                   'a=(1 2 3); echo "[${a[@]:3:-1}]"; echo after') == "[]\nafter\n"


class TestSparseArraySlicing:
    """bash slices indexed arrays by INDEX, not element position."""

    def test_by_index_unquoted(self, captured_shell):
        assert run(captured_shell,
                   'b[2]=x; b[5]=y; b[9]=z; echo "[${b[@]:3}]"') == "[y z]\n"

    def test_by_index_with_length(self, captured_shell):
        assert run(captured_shell,
                   'b[2]=x; b[5]=y; b[9]=z; echo "[${b[@]:5:1}]"') == "[y]\n"

    def test_by_index_in_assignment(self, captured_shell):
        assert run(captured_shell,
                   'b[2]=x; b[5]=y; b[9]=z; x=${b[@]:3}; echo "[$x]"') == "[y z]\n"

    def test_negative_offset_from_max_index(self, captured_shell):
        # max index 9 → top 10; -2 → index 8 → only z
        assert run(captured_shell,
                   'b[2]=x; b[5]=y; b[9]=z; echo "[${b[@]: -2}]"') == "[z]\n"

    def test_negative_offset_before_start_empty(self, captured_shell):
        assert run(captured_shell,
                   'b[2]=x; b[5]=y; echo "[${b[@]: -7}]"') == "[]\n"

    def test_star_subscript_by_index(self, captured_shell):
        assert run(captured_shell,
                   'b[2]=x; b[5]=y; b[9]=z; echo "[${b[*]:3}]"') == "[y z]\n"

    def test_quoted_fields_by_index(self, captured_shell):
        assert run(captured_shell,
                   'b[2]=x; b[5]=y; b[9]=z; printf "(%s)" "${b[@]:3}"; echo') == "(y)(z)\n"

    def test_length_counts_elements(self, captured_shell):
        assert run(captured_shell,
                   'b[2]=x; b[5]=y; b[9]=z; echo "[${b[@]:0:2}]"') == "[x y]\n"


class TestPositionalSlicing:
    def test_basic(self, captured_shell):
        assert run(captured_shell,
                   'set -- a b c d; echo "[${@:2:2}]"') == "[b c]\n"

    def test_zero_includes_dollar_zero(self, captured_shell):
        assert run(captured_shell,
                   'set -- a b; x=${@:0:1}; [ "$x" = "$0" ] && echo same') == "same\n"

    def test_negative_offset(self, captured_shell):
        assert run(captured_shell,
                   'set -- a b c; echo "[${@: -1}]"') == "[c]\n"

    def test_negative_offset_boundary_includes_zero(self, captured_shell):
        # seq is [$0, a, b]: -3 reaches $0
        assert run(captured_shell,
                   'set -- a b; x=${@: -3:1}; [ "$x" = "$0" ] && echo same') == "same\n"

    def test_negative_offset_before_start_empty(self, captured_shell):
        assert run(captured_shell,
                   'set -- a b; printf "(%s)" "${@: -5}"; echo') == "()\n"
        captured_shell.clear_output()
        assert run(captured_shell,
                   'set -- a b; echo "[${*: -5}]"') == "[]\n"

    def test_empty_length_is_zero(self, captured_shell):
        assert run(captured_shell,
                   'set -- a b c; echo "[${@:1:}]"') == "[]\n"

    def test_star_slicing_joins_with_ifs(self, captured_shell):
        assert run(captured_shell,
                   'set -- a b c d; IFS=-; echo "[${*:2:2}]"') == "[b-c]\n"

    def test_zero_length(self, captured_shell):
        assert run(captured_shell,
                   'set -- a b c; echo "[${@:2:0}]"') == "[]\n"

    def test_negative_length_aborts(self):
        r = run_script('set -- a b c; echo "${@:2:-1}"; echo after')
        assert r.returncode == 1
        assert r.stdout == ""

    def test_bounds_checked_before_negative_length(self, captured_shell):
        assert run(captured_shell,
                   'set -- a b c; echo "[${@:9:-1}]"; echo after') == "[]\nafter\n"


class TestScalarSubscriptSlicing:
    """bash gives ${s[@]:o:l} STRING substring semantics for scalars."""

    def test_substring_unquoted(self, captured_shell):
        assert run(captured_shell,
                   's=hello; echo "[${s[@]:1:3}]"') == "[ell]\n"

    def test_substring_star(self, captured_shell):
        assert run(captured_shell,
                   's=hello; x=${s[*]: -3}; echo "[$x]"') == "[llo]\n"

    def test_substring_negative_length(self, captured_shell):
        assert run(captured_shell,
                   's=hello; echo "[${s[@]:1:-1}]"') == "[ell]\n"

    def test_in_range_start_yields_one_field(self, captured_shell):
        assert run(captured_shell,
                   's=hello; set -- "${s[@]:5}"; echo "n=$#"') == "n=1\n"
        captured_shell.clear_output()
        assert run(captured_shell,
                   's=hello; set -- "${s[@]:1:2}"; echo "n=$#"') == "n=1\n"

    def test_out_of_range_start_yields_no_field(self, captured_shell):
        assert run(captured_shell,
                   's=hello; set -- "${s[@]:9}"; echo "n=$#"') == "n=0\n"
        captured_shell.clear_output()
        assert run(captured_shell,
                   's=hello; set -- "${s[@]: -9}"; echo "n=$#"') == "n=0\n"

    def test_empty_scalar_in_range(self, captured_shell):
        assert run(captured_shell,
                   's=""; set -- "${s[@]:0}"; echo "n=$#"') == "n=1\n"

    def test_unset_yields_no_field(self, captured_shell):
        assert run(captured_shell,
                   'unset q; set -- "${q[@]:0}"; echo "n=$#"') == "n=0\n"
