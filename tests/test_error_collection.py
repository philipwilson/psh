"""Tests for multi-error collection functionality."""

import pytest

from psh.lexer import tokenize
from psh.lexer.token_types import TokenType
from psh.parser.recursive_descent.helpers import ParseError
from psh.parser.recursive_descent.parser import MultiErrorParseResult, Parser


class TestMultiErrorParseResult:
    """Test MultiErrorParseResult class."""

    def test_successful_parse_result(self):
        """Test result for successful parse."""
        from psh.ast_nodes import CommandList

        ast = CommandList()
        result = MultiErrorParseResult(ast, [])

        assert result.success == True
        assert result.partial_success == False
        assert result.has_errors() == False
        assert result.get_error_count() == 0

    def test_partial_success_result(self):
        """Test result for partial success with errors."""
        from psh.ast_nodes import CommandList
        from psh.lexer.token_types import Token, TokenType
        from psh.parser.recursive_descent.helpers import ErrorContext

        ast = CommandList()
        token = Token(TokenType.WORD, "test", 0)
        context = ErrorContext(token=token, message="Test error", position=0)
        error = ParseError(context)

        result = MultiErrorParseResult(ast, [error])

        assert result.success == False
        assert result.partial_success == True
        assert result.has_errors() == True
        assert result.get_error_count() == 1

    def test_failed_parse_result(self):
        """Test result for failed parse."""
        from psh.lexer.token_types import Token, TokenType
        from psh.parser.recursive_descent.helpers import ErrorContext

        token = Token(TokenType.WORD, "test", 0)
        context = ErrorContext(token=token, message="Test error", position=0)
        error = ParseError(context)

        result = MultiErrorParseResult(None, [error])

        assert result.success == False
        assert result.partial_success == False
        assert result.has_errors() == True
        assert result.get_error_count() == 1

    def test_format_errors(self):
        """Test error formatting."""
        from psh.lexer.token_types import Token, TokenType
        from psh.parser.recursive_descent.helpers import ErrorContext

        token1 = Token(TokenType.WORD, "test1", 0)
        context1 = ErrorContext(token=token1, message="First error", position=0)
        error1 = ParseError(context1)

        token2 = Token(TokenType.WORD, "test2", 10)
        context2 = ErrorContext(token=token2, message="Second error", position=10)
        error2 = ParseError(context2)

        result = MultiErrorParseResult(None, [error1, error2])
        formatted = result.format_errors()

        assert "Error 1: First error" in formatted
        assert "Error 2: Second error" in formatted


class TestParserWithErrorCollection:
    """Test Parser class with error collection enabled."""

    def test_parser_with_error_collection_enabled(self):
        """Test parser with error collection enabled."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens, collect_errors=True)

        assert parser.ctx.config.collect_errors

    def test_parser_without_error_collection(self):
        """Test parser without error collection."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens, collect_errors=False)

        assert not parser.ctx.config.collect_errors

    def test_parse_with_error_collection_success(self):
        """Test successful parsing with error collection."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens, collect_errors=True)

        result = parser.parse_with_error_collection()

        assert result.success == True
        assert result.get_error_count() == 0
        assert result.ast is not None

    def test_parse_with_error_collection_single_error(self):
        """Test parsing with single error."""
        # This command has a syntax error (incomplete if)
        tokens = tokenize("if true")
        parser = Parser(tokens, collect_errors=True)

        result = parser.parse_with_error_collection()

        assert result.success == False
        assert result.get_error_count() >= 1
        # AST might be partial or None depending on where error occurs

    def test_parse_with_error_collection_enables_collection(self):
        """Test that parse_with_error_collection enables collection if not present."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens, collect_errors=False)  # Start without collection

        assert not parser.ctx.config.collect_errors

        result = parser.parse_with_error_collection()

        assert result.success == True

    def test_max_errors_from_config(self):
        """Test max_errors is accessible from config."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens, collect_errors=True)

        assert parser.ctx.config.max_errors == 10

    def test_context_errors_used_directly(self):
        """Test that errors are stored in ctx.errors."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens, collect_errors=True)

        parser.parse_with_error_collection()

        # ctx.errors should be the source of truth
        assert isinstance(parser.ctx.errors, list)


class TestErrorCollectionIntegration:
    """Test integration of error collection with existing parser."""

    def test_normal_parsing_unaffected(self):
        """Test that normal parsing is unaffected by error collection features."""
        test_cases = [
            "echo hello",
            "if true; then echo hi; fi",
            "for i in 1 2 3; do echo $i; done",
        ]

        for command in test_cases:
            tokens = tokenize(command)

            # Parse normally
            parser1 = Parser(tokens)
            ast1 = parser1.parse()

            # Parse with error collection disabled
            parser2 = Parser(tokens, collect_errors=False)
            ast2 = parser2.parse()

            # Results should be the same type
            assert type(ast1) == type(ast2)

    def test_error_collection_preserves_error_quality(self):
        """Test that error collection doesn't degrade error quality."""
        # Use a command that will definitely cause a parse error
        command = "if"  # Incomplete if statement

        tokens1 = tokenize(command)
        parser1 = Parser(tokens1)

        tokens2 = tokenize(command)
        parser2 = Parser(tokens2, collect_errors=True)

        # Normal parsing should raise ParseError
        with pytest.raises(ParseError) as exc1:
            parser1.parse()

        # Error collection should capture the same error
        result = parser2.parse_with_error_collection()

        assert result.get_error_count() >= 1
        # The error message should be similar quality
        normal_error = str(exc1.value)
        collected_error = result.format_errors()

        # Both should mention the fundamental issue
        assert len(normal_error) > 10  # Non-trivial error message
        assert len(collected_error) > 10  # Non-trivial error message

    def test_fatal_error_stops_parsing(self):
        """Test that fatal errors stop error collection."""
        from psh.lexer.token_types import Token
        from psh.parser.recursive_descent.helpers import ErrorContext, ErrorSeverity

        tokens = tokenize("echo hello")
        parser = Parser(tokens, collect_errors=True)

        # Simulate a fatal error
        token = Token(TokenType.WORD, "test", 0)
        context = ErrorContext(token=token, message="Fatal error", position=0, severity=ErrorSeverity.FATAL)
        error = ParseError(context)

        parser.ctx.add_error(error)
        assert parser.ctx.fatal_error is not None
        assert parser.ctx.can_continue_parsing() == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
