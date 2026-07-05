"""
Basic parser tests - simplified version focusing on core functionality.
"""

import sys
from pathlib import Path

import pytest

# Add PSH to path
PSH_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PSH_ROOT))

from psh.ast_nodes import Program, SimpleCommand, SubshellGroup
from psh.lexer import tokenize
from psh.parser import ParseError, parse


class TestBasicParsing:
    """Basic parser functionality tests."""

    def test_simple_command(self):
        """Test parsing a simple command."""
        ast = parse(list(tokenize("echo hello world")))

        # Navigate: Program -> AndOrList -> Pipeline -> SimpleCommand
        cmd = ast.statements[0].pipelines[0].commands[0]
        assert isinstance(cmd, SimpleCommand)
        assert cmd.args == ["echo", "hello", "world"]

    def test_pipeline(self):
        """Test parsing a pipeline."""
        ast = parse(list(tokenize("ls | grep txt | wc -l")))

        pipeline = ast.statements[0].pipelines[0]
        assert len(pipeline.commands) == 3
        assert pipeline.commands[0].args == ["ls"]
        assert pipeline.commands[1].args == ["grep", "txt"]
        assert pipeline.commands[2].args == ["wc", "-l"]

    def test_multiple_commands(self):
        """Test parsing multiple commands with semicolon."""
        ast = parse(list(tokenize("echo one; echo two; echo three")))

        assert len(ast.statements) == 3
        # Each statement is an AndOrList with one Pipeline
        assert ast.statements[0].pipelines[0].commands[0].args == ["echo", "one"]
        assert ast.statements[1].pipelines[0].commands[0].args == ["echo", "two"]
        assert ast.statements[2].pipelines[0].commands[0].args == ["echo", "three"]

    def test_redirections(self):
        """Test parsing I/O redirections."""
        # Output redirect
        ast = parse(list(tokenize("echo hello > file.txt")))
        cmd = ast.statements[0].pipelines[0].commands[0]
        assert len(cmd.redirects) == 1
        assert cmd.redirects[0].type == ">"
        assert cmd.redirects[0].target == "file.txt"

        # Input redirect
        ast = parse(list(tokenize("cat < input.txt")))
        cmd = ast.statements[0].pipelines[0].commands[0]
        assert cmd.redirects[0].type == "<"
        assert cmd.redirects[0].target == "input.txt"

        # Append redirect
        ast = parse(list(tokenize("echo more >> file.txt")))
        cmd = ast.statements[0].pipelines[0].commands[0]
        assert cmd.redirects[0].type == ">>"
        assert cmd.redirects[0].target == "file.txt"

    def test_background_job(self):
        """Test parsing background jobs."""
        ast = parse(list(tokenize("sleep 100 &")))

        # Background flag is on the command in PSH
        cmd = ast.statements[0].pipelines[0].commands[0]
        assert cmd.background is True
        assert cmd.args == ["sleep", "100"]

    def test_quoted_strings(self):
        """Test parsing quoted arguments."""
        ast = parse(list(tokenize('echo "hello world" \'single quote\'')))

        cmd = ast.statements[0].pipelines[0].commands[0]
        assert cmd.args == ["echo", "hello world", "single quote"]

    def test_empty_input(self):
        """Test parsing empty input."""
        ast = parse(list(tokenize("")))
        assert isinstance(ast, Program)
        assert len(ast.statements) == 0

        # Just whitespace
        ast = parse(list(tokenize("   \n\t\n   ")))
        assert len(ast.statements) == 0

    def test_subshell(self):
        """Test parsing subshell groups."""
        ast = parse(list(tokenize("(echo in subshell)")))

        cmd = ast.statements[0].pipelines[0].commands[0]
        assert isinstance(cmd, SubshellGroup)
        # The subshell contains its own statement list
        subshell_cmd = cmd.statements.statements[0].pipelines[0].commands[0]
        assert subshell_cmd.args == ["echo", "in", "subshell"]

    def test_logical_operators(self):
        """Test parsing && and || operators."""
        ast = parse(list(tokenize("true && echo success || echo fail")))

        # PSH represents this as one AndOrList with multiple pipelines
        and_or = ast.statements[0]
        assert len(and_or.pipelines) == 3
        assert len(and_or.operators) == 2
        assert and_or.operators[0] == "&&"
        assert and_or.operators[1] == "||"

    def test_parse_errors(self):
        """Test that invalid syntax raises errors."""
        # Pipe without command
        with pytest.raises(ParseError):
            parse(list(tokenize("| grep")))

        # Redirect without target
        with pytest.raises(ParseError):
            parse(list(tokenize("echo >")))

        # Unclosed subshell
        with pytest.raises(ParseError):
            parse(list(tokenize("(echo unclosed")))


class TestParserEdgeCases:
    """Test edge cases and error handling."""

    def test_trailing_semicolon(self):
        """Test handling of trailing semicolon."""
        ast = parse(list(tokenize("echo hello;")))
        assert len(ast.statements) == 1
        cmd = ast.statements[0].pipelines[0].commands[0]
        assert cmd.args == ["echo", "hello"]

    def test_multiple_redirects(self):
        """Test multiple redirections on one command."""
        ast = parse(list(tokenize("cmd < input.txt > output.txt 2> error.txt")))

        cmd = ast.statements[0].pipelines[0].commands[0]
        assert len(cmd.redirects) == 3

        # Check each redirect - PSH stores fd separately from type
        redirects_info = [(r.type, r.target, getattr(r, 'fd', None)) for r in cmd.redirects]

        # Should have stdin, stdout, and stderr redirects
        assert any(r[0] == "<" for r in redirects_info)  # stdin
        assert any(r[0] == ">" and r[2] != 2 for r in redirects_info)  # stdout
        assert any(r[0] == ">" and r[2] == 2 for r in redirects_info)  # stderr

    def test_complex_pipeline_with_redirects(self):
        """Test complex pipeline with redirections."""
        ast = parse(list(tokenize(
            "cat < input.txt | grep pattern | sort > output.txt"
        )))

        pipeline = ast.statements[0].pipelines[0]
        assert len(pipeline.commands) == 3

        # First command has input redirect
        assert pipeline.commands[0].redirects[0].type == "<"

        # Last command has output redirect
        assert pipeline.commands[2].redirects[0].type == ">"

    def test_variable_preservation(self):
        """Test that variables are preserved in parsing."""
        ast = parse(list(tokenize("echo $HOME ${USER} $?")))

        cmd = ast.statements[0].pipelines[0].commands[0]
        # Parser preserves variables - exact representation depends on expansion
        assert len(cmd.args) >= 2  # At least echo + variables
        assert cmd.args[0] == "echo"
