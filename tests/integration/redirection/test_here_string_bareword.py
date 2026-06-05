"""Batch 4: here-strings (<<<) with bareword operands.

Regression test for the heredoc-detection regex falsely matching the
trailing `<<` of `<<<`, which caused a bareword here-string to silently
discard the entire command line.

Uses file redirection (external `cat`) so output is captured at the fd
level; run via run_tests.py (these fork + redirect).
"""

import os

import pytest


def _read(shell, name):
    with open(os.path.join(shell.state.variables['PWD'], name)) as f:
        return f.read()


class TestHereStringBareword:
    def test_bareword_does_not_swallow_command(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        # One input line with a bareword here-string in the middle: the old bug
        # treated it as an unclosed heredoc and discarded the whole line.
        shell.run_command(
            'echo before > out.txt; cat <<< hello >> out.txt; echo after >> out.txt'
        )
        assert _read(shell, "out.txt") == "before\nhello\nafter\n"

    def test_bareword(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('cat <<< hello > out.txt')
        assert _read(shell, "out.txt") == "hello\n"

    def test_no_space(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('cat <<<hello > out.txt')
        assert _read(shell, "out.txt") == "hello\n"

    def test_quoted(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('cat <<< "hello world" > out.txt')
        assert _read(shell, "out.txt") == "hello world\n"

    def test_number(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('cat <<< 123 > out.txt')
        assert _read(shell, "out.txt") == "123\n"

    def test_variable_operand_still_works(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('x=hi; cat <<< $x > out.txt')
        assert _read(shell, "out.txt") == "hi\n"


class TestHeredocStillWorks:
    def test_plain_heredoc(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('cat <<EOF > out.txt\nline1\nline2\nEOF')
        assert _read(shell, "out.txt") == "line1\nline2\n"

    def test_quoted_delimiter_no_expansion(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('cat <<"EOF" > out.txt\nno $expand\nEOF')
        assert _read(shell, "out.txt") == "no $expand\n"
