"""Regression: `read` uses the real fd, not sys.stdin.

The read builtin used to decide between os.read(fd) and sys.stdin by probing
sys.stdin.fileno(); under pytest capture (and in forked subshells) that chose
the wrong source, so a subshell `read < file` failed and the whole suite needed
the `-s` flag. These tests deliberately run under normal pytest capture (no -s)
to prove the fix.
"""

import os

import pytest


def _read(shell, name):
    with open(os.path.join(shell.state.variables['PWD'], name)) as f:
        return f.read()


class TestReadFromRedirectedFd:
    def test_read_loop_in_subshell(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        with open(os.path.join(shell.state.variables['PWD'], 'in.txt'), 'w') as f:
            f.write("line1\nline2\n")
        shell.run_command(
            '(while read line; do echo "got: $line"; done) < in.txt > out.txt'
        )
        assert _read(shell, "out.txt") == "got: line1\ngot: line2\n"

    def test_read_from_file_redirection(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        with open(os.path.join(shell.state.variables['PWD'], 'in.txt'), 'w') as f:
            f.write("alpha beta\n")
        shell.run_command('read a b < in.txt; echo "$a-$b" > out.txt')
        assert _read(shell, "out.txt") == "alpha-beta\n"


class TestReadStringInput:
    """read with an in-process StringIO stdin must still work (captured_shell)."""

    def test_read_herestring(self, captured_shell):
        captured_shell.run_command('read a b <<< "hello world"; echo "$a/$b"')
        assert captured_shell.get_stdout() == "hello world".replace(" ", "/") + "\n"
