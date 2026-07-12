"""Conformance tests for the POSIX test/[ file-operator cluster (reappraisal #18 T1-2).

The bash `[[ ]]` parallels of these operators live in
``tests/conformance/bash/test_enhanced_test_operators_conformance.py`` — `[[ ]]`
is a bash extension and is kept out of the POSIX tree.

Pins three families of behavior to bash:

  1. ``-r``/``-w``/``-x`` apply to ANY file type, including directories and
     special files (bash defers to ``access(2)``). psh formerly gated these on
     ``isfile``, so ``[ -x DIR ]``, ``[ -w /dev/null ]`` wrongly returned false.
  2. ``-nt``/``-ot`` are existence-asymmetric: ``f1 -nt f2`` is true when f1 is
     newer OR (f1 exists AND f2 does not); ``-ot`` symmetric. Both-missing is
     false. This is the classic "rebuild if target missing" idiom.
  3. The POSIX ``test`` argument-count algorithm: with 3 arguments a binary
     primary in ``$2`` is evaluated BEFORE ``$1`` is treated as ``!`` or ``(``;
     with 4 arguments a leading ``!`` negates the 3-argument test of the rest.

Each command ends in ``; echo $?`` so the boolean result is compared (not just
emptiness). Only cases whose bash stderr is empty live here — the exit-2 usage
errors (whose message carries a shell-specific program-name prefix) are pinned
by the unit tests in tests/unit/builtins/test_test_builtin.py instead.
"""


from conformance_framework import ConformanceTest


class TestFilePermsAnyFileType(ConformanceTest):
    """-r/-w/-x hold for directories and special files, not just regular files."""

    def test_x_on_directory(self):
        # A freshly-created directory has its search bit set -> -x true.
        self.assert_identical_behavior('mkdir d; [ -x d ]; echo $?')

    def test_r_on_directory(self):
        self.assert_identical_behavior('mkdir d; [ -r d ]; echo $?')

    def test_w_on_directory(self):
        self.assert_identical_behavior('mkdir d; [ -w d ]; echo $?')

    def test_r_on_dev_null(self):
        self.assert_identical_behavior('[ -r /dev/null ]; echo $?')

    def test_w_on_dev_null(self):
        self.assert_identical_behavior('[ -w /dev/null ]; echo $?')

    def test_x_on_dev_null_is_false(self):
        # /dev/null is readable/writable but NOT executable.
        self.assert_identical_behavior('[ -x /dev/null ]; echo $?')

    def test_test_word_form_x_on_dir(self):
        self.assert_identical_behavior('mkdir d; test -x d; echo $?')

    # The bash `[[ ]]` parallels of these operators live in
    # tests/conformance/bash/test_enhanced_test_operators_conformance.py
    # (kept out of the POSIX tree — `[[ ]]` is a bash extension).

    def test_r_on_fifo(self):
        self.assert_identical_behavior('mkfifo p; [ -r p ]; echo $?')

    def test_missing_path_not_readable(self):
        # os.access-style: a nonexistent path is not readable.
        self.assert_identical_behavior('[ -r no_such_file ]; echo $?')

    def test_regular_file_perms_unchanged(self):
        self.assert_identical_behavior(
            'touch f; chmod 644 f; [ -r f ] && [ -w f ] && ! [ -x f ]; echo $?')

    def test_s_on_nonempty_directory(self):
        # -s (size>0) uses stat, not isfile -> a directory (nonzero st_size)
        # is true, matching bash. Was the same isfile-guard bug as -r/-w/-x.
        self.assert_identical_behavior('mkdir d; echo x > d/f; [ -s d ]; echo $?')

    def test_s_on_empty_directory(self):
        # Even a freshly-created dir has nonzero st_size on the tested OSes;
        # psh reads the same st_size bash does, so they agree either way.
        self.assert_identical_behavior('mkdir d; [ -s d ]; echo $?')

    def test_test_word_form_s_on_dir(self):
        self.assert_identical_behavior('mkdir d; test -s d; echo $?')

    def test_s_on_empty_file_is_false(self):
        # Regression guard: -s stays FALSE for a zero-length regular file.
        self.assert_identical_behavior('touch f; [ -s f ]; echo $?')

    def test_s_on_nonempty_file_is_true(self):
        self.assert_identical_behavior('echo content > f; [ -s f ]; echo $?')

    def test_s_on_dev_null_is_false(self):
        self.assert_identical_behavior('[ -s /dev/null ]; echo $?')

    def test_s_on_missing_path_is_false(self):
        self.assert_identical_behavior('[ -s no_such_file ]; echo $?')


class TestNtOtExistenceAsymmetry(ConformanceTest):
    """-nt/-ot honor bash's existence rule (newer/older OR one-exists-one-missing)."""

    def test_nt_source_exists_target_missing(self):
        # Classic rebuild idiom: source present, target absent -> newer.
        self.assert_identical_behavior('touch a; [ a -nt b ]; echo $?')

    def test_nt_source_missing(self):
        self.assert_identical_behavior('touch b; [ a -nt b ]; echo $?')

    def test_nt_both_missing(self):
        self.assert_identical_behavior('[ a -nt b ]; echo $?')

    def test_ot_target_missing(self):
        self.assert_identical_behavior('touch a; [ a -ot b ]; echo $?')

    def test_ot_source_missing(self):
        self.assert_identical_behavior('touch b; [ a -ot b ]; echo $?')

    def test_ot_both_missing(self):
        self.assert_identical_behavior('[ a -ot b ]; echo $?')

    def test_test_word_form_nt(self):
        self.assert_identical_behavior('touch a; test a -nt b; echo $?')

    def test_nt_by_mtime_still_works(self):
        # The ordinary mtime comparison (both exist) is unaffected.
        self.assert_identical_behavior(
            'touch a; sleep 1.1; touch b; [ b -nt a ]; echo $?')


class TestPosixArgDispatch(ConformanceTest):
    """POSIX 3-arg/4-arg dispatch: a $2 binary primary beats a !/( in $1."""

    def test_bang_equals_is_string_compare(self):
        # 3-arg: `! = x` is `"!" = "x"` (false), not negation.
        self.assert_identical_behavior('test ! = x; echo $?')

    def test_paren_equals_is_string_compare(self):
        self.assert_identical_behavior("test '(' = ')'; echo $?")

    def test_paren_double_equals(self):
        self.assert_identical_behavior("test '(' == ')'; echo $?")

    def test_bang_double_equals(self):
        self.assert_identical_behavior('test ! == x; echo $?')

    def test_bang_not_equals(self):
        self.assert_identical_behavior('test ! != x; echo $?')

    def test_paren_ef_both_missing(self):
        self.assert_identical_behavior("test '(' -ef ')'; echo $?")

    def test_bang_nt(self):
        self.assert_identical_behavior('test ! -nt x; echo $?')

    def test_four_arg_bang_negates_binary(self):
        # 4-arg: leading ! negates the 3-arg `( = )` -> negate(false) -> true.
        self.assert_identical_behavior('test ! \'(\' = \')\'; echo $?')

    def test_four_arg_bang_string_equal(self):
        self.assert_identical_behavior('test ! a = a; echo $?')

    def test_four_arg_bang_string_unequal(self):
        self.assert_identical_behavior('test ! a = b; echo $?')

    def test_three_arg_bang_unary_still_negates(self):
        # $2 is NOT a binary primary here, so leading ! DOES negate.
        self.assert_identical_behavior('test ! -z ""; echo $?')

    def test_three_arg_paren_group(self):
        self.assert_identical_behavior("test '(' foo ')'; echo $?")

    def test_double_bang_no_spurious_error(self):
        # `test ! ! a` -> negate(negate(a nonempty)) -> true, no stderr.
        self.assert_identical_behavior('test ! ! a; echo $?')

    def test_negated_paren_group(self):
        self.assert_identical_behavior("[ ! '(' a = a ')' ]; echo $?")
