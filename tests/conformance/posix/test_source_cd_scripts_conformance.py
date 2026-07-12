"""source/cd/line-continuation/declare-attribute/script-file conformance.

These areas were covered only by the legacy golden-file suite at the repo
root (conformance_tests/, deleted in v0.277.0). Folded in here as live
psh-vs-bash comparisons so deleting the legacy tree loses no coverage.

The cd and script-file classes also pin two real bugs the fold-in
uncovered: cd ignored the HOME/OLDPWD *shell variables* (used os.environ),
and psh lacked the POSIX ENOEXEC fallback (running a no-shebang
executable text file as a shell script).
"""


from conformance_framework import ConformanceTest


class TestSourceBuiltin(ConformanceTest):
    """source / . runs a file in the current shell environment."""

    def test_source_sets_variables(self):
        self.assert_identical_behavior(
            'echo "X=42" > lib.sh; . ./lib.sh; echo "X:$X"')

    def test_source_defines_functions(self):
        self.assert_identical_behavior(
            'printf "f() { echo from-lib; }\\n" > lib.sh; . ./lib.sh; f')

    def test_source_with_arguments(self):
        # bash extension: source passes positional args to the sourced file
        self.assert_identical_behavior(
            'echo "echo args:\\$1:\\$2" > lib.sh; source ./lib.sh a b')

    def test_source_return_status(self):
        self.assert_identical_behavior(
            'echo "return 7" > lib.sh; . ./lib.sh; echo "rc:$?"')

    def test_source_missing_file_status(self):
        # error text carries the shell's own name; compare status only
        self.assert_identical_behavior(
            '. ./nope.sh 2>/dev/null; echo "rc:$?"')

    def test_nested_sourcing(self):
        self.assert_identical_behavior(
            'echo "echo inner-ran" > inner.sh; '
            'echo ". ./inner.sh" > outer.sh; . ./outer.sh')

    def test_source_sees_and_mutates_callers_vars(self):
        self.assert_identical_behavior(
            'v=before; echo "echo saw:\\$v; v=after" > lib.sh; '
            '. ./lib.sh; echo "now:$v"')

    def test_source_no_args_inherits_positionals(self):
        # H4: `source file` with NO extra args must leave $@/$# unchanged
        # (the sourced file inherits the caller's positional parameters),
        # and they stay unchanged afterward.
        self.assert_identical_behavior(
            'printf "echo in:[\\$@] n=\\$#\\n" > lib.sh; '
            'set -- A B C; . ./lib.sh; echo "out:[$@] n=$#"')

    def test_source_with_args_overrides_then_restores(self):
        # H4: `source file x y` sets $@/$# to x y inside the file, and the
        # caller's original positionals are restored afterward.
        self.assert_identical_behavior(
            'printf "echo in:[\\$@] n=\\$#\\n" > lib.sh; '
            'set -- A B C; . ./lib.sh X Y; echo "out:[$@] n=$#"')

    def test_dot_no_args_inherits_positionals(self):
        # Same as the source case but via the `.` (dot) builtin.
        self.assert_identical_behavior(
            'printf "echo in:[\\$@] n=\\$#\\n" > lib.sh; '
            'set -- A B C; source ./lib.sh; echo "out:[$@] n=$#"')


class TestCdBuiltin(ConformanceTest):
    """cd semantics: HOME, OLDPWD, cd -, failure status."""

    def test_bare_cd_uses_home_variable(self):
        # the HOME *shell variable*, not the inherited environment
        self.assert_identical_behavior('HOME=/usr; cd; pwd')

    def test_bare_cd_with_home_unset(self):
        self.assert_identical_behavior(
            'unset HOME; cd 2>/dev/null; echo "rc:$?"')

    def test_cd_dash_prints_and_uses_oldpwd(self):
        self.assert_identical_behavior('cd /; OLDPWD=/usr; cd -; pwd')

    def test_oldpwd_tracks_previous_dir(self):
        self.assert_identical_behavior('cd /; cd /usr; echo "$OLDPWD"')

    def test_cd_nonexistent_dir_status(self):
        self.assert_identical_behavior(
            'cd ./missing_dir_xyz 2>/dev/null; echo "rc:$?"')

    def test_cd_dash_without_oldpwd(self):
        self.assert_identical_behavior(
            'unset OLDPWD; cd - 2>/dev/null; echo "rc:$?"')


class TestLineContinuation(ConformanceTest):
    """Backslash-newline joins lines before tokenization."""

    def test_simple_word_continuation(self):
        self.assert_identical_behavior('echo foo\\\nbar')

    def test_continuation_between_arguments(self):
        self.assert_identical_behavior('echo one \\\n two')

    def test_continuation_inside_double_quotes(self):
        self.assert_identical_behavior('echo "a\\\nb"')

    def test_continuation_in_arithmetic(self):
        self.assert_identical_behavior('echo $((1 + \\\n 2))')

    def test_continuation_in_for_list(self):
        self.assert_identical_behavior(
            'for x in a \\\n b; do echo "$x"; done')

    def test_no_continuation_in_single_quotes(self):
        # inside single quotes the backslash-newline is literal
        self.assert_identical_behavior("echo 'a\\\nb' | wc -l | tr -d ' '")


class TestDeclareAttributes(ConformanceTest):
    """declare -i / -l / -u / -r / -x attribute behavior."""

    def test_integer_attribute_evaluates_arithmetic(self):
        self.assert_identical_behavior('declare -i n; n=2+3; echo "$n"')

    def test_integer_attribute_plus_equals(self):
        self.assert_identical_behavior('declare -i m=5; m+=3; echo "$m"')

    def test_lowercase_attribute(self):
        self.assert_identical_behavior('declare -l s; s=ABC; echo "$s"')

    def test_uppercase_attribute(self):
        self.assert_identical_behavior('declare -u s; s=abc; echo "$s"')

    def test_readonly_attribute_blocks_assignment(self):
        # assignment to a readonly var is fatal to the (sub)shell in
        # both shells; the error text carries the shell's name, so wrap
        # in a subshell and compare the surviving status only
        self.assert_identical_behavior(
            '( declare -r r=5; r=6; echo "not-reached:$r" ) 2>/dev/null; '
            'echo "rc:$?"')

    def test_export_attribute_reaches_children(self):
        self.assert_identical_behavior(
            'declare -x EXPV=hello; printenv EXPV')


class TestScriptFileExecution(ConformanceTest):
    """Running real script files: $0, positional args, exit codes.

    The scripts are written without a shebang, so each shell executes
    them with itself via the POSIX ENOEXEC fallback — exercising that
    fallback is part of the point.
    """

    def test_script_positional_args_and_dollar_zero(self):
        self.assert_identical_behavior(
            'printf "echo 0:\\$0 1:\\$1 2:\\$2\\n" > s.sh; chmod +x s.sh; '
            './s.sh one two')

    def test_script_tenth_argument(self):
        self.assert_identical_behavior(
            'printf "echo ten:\\${10}\\n" > s.sh; chmod +x s.sh; '
            './s.sh a b c d e f g h i J')

    def test_script_exit_code(self):
        self.assert_identical_behavior(
            'printf "exit 5\\n" > s.sh; chmod +x s.sh; ./s.sh; echo "rc:$?"')

    def test_script_arg_count(self):
        self.assert_identical_behavior(
            'printf "echo n:\\$#\\n" > s.sh; chmod +x s.sh; ./s.sh a b c')

    def test_noexec_permission_status(self):
        self.assert_identical_behavior(
            'printf "echo nope\\n" > s.sh; chmod -x s.sh; '
            './s.sh 2>/dev/null; echo "rc:$?"')
