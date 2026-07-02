"""Array subscripts with invalid arithmetic are fatal errors (bash).

History: the array-index code once caught a bare ``except Exception``
(defaulting the index to 0), which both swallowed real defects AND
silently corrupted data — ``a[08]=x`` overwrote a[0] where bash reports
"value too great for base" and aborts the command (reappraisal #15,
cluster H MED). Subscripts that fail to EVALUATE now raise a fatal
expansion error on both the read and write paths, matching bash 5.2:
stderr message, status 1, no partial output, no index-0 fallback. A
subscript that evaluates cleanly (an unset name -> 0) still addresses
index 0.
"""


class TestArrayIndexArithmeticErrors:
    def _assert_fatal(self, shell, expected_stderr_fragment):
        assert shell.get_stdout() == ""
        assert expected_stderr_fragment in shell.get_stderr()
        assert "Traceback" not in shell.get_stderr()

    def test_read_with_invalid_arith_index_is_fatal(self, captured_shell):
        rc = captured_shell.run_command('arr=(a b c); echo "[${arr[1+]}]"')
        # bash: "1+: syntax error: operand expected", status 1, echo suppressed.
        assert rc == 1
        self._assert_fatal(captured_shell, "Unexpected token")

    def test_paren_garbage_index_is_fatal(self, captured_shell):
        rc = captured_shell.run_command('arr=(a b c); echo "[${arr[)(]}]"')
        assert rc == 1
        self._assert_fatal(captured_shell, "Unexpected token")

    def test_length_of_invalid_arith_index_is_fatal(self, captured_shell):
        rc = captured_shell.run_command('arr=(a b c); echo "[${#arr[bad+]}]"')
        assert rc == 1
        self._assert_fatal(captured_shell, "Unexpected token")

    def test_set_with_invalid_arith_index_is_fatal(self, captured_shell):
        # The write must NOT land on index 0 (the old data-corrupting
        # fallback): arr[0] stays "a" and the command fails.
        rc = captured_shell.run_command('arr=(a b c); arr[1+]=x')
        assert rc == 1
        self._assert_fatal(captured_shell, "Unexpected token")
        captured_shell.clear_output()
        assert captured_shell.run_command('echo "[${arr[0]}]"') == 0
        assert captured_shell.get_stdout() == "[a]\n"

    def test_bad_base_write_is_fatal_and_preserves_element(self, captured_shell):
        # bash: `a[08]=Q` -> "08: value too great for base", status 1.
        rc = captured_shell.run_command('a=(x y z w); a[08]=Q')
        assert rc == 1
        self._assert_fatal(captured_shell, "value too great for base")
        captured_shell.clear_output()
        assert captured_shell.run_command('echo "${a[@]}"') == 0
        assert captured_shell.get_stdout() == "x y z w\n"

    def test_bad_base_read_is_fatal(self, captured_shell):
        rc = captured_shell.run_command('a=(x y z); echo "${a[08]}"')
        assert rc == 1
        self._assert_fatal(captured_shell, "value too great for base")

    def test_bad_base_init_element_is_fatal(self, captured_shell):
        rc = captured_shell.run_command('a=([08]=q)')
        assert rc == 1
        self._assert_fatal(captured_shell, "value too great for base")

    def test_unset_name_subscript_still_addresses_zero(self, captured_shell):
        # `a[junk]` with junk unset EVALUATES cleanly to 0 (bash): the
        # index-0 addressing survives for evaluable subscripts.
        rc = captured_shell.run_command(
            'unset junk; a=(x y z); a[junk]=Q; echo "${a[@]}"')
        assert rc == 0
        assert captured_shell.get_stdout() == "Q y z\n"
        assert captured_shell.get_stderr() == ""

    def test_assoc_array_keeps_literal_string_keys(self, captured_shell):
        # An existing associative array never arithmetic-evaluates its
        # subscript: "08" is a literal key (bash).
        rc = captured_shell.run_command(
            'declare -A h; h[08]=v; echo "rc=$? ${h[08]}"')
        assert rc == 0
        assert captured_shell.get_stdout() == "rc=0 v\n"
        assert captured_shell.get_stderr() == ""

    def test_valid_arithmetic_index_still_works(self, captured_shell):
        captured_shell.run_command('arr=(a b c d); i=2; echo "${arr[i+1]}"')
        assert captured_shell.get_stdout() == "d\n"
