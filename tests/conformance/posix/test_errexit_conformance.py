"""
POSIX errexit (set -e) conformance tests.

These pin psh's set -e semantics to bash, covering the POSIX exemptions:
failures in if/elif/while/until conditions, in non-final members of
&& / || lists, and under ! negation do not trigger errexit; everything
else does. The user guide claims "Full support" for set -e — per the
project's development principles, that claim is proven here.
"""


from conformance_framework import ConformanceTest


class TestErrexitTriggers(ConformanceTest):
    """Failures that MUST exit the shell."""

    def test_plain_failure_exits(self):
        self.assert_identical_behavior('set -e; false; echo no')

    def test_function_failure_exits(self):
        self.assert_identical_behavior('set -e; f(){ false; }; f; echo no')

    def test_final_and_member_failure_exits(self):
        self.assert_identical_behavior('set -e; true && false; echo no')

    def test_pipeline_last_element_failure_exits(self):
        self.assert_identical_behavior('set -e; true | false; echo no')

    def test_subshell_failure_exits(self):
        self.assert_identical_behavior('set -e; (false; echo notreached); echo no')

    def test_exit_code_is_failing_status(self):
        self.assert_identical_behavior('set -e; f(){ return 3; }; f; echo no')


class TestErrexitExemptions(ConformanceTest):
    """Failures POSIX exempts from errexit."""

    def test_if_condition_exempt(self):
        self.assert_identical_behavior('set -e; if false; then echo t; fi; echo after')

    def test_elif_condition_exempt(self):
        self.assert_identical_behavior(
            'set -e; if false; then :; elif false; then :; fi; echo after')

    def test_while_condition_exempt(self):
        self.assert_identical_behavior('set -e; while false; do :; done; echo after')

    def test_until_condition_exempt(self):
        self.assert_identical_behavior('set -e; until true; do :; done; echo after')

    def test_function_as_condition_exempt(self):
        self.assert_identical_behavior(
            'set -e; f(){ false; }; if f; then :; fi; echo after')

    def test_nonfinal_and_member_exempt(self):
        self.assert_identical_behavior('set -e; false && true; echo after')

    def test_or_rescue_exempt(self):
        self.assert_identical_behavior('set -e; false || echo rescued; echo after')

    def test_negation_exempt(self):
        self.assert_identical_behavior('set -e; ! true; echo after')

    def test_negated_failure_exempt(self):
        self.assert_identical_behavior('set -e; ! false; echo after')

    def test_group_inside_nonfinal_member_exempt(self):
        self.assert_identical_behavior(
            'set -e; { false; echo x; } && echo y; echo z')

    def test_command_sub_assignment_rescued(self):
        self.assert_identical_behavior('set -e; v=$(false) || true; echo after')

    def test_pipeline_nonlast_failure_exempt(self):
        self.assert_identical_behavior('set -e; false | true; echo after')


class TestSubshellStateInheritance(ConformanceTest):
    """Subshells inherit shell options and $?."""

    def test_subshell_inherits_last_exit_code(self):
        self.assert_identical_behavior('false; (echo $?)')

    def test_subshell_inherits_errexit(self):
        self.assert_identical_behavior('set -e; (false; echo notreached) || echo caught')

    def test_subshell_inherits_pipefail(self):
        self.assert_identical_behavior(
            'set -o pipefail; (false | true); echo rc=$?')
