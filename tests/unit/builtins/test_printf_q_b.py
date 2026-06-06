"""printf %q (shell-quote) and %b (interpret escapes) format specifiers."""

import pytest


def _out(captured_shell, cmd):
    captured_shell.clear_output()
    assert captured_shell.run_command(cmd) == 0
    return captured_shell.get_stdout()


class TestPrintfQ:
    def test_space_backslash_escaped(self, captured_shell):
        assert _out(captured_shell, 'printf "%q\\n" "a b"') == "a\\ b\n"

    def test_empty_string(self, captured_shell):
        assert _out(captured_shell, 'printf "[%q]\\n" ""') == "['']\n"

    def test_safe_passthrough(self, captured_shell):
        assert _out(captured_shell, 'printf "%q\\n" abc123_./') == "abc123_./\n"

    def test_glob_metachars_escaped(self, captured_shell):
        assert _out(captured_shell, 'printf "%q\\n" "a*b?c"') == "a\\*b\\?c\n"

    def test_control_char_uses_ansi_c(self, captured_shell):
        # A tab triggers the whole-string $'...' form.
        assert _out(captured_shell, 'printf "%q\\n" "$(printf "a\\tb")"') == "$'a\\tb'\n"


class TestPrintfB:
    def test_interprets_escapes(self, captured_shell):
        assert _out(captured_shell, 'printf "%b\\n" "a\\tb"') == "a\tb\n"

    def test_newline_escape(self, captured_shell):
        assert _out(captured_shell, 'printf "%b" "x\\ny\\n"') == "x\ny\n"

    def test_cycling(self, captured_shell):
        assert _out(captured_shell, 'printf "%b\\n" "a\\tb" "c\\td"') == "a\tb\nc\td\n"

    def test_plain_passthrough(self, captured_shell):
        assert _out(captured_shell, 'printf "%b\\n" hello') == "hello\n"
