"""
Tests for the umask and times builtins (added v0.260.0).

umask was previously a silent no-op on macOS: /usr/bin/umask ran as an
external command, so the mask never changed in the shell process.
All expectations verified against bash 5.2.
"""

import os
import re
import subprocess
import sys

import pytest


def run_psh(cmd, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, cwd=cwd)


@pytest.fixture
def saved_umask():
    """umask is process-global state — restore it around in-process tests."""
    mask = os.umask(0)
    os.umask(mask)
    yield mask
    os.umask(mask)


class TestUmask:
    def test_display_octal(self, captured_shell, saved_umask):
        assert captured_shell.run_command('umask') == 0
        assert captured_shell.get_stdout() == f"{saved_umask:04o}\n"

    def test_set_and_display(self, captured_shell, saved_umask):
        captured_shell.run_command('umask 077')
        captured_shell.clear_output()
        captured_shell.run_command('umask')
        assert captured_shell.get_stdout() == "0077\n"

    def test_symbolic_display(self, captured_shell, saved_umask):
        captured_shell.run_command('umask 0027')
        captured_shell.clear_output()
        captured_shell.run_command('umask -S')
        assert captured_shell.get_stdout() == "u=rwx,g=rx,o=\n"

    def test_reusable_form(self, captured_shell, saved_umask):
        captured_shell.run_command('umask 022')
        captured_shell.clear_output()
        captured_shell.run_command('umask -p')
        assert captured_shell.get_stdout() == "umask 0022\n"

    def test_symbolic_set(self, captured_shell, saved_umask):
        captured_shell.run_command('umask u=rwx,g=,o=')
        captured_shell.clear_output()
        captured_shell.run_command('umask')
        assert captured_shell.get_stdout() == "0077\n"

    def test_symbolic_minus(self, captured_shell, saved_umask):
        captured_shell.run_command('umask 022; umask g-w')
        captured_shell.clear_output()
        captured_shell.run_command('umask')
        # g-w on allowed perms of 0022 leaves the mask unchanged (g already
        # lacks w); bash prints 0022.
        assert captured_shell.get_stdout() == "0022\n"

    def test_out_of_range_octal(self, captured_shell, saved_umask):
        assert captured_shell.run_command('umask 8') == 1
        assert 'octal number out of range' in captured_shell.get_stderr()

    def test_invalid_symbolic(self, captured_shell, saved_umask):
        assert captured_shell.run_command('umask xyz') == 1

    def test_mask_actually_applies_to_created_files(self, tmp_path):
        """The regression that motivated this builtin."""
        result = run_psh('umask 077; touch f.txt; ls -l f.txt', cwd=tmp_path)
        assert result.stdout.startswith('-rw-------')


class TestTimes:
    def test_format_matches_bash(self, captured_shell):
        assert captured_shell.run_command('times') == 0
        out = captured_shell.get_stdout()
        lines = out.splitlines()
        assert len(lines) == 2
        pat = re.compile(r'^\d+m\d+\.\d{3}s \d+m\d+\.\d{3}s$')
        assert pat.match(lines[0]), lines[0]
        assert pat.match(lines[1]), lines[1]

    def test_is_builtin(self, captured_shell):
        captured_shell.run_command('type times')
        assert 'builtin' in captured_shell.get_stdout()
