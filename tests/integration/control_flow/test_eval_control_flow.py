"""
Tests for control flow (break / continue / return) inside `eval`.

Regression guards (verified against bash 5.2):
- `eval break` inside a loop printed "only meaningful in a loop" three times
  and the loop kept running. Two causes: eval executed with a FRESH
  ExecutorVisitor whose loop_depth was 0, and the broad exception guards in
  executor/strategies.py converted LoopBreak/LoopContinue to exit status 1.
- `eval return N` inside a function reported "unexpected error" and did not
  return.
- Top-level `break`/`continue` printed the warning twice and exited 1
  (bash: warn once, continue executing, status 0).
"""

import subprocess
import sys


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestEvalControlFlow:
    def test_eval_break_exits_loop(self):
        result = run_psh('for i in 1 2 3; do eval break; echo $i; done; echo rc=$?')
        assert result.stdout == 'rc=0\n'
        assert 'only meaningful' not in result.stderr

    def test_eval_continue_skips_body(self):
        result = run_psh('for i in 1 2 3; do eval continue; echo $i; done; echo done')
        assert result.stdout == 'done\n'
        assert 'only meaningful' not in result.stderr

    def test_eval_break_n_nested_loops(self):
        result = run_psh('for i in 1 2; do for j in a b; do eval "break 2"; done; '
                         'echo no; done; echo out')
        assert result.stdout == 'out\n'

    def test_eval_return_in_function(self):
        result = run_psh('f(){ eval return 7; echo no; }; f; echo rc=$?')
        assert result.stdout == 'rc=7\n'
        assert 'unexpected error' not in result.stderr

    def test_eval_normal_commands_unaffected(self):
        result = run_psh('x=5; eval "echo \\$x"; eval false; echo rc=$?')
        assert result.stdout == '5\nrc=1\n'


class TestTopLevelBreakContinue:
    def test_top_level_break_warns_once_continues(self):
        """bash: warn once, keep executing, exit status 0."""
        result = run_psh('break; echo rc=$?')
        assert result.stdout == 'rc=0\n'
        assert result.stderr.count('only meaningful') == 1

    def test_top_level_continue_warns_once_continues(self):
        result = run_psh('continue; echo rc=$?')
        assert result.stdout == 'rc=0\n'
        assert result.stderr.count('only meaningful') == 1

    def test_break_in_loop_still_works(self):
        result = run_psh('for i in 1 2 3; do echo $i; break; done; echo ok')
        assert result.stdout == '1\nok\n'

    def test_continue_in_loop_still_works(self):
        result = run_psh('for i in 1 2; do continue; echo no; done; echo ok')
        assert result.stdout == 'ok\n'
