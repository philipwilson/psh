"""Tests for ParserContext centralized state management.

These cover the context's REAL responsibilities: token access, error
creation/collection, and factory construction. (Earlier versions also
tested scope/rule tracking, heredoc trackers, profiling, and state-flag
save/restore — machinery that was never read by the parser and was removed
in v0.256.0.)
"""

from unittest.mock import Mock

import pytest

from psh.lexer.token_types import Token, TokenType
from psh.parser.config import ParserConfig, ParsingMode
from psh.parser.recursive_descent.context import ParserContext
from psh.parser.recursive_descent.helpers import ParseError
from psh.parser.recursive_descent.support.context_factory import create_context


class TestParserContext:
    """Test ParserContext functionality."""

    def test_context_creation(self):
        """Test basic context creation."""
        tokens = [
            Token(TokenType.WORD, "echo", 0),
            Token(TokenType.WORD, "hello", 5),
            Token(TokenType.EOF, "", 10)
        ]

        ctx = ParserContext(tokens=tokens)

        assert ctx.tokens == tokens
        assert ctx.current == 0
        assert isinstance(ctx.config, ParserConfig)
        assert ctx.errors == []
        assert not ctx.error_recovery_mode

    def test_token_access(self):
        """Test token access methods."""
        tokens = [
            Token(TokenType.WORD, "echo", 0),
            Token(TokenType.WORD, "hello", 5),
            Token(TokenType.EOF, "", 10)
        ]

        ctx = ParserContext(tokens=tokens)

        # Test peek
        assert ctx.peek() == tokens[0]
        assert ctx.peek(1) == tokens[1]
        assert ctx.peek(2) == tokens[2]
        assert ctx.peek(5) == tokens[2]  # Should return EOF for out of bounds

        # Test advance
        token = ctx.advance()
        assert token == tokens[0]
        assert ctx.current == 1

        # Test at_end
        assert not ctx.at_end()
        ctx.current = 2
        assert ctx.at_end()

        # Test match
        ctx.current = 0
        assert ctx.match(TokenType.WORD)
        assert not ctx.match(TokenType.SEMICOLON)
        assert ctx.match(TokenType.WORD, TokenType.SEMICOLON)

    def test_consume_success(self):
        """Test successful token consumption."""
        tokens = [
            Token(TokenType.WORD, "echo", 0),
            Token(TokenType.EOF, "", 5)
        ]

        ctx = ParserContext(tokens=tokens)

        token = ctx.consume(TokenType.WORD)
        assert token == tokens[0]
        assert ctx.current == 1

    def test_consume_error_strict(self):
        """Test consume error in strict mode."""
        tokens = [
            Token(TokenType.WORD, "echo", 0),
            Token(TokenType.EOF, "", 5)
        ]

        config = ParserConfig(collect_errors=False)
        ctx = ParserContext(tokens=tokens, config=config)

        with pytest.raises(ParseError):
            ctx.consume(TokenType.SEMICOLON)

    def test_consume_error_collect(self):
        """Test consume error in error collection mode."""
        tokens = [
            Token(TokenType.WORD, "echo", 0),
            Token(TokenType.EOF, "", 5)
        ]

        config = ParserConfig(collect_errors=True)
        ctx = ParserContext(tokens=tokens, config=config)

        # Should not raise, but add to errors
        token = ctx.consume(TokenType.SEMICOLON)
        assert token == tokens[0]  # Returns current token
        assert len(ctx.errors) == 1
        assert isinstance(ctx.errors[0], ParseError)

    def test_error_state_queries(self):
        """Test error-related state queries."""
        config = ParserConfig(
            collect_errors=True,
            enable_error_recovery=True,
            max_errors=5
        )
        # Add a token so we're not at end
        tokens = [Token(TokenType.WORD, "test", 0)]
        ctx = ParserContext(tokens=tokens, config=config)

        assert ctx.should_collect_errors()
        assert ctx.should_attempt_recovery()
        assert ctx.can_continue_parsing()

        # Add errors up to limit
        for i in range(4):  # Changed to 4 to stay under limit
            ctx.errors.append(Mock(spec=ParseError))

        # Should still be able to continue under limit
        assert ctx.can_continue_parsing()

        # Add one more error to reach limit
        ctx.errors.append(Mock(spec=ParseError))
        assert not ctx.can_continue_parsing()

    def test_source_lines_derived_from_text(self):
        """source_lines is split from source_text for error display."""
        tokens = [Token(TokenType.WORD, "echo", 0)]
        ctx = ParserContext(tokens=tokens, source_text="echo a\necho b")
        assert ctx.source_lines == ["echo a", "echo b"]


class TestParserContextFactory:
    """Test parser context factory functions."""

    def test_create_basic(self):
        """Test basic context creation."""
        tokens = [Token(TokenType.WORD, "test", 0)]

        ctx = create_context(tokens)

        assert ctx.tokens == tokens
        assert isinstance(ctx.config, ParserConfig)
        assert ctx.source_text is None

    def test_create_with_config(self):
        """Test context creation with custom config."""
        tokens = [Token(TokenType.WORD, "test", 0)]
        config = ParserConfig(parsing_mode=ParsingMode.STRICT_POSIX)

        ctx = create_context(tokens, config)

        assert ctx.config.parsing_mode == ParsingMode.STRICT_POSIX

    def test_create_default(self):
        """Test default context creation (bash-compatible by default)."""
        tokens = [Token(TokenType.WORD, "test", 0)]

        ctx = create_context(tokens)

        assert ctx.config.parsing_mode == ParsingMode.BASH_COMPAT
