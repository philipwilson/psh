"""Tests for psh.line_editor_helpers.convert_multiline_to_single."""

from psh.line_editor_helpers import convert_multiline_to_single as conv


class TestConvertMultilineToSingle:
    def test_for_loop(self):
        assert conv("for i in 1 2 3\ndo\necho $i\ndone") == "for i in 1 2 3; do echo $i; done"

    def test_while_loop(self):
        assert conv("while read x\ndo\necho $x\ndone") == "while read x; do echo $x; done"

    def test_if_then_else_fi(self):
        out = conv("if true\nthen\necho yes\nelse\necho no\nfi")
        assert out == "if true; then echo yes; else echo no; fi"

    def test_case(self):
        out = conv("case $x in\na)\necho A\n;;\nesac")
        # Joined onto a single line; ends with esac
        assert out.startswith("case $x in") and out.endswith("; esac")

    def test_function_paren_form(self):
        assert conv("greet()\necho hi\n}") == "greet() { echo hi; }"

    def test_function_brace_form(self):
        assert conv("greet() {\necho hi\n}") == "greet() { echo hi; }"

    def test_backslash_continuation_joined_with_spaces(self):
        assert conv("echo one \\\necho two") == "echo one \\ echo two"

    def test_plain_single_line(self):
        assert conv("echo hello") == "echo hello"

    def test_empty(self):
        assert conv("") == ""
