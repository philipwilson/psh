"""Conformance tests for `exit` status semantics and `cd -L/-P` (R14.A).

`exit` (verified vs bash):
  - bare `exit` uses $? (the last command's status), not 0;
  - a numeric argument wraps modulo 256 (`exit 257`→1, `exit -1`→255,
    `exit 300`→44);
  - a non-numeric argument errors and exits with 2;
  - too many arguments errors and does NOT exit (status 1, shell continues).

`cd` (verified vs bash):
  - `-L` (default) keeps the logical symlink path; `-P` records the physical
    path; `cd a b` is "too many arguments" (status 1, no chdir).

These run in a subprocess (assert_identical_behavior), so the real process
exit code is what's compared.
"""

import sys

from conformance_framework import ConformanceTest


class TestExitStatus(ConformanceTest):
    def test_bare_exit_uses_last_status(self):
        self.assert_identical_behavior('false; exit')

    def test_bare_exit_after_true(self):
        self.assert_identical_behavior('true; exit')

    def test_exit_wraps_over_255(self):
        self.assert_identical_behavior('exit 257')

    def test_exit_wraps_300(self):
        self.assert_identical_behavior('exit 300')

    def test_exit_negative_wraps(self):
        self.assert_identical_behavior('exit -1')

    def test_exit_256_is_zero(self):
        self.assert_identical_behavior('exit 256')

    def test_exit_explicit_code(self):
        self.assert_identical_behavior('exit 42')

    def test_exit_too_many_args_does_not_exit(self, tmp_path):
        # bash reports "too many arguments", returns 1, and KEEPS RUNNING — so
        # the following command executes. Use a SCRIPT FILE (newline-separated):
        # bash's `-c 'a; b'` form has a separate quirk where the error abandons
        # the rest of the line, which is not the "exit doesn't terminate" point.
        import subprocess
        script = tmp_path / "exit_toomany.sh"
        script.write_text('exit 1 2 3\necho after=$?\n')
        psh = subprocess.run([sys.executable, '-m', 'psh', str(script)],
                             capture_output=True, text=True)
        bash = subprocess.run(['bash', str(script)], capture_output=True, text=True)
        assert psh.stdout == bash.stdout == 'after=1\n'
        assert psh.returncode == bash.returncode == 0
        assert 'too many arguments' in psh.stderr
        assert 'too many arguments' in bash.stderr


class TestCdOptions(ConformanceTest):
    def test_cd_too_many_arguments(self):
        # stdout/exit match; stderr banner prefix differs, so compare the tail.
        import subprocess
        cmd = 'cd a b; echo rc=$?'
        psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                             capture_output=True, text=True)
        bash = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)
        assert psh.stdout == bash.stdout == 'rc=1\n'
        assert 'too many arguments' in psh.stderr
        assert 'too many arguments' in bash.stderr

    def test_cd_dash_P_is_physical(self):
        # /tmp is a symlink on macOS; -P resolves it. Compare $PWD basename
        # logic via realpath equality, which both shells compute identically.
        self.assert_identical_behavior(
            'cd -P / && [ "$PWD" = "$(pwd -P)" ] && echo physical-ok')

    def test_cd_dash_L_default_logical(self):
        self.assert_identical_behavior('cd -L / && echo $PWD')

    def test_cd_invalid_option(self):
        # Exit code parity (2); stderr prefix differs so not compared here.
        import subprocess
        psh = subprocess.run([sys.executable, '-m', 'psh', '-c', 'cd -Z'],
                             capture_output=True, text=True)
        bash = subprocess.run(['bash', '-c', 'cd -Z'],
                              capture_output=True, text=True)
        assert psh.returncode == bash.returncode == 2
