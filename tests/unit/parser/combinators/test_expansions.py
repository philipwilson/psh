"""Tests for expansion and word-building parsers."""

import dataclasses

import pytest

from psh.ast_nodes import (
    ArithmeticExpansion,
    CommandSubstitution,
    ExpansionPart,
    LiteralPart,
    ProcessSubstitution,
    VariableExpansion,
    Word,
)
from psh.lexer.token_types import Token, TokenType
from psh.parser.combinators.expansions import (
    ExpansionParsers,
    create_expansion_parsers,
    parse_arithmetic_expansion,
    parse_command_substitution,
    parse_parameter_expansion,
    parse_process_substitution,
    parse_variable_expansion,
)


def make_token(token_type: TokenType, value: str, position: int = 0) -> Token:
    """Helper to create a token with minimal required fields."""
    return Token(type=token_type, value=value, position=position)


class TestExpansionParsers:
    """Test the ExpansionParsers class."""

    def test_initialization(self):
        """Test that ExpansionParsers initializes correctly."""
        parsers = ExpansionParsers()

        assert parsers.config is not None
        assert parsers.variable is not None
        assert parsers.command_sub is not None
        assert parsers.arith_expansion is not None

    def test_variable_expansion(self):
        """Test variable expansion parsing."""
        parsers = ExpansionParsers()

        tokens = [make_token(TokenType.VARIABLE, "USER")]
        result = parsers.variable.parse(tokens, 0)
        assert result.success is True
        assert result.value.value == "USER"

    def test_command_substitution(self):
        """Test command substitution parsing."""
        parsers = ExpansionParsers()

        # Test $(...) style
        tokens = [make_token(TokenType.COMMAND_SUB, "$(echo hello)")]
        result = parsers.command_sub.parse(tokens, 0)
        assert result.success is True
        assert result.value.value == "$(echo hello)"

        # Test backtick style
        tokens = [make_token(TokenType.COMMAND_SUB_BACKTICK, "`echo hello`")]
        result = parsers.command_sub_backtick.parse(tokens, 0)
        assert result.success is True
        assert result.value.value == "`echo hello`"

    def test_arithmetic_expansion(self):
        """Test arithmetic expansion parsing."""
        parsers = ExpansionParsers()

        tokens = [make_token(TokenType.ARITH_EXPANSION, "$((1 + 2))")]
        result = parsers.arith_expansion.parse(tokens, 0)
        assert result.success is True
        assert result.value.value == "$((1 + 2))"

    def test_combined_expansion_parser(self):
        """Test the combined expansion parser."""
        parsers = ExpansionParsers()

        # Should accept any expansion type
        test_cases = [
            (TokenType.VARIABLE, "USER"),
            (TokenType.COMMAND_SUB, "$(pwd)"),
            (TokenType.ARITH_EXPANSION, "$((10 * 2))"),
            (TokenType.PROCESS_SUB_IN, "<(cat file)"),
        ]

        for token_type, value in test_cases:
            tokens = [make_token(token_type, value)]
            result = parsers.expansion.parse(tokens, 0)
            assert result.success is True

    def test_format_token_value(self):
        """Test token value formatting."""
        parsers = ExpansionParsers()

        # Variable tokens get $ prefix
        var_token = make_token(TokenType.VARIABLE, "USER")
        assert parsers.format_token_value(var_token) == "$USER"

        # Command substitution keeps its format
        cmd_token = make_token(TokenType.COMMAND_SUB, "$(echo test)")
        assert parsers.format_token_value(cmd_token) == "$(echo test)"

        # Regular words stay as-is
        word_token = make_token(TokenType.WORD, "hello")
        assert parsers.format_token_value(word_token) == "hello"

    def test_is_expansion_token(self):
        """Test expansion token detection."""
        parsers = ExpansionParsers()

        # Expansion tokens
        exp_token = make_token(TokenType.VARIABLE, "VAR")
        assert parsers.is_expansion_token(exp_token) is True

        cmd_token = make_token(TokenType.COMMAND_SUB, "$(cmd)")
        assert parsers.is_expansion_token(cmd_token) is True

        # Non-expansion tokens
        word_token = make_token(TokenType.WORD, "hello")
        assert parsers.is_expansion_token(word_token) is False

        semi_token = make_token(TokenType.SEMICOLON, ";")
        assert parsers.is_expansion_token(semi_token) is False


class TestWordBuilding:
    """Test Word AST node building."""

    def test_build_word_from_literal(self):
        """Test building Word from literal token."""
        parsers = ExpansionParsers()

        token = make_token(TokenType.WORD, "hello")
        word = parsers.build_word_from_token(token)

        assert isinstance(word, Word)
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], LiteralPart)
        assert word.parts[0].text == "hello"

    def test_build_word_from_string(self):
        """Test building Word from string token."""
        parsers = ExpansionParsers()

        # Tokens are immutable; build with the quote type set.
        token = dataclasses.replace(
            make_token(TokenType.STRING, "hello world"), quote_type='"')
        word = parsers.build_word_from_token(token)

        assert isinstance(word, Word)
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], LiteralPart)
        assert word.parts[0].text == "hello world"
        assert word.quote_type == '"'

    def test_build_word_from_variable(self):
        """Test building Word from variable expansion."""
        parsers = ExpansionParsers()

        token = make_token(TokenType.VARIABLE, "USER")
        word = parsers.build_word_from_token(token)

        assert isinstance(word, Word)
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, VariableExpansion)
        assert word.parts[0].expansion.name == "USER"

    def test_build_word_from_command_sub(self):
        """Test building Word from command substitution."""
        parsers = ExpansionParsers()

        token = make_token(TokenType.COMMAND_SUB, "$(echo test)")
        word = parsers.build_word_from_token(token)

        assert isinstance(word, Word)
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, CommandSubstitution)
        assert word.parts[0].expansion.source == "echo test"
        assert word.parts[0].expansion.backtick_style is False

    def test_build_word_from_backtick_command_sub(self):
        """Test building Word from backtick command substitution."""
        parsers = ExpansionParsers()

        token = make_token(TokenType.COMMAND_SUB_BACKTICK, "`pwd`")
        word = parsers.build_word_from_token(token)

        assert isinstance(word, Word)
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, CommandSubstitution)
        assert word.parts[0].expansion.source == "pwd"
        assert word.parts[0].expansion.backtick_style is True

    def test_build_word_from_arithmetic(self):
        """Test building Word from arithmetic expansion."""
        parsers = ExpansionParsers()

        token = make_token(TokenType.ARITH_EXPANSION, "$((5 + 3))")
        word = parsers.build_word_from_token(token)

        assert isinstance(word, Word)
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, ArithmeticExpansion)
        assert word.parts[0].expansion.expression == "5 + 3"

    def test_build_word_from_process_sub_in(self):
        """Test building Word from input process substitution.

        Process substitution tokens become ProcessSubstitution expansion
        parts (same representation as the recursive descent parser) so the
        expansion manager performs the substitution and splices the
        /dev/fd/N path into the word — including embedded forms like
        ``pre<(cmd)post``.
        """
        parsers = ExpansionParsers()

        token = make_token(TokenType.PROCESS_SUB_IN, "<(sort file.txt)")
        word = parsers.build_word_from_token(token)

        assert isinstance(word, Word)
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, ProcessSubstitution)
        assert word.parts[0].expansion.direction == 'in'
        assert word.parts[0].expansion.source == 'sort file.txt'

    def test_build_word_from_process_sub_out(self):
        """Test building Word from output process substitution."""
        parsers = ExpansionParsers()

        token = make_token(TokenType.PROCESS_SUB_OUT, ">(gzip > output.gz)")
        word = parsers.build_word_from_token(token)

        assert isinstance(word, Word)
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, ProcessSubstitution)
        assert word.parts[0].expansion.direction == 'out'
        assert word.parts[0].expansion.source == 'gzip > output.gz'


class TestConvenienceFunctions:
    """Test convenience functions for expansion parsing."""

    def test_create_expansion_parsers(self):
        """Test factory function."""
        parsers = create_expansion_parsers()
        assert isinstance(parsers, ExpansionParsers)
        assert parsers.config is not None

    def test_parse_variable_expansion(self):
        """Test variable expansion parser function."""
        parser = parse_variable_expansion()
        tokens = [make_token(TokenType.VARIABLE, "HOME")]
        result = parser.parse(tokens, 0)
        assert result.success is True

    def test_parse_command_substitution(self):
        """Test command substitution parser function."""
        parser = parse_command_substitution()

        # Should accept both styles
        tokens1 = [make_token(TokenType.COMMAND_SUB, "$(date)")]
        result1 = parser.parse(tokens1, 0)
        assert result1.success is True

        tokens2 = [make_token(TokenType.COMMAND_SUB_BACKTICK, "`date`")]
        result2 = parser.parse(tokens2, 0)
        assert result2.success is True

    def test_parse_arithmetic_expansion(self):
        """Test arithmetic expansion parser function."""
        parser = parse_arithmetic_expansion()
        tokens = [make_token(TokenType.ARITH_EXPANSION, "$((42))")]
        result = parser.parse(tokens, 0)
        assert result.success is True

    def test_parse_parameter_expansion(self):
        """Test parameter expansion parser function."""
        parser = parse_parameter_expansion()
        tokens = [make_token(TokenType.PARAM_EXPANSION, "${USER:-nobody}")]
        result = parser.parse(tokens, 0)
        assert result.success is True

    def test_parse_process_substitution(self):
        """Test process substitution parser function."""
        parser = parse_process_substitution()

        # Should accept both directions
        tokens1 = [make_token(TokenType.PROCESS_SUB_IN, "<(cat)")]
        result1 = parser.parse(tokens1, 0)
        assert result1.success is True

        tokens2 = [make_token(TokenType.PROCESS_SUB_OUT, ">(tee)")]
        result2 = parser.parse(tokens2, 0)
        assert result2.success is True


class TestValidation:
    """Command-substitution bodies are parsed into a nested Program.

    Building a COMMAND_SUB word now parses the body (via the shared
    WordBuilder): valid bodies produce a Program, a function definition is
    accepted (bash allows it inside ``$(...)``), and a syntax error is raised
    at build time — the old shallow function-def guard is gone.
    """

    def _cmdsub_expansion(self, body):
        parsers = ExpansionParsers()
        token = make_token(TokenType.COMMAND_SUB, f"$({body})")
        word = parsers.build_word_from_token(token)
        return word.parts[0].expansion

    def test_valid_command_substitution_carries_program(self):
        for body in ("echo hello", "ls -la", "pwd"):
            exp = self._cmdsub_expansion(body)
            assert exp.source == body
            assert exp.program is not None

    def test_function_definition_in_cmdsub_is_accepted(self):
        # bash accepts a function definition inside $(...); the shallow
        # combinator guard that used to reject it is gone.
        exp = self._cmdsub_expansion("foo() { echo bar; }; foo")
        assert exp.program is not None

    def test_syntax_error_in_cmdsub_raises_at_build_time(self):
        from psh.parser.recursive_descent.helpers import ParseError
        with pytest.raises(ParseError):
            self._cmdsub_expansion("if")
