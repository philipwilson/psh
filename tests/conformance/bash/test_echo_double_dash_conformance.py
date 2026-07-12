"""
Conformance tests: `echo` has no `--` option terminator (bash).

psh used to treat `--` as an end-of-options marker and drop it (reappraisal
#13), so `echo -- hi` printed `hi`. bash's `echo` has no `--`: it stops flag
scanning at the first non-flag argument and prints `--` literally.

Verified against bash 5.2.
"""


from conformance_framework import ConformanceTest


class TestEchoDoubleDash(ConformanceTest):
    def test_double_dash_is_literal(self):
        self.assert_identical_behavior('echo -- hi')

    def test_double_dash_then_flaglike(self):
        self.assert_identical_behavior('echo -- -n hello')

    def test_flags_before_double_dash(self):
        self.assert_identical_behavior('echo -n -- hello; echo')

    def test_flags_with_escapes_before_double_dash(self):
        self.assert_identical_behavior("echo -e -- 'a\\tb'")

    def test_double_dash_alone(self):
        self.assert_identical_behavior('echo --')

    def test_normal_flags_unaffected(self):
        self.assert_identical_behavior('echo -n hi; echo')
        self.assert_identical_behavior("echo -e 'a\\nb'")
