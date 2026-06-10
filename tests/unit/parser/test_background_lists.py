"""
Tests for POSIX & grammar and structural incomplete-input detection
(v0.264.0).

Regression guards (verified against bash 5.2):
- `a && b &` used to attach '&' to the last simple command, so the list
  ran synchronously with only its tail backgrounded.
- `while ...; done &` and `if ...; fi &` were parse errors.
- `echo a & && b` was silently accepted.
- A line ending in `|` or `&&` in a script failed instead of continuing,
  because incomplete-input detection string-matched ~40 error messages
  (now: ParseError.at_eof).
"""

import subprocess
import sys


def run_psh(script):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                          capture_output=True, text=True, timeout=15)


class TestBackgroundLists:
    def test_and_list_backgrounds_whole_list(self):
        """`a && b &` returns immediately; b runs in the background."""
        result = run_psh('sleep 0.05 && echo bg-done & echo immediate; wait')
        assert result.stdout == 'immediate\nbg-done\n'

    def test_or_list_background(self):
        result = run_psh('false || echo rescued & wait')
        assert result.stdout == 'rescued\n'

    def test_while_loop_background(self):
        result = run_psh('while false; do :; done & echo ok; wait')
        assert result.stdout == 'ok\n'

    def test_if_background(self):
        result = run_psh('if true; then echo inner; fi & wait')
        assert result.stdout == 'inner\n'

    def test_for_background_in_function(self):
        result = run_psh('f(){ for i in 1; do echo $i; done & wait; }; f')
        assert result.stdout == '1\n'

    def test_amp_then_andand_is_syntax_error(self):
        result = run_psh('echo a & && echo b')
        assert result.returncode == 2
        assert 'syntax error' in result.stderr

    def test_simple_background_still_works(self):
        result = run_psh('echo a & wait; echo done')
        assert 'a' in result.stdout and 'done' in result.stdout

    def test_background_isolation(self):
        """The backgrounded list runs in a subshell (no state leaks back)."""
        result = run_psh('x=1; { x=2; } && x=3 & wait; echo $x')
        assert result.stdout == '1\n'


class TestLineContinuations:
    def test_newline_after_pipe(self):
        result = run_psh('echo hi |\ncat')
        assert result.stdout == 'hi\n'

    def test_script_line_ending_in_andand(self):
        result = run_psh('true &&\necho yes')
        assert result.stdout == 'yes\n'

    def test_script_line_ending_in_oror(self):
        result = run_psh('false ||\necho rescued')
        assert result.stdout == 'rescued\n'

    def test_genuinely_incomplete_still_errors(self):
        result = run_psh('echo oops &&')
        assert result.returncode == 2
