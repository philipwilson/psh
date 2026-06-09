"""
Tests for `return` inside sourced files.

Regression guard (verified against bash 5.2): `return N` in a sourced script
used to print "can only `return' from a function" and keep executing the
rest of the file with source rc 0. It must stop the file and become the exit
status of `source` itself.
"""

import subprocess
import sys


def run_psh(cmd, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, cwd=cwd)


class TestReturnFromSource:
    def test_return_stops_file_and_sets_status(self, tmp_path):
        (tmp_path / 's.sh').write_text('echo first\nreturn 3\necho not-reached\n')
        result = run_psh('source s.sh; echo rc=$?', cwd=tmp_path)
        assert result.stdout == 'first\nrc=3\n'
        assert 'not-reached' not in result.stdout
        assert 'can only' not in result.stderr

    def test_dot_alias_same_behavior(self, tmp_path):
        (tmp_path / 's.sh').write_text('return 4\n')
        result = run_psh('. s.sh; echo rc=$?', cwd=tmp_path)
        assert result.stdout == 'rc=4\n'

    def test_source_status_propagates_as_last_exit(self, tmp_path):
        (tmp_path / 's.sh').write_text('return 3\n')
        result = run_psh('source s.sh', cwd=tmp_path)
        assert result.returncode == 3

    def test_return_without_value_uses_last_status(self, tmp_path):
        (tmp_path / 's.sh').write_text('false\nreturn\necho no\n')
        result = run_psh('source s.sh; echo rc=$?', cwd=tmp_path)
        assert result.stdout == 'rc=1\n'

    def test_function_inside_sourced_file_returns_locally(self, tmp_path):
        """return inside a function in a sourced file exits the function only."""
        (tmp_path / 's.sh').write_text(
            'g(){ return 5; echo no; }\ng\necho after-g rc=$?\nreturn 9\necho not-reached\n')
        result = run_psh('source s.sh; echo rc=$?', cwd=tmp_path)
        assert result.stdout == 'after-g rc=5\nrc=9\n'

    def test_nested_source_returns_one_level(self, tmp_path):
        """return in an inner sourced file stops only that file."""
        (tmp_path / 'inner.sh').write_text('return 6\necho inner-no\n')
        (tmp_path / 'outer.sh').write_text('source inner.sh\necho outer rc=$?\n')
        result = run_psh('source outer.sh; echo rc=$?', cwd=tmp_path)
        assert result.stdout == 'outer rc=6\nrc=0\n'


class TestReturnErrors:
    def test_top_level_return_is_error_rc_2(self):
        result = run_psh('return; echo rc=$?')
        assert result.stdout == 'rc=2\n'
        assert 'can only' in result.stderr

    def test_non_numeric_arg_returns_from_function_rc_2(self):
        """bash: the error still returns from the function, status 2."""
        result = run_psh('f(){ return abc; echo continues; }; f; echo rc=$?')
        assert result.stdout == 'rc=2\n'
        assert 'continues' not in result.stdout
        assert 'numeric argument required' in result.stderr
