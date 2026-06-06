"""Array subscripts with invalid arithmetic are handled gracefully.

Regression for study triage #4: the array-index code caught a bare
``except Exception`` (defaulting the index to 0), which swallowed real defects.
It now catches only ``ArithmeticError`` — so a genuinely invalid arithmetic
subscript is still handled gracefully (no crash), while non-arithmetic defects
would propagate. These tests pin the graceful-handling behavior for the
arithmetic case.
"""


class TestArrayIndexArithmeticErrors:
    def test_read_with_invalid_arith_index_does_not_crash(self, captured_shell):
        captured_shell.run_command('arr=(a b c); echo "[${arr[1+]}]"')
        # Invalid arithmetic -> index defaults to 0; no traceback / crash.
        assert captured_shell.get_stdout() == "[a]\n"
        assert "Traceback" not in captured_shell.get_stderr()

    def test_paren_garbage_index_does_not_crash(self, captured_shell):
        captured_shell.run_command('arr=(a b c); echo "[${arr[)(]}]"')
        assert captured_shell.get_stdout() == "[a]\n"

    def test_length_of_invalid_arith_index(self, captured_shell):
        # Invalid arith index -> 0 -> element "a" -> length 1 (graceful, no crash).
        captured_shell.run_command('arr=(a b c); echo "[${#arr[bad+]}]"')
        assert captured_shell.get_stdout() == "[1]\n"

    def test_set_with_invalid_arith_index_does_not_crash(self, captured_shell):
        captured_shell.run_command('arr=(a b c); arr[1+]=x; echo "[${arr[0]}]"')
        # The bad index defaults to 0, so element 0 is overwritten.
        assert captured_shell.get_stdout() == "[x]\n"

    def test_valid_arithmetic_index_still_works(self, captured_shell):
        captured_shell.run_command('arr=(a b c d); i=2; echo "${arr[i+1]}"')
        assert captured_shell.get_stdout() == "d\n"
