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
