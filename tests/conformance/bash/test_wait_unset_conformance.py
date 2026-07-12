"""
Conformance tests for two standalone bugs (reappraisal #13 R15.A):

  - `wait` with no operands always returns 0 (POSIX/bash); a failing background
    job must not leak into it. psh returned the last job's status. Only the
    operand form `wait PID`/`wait %job` reports a job's exit status.
  - a bare `unset NAME` (no -v/-f) unsets the variable if one exists, else
    falls back to unsetting a FUNCTION of that name; psh never fell back.

Verified against bash 5.2.
"""


from conformance_framework import ConformanceTest


class TestWaitNoOperandReturnsZero(ConformanceTest):
    def test_failed_bg_job_does_not_leak(self):
        self.assert_identical_behavior('(exit 42) & wait; echo rc=$?')

    def test_two_bg_jobs_one_fails(self):
        self.assert_identical_behavior('true & false & wait; echo rc=$?')

    def test_successful_bg_job(self):
        self.assert_identical_behavior('true & wait; echo rc=$?')

    def test_wait_then_continues(self):
        self.assert_identical_behavior('(exit 3) & wait; echo done')


class TestWaitOperandReturnsStatus(ConformanceTest):
    """The operand form still reports the waited job's own status."""

    def test_wait_pid_success(self):
        self.assert_identical_behavior('true & wait $!; echo rc=$?')

    def test_wait_pid_failure(self):
        self.assert_identical_behavior('(exit 7) & wait $!; echo rc=$?')


class TestUnsetFunctionFallback(ConformanceTest):
    """`unset NAME` falls back to a function; checked by observable behavior
    (the `command not found` message prefix differs from bash by design)."""

    def test_bare_unset_removes_function(self):
        self.assert_identical_behavior(
            'f(){ echo FN; }; unset f; f 2>/dev/null || echo gone')

    def test_dash_v_does_not_touch_function(self):
        self.assert_identical_behavior(
            'f(){ echo FN; }; unset -v f 2>/dev/null; f')

    def test_variable_wins_over_function(self):
        self.assert_identical_behavior(
            'x(){ echo FN; }; x=1; unset x; echo "[${x-unset}]"; x')

    def test_dash_f_removes_function(self):
        self.assert_identical_behavior(
            'f(){ echo FN; }; unset -f f; f 2>/dev/null || echo gone')

    def test_unset_nonexistent_is_ok(self):
        self.assert_identical_behavior('unset nope; echo rc=$?')
