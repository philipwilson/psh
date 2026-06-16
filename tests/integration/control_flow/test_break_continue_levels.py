"""
Tests for break N / continue N level semantics.

Bash reference (verified against bash 5.2):
- `break N` with N greater than the number of enclosing loops exits ALL
  enclosing loops with status 0 (it is not an error).
- `continue N` with N greater than the nesting depth resumes the outermost
  enclosing loop.

Regression guard: `break N` beyond the loop depth used to crash with
"cannot access local variable 'sys'" because function-local `import sys`
statements in ExecutorVisitor shadowed the module-level import.
"""

import subprocess
import sys


def run_psh(cmd):
    """Run a command in psh via subprocess, returning (stdout, stderr, rc)."""
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', cmd],
        capture_output=True, text=True
    )
    return result.stdout, result.stderr, result.returncode


class TestBreakContinueLevels:
    def test_break_beyond_depth_exits_loop_cleanly(self):
        """break 2 in a single loop exits the loop with status 0 (bash)."""
        out, err, rc = run_psh('while true; do break 2; done; echo rc=$?')
        assert out == 'rc=0\n'
        assert err == ''
        assert rc == 0

    def test_break_beyond_depth_no_internal_crash(self):
        """Regression: must not crash with a shadowed-import UnboundLocalError."""
        out, err, rc = run_psh('while true; do break 2; done; echo ok')
        assert 'unexpected error' not in err
        assert 'sys' not in err
        assert out == 'ok\n'

    def test_break_far_beyond_depth_in_nested_loops(self):
        """break 5 inside two nested loops exits both loops (bash)."""
        out, err, rc = run_psh(
            'for i in 1 2 3; do for j in a b; do break 5; done; done; echo rc=$?')
        assert out == 'rc=0\n'
        assert err == ''

    def test_continue_beyond_depth_resumes_outermost_loop(self):
        """continue 5 inside nested loops resumes the outermost loop (bash)."""
        out, err, rc = run_psh(
            'for i in 1 2; do for j in a b; do continue 5; echo no; done; '
            'echo i=$i; done; echo rc=$?')
        # The outer loop is resumed, so "echo i=$i" never runs.
        assert out == 'rc=0\n'
        assert err == ''

    def test_break_within_depth_still_targets_correct_loop(self):
        """break 2 with two enclosing loops exits exactly those two loops."""
        out, err, rc = run_psh(
            'for i in 1 2; do for j in a b; do echo $i$j; break 2; done; done; '
            'echo rc=$?')
        assert out == '1a\nrc=0\n'

    def test_continue_within_depth_still_targets_correct_loop(self):
        """continue 2 with two enclosing loops resumes the outer loop."""
        out, err, rc = run_psh(
            'for i in 1 2; do for j in a b; do echo $i$j; continue 2; done; done')
        assert out == '1a\n2a\n'

    def test_break_beyond_depth_c_style_for(self):
        """break 3 inside a C-style for loop exits it cleanly."""
        out, err, rc = run_psh(
            'for ((i=0; i<3; i++)); do break 3; done; echo rc=$?')
        assert out == 'rc=0\n'
        assert err == ''

    def test_break_beyond_depth_until_loop(self):
        """break 2 inside an until loop exits it cleanly."""
        out, err, rc = run_psh('until false; do break 2; done; echo rc=$?')
        assert out == 'rc=0\n'
        assert err == ''


class TestBreakContinueArgumentValidation:
    """R13.A: break/continue validate their level argument at RUNTIME.

    bash reference (bash 5.2). Previously psh silently dropped a non-numeric
    or variable argument (parsing ``break foo`` as ``break`` + a stray
    ``foo`` command), so ``break $n`` and ``break foo`` misbehaved.
    """

    def test_nonnumeric_argument_aborts_with_128(self):
        """break foo: 'numeric argument required', exit 128, shell aborts."""
        out, err, rc = run_psh(
            'for i in 1 2; do break foo; echo $i; done; echo AFTER')
        assert rc == 128
        assert 'numeric argument required' in err
        assert out == ''

    def test_continue_nonnumeric_argument_aborts_with_128(self):
        out, err, rc = run_psh(
            'for i in 1 2; do continue foo; echo $i; done; echo AFTER')
        assert rc == 128
        assert 'numeric argument required' in err

    def test_empty_string_argument_is_nonnumeric(self):
        """break "" is one (empty) field, not a missing argument."""
        out, err, rc = run_psh('for i in 1 2; do break ""; done; echo AFTER')
        assert rc == 128
        assert 'numeric argument required' in err

    def test_variable_level_argument_is_expanded(self):
        """break $n expands and breaks that many levels (was silently 1)."""
        out, err, rc = run_psh(
            'n=2; for i in 1 2; do for j in a b; do break $n; echo $i$j; done; '
            'done; echo AFTER')
        assert out == 'AFTER\n'
        assert rc == 0

    def test_zero_argument_out_of_range_status_1(self):
        """R14.B: break 0 reports 'loop count out of range' and the loop's
        status is 1 (bash) — captured immediately, before any command resets
        $?. (The loop body's `echo $i` does not run: the loop exited.)"""
        out, err, rc = run_psh(
            'for i in 1 2; do break 0; echo $i; done; echo "rc=$?"')
        assert out == 'rc=1\n'
        assert 'loop count out of range' in err

    def test_negative_argument_out_of_range_status_1(self):
        out, err, rc = run_psh(
            'for i in 1 2; do break -1; echo $i; done; echo "rc=$?"')
        assert out == 'rc=1\n'
        assert 'loop count out of range' in err

    def test_zero_argument_exits_all_enclosing_loops(self):
        """R14.B: break 0 / continue 0 exit ALL enclosing loops (bash), not
        just one — the outer loop body after the inner loop does not run."""
        out, err, rc = run_psh(
            'for i in 1 2; do for j in a b; do break 0; done; echo "in$i"; '
            'done; echo "D=$?"')
        assert out == 'D=1\n'  # neither 'in1' nor 'in2'
        assert 'loop count out of range' in err

    def test_too_many_arguments(self):
        """break 1 2: 'too many arguments', exit 1, shell aborts."""
        out, err, rc = run_psh('for i in 1 2; do break 1 2; done; echo AFTER')
        assert rc == 1
        assert 'too many arguments' in err
        assert 'AFTER' not in out

    def test_word_split_argument_is_too_many(self):
        """An unquoted variable splitting to two fields is 'too many'."""
        out, err, rc = run_psh(
            'm="1 2"; for i in 1 2; do break $m; done; echo AFTER')
        assert rc == 1
        assert 'too many arguments' in err

    def test_never_executed_bad_argument_is_not_an_error(self):
        """Validation is at runtime: a never-taken break foo must not error."""
        out, err, rc = run_psh(
            'for i in 1 2 3; do if false; then break foo; fi; echo $i; done')
        assert out == '1\n2\n3\n'
        assert err == ''
        assert rc == 0
