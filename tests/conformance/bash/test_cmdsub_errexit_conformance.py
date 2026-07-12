"""
Conformance tests: command substitution vs `set -e` (errexit).

bash CLEARS errexit in command-substitution children — `set -e;
x=$(false; echo hi)` sets x=hi — unless POSIX mode or `shopt -s
inherit_errexit` asks otherwise. `( )` subshells and process
substitutions, by contrast, INHERIT errexit. The substitution's exit
STATUS still participates in the parent's errexit as usual (a bare
failing `x=$(false)` aborts). Additionally, the errexit-ignored state
of the forking context (if/while condition, non-final && / || member,
`!`) crosses the fork into substitution children, so `set -e` inside
the body cannot re-arm aborting there (reappraisal #15 cluster F1).

Verified against bash 5.2.
"""


from conformance_framework import ConformanceTest


class TestCmdsubResetsErrexit(ConformanceTest):
    """By default the $( ) / ` ` child runs with errexit OFF."""

    def test_assignment_body_continues_past_failure(self):
        self.assert_identical_behavior(
            'set -e; x=$(false; echo hi); echo "x=$x after"')

    def test_backticks_body_continues_past_failure(self):
        self.assert_identical_behavior(
            'set -e; x=`false; echo hi`; echo "x=$x after"')

    def test_inside_double_quotes(self):
        self.assert_identical_behavior(
            'set -e; echo "got $(false; echo hi) end"')

    def test_nested_substitution(self):
        self.assert_identical_behavior(
            'set -e; x=$(echo $(false; echo in)); echo "x=$x"')

    def test_non_assignment_context(self):
        self.assert_identical_behavior(
            'set -e; echo "$(false; echo hi)"; echo after')

    def test_inside_function(self):
        self.assert_identical_behavior(
            'set -e; f() { local x; x=$(false; echo hi); echo "f:$x"; }; '
            'f; echo after')

    def test_child_dollar_dash_loses_e(self):
        self.assert_identical_behavior(
            'set -e; x=$(echo $-); '
            'case $x in *e*) echo has_e;; *) echo no_e;; esac')

    def test_set_e_in_body_rearms(self):
        self.assert_identical_behavior(
            'set -e; x=$(set -e; false; echo no); echo "x=$x after"')


class TestCmdsubStatusStillDrivesParent(ConformanceTest):
    """The substitution's exit status participates in the parent's errexit."""

    def test_bare_failing_assignment_aborts(self):
        self.assert_identical_behavior('set -e; x=$(false); echo after')

    def test_exit_status_of_body_propagates(self):
        self.assert_identical_behavior(
            'set -e; x=$(false; echo hi; exit 5); echo "x=$x after"')

    def test_if_condition_assignment_exempt(self):
        self.assert_identical_behavior(
            'set -e; if x=$(false); then echo t; else echo f; fi; echo after')


class TestInheritErrexitShopt(ConformanceTest):
    """shopt -s inherit_errexit keeps errexit in cmdsub children."""

    def test_shopt_recognized(self):
        self.assert_identical_behavior('shopt -s inherit_errexit; echo rc=$?')

    def test_shopt_query_states(self):
        self.assert_identical_behavior('shopt inherit_errexit')
        self.assert_identical_behavior(
            'shopt -s inherit_errexit; shopt inherit_errexit')

    def test_inherit_on_child_aborts(self):
        self.assert_identical_behavior(
            'shopt -s inherit_errexit; set -e; '
            'x=$(false; echo hi); echo "x=$x after"')

    def test_inherit_off_again_resets(self):
        self.assert_identical_behavior(
            'shopt -s inherit_errexit; shopt -u inherit_errexit; set -e; '
            'x=$(false; echo hi); echo "x=$x after"')

    def test_inherit_without_set_e_is_noop(self):
        self.assert_identical_behavior(
            'shopt -s inherit_errexit; x=$(false; echo hi); echo "x=$x after"')

    def test_posix_mode_keeps_errexit(self):
        self.assert_identical_behavior(
            'set -o posix; set -e; x=$(false; echo hi); echo "x=$x after"')


class TestSuppressionCrossesFork(ConformanceTest):
    """The errexit-ignored context crosses into substitution children."""

    def test_if_condition_body_continues(self):
        self.assert_identical_behavior(
            'shopt -s inherit_errexit; set -e; '
            'if x=$(false; echo hi); then echo "t:$x"; else echo f; fi; '
            'echo after')

    def test_or_guard_body_continues(self):
        self.assert_identical_behavior(
            'shopt -s inherit_errexit; set -e; '
            'x=$(false; echo hi) || true; echo "x=$x after"')

    def test_set_e_in_body_cannot_rearm_in_condition(self):
        self.assert_identical_behavior(
            'set -e; if x=$(set -e; false; echo no); '
            'then echo "t:$x"; else echo f; fi; echo after')

    def test_procsub_in_condition_continues(self):
        self.assert_identical_behavior(
            'set -e; if cat <(false; echo hi); then echo t; fi; echo after')

    def test_procsub_after_or_guard_continues(self):
        self.assert_identical_behavior(
            'set -e; cat <(false; echo hi) || true; echo after')


class TestSubshellAndProcsubStillInherit(ConformanceTest):
    """Regression pins: ( ) and <(...) keep INHERITING errexit."""

    def test_subshell_inherits_errexit(self):
        self.assert_identical_behavior('set -e; (false; echo no); echo after')

    def test_procsub_inherits_errexit(self):
        self.assert_identical_behavior(
            'set -e; cat <(false; echo hi); echo after')

    def test_procsub_ignores_inherit_errexit_shopt(self):
        self.assert_identical_behavior(
            'shopt -s inherit_errexit; set -e; '
            'cat <(false; echo hi); echo after')
