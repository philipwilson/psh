"""
Unit tests for test builtin and [ command.

Tests cover:
- File tests (-f, -d, -e, -r, -w, -x, etc.)
- String tests (-z, -n, =, !=)
- Numeric tests (-eq, -ne, -lt, -gt, -le, -ge)
- Logical operators (-a, -o, !)
- Both 'test' and '[' syntax
"""

import os

import pytest


class TestFileTests:
    """Test file-related test conditions."""

    @pytest.fixture(autouse=True)
    def _isolate_cwd(self, tmp_path, monkeypatch):
        """Give each file test its own working directory.

        These tests create fixed-name files/dirs (``testdir``, ``regular.txt``,
        …) and remove them with relative paths. Run in the shared cwd under
        pytest-xdist they collide across workers (a `testdir` created by one
        test is removed by another, raising FileNotFoundError). Per-test temp
        cwd isolation removes the collision (CLAUDE.md parallel-safety rule 2).
        """
        monkeypatch.chdir(tmp_path)

    def test_file_exists(self, shell, capsys):
        """Test -e (file exists)."""
        # Create a test file
        shell.run_command('touch testfile')

        # Test with 'test'
        exit_code = shell.run_command('test -e testfile')
        assert exit_code == 0

        # Test with '['
        exit_code = shell.run_command('[ -e testfile ]')
        assert exit_code == 0

        # Non-existent file
        exit_code = shell.run_command('test -e nonexistent')
        assert exit_code != 0

        # Clean up
        os.remove('testfile')

    def test_regular_file(self, shell, capsys):
        """Test -f (regular file)."""
        # Create a regular file
        shell.run_command('touch regular.txt')

        exit_code = shell.run_command('[ -f regular.txt ]')
        assert exit_code == 0

        # Directory is not a regular file
        shell.run_command('mkdir testdir')
        exit_code = shell.run_command('[ -f testdir ]')
        assert exit_code != 0

        # Clean up
        os.remove('regular.txt')
        os.rmdir('testdir')

    def test_directory(self, shell, capsys):
        """Test -d (directory)."""
        # Create a directory
        shell.run_command('mkdir testdir')

        exit_code = shell.run_command('test -d testdir')
        assert exit_code == 0

        # File is not a directory
        shell.run_command('touch file.txt')
        exit_code = shell.run_command('test -d file.txt')
        assert exit_code != 0

        # Clean up
        os.rmdir('testdir')
        os.remove('file.txt')

    def test_readable_file(self, shell, capsys):
        """Test -r (readable)."""
        shell.run_command('touch readable.txt')
        shell.run_command('chmod 644 readable.txt')

        exit_code = shell.run_command('[ -r readable.txt ]')
        assert exit_code == 0

        # Clean up
        os.remove('readable.txt')

    def test_writable_file(self, shell, capsys):
        """Test -w (writable)."""
        shell.run_command('touch writable.txt')
        shell.run_command('chmod 644 writable.txt')

        exit_code = shell.run_command('test -w writable.txt')
        assert exit_code == 0

        # Clean up
        os.remove('writable.txt')

    def test_executable_file(self, shell, capsys):
        """Test -x (executable)."""
        shell.run_command('touch script.sh')
        shell.run_command('chmod 755 script.sh')

        exit_code = shell.run_command('[ -x script.sh ]')
        assert exit_code == 0

        # Non-executable
        shell.run_command('chmod 644 script.sh')
        exit_code = shell.run_command('[ -x script.sh ]')
        assert exit_code != 0

        # Clean up
        os.remove('script.sh')

    def test_file_size(self, shell, capsys):
        """Test -s (file has size > 0)."""
        # Empty file
        shell.run_command('touch empty.txt')
        exit_code = shell.run_command('test -s empty.txt')
        assert exit_code != 0

        # Non-empty file
        shell.run_command('echo "content" > nonempty.txt')
        exit_code = shell.run_command('test -s nonempty.txt')
        assert exit_code == 0

        # Clean up
        os.remove('empty.txt')
        os.remove('nonempty.txt')


class TestStringTests:
    """Test string-related test conditions."""

    def test_string_empty(self, shell, capsys):
        """Test -z (string is empty)."""
        # Empty string
        exit_code = shell.run_command('test -z ""')
        assert exit_code == 0

        exit_code = shell.run_command('[ -z "" ]')
        assert exit_code == 0

        # Non-empty string
        exit_code = shell.run_command('test -z "hello"')
        assert exit_code != 0

    def test_string_not_empty(self, shell, capsys):
        """Test -n (string is not empty)."""
        # Non-empty string
        exit_code = shell.run_command('test -n "hello"')
        assert exit_code == 0

        # Empty string
        exit_code = shell.run_command('[ -n "" ]')
        assert exit_code != 0

    def test_string_equality(self, shell, capsys):
        """Test string = string."""
        # Equal strings
        exit_code = shell.run_command('test "hello" = "hello"')
        assert exit_code == 0

        exit_code = shell.run_command('[ "abc" = "abc" ]')
        assert exit_code == 0

        # Different strings
        exit_code = shell.run_command('test "hello" = "world"')
        assert exit_code != 0

    def test_string_inequality(self, shell, capsys):
        """Test string != string."""
        # Different strings
        exit_code = shell.run_command('test "hello" != "world"')
        assert exit_code == 0

        # Equal strings
        exit_code = shell.run_command('[ "same" != "same" ]')
        assert exit_code != 0

    def test_string_with_variables(self, shell, capsys):
        """Test strings with variable expansion."""
        shell.run_command('VAR="test"')

        exit_code = shell.run_command('[ "$VAR" = "test" ]')
        assert exit_code == 0

        exit_code = shell.run_command('test -z "$UNSET_VAR"')
        assert exit_code == 0


class TestNumericTests:
    """Test numeric comparison conditions."""

    def test_numeric_equal(self, shell, capsys):
        """Test -eq (equal)."""
        exit_code = shell.run_command('test 5 -eq 5')
        assert exit_code == 0

        exit_code = shell.run_command('[ 10 -eq 20 ]')
        assert exit_code != 0

    def test_numeric_not_equal(self, shell, capsys):
        """Test -ne (not equal)."""
        exit_code = shell.run_command('test 5 -ne 10')
        assert exit_code == 0

        exit_code = shell.run_command('[ 7 -ne 7 ]')
        assert exit_code != 0

    def test_numeric_less_than(self, shell, capsys):
        """Test -lt (less than)."""
        exit_code = shell.run_command('test 5 -lt 10')
        assert exit_code == 0

        exit_code = shell.run_command('[ 10 -lt 5 ]')
        assert exit_code != 0

    def test_numeric_greater_than(self, shell, capsys):
        """Test -gt (greater than)."""
        exit_code = shell.run_command('test 10 -gt 5')
        assert exit_code == 0

        exit_code = shell.run_command('[ 5 -gt 10 ]')
        assert exit_code != 0

    def test_numeric_less_equal(self, shell, capsys):
        """Test -le (less than or equal)."""
        exit_code = shell.run_command('test 5 -le 10')
        assert exit_code == 0

        exit_code = shell.run_command('test 5 -le 5')
        assert exit_code == 0

        exit_code = shell.run_command('[ 10 -le 5 ]')
        assert exit_code != 0

    def test_numeric_greater_equal(self, shell, capsys):
        """Test -ge (greater than or equal)."""
        exit_code = shell.run_command('test 10 -ge 5')
        assert exit_code == 0

        exit_code = shell.run_command('test 5 -ge 5')
        assert exit_code == 0

        exit_code = shell.run_command('[ 5 -ge 10 ]')
        assert exit_code != 0


class TestNumericInt64Range:
    """test/[ integer operands are signed 64-bit (bash uses intmax_t).

    A literal outside [-2**63, 2**63-1] is rejected as "integer expression
    expected" (exit 2), exactly like a non-numeric operand — it is NOT the
    arbitrary-precision comparison Python's int() would give.
    """

    INT64_MIN = str(-(2 ** 63))          # -9223372036854775808
    INT64_MAX = str(2 ** 63 - 1)         #  9223372036854775807
    OVER_MAX = str(2 ** 63)              #  9223372036854775808
    UNDER_MIN = str(-(2 ** 63) - 1)      # -9223372036854775809

    @pytest.mark.parametrize("op", ['-eq', '-ne', '-lt', '-le', '-gt', '-ge'])
    def test_over_max_left_operand_rejected(self, captured_shell, op):
        rc = captured_shell.run_command(f'test {self.OVER_MAX} {op} 5')
        assert rc == 2
        err = captured_shell.get_stderr()
        assert "integer expression expected" in err
        # bash echoes the offending token in the message.
        assert self.OVER_MAX in err

    @pytest.mark.parametrize("op", ['-eq', '-ne', '-lt', '-le', '-gt', '-ge'])
    def test_over_max_right_operand_rejected(self, captured_shell, op):
        rc = captured_shell.run_command(f'test 5 {op} {self.OVER_MAX}')
        assert rc == 2
        assert "integer expression expected" in captured_shell.get_stderr()

    def test_under_min_rejected(self, captured_shell):
        rc = captured_shell.run_command(f'test {self.UNDER_MIN} -lt 5')
        assert rc == 2
        assert "integer expression expected" in captured_shell.get_stderr()

    def test_over_2_64_rejected(self, captured_shell):
        rc = captured_shell.run_command('test 18446744073709551616 -gt 5')
        assert rc == 2
        assert "integer expression expected" in captured_shell.get_stderr()

    def test_bracket_form_rejects_over_max(self, captured_shell):
        rc = captured_shell.run_command(f'[ {self.OVER_MAX} -gt 5 ]')
        assert rc == 2
        err = captured_shell.get_stderr()
        assert "integer expression expected" in err
        # The '[' builtin prefixes its own name, matching bash.
        assert err.startswith('[: ') or ' [: ' in err

    def test_int64_boundaries_accepted(self, captured_shell):
        # The exact signed-64-bit extremes are IN range and compare normally.
        assert captured_shell.run_command(
            f'test {self.INT64_MAX} -gt 5') == 0
        assert captured_shell.run_command(
            f'test {self.INT64_MIN} -lt 5') == 0
        assert captured_shell.get_stderr() == ""

    def test_over_max_equals_negative_does_not_wrap(self, captured_shell):
        # Unlike $((...)) (which wraps to signed 64-bit), test rejects the
        # literal outright rather than wrapping 2**63 to -2**63 and matching.
        rc = captured_shell.run_command(
            f'test {self.OVER_MAX} -eq {self.INT64_MIN}')
        assert rc == 2
        assert "integer expression expected" in captured_shell.get_stderr()

    def test_large_in_range_comparison_unchanged(self, captured_shell):
        assert captured_shell.run_command(
            'test 1000000000000 -gt 999999999999') == 0
        assert captured_shell.get_stderr() == ""


class TestLogicalOperators:
    """Test logical operators in test expressions."""

    def test_logical_and(self, shell, capsys):
        """Test -a (logical AND)."""
        # Both true
        exit_code = shell.run_command('test -n "hello" -a -n "world"')
        assert exit_code == 0

        # One false
        exit_code = shell.run_command('[ -n "hello" -a -z "hello" ]')
        assert exit_code != 0

    def test_logical_or(self, shell, capsys):
        """Test -o (logical OR)."""
        # One true
        exit_code = shell.run_command('test -n "hello" -o -z "hello"')
        assert exit_code == 0

        # Both false
        exit_code = shell.run_command('[ -z "hello" -o -z "world" ]')
        assert exit_code != 0

    def test_negation(self, shell, capsys):
        """Test ! (negation)."""
        # Negate true
        exit_code = shell.run_command('test ! -n "hello"')
        assert exit_code != 0

        # Negate false
        exit_code = shell.run_command('[ ! -z "hello" ]')
        assert exit_code == 0

    def test_parentheses(self, shell, capsys):
        """Test parentheses for grouping."""
        # Complex expression with grouping
        exit_code = shell.run_command('test \\( -n "a" -a -n "b" \\) -o -z "c"')
        assert exit_code == 0


class TestSpecialCases:
    """Test special cases and error conditions."""

    def test_empty_test(self, shell, capsys):
        """Test with no arguments."""
        exit_code = shell.run_command('test')
        assert exit_code != 0

        exit_code = shell.run_command('[  ]')
        assert exit_code != 0

    def test_single_argument(self, shell, capsys):
        """Test with single argument (tests if non-empty)."""
        exit_code = shell.run_command('test "hello"')
        assert exit_code == 0

        exit_code = shell.run_command('test ""')
        assert exit_code != 0

        exit_code = shell.run_command('[ "x" ]')
        assert exit_code == 0

    def test_lone_bang_is_nonempty_string(self, shell, capsys):
        """R13.A: a lone `!` is the one-argument non-empty-string test (exit 0),
        not negation-of-empty (bash/POSIX)."""
        assert shell.run_command('test !') == 0
        assert shell.run_command('[ ! ]') == 0
        # `!` still negates a following operand
        assert shell.run_command('test ! -e /nonexistent_xyz_psh') == 0
        assert shell.run_command("test ! ''") == 0

    def test_v_variable_is_set(self, shell, capsys):
        """R13.A: `test -v VAR` / `[ -v VAR ]` reports whether a variable is set
        (previously always returned the sentinel exit 2)."""
        shell.run_command('vv=5')
        assert shell.run_command('test -v vv') == 0
        assert shell.run_command('[ -v vv ]') == 0
        shell.run_command('unset nope_xyz')
        assert shell.run_command('test -v nope_xyz') == 1

    def test_v_array_element(self, shell, capsys):
        """`test -v arr[i]` checks element existence."""
        shell.run_command('arr=(a b c)')
        assert shell.run_command('test -v "arr[1]"') == 0
        assert shell.run_command('test -v "arr[9]"') == 1

    def test_bracket_spacing(self, shell, capsys):
        """Test [ requires spaces."""
        # Correct spacing
        exit_code = shell.run_command('[ -n "test" ]')
        assert exit_code == 0

        # Missing closing bracket should fail
        exit_code = shell.run_command('[ -n "test"')
        assert exit_code != 0

    def test_invalid_operator(self, shell, capsys):
        """Test invalid operators."""
        exit_code = shell.run_command('test 5 -foo 10')
        assert exit_code != 0
        captured = capsys.readouterr()
        # Now checks for the actual error message
        assert 'binary operator expected' in captured.err

    def test_file_comparison(self, shell, capsys):
        """Test file comparison operators."""
        try:
            # Create test files
            shell.run_command('touch file1')
            shell.run_command('sleep 0.1')  # Ensure different timestamps
            shell.run_command('touch file2')

            # file2 should be newer
            exit_code = shell.run_command('[ file2 -nt file1 ]')
            assert exit_code == 0

            # file1 should be older
            exit_code = shell.run_command('test file1 -ot file2')
            assert exit_code == 0
        finally:
            # Clean up
            if os.path.exists('file1'):
                os.remove('file1')
            if os.path.exists('file2'):
                os.remove('file2')


class TestErrorPrefix:
    """Error messages carry the invocation name, matching bash (R9.D).

    bash reports `[: 1: unary operator expected` when invoked as `[` and
    `test: 1: unary operator expected` when invoked as `test`.
    """

    def test_bracket_errors_use_bracket_prefix(self, captured_shell):
        captured_shell.run_command('[ 1 -eq ]')
        assert captured_shell.get_stderr().startswith('psh: line 1: [: ')

    def test_test_errors_use_test_prefix(self, captured_shell):
        captured_shell.run_command('test 1 -eq')
        assert captured_shell.get_stderr().startswith('psh: line 1: test: ')


class TestTooManyArguments:
    """4+-argument expressions that parse as nothing print bash's
    "too many arguments" diagnostic with status 2 (reappraisal #17
    builtins M4 — the rc was already 2, but SILENTLY).
    """

    def test_binary_with_trailing_operand(self, captured_shell):
        # bash: `[: too many arguments`, rc 2
        rc = captured_shell.run_command('[ x = ab ac ]')
        assert rc == 2
        assert captured_shell.get_stderr() == 'psh: line 1: [: too many arguments\n'

    def test_test_spelling_uses_test_prefix(self, captured_shell):
        rc = captured_shell.run_command('test x = y z')
        assert rc == 2
        assert captured_shell.get_stderr() == 'psh: line 1: test: too many arguments\n'

    def test_five_bare_words(self, captured_shell):
        rc = captured_shell.run_command('[ a b c d e ]')
        assert rc == 2
        assert captured_shell.get_stderr() == 'psh: line 1: [: too many arguments\n'

    def test_valid_four_arg_forms_stay_silent(self, captured_shell):
        # -a/-o combinations and POSIX leading-`!` negation are still
        # recognized 4-argument forms and stay silent.
        assert captured_shell.run_command('[ -n x -a -n y ]') == 0
        assert captured_shell.run_command('test ! hello = hello') == 1
        assert captured_shell.run_command('test ! hello != hello') == 0
        assert captured_shell.get_stderr() == ''

    def test_split_operators_are_too_many_arguments(self, captured_shell):
        # bash does NOT reconstruct split operators: `test a ! = b`,
        # `test a = = b`, `test a = ~ b` are all "too many arguments",
        # rc 2 (psh used to glue them into !=/==/=~ and evaluate).
        for cmd in ('test hello ! = hello',
                    'test a = = b',
                    'test a = ~ b'):
            captured_shell.clear_output()
            rc = captured_shell.run_command(cmd)
            assert rc == 2, cmd
            assert captured_shell.get_stderr() == \
                'psh: line 1: test: too many arguments\n', cmd


class TestPermsAnyFileType:
    """-r/-w/-x apply to ANY file type, not just regular files (R18 T1-2).

    psh formerly gated -r/-w/-x on os.path.isfile, so directories and special
    files (which bash reports via access(2)) wrongly tested false.
    """

    @pytest.fixture(autouse=True)
    def _isolate_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

    def test_directory_is_readable_writable_executable(self, shell):
        shell.run_command('mkdir d')
        assert shell.run_command('[ -r d ]') == 0
        assert shell.run_command('[ -w d ]') == 0
        assert shell.run_command('[ -x d ]') == 0  # search bit
        assert shell.run_command('test -x d') == 0

    def test_enhanced_test_directory_executable(self, shell):
        shell.run_command('mkdir d')
        assert shell.run_command('[[ -x d ]]') == 0

    def test_dev_null_readable_writable_not_executable(self, shell):
        assert shell.run_command('[ -r /dev/null ]') == 0
        assert shell.run_command('[ -w /dev/null ]') == 0
        assert shell.run_command('[ -x /dev/null ]') == 1

    def test_fifo_readable_writable(self, shell):
        shell.run_command('mkfifo p')
        assert shell.run_command('[ -r p ]') == 0
        assert shell.run_command('[ -w p ]') == 0

    def test_missing_path_not_readable(self, shell):
        # os.access returns False for a nonexistent path.
        assert shell.run_command('[ -r no_such_file ]') == 1
        assert shell.run_command('[ -w no_such_file ]') == 1
        assert shell.run_command('[ -x no_such_file ]') == 1

    def test_regular_file_perms_unchanged(self, shell):
        shell.run_command('touch f')
        shell.run_command('chmod 644 f')
        assert shell.run_command('[ -r f ]') == 0
        assert shell.run_command('[ -w f ]') == 0
        assert shell.run_command('[ -x f ]') == 1

    def test_s_true_for_directory(self, shell):
        # -s (size>0) uses stat, not isfile: a directory has nonzero st_size.
        shell.run_command('mkdir d')
        shell.run_command('echo x > d/f')
        assert shell.run_command('[ -s d ]') == 0
        assert shell.run_command('test -s d') == 0
        assert shell.run_command('[[ -s d ]]') == 0

    def test_s_still_false_for_empty_regular_file(self, shell):
        # Regression guard: the fix must NOT make -s true for a 0-byte file.
        shell.run_command('touch empty')
        assert shell.run_command('[ -s empty ]') == 1
        # ...and stays true for a nonempty regular file.
        shell.run_command('echo content > full')
        assert shell.run_command('[ -s full ]') == 0

    def test_s_false_for_dev_null_and_missing(self, shell):
        assert shell.run_command('[ -s /dev/null ]') == 1
        assert shell.run_command('[ -s no_such_file ]') == 1


class TestNtOtExistenceAsymmetry:
    """-nt/-ot are existence-asymmetric and delegate to the shared helper
    (psh.utils.file_tests) used by both test/[ and [[ ]] (R18 T1-2).

    bash rule: `f1 -nt f2` is true if f1 is newer OR (f1 exists AND f2 does
    not). `-ot` is symmetric. Both-missing is false. The absolute /dev/null
    (present) paired with a nonexistent path exercises this without touching
    the cwd, so no fixture isolation is needed for these cases.
    """

    NX = '/nonexistent_xyz_psh_r18t1'
    NX2 = '/nonexistent_abc_psh_r18t1'

    def test_nt_exists_vs_missing(self, shell):
        assert shell.run_command(f'[ /dev/null -nt {self.NX} ]') == 0

    def test_nt_missing_vs_exists(self, shell):
        assert shell.run_command(f'[ {self.NX} -nt /dev/null ]') == 1

    def test_nt_both_missing(self, shell):
        assert shell.run_command(f'[ {self.NX} -nt {self.NX2} ]') == 1

    def test_ot_exists_vs_missing(self, shell):
        # f1 exists, f2 missing -> f1 is NOT older.
        assert shell.run_command(f'[ /dev/null -ot {self.NX} ]') == 1

    def test_ot_missing_vs_exists(self, shell):
        # f2 exists, f1 missing -> f1 IS older.
        assert shell.run_command(f'[ {self.NX} -ot /dev/null ]') == 0

    def test_ot_both_missing(self, shell):
        assert shell.run_command(f'[ {self.NX} -ot {self.NX2} ]') == 1

    def test_enhanced_test_nt_rebuild_idiom(self, shell):
        # [[ src -nt missing ]] routes through the SAME shared helper.
        assert shell.run_command(f'[[ /dev/null -nt {self.NX} ]]') == 0

    def test_enhanced_test_ot_missing_vs_exists(self, shell):
        assert shell.run_command(f'[[ {self.NX} -ot /dev/null ]]') == 0

    def test_shared_helper_matches_between_forms(self, shell):
        # test/[ and [[ ]] must agree on the asymmetric result.
        for form in ('[ /dev/null -nt %s ]', '[[ /dev/null -nt %s ]]'):
            assert shell.run_command(form % self.NX) == 0
        for form in ('[ %s -ot /dev/null ]', '[[ %s -ot /dev/null ]]'):
            assert shell.run_command(form % self.NX) == 0


class TestPosixArgDispatch:
    """POSIX test argument-count algorithm: a binary primary in $2 is
    recognised BEFORE $1 is treated as ! or ( (R18 T1-2).
    """

    def test_three_arg_bang_is_string_compare(self, shell):
        # `! = x` is `"!" = "x"` (false), not a negation.
        assert shell.run_command('test ! = x') == 1
        assert shell.run_command('test ! != x') == 0
        assert shell.run_command('test ! = =') == 1

    def test_three_arg_paren_is_string_compare(self, shell):
        assert shell.run_command("test '(' = ')'") == 1
        assert shell.run_command("test '(' == ')'") == 1
        assert shell.run_command("test '(' != ')'") == 0

    def test_three_arg_paren_ef_both_missing(self, shell):
        assert shell.run_command("test '(' -ef ')'") == 1

    def test_three_arg_bang_nt_both_missing(self, shell):
        assert shell.run_command('test ! -nt x') == 1

    def test_three_arg_bang_still_negates_non_primary(self, shell):
        # $2 is NOT a binary primary, so the leading ! DOES negate.
        assert shell.run_command("test ! -z ''") == 1   # -z '' true -> negate
        assert shell.run_command("test ! -n ''") == 0   # -n '' false -> negate
        assert shell.run_command('test ! -f no_such_file') == 0

    def test_three_arg_paren_group(self, shell):
        assert shell.run_command("test '(' foo ')'") == 0
        assert shell.run_command("test '(' '' ')'") == 1

    def test_four_arg_bang_negates_three_arg(self, shell):
        assert shell.run_command("test ! '(' = ')'") == 0  # negate(false)
        assert shell.run_command('test ! a = a') == 1      # negate(true)
        assert shell.run_command('test ! a = b') == 0      # negate(false)

    def test_double_bang_no_spurious_error(self, captured_shell):
        # `test ! ! a` -> negate(negate(a nonempty)) -> true, NO stderr.
        assert captured_shell.run_command('test ! ! a') == 0
        assert captured_shell.get_stderr() == ''

    def test_bracket_form_dispatch(self, shell):
        assert shell.run_command('[ ! = x ]') == 1
        assert shell.run_command("[ '(' = ')' ]") == 1
        assert shell.run_command("[ ! '(' = ')' ]") == 0


class TestPosixDispatchErrors:
    """3/4-arg forms that are usage errors return rc 2 with the offending
    token named (matching bash's message content; the program-name prefix is
    psh's own). Negation propagates rc 2 rather than turning it into 0.
    """

    def test_bang_eq_integer_error(self, captured_shell):
        # `! -eq x` is `"!" -eq "x"` -> "!" is not an integer.
        rc = captured_shell.run_command('test ! -eq x')
        assert rc == 2
        err = captured_shell.get_stderr()
        assert 'integer expression expected' in err
        assert '!' in err  # offending token is the LHS operand

    def test_paren_eq_integer_error(self, captured_shell):
        rc = captured_shell.run_command("test '(' -eq ')'")
        assert rc == 2
        err = captured_shell.get_stderr()
        assert 'integer expression expected' in err
        assert '(' in err

    def test_bracket_form_uses_bracket_prefix(self, captured_shell):
        rc = captured_shell.run_command('[ ! -eq x ]')
        assert rc == 2
        assert captured_shell.get_stderr().startswith('psh: line 1: [: ')

    def test_negation_propagates_usage_error(self, captured_shell):
        # `test ! a b c` -> negate(3-arg `a b c` which is an error) -> rc 2,
        # NOT 0. (The old negate turned rc 2 into 0.)
        rc = captured_shell.run_command('test ! a b c')
        assert rc == 2
        assert 'binary operator expected' in captured_shell.get_stderr()

    def test_negation_propagates_unary_usage_error(self, captured_shell):
        rc = captured_shell.run_command('test ! a b')
        assert rc == 2
        assert 'unary operator expected' in captured_shell.get_stderr()
