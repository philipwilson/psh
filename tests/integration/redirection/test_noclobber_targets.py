"""noclobber (`set -C`) target-type semantics, bash-verified.

bash 5.2 blocks `>` under noclobber only when the target exists AND is a
regular file (directly or through a symlink), or is a dangling symlink.
Non-regular targets — /dev/null, devices, FIFOs — are always writable:
opening them for write destroys no data. `>|` and `>>` are never blocked.
"""

import os
import subprocess
import sys


class TestNoclobberNonRegularTargets:
    def test_dev_null_allowed(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('set -o noclobber')
        assert shell.run_command('echo x > /dev/null') == 0

    def test_stderr_to_dev_null_allowed(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('set -o noclobber')
        assert shell.run_command('echo x 2>/dev/null') == 0

    def test_external_command_to_dev_null_allowed(self, isolated_shell_with_temp_dir):
        # Exercises the forked-child noclobber path (setup_child_redirections).
        shell = isolated_shell_with_temp_dir
        shell.run_command('set -o noclobber')
        assert shell.run_command('/bin/echo x > /dev/null') == 0

    def test_exec_to_dev_null_allowed(self, temp_dir):
        # Permanent fd redirection rewrites the shell's own fds — MUST be a
        # subprocess (in-process it clobbers the test runner's capture fds).
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'set -o noclobber; exec 3>/dev/null; echo ok'],
            capture_output=True, text=True, cwd=temp_dir, timeout=10)
        assert result.returncode == 0
        assert result.stdout == 'ok\n'


class TestNoclobberRegularTargets:
    def test_existing_regular_file_blocked(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('echo first > guarded.txt')
        shell.run_command('set -o noclobber')
        assert shell.run_command('echo second > guarded.txt') != 0
        with open('guarded.txt') as f:
            assert f.read() == 'first\n'

    def test_nonexistent_file_allowed(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('set -o noclobber')
        assert shell.run_command('echo x > brand_new.txt') == 0
        with open('brand_new.txt') as f:
            assert f.read() == 'x\n'

    def test_clobber_operator_allowed(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('echo first > guarded.txt')
        shell.run_command('set -o noclobber')
        assert shell.run_command('echo second >| guarded.txt') == 0
        with open('guarded.txt') as f:
            assert f.read() == 'second\n'

    def test_append_allowed(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('echo first > guarded.txt')
        shell.run_command('set -o noclobber')
        assert shell.run_command('echo second >> guarded.txt') == 0
        with open('guarded.txt') as f:
            assert f.read() == 'first\nsecond\n'


class TestNoclobberSymlinkTargets:
    def test_symlink_to_regular_file_blocked(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('echo data > real.txt')
        os.symlink('real.txt', 'link')
        shell.run_command('set -o noclobber')
        assert shell.run_command('echo x > link') != 0

    def test_dangling_symlink_blocked(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        os.symlink('missing.txt', 'dangling')
        shell.run_command('set -o noclobber')
        assert shell.run_command('echo x > dangling') != 0
        assert not os.path.exists('missing.txt')
