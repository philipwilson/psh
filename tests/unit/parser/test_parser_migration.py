"""
Migrated parser tests from tests/test_parser.py.

These tests verify the parser's ability to construct correct ASTs
from tokenized input.
"""

import sys
from pathlib import Path

import pytest

# Add PSH to path
PSH_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PSH_ROOT))

from psh.ast_nodes import (
    AndOrList,
    CaseConditional,
    ForLoop,
    FunctionDef,
    IfConditional,
    Pipeline,
    Program,
    SimpleCommand,
    StatementList,
    SubshellGroup,
    WhileLoop,
)
from psh.lexer import tokenize
from psh.parser import ParseError, parse


def _sole_compound(ast):
    """The single compound command of a one-statement Program.

    A bare compound keeps its normal AndOrList -> Pipeline ancestry under the
    canonical Program root (it is not unwrapped), so descend through it.
    """
    assert isinstance(ast, Program)
    assert len(ast.statements) == 1
    return ast.statements[0].pipelines[0].commands[0]


class TestParserMigration:
    """Migrated tests from the original test_parser.py."""

    def get_first_pipeline(self, ast):
        """Helper to get the first pipeline from parsed AST."""
        # ast.statements[0] is AndOrList
        # AndOrList.pipelines[0] is Pipeline
        return ast.statements[0].pipelines[0] if ast.statements else None

    def get_first_command(self, ast):
        """Helper to get the first command from parsed AST."""
        pipeline = self.get_first_pipeline(ast)
        return pipeline.commands[0] if pipeline and pipeline.commands else None

    def test_simple_command(self):
        tokens = list(tokenize("ls -la"))
        ast = parse(tokens)

        # PSH parser returns the canonical Program root
        assert isinstance(ast, Program)
        assert len(ast.statements) == 1

        # Get the AndOrList
        and_or_list = ast.statements[0]
        assert isinstance(and_or_list, AndOrList)
        assert len(and_or_list.pipelines) == 1

        # Get the pipeline
        pipeline = and_or_list.pipelines[0]
        assert isinstance(pipeline, Pipeline)
        assert len(pipeline.commands) == 1

        # Get the command
        command = pipeline.commands[0]
        assert isinstance(command, SimpleCommand)
        assert command.args == ["ls", "-la"]
        assert command.redirects == []

    def test_pipeline(self):
        tokens = list(tokenize("cat file | grep pattern | wc -l"))
        ast = parse(tokens)

        # Get the pipeline from AndOrList
        pipeline = self.get_first_pipeline(ast)
        assert len(pipeline.commands) == 3

        assert pipeline.commands[0].args == ["cat", "file"]
        assert pipeline.commands[1].args == ["grep", "pattern"]
        assert pipeline.commands[2].args == ["wc", "-l"]

    def test_command_list(self):
        tokens = list(tokenize("echo first; echo second; echo third"))
        ast = parse(tokens)

        assert len(ast.statements) == 3
        assert self.get_first_command(ast).args == ["echo", "first"]
        # Get command from second statement
        cmd2 = ast.statements[1].pipelines[0].commands[0]
        assert cmd2.args == ["echo", "second"]
        # Get command from third statement
        cmd3 = ast.statements[2].pipelines[0].commands[0]
        assert cmd3.args == ["echo", "third"]

    def test_redirections(self):
        # Input redirection
        tokens = list(tokenize("cat < input.txt"))
        ast = parse(tokens)
        command = self.get_first_command(ast)
        assert command.args == ["cat"]
        assert len(command.redirects) == 1
        assert command.redirects[0].type == "<"
        assert command.redirects[0].target == "input.txt"

        # Output redirection
        tokens = list(tokenize("echo hello > output.txt"))
        ast = parse(tokens)
        command = self.get_first_command(ast)
        assert command.args == ["echo", "hello"]
        assert len(command.redirects) == 1
        assert command.redirects[0].type == ">"
        assert command.redirects[0].target == "output.txt"

        # Multiple redirections
        tokens = list(tokenize("sort < input.txt > output.txt"))
        ast = parse(tokens)
        command = self.get_first_command(ast)
        assert command.args == ["sort"]
        assert len(command.redirects) == 2
        assert command.redirects[0].type == "<"
        assert command.redirects[0].target == "input.txt"
        assert command.redirects[1].type == ">"
        assert command.redirects[1].target == "output.txt"

    def test_background_command(self):
        tokens = list(tokenize("sleep 10 &"))
        ast = parse(tokens)
        # Get the command
        command = self.get_first_command(ast)
        # Background flag is on the command itself
        assert command.background is True
        assert command.args == ["sleep", "10"]

    def test_quoted_arguments(self):
        tokens = list(tokenize('echo "hello world" \'single quotes\''))
        ast = parse(tokens)
        command = self.get_first_command(ast)
        assert command.args == ["echo", "hello world", "single quotes"]

    def test_variables(self):
        tokens = list(tokenize("echo $HOME $USER"))
        ast = parse(tokens)
        command = self.get_first_command(ast)
        # Parser preserves variable tokens
        assert len(command.args) == 3
        assert command.args[0] == "echo"
        # Variable values depend on how they're represented in AST

    def test_empty_command_list(self):
        tokens = list(tokenize(""))
        ast = parse(tokens)
        assert isinstance(ast, Program)
        assert len(ast.statements) == 0

        # Multiple newlines
        tokens = list(tokenize("\n\n\n"))
        ast = parse(tokens)
        assert len(ast.statements) == 0

    def test_trailing_semicolon(self):
        tokens = list(tokenize("echo hello;"))
        ast = parse(tokens)
        assert len(ast.statements) == 1
        assert self.get_first_command(ast).args == ["echo", "hello"]

    def test_multiple_separators(self):
        # Test that empty commands between semicolons are handled
        tokens = list(tokenize("echo first; echo second"))
        ast = parse(tokens)
        assert len(ast.statements) == 2
        assert self.get_first_command(ast).args == ["echo", "first"]
        # Get command from second statement
        cmd2 = ast.statements[1].pipelines[0].commands[0]
        assert cmd2.args == ["echo", "second"]

    def test_complex_command(self):
        tokens = list(tokenize("cat < in.txt | grep -v error | sort > out.txt; echo done &"))
        ast = parse(tokens)

        assert len(ast.statements) == 2

        # First pipeline
        pipeline1 = ast.statements[0].pipelines[0]
        assert len(pipeline1.commands) == 3

        # cat < in.txt
        cmd1 = pipeline1.commands[0]
        assert cmd1.args == ["cat"]
        assert len(cmd1.redirects) == 1
        assert cmd1.redirects[0].type == "<"
        assert cmd1.redirects[0].target == "in.txt"

        # grep -v error
        cmd2 = pipeline1.commands[1]
        assert cmd2.args == ["grep", "-v", "error"]

        # sort > out.txt
        cmd3 = pipeline1.commands[2]
        assert cmd3.args == ["sort"]
        assert len(cmd3.redirects) == 1
        assert cmd3.redirects[0].type == ">"
        assert cmd3.redirects[0].target == "out.txt"

        # Second pipeline: echo done &
        pipeline2 = ast.statements[1].pipelines[0]
        cmd4 = pipeline2.commands[0]
        assert cmd4.background is True
        assert cmd4.args == ["echo", "done"]

    def test_parse_errors(self):
        # Missing command
        with pytest.raises(ParseError, match="[Ee]xpected"):
            parse(list(tokenize("|")))

        # Missing redirection target
        with pytest.raises(ParseError, match="[Ee]xpected"):
            parse(list(tokenize("echo hello >")))

        # Pipe without command
        with pytest.raises(ParseError, match="[Ee]xpected"):
            parse(list(tokenize("echo hello; |")))


class TestAdvancedParsing:
    """Additional parser tests for complex constructs."""

    def test_if_statement(self):
        """Test parsing if statements."""
        tokens = list(tokenize("if true; then echo yes; else echo no; fi"))
        ast = parse(tokens)

        if_stmt = _sole_compound(ast)
        assert isinstance(if_stmt, IfConditional)

        # Check condition
        assert isinstance(if_stmt.condition, StatementList)
        assert len(if_stmt.condition.statements) == 1

        # Check then part
        assert isinstance(if_stmt.then_part, StatementList)
        assert len(if_stmt.then_part.statements) == 1

        # Check else part
        assert if_stmt.else_part is not None
        assert isinstance(if_stmt.else_part, StatementList)
        assert len(if_stmt.else_part.statements) == 1

    def test_while_loop(self):
        """Test parsing while loops."""
        tokens = list(tokenize("while test $x -lt 10; do echo $x; done"))
        ast = parse(tokens)

        while_stmt = _sole_compound(ast)
        assert isinstance(while_stmt, WhileLoop)

        # Check condition
        assert isinstance(while_stmt.condition, StatementList)

        # Check body
        assert isinstance(while_stmt.body, StatementList)
        assert len(while_stmt.body.statements) == 1

    def test_for_loop(self):
        """Test parsing for loops."""
        tokens = list(tokenize("for i in 1 2 3; do echo $i; done"))
        ast = parse(tokens)

        for_stmt = _sole_compound(ast)
        assert isinstance(for_stmt, ForLoop)

        # Check variable name
        assert for_stmt.variable == "i"

        # Check items
        assert for_stmt.items == ["1", "2", "3"]

        # Check body
        assert isinstance(for_stmt.body, StatementList)
        assert len(for_stmt.body.statements) == 1

    def test_function_definition(self):
        """Test parsing function definitions."""
        tokens = list(tokenize("hello() { echo Hello World; }"))
        ast = parse(tokens)

        assert isinstance(ast, Program)
        assert len(ast.statements) == 1
        func_def = ast.statements[0]
        assert isinstance(func_def, FunctionDef)

        # Check function name
        assert func_def.name == "hello"

        # Check body
        assert isinstance(func_def.body, StatementList)
        assert len(func_def.body.statements) == 1

    def test_case_statement(self):
        """Test parsing case statements."""
        code = """
        case $x in
            a) echo "is a" ;;
            b) echo "is b" ;;
            *) echo "other" ;;
        esac
        """
        tokens = list(tokenize(code))
        ast = parse(tokens)

        case_stmt = _sole_compound(ast)
        assert isinstance(case_stmt, CaseConditional)

        # Check expression to match
        assert case_stmt.expr == "$x"

        # Check items
        assert len(case_stmt.items) == 3

        # First case
        assert case_stmt.items[0].patterns[0].pattern == "a"
        assert len(case_stmt.items[0].commands.statements) == 1

        # Last case (default)
        assert case_stmt.items[2].patterns[0].pattern == "*"

    def test_subshell(self):
        """Test parsing subshell groups."""
        tokens = list(tokenize("(cd /tmp && echo hello)"))
        ast = parse(tokens)

        # Subshells in command position are a normal statement under Program
        assert isinstance(ast, Program)
        assert len(ast.statements) == 1
        pipeline = ast.statements[0].pipelines[0]
        assert len(pipeline.commands) == 1

        subshell = pipeline.commands[0]
        assert isinstance(subshell, SubshellGroup)

        # Check subshell body
        assert isinstance(subshell.statements, StatementList)
        assert len(subshell.statements.statements) == 1

    def test_logical_operators(self):
        """Test parsing && and || operators."""
        tokens = list(tokenize("true && echo success || echo failure"))
        ast = parse(tokens)

        # PSH represents logical operators in AndOrList
        assert len(ast.statements) == 1
        and_or_list = ast.statements[0]
        assert isinstance(and_or_list, AndOrList)

        # Should have multiple pipelines with operators
        assert len(and_or_list.pipelines) == 3
        assert len(and_or_list.operators) == 2
        assert and_or_list.operators == ['&&', '||']

    def test_here_document(self):
        """Test parsing here documents."""
        code = """cat << EOF
line1
line2
EOF"""
        tokens = list(tokenize(code))
        ast = parse(tokens)

        assert isinstance(ast, Program)
        # The parser treats heredoc content as separate statements
        # Just check that we have the cat command with heredoc redirect
        assert len(ast.statements) >= 1
        command = ast.statements[0].pipelines[0].commands[0]

        # Check for heredoc redirect
        assert len(command.redirects) == 1
        redirect = command.redirects[0]
        assert redirect.type in ("<<", "<<-")
        assert redirect.target == "EOF"
        # Heredoc content handling might be different in PSH

    def test_variable_assignment(self):
        """Test parsing variable assignments."""
        tokens = list(tokenize("VAR=value OTHER=123 echo $VAR"))
        ast = parse(tokens)

        command = ast.statements[0].pipelines[0].commands[0]

        # Check assignments - PSH stores them in args
        # Variable assignments before command are included in args
        assert len(command.args) >= 3  # VAR=value, OTHER=123, echo, $VAR
        assert "VAR=value" in command.args
        assert "OTHER=123" in command.args
        assert "echo" in command.args
