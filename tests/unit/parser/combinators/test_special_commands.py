"""Tests for special command parsers."""

from psh.ast_nodes import (
    ArithmeticEvaluation,
    BinaryTestExpression,
    EnhancedTestStatement,
    NegatedTestExpression,
    ProcessSubstitution,
    UnaryTestExpression,
)
from psh.lexer.token_types import Token, TokenType
from psh.parser.combinators.special_commands import SpecialCommandParsers, create_special_command_parsers


def make_token(token_type: TokenType, value: str, position: int = 0) -> Token:
    """Helper to create a token with minimal required fields."""
    return Token(type=token_type, value=value, position=position)


class TestArithmeticCommands:
    """Test arithmetic command parsing."""

    def test_simple_arithmetic_command(self):
        """Test basic ((...)) arithmetic command."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.DOUBLE_LPAREN, "(("),
            make_token(TokenType.WORD, "1"),
            make_token(TokenType.WORD, "+"),
            make_token(TokenType.WORD, "2"),
            make_token(TokenType.DOUBLE_RPAREN, "))")
        ]

        result = parsers.arithmetic_command.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, ArithmeticEvaluation)
        assert result.value.expression == "1 + 2"

    def test_arithmetic_with_variables(self):
        """Test arithmetic command with variables."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.DOUBLE_LPAREN, "(("),
            make_token(TokenType.VARIABLE, "x"),
            make_token(TokenType.WORD, "*"),
            make_token(TokenType.WORD, "2"),
            make_token(TokenType.WORD, "+"),
            make_token(TokenType.VARIABLE, "y"),
            make_token(TokenType.DOUBLE_RPAREN, "))")
        ]

        result = parsers.arithmetic_command.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, ArithmeticEvaluation)
        assert result.value.expression == "$x * 2 + $y"

    def test_nested_parentheses_in_arithmetic(self):
        """Test arithmetic with nested parentheses."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.DOUBLE_LPAREN, "(("),
            make_token(TokenType.LPAREN, "("),
            make_token(TokenType.WORD, "3"),
            make_token(TokenType.WORD, "+"),
            make_token(TokenType.WORD, "4"),
            make_token(TokenType.RPAREN, ")"),
            make_token(TokenType.WORD, "*"),
            make_token(TokenType.WORD, "2"),
            make_token(TokenType.DOUBLE_RPAREN, "))")
        ]

        result = parsers.arithmetic_command.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, ArithmeticEvaluation)
        assert result.value.expression == "( 3 + 4 ) * 2"

    def test_unterminated_arithmetic_command(self):
        """Test error on unterminated arithmetic command."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.DOUBLE_LPAREN, "(("),
            make_token(TokenType.WORD, "1"),
            make_token(TokenType.WORD, "+"),
            make_token(TokenType.WORD, "2")
        ]

        result = parsers.arithmetic_command.parse(tokens, 0)
        assert result.success is False
        assert "Unterminated" in result.error


class TestEnhancedTestExpressions:
    """Test enhanced test expression parsing."""

    def test_simple_string_comparison(self):
        """Test basic [[ string == string ]] expression."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.DOUBLE_LBRACKET, "[["),
            make_token(TokenType.WORD, "foo"),
            make_token(TokenType.WORD, "=="),
            make_token(TokenType.WORD, "bar"),
            make_token(TokenType.DOUBLE_RBRACKET, "]]")
        ]

        result = parsers.enhanced_test_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, EnhancedTestStatement)
        assert isinstance(result.value.expression, BinaryTestExpression)
        assert result.value.expression.left == "foo"
        assert result.value.expression.operator == "=="
        assert result.value.expression.right == "bar"

    def test_numeric_comparison(self):
        """Test numeric comparison operators."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.DOUBLE_LBRACKET, "[["),
            make_token(TokenType.VARIABLE, "x"),
            make_token(TokenType.WORD, "-gt"),
            make_token(TokenType.WORD, "10"),
            make_token(TokenType.DOUBLE_RBRACKET, "]]")
        ]

        result = parsers.enhanced_test_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, EnhancedTestStatement)
        assert isinstance(result.value.expression, BinaryTestExpression)
        assert result.value.expression.left == "$x"
        assert result.value.expression.operator == "-gt"
        assert result.value.expression.right == "10"

    def test_unary_file_test(self):
        """Test unary file test operator."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.DOUBLE_LBRACKET, "[["),
            make_token(TokenType.WORD, "-f"),
            make_token(TokenType.WORD, "/etc/passwd"),
            make_token(TokenType.DOUBLE_RBRACKET, "]]")
        ]

        result = parsers.enhanced_test_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, EnhancedTestStatement)
        assert isinstance(result.value.expression, UnaryTestExpression)
        assert result.value.expression.operator == "-f"
        assert result.value.expression.operand == "/etc/passwd"

    def test_negated_expression(self):
        """Test negated test expression."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.DOUBLE_LBRACKET, "[["),
            make_token(TokenType.WORD, "!"),
            make_token(TokenType.WORD, "-z"),
            make_token(TokenType.VARIABLE, "var"),
            make_token(TokenType.DOUBLE_RBRACKET, "]]")
        ]

        result = parsers.enhanced_test_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, EnhancedTestStatement)
        assert isinstance(result.value.expression, NegatedTestExpression)
        assert isinstance(result.value.expression.expression, UnaryTestExpression)
        assert result.value.expression.expression.operator == "-z"
        assert result.value.expression.expression.operand == "$var"

    def test_single_operand_test(self):
        """Test single operand (non-empty string test)."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.DOUBLE_LBRACKET, "[["),
            make_token(TokenType.VARIABLE, "var"),
            make_token(TokenType.DOUBLE_RBRACKET, "]]")
        ]

        result = parsers.enhanced_test_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, EnhancedTestStatement)
        assert isinstance(result.value.expression, UnaryTestExpression)
        assert result.value.expression.operator == "-n"
        assert result.value.expression.operand == "$var"


class TestProcessSubstitution:
    """Test process substitution parsing."""

    def test_input_process_substitution(self):
        """Test <(command) process substitution."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.PROCESS_SUB_IN, "<(ls -la)")
        ]

        result = parsers.process_substitution.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, ProcessSubstitution)
        assert result.value.direction == "in"
        assert result.value.command == "ls -la"

    def test_output_process_substitution(self):
        """Test >(command) process substitution."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.PROCESS_SUB_OUT, ">(tee log.txt)")
        ]

        result = parsers.process_substitution.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, ProcessSubstitution)
        assert result.value.direction == "out"
        assert result.value.command == "tee log.txt"

    def test_incomplete_process_substitution(self):
        """Test incomplete process substitution (missing closing paren)."""
        parsers = SpecialCommandParsers()

        tokens = [
            make_token(TokenType.PROCESS_SUB_IN, "<(incomplete")
        ]

        result = parsers.process_substitution.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, ProcessSubstitution)
        assert result.value.direction == "in"
        assert result.value.command == "incomplete"


class TestConvenienceFunctions:
    """Test convenience functions for special command parsing."""

    def test_create_special_command_parsers(self):
        """Test factory function."""
        parsers = create_special_command_parsers()
        assert isinstance(parsers, SpecialCommandParsers)
        assert parsers.config is not None
        assert parsers.tokens is not None
