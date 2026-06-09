"""
Regression tests for redirection save/restore correctness.

These cover defects found in the 2026-06-09 architecture review:
- `builtin 2>&1` closed the shell's real stdout (every later builtin failed
  with "I/O operation on closed file").
- Restore iterated forward, so the same fd redirected twice (`cmd >a >b`)
  left fd pointing at the FIRST file afterwards; the builtin variant
  overwrote the stream backup the same way.
- A redirect failing part-way through (`cmd >a >/bad/x`) leaked the applied
  redirections permanently, hijacking the shell's stdout for the rest of
  the session.

All run psh in a subprocess: they exercise process-level fd state, which
must not run in the test runner's own process (see CLAUDE.md). Expected
behavior verified against bash 5.2.
"""

import subprocess
import sys

import pytest


def run_psh(cmd, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, cwd=cwd)


class TestDupRestores:
    def test_builtin_2_to_1_does_not_kill_stdout(self):
        """Regression: `true 2>&1` permanently broke builtin output."""
        result = run_psh('true 2>&1; echo after')
        assert result.stdout == 'after\n'
        assert 'closed file' not in result.stderr

    def test_builtin_echo_2_to_1_then_more_output(self):
        result = run_psh('echo hi 2>&1; echo again')
        assert result.stdout == 'hi\nagain\n'

    def test_builtin_1_to_2_does_not_kill_stderr(self):
        """`echo hi 1>&2` must not close the real stderr."""
        result = run_psh('echo hi 1>&2; echo err2 1>&2; echo out')
        assert result.stdout == 'out\n'
        assert result.stderr == 'hi\nerr2\n'
        assert 'lost sys.stderr' not in result.stderr

    def test_dup_into_file_for_builtin(self):
        result = run_psh('echo hi >tmp/dup1.txt 2>&1; cat tmp/dup1.txt; rm -f tmp/dup1.txt')
        assert result.stdout == 'hi\n'


class TestSameFdTwice:
    def test_builtin_same_fd_twice_restores_original(self, tmp_path):
        """`echo hi >c >d`: output in d, c empty, then stdout back to tty."""
        result = run_psh('echo hi >c >d; echo AFTER; cat c d', cwd=tmp_path)
        assert result.stdout == 'AFTER\nhi\n'

    def test_external_same_fd_twice_restores_original(self, tmp_path):
        """Brace group (fd-level path): restore must run in reverse order."""
        result = run_psh('{ /bin/echo hi; } >e >f; echo AFTER; cat e f',
                         cwd=tmp_path)
        assert result.stdout == 'AFTER\nhi\n'


class TestErrorPathRollback:
    def test_builtin_failed_second_redirect_rolls_back(self, tmp_path):
        """`echo hi >a >/bad/x` must not leave stdout pointing at a."""
        result = run_psh('echo hi >a >/nonexistent_zz/x; echo AFTER', cwd=tmp_path)
        assert 'AFTER' in result.stdout
        assert (tmp_path / 'a').read_text() == ''

    def test_external_failed_second_redirect_rolls_back(self, tmp_path):
        """fd-level path: later commands must not write into the dead file."""
        result = run_psh(
            '{ /bin/echo hi; } >y >/nonexistent_zz/x\n'
            'echo SECOND\n/bin/echo THIRD\n', cwd=tmp_path)
        assert 'SECOND' in result.stdout
        assert 'THIRD' in result.stdout
        assert (tmp_path / 'y').read_text() == ''


class TestNormalPathsStillWork:
    @pytest.mark.parametrize('cmd,expected', [
        ('echo hi >o; cat o', 'hi\n'),
        ('echo one >>ap; echo two >>ap; cat ap', 'one\ntwo\n'),
        ('echo both &>b1; cat b1', 'both\n'),
        ('printf "x\\n" >r1; read v <r1; echo "got=$v"', 'got=x\n'),
    ])
    def test_basic_redirections(self, tmp_path, cmd, expected):
        result = run_psh(cmd, cwd=tmp_path)
        assert result.stdout == expected
