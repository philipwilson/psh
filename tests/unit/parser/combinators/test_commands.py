"""Tests for command and pipeline parsers."""

from psh.ast_nodes import AndOrList, CommandList, Pipeline, SimpleCommand, Word
from psh.lexer.token_types import Token, TokenType
from psh.parser.combinators.commands import (
    CommandParsers,
    create_command_parsers,
    parse_simple_command,
)
from psh.parser.combinators.expansions import ExpansionParsers
from psh.parser.combinators.tokens import TokenParsers
from psh.parser.config import ParserConfig


def make_token(token_type: TokenType, value: str, position: int = 0) -> Token:
    """Helper to create a token with minimal required fields."""
    return Token(type=token_type, value=value, position=position)


class TestCommandParsers:
    """Test the CommandParsers class."""

    def test_initialization(self):
        """Test that CommandParsers initializes correctly."""
        parsers = CommandParsers()

        assert parsers.config is not None
        assert parsers.tokens is not None
        assert parsers.expansions is not None
        assert parsers.redirection is not None
        assert parsers.simple_command is not None
        assert parsers.pipeline is not None

    def test_parse_simple_command(self):
        """Test parsing a simple command."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "hello"),
            make_token(TokenType.WORD, "world")
        ]

        result = parsers.simple_command.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, SimpleCommand)
        assert result.value.args == ["echo", "hello", "world"]
        assert result.value.background is False

    def test_parse_simple_command_with_background(self):
        """Test parsing a command with background operator."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "sleep"),
            make_token(TokenType.WORD, "10"),
            make_token(TokenType.AMPERSAND, "&")
        ]

        result = parsers.simple_command.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, SimpleCommand)
        assert result.value.args == ["sleep", "10"]
        assert result.value.background is True

    def test_parse_simple_command_with_redirection(self):
        """Test parsing a command with output redirection."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "test"),
            make_token(TokenType.REDIRECT_OUT, ">"),
            make_token(TokenType.WORD, "output.txt")
        ]

        result = parsers.simple_command.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, SimpleCommand)
        assert result.value.args == ["echo", "test"]
        assert len(result.value.redirects) == 1
        assert result.value.redirects[0].type == ">"
        assert result.value.redirects[0].target == "output.txt"

    def test_parse_multiple_redirections(self):
        """Test parsing a command with multiple redirections."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "cmd"),
            make_token(TokenType.REDIRECT_IN, "<"),
            make_token(TokenType.WORD, "input.txt"),
            make_token(TokenType.REDIRECT_OUT, ">"),
            make_token(TokenType.WORD, "output.txt")
        ]

        result = parsers.simple_command.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, SimpleCommand)
        assert result.value.args == ["cmd"]
        assert len(result.value.redirects) == 2
        assert result.value.redirects[0].type == "<"
        assert result.value.redirects[0].target == "input.txt"
        assert result.value.redirects[1].type == ">"
        assert result.value.redirects[1].target == "output.txt"

    def test_parse_redirect_append(self):
        """Test parsing append redirection."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "more"),
            make_token(TokenType.REDIRECT_APPEND, ">>"),
            make_token(TokenType.WORD, "log.txt")
        ]

        result = parsers.simple_command.parse(tokens, 0)
        assert result.success is True
        assert len(result.value.redirects) == 1
        assert result.value.redirects[0].type == ">>"
        assert result.value.redirects[0].target == "log.txt"

    def test_parse_heredoc_redirection(self):
        """Test parsing heredoc redirection."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "cat"),
            make_token(TokenType.HEREDOC, "<<"),
            make_token(TokenType.WORD, "EOF")
        ]

        result = parsers.simple_command.parse(tokens, 0)
        assert result.success is True
        assert len(result.value.redirects) == 1
        redirect = result.value.redirects[0]
        assert redirect.type == "<<"
        assert redirect.target == "EOF"
        # heredoc_key and heredoc_quoted are not part of the AST node
        # They would be handled separately by a heredoc processor

    def test_parse_here_string(self):
        """Test parsing here string redirection."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "cat"),
            make_token(TokenType.HERE_STRING, "<<<"),
            make_token(TokenType.WORD, "hello")
        ]

        result = parsers.simple_command.parse(tokens, 0)
        assert result.success is True
        assert len(result.value.redirects) == 1
        redirect = result.value.redirects[0]
        assert redirect.type == "<<<"
        assert redirect.target == "hello"
        assert redirect.heredoc_content is None
        assert redirect.quote_type is None


class TestPipelineParsing:
    """Test pipeline parsing."""

    def test_parse_simple_pipeline(self):
        """Test parsing a simple two-command pipeline."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "ls"),
            make_token(TokenType.PIPE, "|"),
            make_token(TokenType.WORD, "grep"),
            make_token(TokenType.WORD, "test")
        ]

        result = parsers.pipeline.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, Pipeline)
        assert len(result.value.commands) == 2
        assert result.value.commands[0].args == ["ls"]
        assert result.value.commands[1].args == ["grep", "test"]

    def test_parse_multi_stage_pipeline(self):
        """Test parsing a three-stage pipeline."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "cat"),
            make_token(TokenType.WORD, "file.txt"),
            make_token(TokenType.PIPE, "|"),
            make_token(TokenType.WORD, "sort"),
            make_token(TokenType.PIPE, "|"),
            make_token(TokenType.WORD, "uniq")
        ]

        result = parsers.pipeline.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, Pipeline)
        assert len(result.value.commands) == 3
        assert result.value.commands[0].args == ["cat", "file.txt"]
        assert result.value.commands[1].args == ["sort"]
        assert result.value.commands[2].args == ["uniq"]

    def test_single_command_not_wrapped(self):
        """Test that single commands are not unnecessarily wrapped in Pipeline."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "hello")
        ]

        result = parsers.pipeline.parse(tokens, 0)
        assert result.success is True
        # Single simple command should still be wrapped in Pipeline
        assert isinstance(result.value, Pipeline)
        assert len(result.value.commands) == 1


class TestAndOrLists:
    """Test and-or list parsing."""

    def test_parse_and_list(self):
        """Test parsing commands connected with &&."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "test"),
            make_token(TokenType.WORD, "-f"),
            make_token(TokenType.WORD, "file"),
            make_token(TokenType.AND_AND, "&&"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "exists")
        ]

        result = parsers.and_or_list.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, AndOrList)
        assert len(result.value.pipelines) == 2
        assert len(result.value.operators) == 1
        assert result.value.operators[0] == "&&"

    def test_parse_or_list(self):
        """Test parsing commands connected with ||."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "command1"),
            make_token(TokenType.OR_OR, "||"),
            make_token(TokenType.WORD, "command2")
        ]

        result = parsers.and_or_list.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, AndOrList)
        assert len(result.value.pipelines) == 2
        assert len(result.value.operators) == 1
        assert result.value.operators[0] == "||"

    def test_parse_mixed_and_or(self):
        """Test parsing mixed && and || operators."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "cmd1"),
            make_token(TokenType.AND_AND, "&&"),
            make_token(TokenType.WORD, "cmd2"),
            make_token(TokenType.OR_OR, "||"),
            make_token(TokenType.WORD, "cmd3")
        ]

        result = parsers.and_or_list.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, AndOrList)
        assert len(result.value.pipelines) == 3
        assert len(result.value.operators) == 2
        assert result.value.operators[0] == "&&"
        assert result.value.operators[1] == "||"


class TestStatementLists:
    """Test statement list parsing."""

    def test_parse_statement_list(self):
        """Test parsing multiple statements separated by semicolons."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "one"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "two"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "three")
        ]

        result = parsers.statement_list.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, CommandList)
        assert len(result.value.statements) == 3

    def test_parse_statements_with_newlines(self):
        """Test parsing statements separated by newlines."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.WORD, "cmd1"),
            make_token(TokenType.NEWLINE, "\n"),
            make_token(TokenType.WORD, "cmd2"),
            make_token(TokenType.NEWLINE, "\n"),
            make_token(TokenType.WORD, "cmd3")
        ]

        result = parsers.statement_list.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, CommandList)
        assert len(result.value.statements) == 3

    def test_parse_empty_statement_list(self):
        """Test parsing an empty statement list."""
        parsers = CommandParsers()

        tokens = []
        result = parsers.statement_list.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, CommandList)
        assert len(result.value.statements) == 0

    def test_parse_with_leading_trailing_separators(self):
        """Test parsing with leading and trailing separators."""
        parsers = CommandParsers()

        tokens = [
            make_token(TokenType.NEWLINE, "\n"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "test"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.NEWLINE, "\n")
        ]

        result = parsers.statement_list.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, CommandList)
        assert len(result.value.statements) == 1


class TestConvenienceFunctions:
    """Test convenience functions for command parsing."""

    def test_create_command_parsers(self):
        """Test factory function."""
        parsers = create_command_parsers()
        assert isinstance(parsers, CommandParsers)
        assert parsers.config is not None

    def test_parse_simple_command_function(self):
        """Test simple command parser function."""
        tokens = TokenParsers()
        expansions = ExpansionParsers()
        parser = parse_simple_command(tokens, expansions)

        token_list = [
            make_token(TokenType.WORD, "ls"),
            make_token(TokenType.WORD, "-la")
        ]

        result = parser.parse(token_list, 0)
        assert result.success is True
        assert isinstance(result.value, SimpleCommand)

    def test_build_simple_command_with_word_ast(self):
        """Test building simple command with Word AST nodes."""
        config = ParserConfig()
        parsers = CommandParsers(config=config)

        tokens = [
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.VARIABLE, "USER")
        ]

        result = parsers.simple_command.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, SimpleCommand)
        assert hasattr(result.value, 'words')
        assert len(result.value.words) == 2
        assert isinstance(result.value.words[0], Word)
        assert isinstance(result.value.words[1], Word)
