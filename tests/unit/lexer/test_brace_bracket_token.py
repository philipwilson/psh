"""Batch 9 (#19): '{' immediately followed by '[' is not a brace-group token.

`{[ab]}` was lexed as LBRACE + '[ab]}', inserting a spurious space. The
'{'-as-brace-group heuristic now only fires when '{' is followed by whitespace
or a command operator, not by '[' / ']'.
"""

import pytest


class TestBraceBracketToken:
    def _out(self, captured_shell, cmd):
        captured_shell.clear_output()
        assert captured_shell.run_command(cmd) == 0
        return captured_shell.get_stdout()

    def test_brace_bracket_is_one_word(self, captured_shell):
        assert self._out(captured_shell, 'echo {[ab]}') == "{[ab]}\n"

    def test_brace_bracket_with_trailing(self, captured_shell):
        assert self._out(captured_shell, 'echo {[ab]c}') == "{[ab]c}\n"


class TestBraceGroupsStillWork:
    def _out(self, captured_shell, cmd):
        captured_shell.clear_output()
        assert captured_shell.run_command(cmd) == 0
        return captured_shell.get_stdout()

    def test_brace_group(self, captured_shell):
        assert self._out(captured_shell, '{ echo hi; }') == "hi\n"

    def test_brace_group_multi(self, captured_shell):
        assert self._out(captured_shell, '{ echo a; echo b; }') == "a\nb\n"

    def test_function_with_brace_body(self, captured_shell):
        assert self._out(captured_shell, 'f() { echo fn; }; f') == "fn\n"

    def test_brace_expansion_unaffected(self, captured_shell):
        assert self._out(captured_shell, 'echo {a,b}') == "a b\n"
        assert self._out(captured_shell, 'echo pre{a,b}') == "prea preb\n"

    def test_empty_braces_is_word(self, captured_shell):
        assert self._out(captured_shell, 'echo {}') == "{}\n"
