"""Integration tests for the ``print`` builtin (redirection, pipelines, fds).

These exercise the forked-child write path, so they must be run with pytest's
``-s`` flag (use ``python run_tests.py``).
"""

import os

import pytest


def _read(shell, name):
    with open(os.path.join(shell.state.variables['PWD'], name)) as f:
        return f.read()


class TestPrintRedirection:
    def test_redirect_to_file(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command("print foo bar > out.txt")
        assert _read(shell, "out.txt") == "foo bar\n"

    def test_list_redirect(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command("print -l a b c > out.txt")
        assert _read(shell, "out.txt") == "a\nb\nc\n"


class TestPrintPipeline:
    def test_pipeline_line_count(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command("print -l a b c | wc -l > count.txt")
        assert _read(shell, "count.txt").strip() == "3"


class TestPrintFileDescriptor:
    def test_u2_to_stderr(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command("print -u2 oops 2> err.txt")
        assert _read(shell, "err.txt") == "oops\n"

    def test_u1_to_stdout(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command("print -u1 hi > out.txt")
        assert _read(shell, "out.txt") == "hi\n"
