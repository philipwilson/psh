"""set / shift / exit argument + abort policy (builtins contracts cluster).

Pinned to bash 5.2.26 (probe battery, campaign fix/builtin-contracts).

Red→green anchors (all FAILED at base dff3e875):
- `set ""` raised IndexError ("string index out of range") under strict-errors.
- lone `set -` / `set +` installed "-"/"+" as $1; `set - a b` kept "-" as $1.
- `shift 1 2` silently ignored the extra operand (rc 0); bash: "too many
  arguments", rc 1, and the current input unit is discarded.
- `exit 7 8` ran the rest of the -c string; `exit abc 7` reported "too many
  arguments" (rc 1, continued) instead of the numeric error (exit 2).
"""
import subprocess
import sys

PSH = [sys.executable, "-m", "psh"]


def run_c(script):
    """Run `psh -c script` sealed from stdin; return (rc, stdout, stderr)."""
    p = subprocess.run(PSH + ["-c", script], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=30)
    return p.returncode, p.stdout, p.stderr


def run_script(body, tmp_path):
    """Run a multi-line script FILE so line-2 survival distinguishes a
    discarded input unit from a whole-shell exit."""
    path = tmp_path / "s.sh"
    path.write_text(body)
    p = subprocess.run(PSH + [str(path)], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=30)
    return p.returncode, p.stdout, p.stderr


class TestSetOperandPolicy:
    def test_empty_operand_sets_one_empty_param(self, captured_shell):
        """`set ""` no longer crashes; it sets one empty positional (bash)."""
        rc = captured_shell.run_command('set ""; echo "$#:[$1]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "1:[]\n"

    def test_empty_operand_then_more(self, captured_shell):
        rc = captured_shell.run_command('set "" b c; echo "$#:[$1][$2][$3]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "3:[][b][c]\n"

    def test_lone_dash_leaves_params_unchanged(self, captured_shell):
        rc = captured_shell.run_command('set a b c; set -; echo "$#:[$1]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "3:[a]\n"

    def test_lone_plus_leaves_params_unchanged(self, captured_shell):
        rc = captured_shell.run_command('set a b c; set +; echo "$#:[$1]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "3:[a]\n"

    def test_dash_then_args_become_positional(self, captured_shell):
        rc = captured_shell.run_command('set - a b; echo "$#:[$1][$2]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "2:[a][b]\n"

    def test_lone_dash_resets_xtrace(self, captured_shell):
        captured_shell.run_command('set -x')
        captured_shell.run_command('set -')
        assert captured_shell.state.options['xtrace'] is False

    def test_double_dash_clears_params(self, captured_shell):
        rc = captured_shell.run_command('set a b c; set --; echo "$#"')
        assert rc == 0
        assert captured_shell.get_stdout() == "0\n"


class TestShiftPolicy:
    def test_too_many_operands_discards_unit(self):
        """`shift 1 2` -> too many arguments, rc 1, rest of -c string dropped."""
        rc, out, err = run_c('set -- a b c; shift 1 2; echo survived')
        assert rc == 1
        assert out == ""
        assert "too many arguments" in err

    def test_too_many_discard_resumes_next_script_line(self, tmp_path):
        """In a script FILE only the current line is discarded (bash)."""
        rc, out, err = run_script("set -- a b c\nshift 1 2\necho survived\n", tmp_path)
        assert out == "survived\n"

    def test_bad_first_operand_wins_over_extra(self):
        """`shift x y` reports the numeric error for x, NOT 'too many', rc 1,
        and the shell continues (bash)."""
        rc, out, err = run_c('set -- a b c; shift x y; echo "n=$#"')
        assert out == "n=3\n"
        assert "numeric argument required" in err

    def test_valid_shift_still_works(self, captured_shell):
        rc = captured_shell.run_command('set -- a b c d; shift 2; echo "$#:[$1]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "2:[c]\n"


class TestExitPolicy:
    def test_too_many_operands_discards_without_exit(self):
        """`exit 7 8` -> too many arguments, rc 1, does NOT exit; rest of the
        -c input unit is dropped (bash)."""
        rc, out, err = run_c('exit 7 8; echo survived')
        assert rc == 1
        assert out == ""
        assert "too many arguments" in err

    def test_too_many_resumes_next_script_line(self, tmp_path):
        """A valid-first + extra exit discards only the current line; the shell
        keeps running the script (bash)."""
        rc, out, err = run_script("exit 7 8\necho survived\n", tmp_path)
        assert out == "survived\n"

    def test_bad_first_operand_exits_two(self):
        """`exit abc 7`: the bad numeric first operand wins — exit rc 2."""
        rc, out, err = run_c('exit abc 7; echo survived')
        assert rc == 2
        assert out == ""
        assert "numeric argument required" in err

    def test_bad_operand_exits_two_in_script(self, tmp_path):
        rc, out, err = run_script("exit abc\necho survived\n", tmp_path)
        assert rc == 2
        assert out == ""

    def test_valid_exit_code(self):
        rc, out, err = run_c('exit 7; echo survived')
        assert rc == 7
        assert out == ""


class TestDiscardContainment:
    """The exit/shift usage discard passes THROUGH eval and is errexit-immune
    (bash 5.2), matching arith_assignment_discard."""

    def test_discard_passes_through_eval(self):
        rc, out, err = run_c("set -- a b; eval 'shift 1 2'; echo same-after")
        assert rc == 1
        assert out == ""

    def test_discard_is_errexit_immune(self, tmp_path):
        rc, out, err = run_script(
            "set -e\nset -- a b\nshift 1 2\necho survived\n", tmp_path)
        assert out == "survived\n"
