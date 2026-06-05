"""Unit tests for the zsh-compatible ``print`` builtin."""

import pytest


class TestPrintBasic:
    def test_basic(self, captured_shell):
        assert captured_shell.run_command("print hello world") == 0
        assert captured_shell.get_stdout() == "hello world\n"

    def test_no_args(self, captured_shell):
        assert captured_shell.run_command("print") == 0
        assert captured_shell.get_stdout() == "\n"

    def test_escapes_on_by_default(self, captured_shell):
        # Unlike echo, print interprets escapes without -e.
        captured_shell.run_command(r"print 'a\tb'")
        assert captured_shell.get_stdout() == "a\tb\n"

    def test_newline_escape(self, captured_shell):
        captured_shell.run_command(r"print 'a\nb'")
        assert captured_shell.get_stdout() == "a\nb\n"


class TestPrintFlags:
    def test_raw(self, captured_shell):
        captured_shell.run_command(r"print -r 'a\tb'")
        assert captured_shell.get_stdout() == r"a\tb" + "\n"

    def test_no_newline(self, captured_shell):
        captured_shell.run_command("print -n hello")
        assert captured_shell.get_stdout() == "hello"

    def test_list(self, captured_shell):
        captured_shell.run_command("print -l a b c")
        assert captured_shell.get_stdout() == "a\nb\nc\n"

    def test_list_no_newline(self, captured_shell):
        captured_shell.run_command("print -nl a b c")
        assert captured_shell.get_stdout() == "a\nb\nc"

    def test_null_separated(self, captured_shell):
        captured_shell.run_command("print -N a b")
        assert captured_shell.get_stdout() == "a\0b\0"

    def test_combined_raw_no_newline(self, captured_shell):
        captured_shell.run_command(r"print -rn 'a\tb'")
        assert captured_shell.get_stdout() == r"a\tb"

    def test_c_terminates_output(self, captured_shell):
        captured_shell.run_command(r"print 'foo\cbar'")
        assert captured_shell.get_stdout() == "foo"


class TestPrintBSDMode:
    def test_R_is_raw(self, captured_shell):
        captured_shell.run_command(r"print -R 'a\tb'")
        assert captured_shell.get_stdout() == r"a\tb" + "\n"

    def test_R_with_e_enables_escapes(self, captured_shell):
        captured_shell.run_command(r"print -R -e 'a\tb'")
        assert captured_shell.get_stdout() == "a\tb\n"

    def test_R_with_n(self, captured_shell):
        captured_shell.run_command(r"print -R -n 'a\tb'")
        assert captured_shell.get_stdout() == r"a\tb"

    def test_R_stops_option_parsing(self, captured_shell):
        # After -R, a -l is treated as an argument, not an option.
        captured_shell.run_command("print -R -l x")
        assert captured_shell.get_stdout() == "-l x\n"


class TestPrintOptionTerminators:
    def test_double_dash(self, captured_shell):
        captured_shell.run_command("print -- -n hello")
        assert captured_shell.get_stdout() == "-n hello\n"

    def test_lone_dash_terminates_options(self, captured_shell):
        # zsh treats a bare '-' as an end-of-options marker (consumed).
        captured_shell.run_command("print -")
        assert captured_shell.get_stdout() == "\n"

    def test_lone_dash_then_args(self, captured_shell):
        captured_shell.run_command("print - -n foo")
        assert captured_shell.get_stdout() == "-n foo\n"

    def test_invalid_option(self, captured_shell):
        rc = captured_shell.run_command("print -Z x")
        assert rc == 2
        assert "invalid option" in captured_shell.get_stderr()

    def test_unsupported_option(self, captured_shell):
        rc = captured_shell.run_command("print -z x")
        assert rc == 2
        assert "unsupported option" in captured_shell.get_stderr()


class TestPrintFormat:
    def test_format_cycling(self, captured_shell):
        captured_shell.run_command(r"print -f '%s=%d\n' a 1 b 2")
        assert captured_shell.get_stdout() == "a=1\nb=2\n"

    def test_format_attached(self, captured_shell):
        captured_shell.run_command(r"print -f'%s\n' hi")
        assert captured_shell.get_stdout() == "hi\n"

    def test_format_no_extra_newline(self, captured_shell):
        # -f controls output entirely; no separator/terminator added.
        captured_shell.run_command(r"print -f '%s' abc")
        assert captured_shell.get_stdout() == "abc"


class TestPrintMatch:
    def test_match_filters(self, captured_shell):
        captured_shell.run_command("print -m 'f*' foo far bar")
        assert captured_shell.get_stdout() == "foo far\n"

    def test_match_no_matches(self, captured_shell):
        captured_shell.run_command("print -m 'z*' foo bar")
        assert captured_shell.get_stdout() == "\n"

    def test_match_question_mark(self, captured_shell):
        captured_shell.run_command("print -m '?' a bb c")
        assert captured_shell.get_stdout() == "a c\n"


class TestPrintSort:
    def test_sort_ascending(self, captured_shell):
        captured_shell.run_command("print -o c b a")
        assert captured_shell.get_stdout() == "a b c\n"

    def test_sort_descending(self, captured_shell):
        captured_shell.run_command("print -O a b c")
        assert captured_shell.get_stdout() == "c b a\n"

    def test_sort_case_insensitive(self, captured_shell):
        captured_shell.run_command("print -i -o B a C")
        assert captured_shell.get_stdout() == "a B C\n"

    def test_sort_case_sensitive_default(self, captured_shell):
        # Uppercase sorts before lowercase by codepoint.
        captured_shell.run_command("print -o b A c")
        assert captured_shell.get_stdout() == "A b c\n"


class TestPrintHistory:
    def test_s_adds_to_history(self, captured_shell):
        captured_shell.run_command("print -s 'echo from history'")
        # Nothing printed.
        assert captured_shell.get_stdout() == ""
        assert "echo from history" in captured_shell.state.history


class TestPrintPromptExpansion:
    def test_P_expands(self, captured_shell):
        from psh.prompt import PromptExpander
        expected = PromptExpander(captured_shell).expand_prompt(r"\h")
        captured_shell.run_command(r"print -P '\h'")
        assert captured_shell.get_stdout() == expected + "\n"
