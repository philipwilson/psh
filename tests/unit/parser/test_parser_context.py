"""Tests for ParserContext centralized state management.

These cover the context's REAL responsibilities: token access, error
creation/collection, and factory construction. (Earlier versions also
tested scope/rule tracking, heredoc trackers, profiling, and state-flag
save/restore — machinery that was never read by the parser and was removed
in v0.256.0.)
"""

import pytest

from psh.lexer.token_types import Token, TokenType
from psh.parser.config import ParserConfig
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
        # Out-of-bounds peek returns a synthetic EOF token (not the last real
        # token echoed back — that caused nontermination on sentinel-free
        # streams; see EOF-safe token stream fix / appraisal finding 4).
        assert ctx.peek(5).type == TokenType.EOF
        # Negative positions are rejected rather than wrapping around.
        with pytest.raises(IndexError):
            ctx.peek(-1)

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

        config = ParserConfig()
        ctx = ParserContext(tokens=tokens, config=config)

        with pytest.raises(ParseError):
            ctx.consume(TokenType.SEMICOLON)

    def test_consume_error_always_raises(self):
        """consume() ALWAYS raises on an unexpected token.

        There is no error-collection mode: a parse either succeeds or raises,
        so a missing required token can never yield a partial/fabricated AST.
        """
        tokens = [
            Token(TokenType.WORD, "echo", 0),
            Token(TokenType.EOF, "", 5)
        ]

        ctx = ParserContext(tokens=tokens, config=ParserConfig())

        with pytest.raises(ParseError):
            ctx.consume(TokenType.SEMICOLON)

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
        """Test context creation with a caller-supplied config."""
        tokens = [Token(TokenType.WORD, "test", 0)]
        config = ParserConfig()

        ctx = create_context(tokens, config)

        assert ctx.config is config

    def test_create_default(self):
        """Test default context creation."""
        tokens = [Token(TokenType.WORD, "test", 0)]

        ctx = create_context(tokens)

        assert isinstance(ctx.config, ParserConfig)
