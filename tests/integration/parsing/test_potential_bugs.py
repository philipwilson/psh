"""
Potential bug regression tests for parsing/expansion/execution interactions.

These are marked xfail because they document suspected behavior gaps.
"""

from pathlib import Path

from psh.ast_nodes import ExpansionPart, SimpleCommand
from psh.lexer import tokenize
from psh.parser import Parser, ParserConfig


def _first_simple_command(ast):
    """Extract the first SimpleCommand from a parsed AST."""
    # Matches the structure used in tests/unit/expansion/test_word_ast_expansion.py
    and_or_list = ast.statements[0]
    return and_or_list.pipelines[0].commands[0]


def test_assignment_whitespace_does_not_absorb_next_token(captured_shell):
    """POSIX expands $BAR before BAR=echo applies: with BAR previously
    unset the command is `ok`, which is not found (bash: rc 127)."""
    shell = captured_shell
    shell.clear_output()

    result = shell.run_command("BAR=echo FOO= $BAR ok")

    assert result == 127
    assert shell.get_stdout() == ""

    # With BAR previously set, $BAR expands to the prior value while the
    # new one is only visible inside the command.
    shell.clear_output()
    result = shell.run_command("BAR=echo; BAR=printf $BAR ok")
    assert result == 0
    assert shell.get_stdout() == "ok\n"


def test_assignment_single_quoted_value_remains_literal(captured_shell):
    """$FOO in the command's own words expands BEFORE the temporary
    assignment applies (bash prints an empty line); the literal $HOME
    value is what the command itself sees."""
    shell = captured_shell
    shell.clear_output()

    result = shell.run_command("FOO='$HOME' echo \"$FOO\"")
    assert result == 0
    assert shell.get_stdout() == "\n"

    shell.clear_output()
    result = shell.run_command("f() { echo \"$FOO\"; }; FOO='$HOME' f")
    assert result == 0
    assert shell.get_stdout() == "$HOME\n"


def test_quoted_expansion_does_not_trigger_glob(captured_shell, temp_dir, monkeypatch):
    shell = captured_shell
    monkeypatch.chdir(temp_dir)

    Path(temp_dir, "fooXbar").write_text("")

    shell.run_command("var='*'")
    shell.clear_output()

    result = shell.run_command('echo foo"$var"bar')

    assert result == 0
    assert shell.get_stdout() == "foo*bar\n"


def test_tilde_not_expanded_from_parameter_expansion(captured_shell):
    shell = captured_shell
    shell.state.set_variable("var", "~")
    shell.clear_output()

    result = shell.run_command("echo ${var:-x}")

    assert result == 0
    assert shell.get_stdout() == "~\n"


def test_quoted_dollar_at_concatenation_splits(captured_shell):
    shell = captured_shell
    shell.state.positional_params = ["a", "b"]
    shell.clear_output()

    result = shell.run_command('printf "[%s]\\n" "x$@y"')

    assert result == 0
    assert shell.get_stdout() == "[xa]\n[by]\n"


def test_word_ast_tracks_expansion_inside_quoted_string():
    tokens = tokenize('echo "$HOME"')
    config = ParserConfig()
    parser = Parser(tokens, config=config)
    ast = parser.parse()

    cmd = _first_simple_command(ast)
    assert isinstance(cmd, SimpleCommand)
    assert cmd.words is not None
    assert len(cmd.words) >= 2

    quoted_word = cmd.words[1]
    assert any(isinstance(part, ExpansionPart) for part in quoted_word.parts)
