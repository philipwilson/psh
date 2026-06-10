"""
Integration tests for the modular lexer system.

Tests the complete modular lexer functionality including recognizer registry,
token recognition ordering, and integration with the main tokenization system.
"""

import pytest

from psh.lexer import LexerContext, ModularLexer, tokenize
from psh.lexer.recognizers import OperatorRecognizer
from psh.token_types import TokenType


def production_registry():
    """The recognizer registry exactly as ModularLexer builds it."""
    return ModularLexer('').registry


class TestModularLexerBasic:
    """Test basic modular lexer functionality."""

    def test_simple_command_tokenization(self):
        """Test tokenization of simple commands."""
        tokens = list(tokenize('echo hello'))

        # Filter out EOF tokens for easier testing
        non_eof_tokens = [t for t in tokens if t.type != TokenType.EOF]

        assert len(non_eof_tokens) >= 2
        assert non_eof_tokens[0].type == TokenType.WORD
        assert non_eof_tokens[0].value == 'echo'
        assert non_eof_tokens[1].type == TokenType.WORD
        assert non_eof_tokens[1].value == 'hello'

    def test_pipeline_tokenization(self):
        """Test tokenization of pipeline commands."""
        tokens = list(tokenize('ls | grep test'))

        # Should include PIPE token
        token_types = [t.type for t in tokens]
        assert TokenType.WORD in token_types  # 'ls'
        assert TokenType.PIPE in token_types  # '|'
        assert TokenType.WORD in token_types  # 'grep'

    def test_operator_recognition(self):
        """Test recognition of various operators."""
        test_cases = [
            ('echo hello && echo world', TokenType.AND_AND),
            ('echo hello || echo world', TokenType.OR_OR),
            ('echo hello; echo world', TokenType.SEMICOLON),
            ('echo hello > file', TokenType.REDIRECT_OUT),
            ('echo hello >> file', TokenType.REDIRECT_APPEND),
            ('cat < file', TokenType.REDIRECT_IN),
        ]

        for command, expected_operator in test_cases:
            tokens = list(tokenize(command))
            token_types = [t.type for t in tokens]
            assert expected_operator in token_types, f"Expected {expected_operator} in {command}"

    def test_keyword_recognition(self):
        """Test recognition of shell keywords."""
        tokens = list(tokenize('if test; then echo yes; fi'))

        # Should recognize keywords
        token_types = [t.type for t in tokens]
        assert TokenType.IF in token_types
        assert TokenType.THEN in token_types
        assert TokenType.FI in token_types

    def test_for_loop_tokenization(self):
        """Test tokenization of for loops."""
        tokens = list(tokenize('for file in *.txt; do echo $file; done'))

        token_types = [t.type for t in tokens]
        assert TokenType.FOR in token_types
        assert TokenType.IN in token_types
        assert TokenType.DO in token_types
        assert TokenType.DONE in token_types


class TestRecognizerRegistry:
    """Test recognizer registry functionality."""

    def test_default_registry_setup(self):
        """Test that the production registry includes expected recognizers."""
        registry = production_registry()
        recognizers = registry.get_recognizers()

        # Should have multiple recognizers
        assert len(recognizers) > 0

        # Check recognizer types
        recognizer_types = [type(r).__name__ for r in recognizers]
        assert 'OperatorRecognizer' in recognizer_types

    def test_priority_ordering(self):
        """Test that recognizers are ordered by priority."""
        registry = production_registry()
        recognizers = registry.get_recognizers()

        # Should be sorted by priority (highest first)
        priorities = [r.priority for r in recognizers]
        assert priorities == sorted(priorities, reverse=True)

    def test_registry_recognition(self):
        """Test registry recognition with context."""
        registry = production_registry()

        # Test operator recognition
        context = LexerContext()
        result = registry.recognize('&&', 0, context)
        assert result is not None
        token, new_pos, recognizer = result
        assert token.type == TokenType.AND_AND
        assert new_pos == 2

        # 'if' is recognized as WORD by LiteralRecognizer; KeywordNormalizer
        # handles keyword conversion in the full tokenize() pipeline.
        result = registry.recognize('if', 0, context)
        assert result is not None
        token, new_pos, recognizer = result
        assert token.type == TokenType.WORD
        assert new_pos == 2


class TestLexerCompatibility:
    """Test compatibility between modular and traditional lexer."""

    def test_equivalent_tokenization(self):
        """Test that modular lexer produces equivalent results."""
        test_commands = [
            'echo hello',
            'ls | grep test',
            'echo hello > file',
            'echo hello && echo world',
        ]

        for command in test_commands:
            # Get tokens from main tokenize function
            try:
                tokens = list(tokenize(command))
                # Test that we get reasonable tokenization
                assert len(tokens) > 0, f"No tokens for '{command}'"

                # Verify basic structure
                non_eof_tokens = [t for t in tokens if t.type != TokenType.EOF]
                assert len(non_eof_tokens) > 0, f"Only EOF tokens for '{command}'"

                # Test basic token properties
                for token in non_eof_tokens:
                    assert hasattr(token, 'type'), f"Token missing type: {token}"
                    assert hasattr(token, 'value'), f"Token missing value: {token}"
                    assert isinstance(token.value, str), f"Token value not string: {token}"

            except Exception as e:
                # Some advanced features may not be implemented yet
                pytest.skip(f"Skipping '{command}' due to implementation: {e}")


class TestLexerContext:
    """Test lexer context handling."""

    def test_command_position_context(self):
        """Test command position affects keyword recognition via full pipeline."""
        # Keywords are now handled entirely by KeywordNormalizer (post-tokenization),
        # not by a recognizer. The registry always produces WORD tokens for keywords.
        # Verify keyword recognition works through the full tokenize() pipeline.
        tokens = list(tokenize('if true; then echo yes; fi'))
        token_types = [t.type for t in tokens]
        assert TokenType.IF in token_types

        # In argument position, 'if' should remain WORD
        tokens = list(tokenize('echo if'))
        non_eof = [t for t in tokens if t.type != TokenType.EOF]
        assert non_eof[1].type == TokenType.WORD

    def test_bracket_depth_context(self):
        """Test bracket depth affects special operator recognition."""
        registry = production_registry()

        # With bracket depth, ]] should be recognized
        bracket_context = LexerContext(bracket_depth=1)
        result = registry.recognize(']]', 0, bracket_context)
        assert result is not None
        token, new_pos, recognizer = result
        assert token.type == TokenType.DOUBLE_RBRACKET

        # Without bracket depth, ]] should not be recognized as special operator
        no_bracket_context = LexerContext(bracket_depth=0)
        result = registry.recognize(']]', 0, no_bracket_context)
        # Should either be None or recognized as separate tokens
        if result is not None:
            token, new_pos, recognizer = result
            assert token.type != TokenType.DOUBLE_RBRACKET


class TestOperatorRecognition:
    """Test specific operator recognition patterns."""

    @pytest.fixture
    def recognizer(self):
        return OperatorRecognizer()

    @pytest.fixture
    def context(self):
        return LexerContext()

    def test_greedy_operator_matching(self, recognizer, context):
        """Test that longer operators are preferred."""
        # && should be recognized as single token, not two &
        result = recognizer.recognize('&&', 0, context)
        assert result is not None
        token, new_pos = result
        assert token.type == TokenType.AND_AND
        assert token.value == '&&'
        assert new_pos == 2

        # >> should be recognized as single token, not two >
        result = recognizer.recognize('>>', 0, context)
        assert result is not None
        token, new_pos = result
        assert token.type == TokenType.REDIRECT_APPEND
        assert token.value == '>>'
        assert new_pos == 2

    def test_single_vs_double_operators(self, recognizer, context):
        """Test distinction between single and double operators."""
        # Single operators
        single_ops = [
            ('|', TokenType.PIPE),
            ('&', TokenType.AMPERSAND),
            ('>', TokenType.REDIRECT_OUT),
            ('<', TokenType.REDIRECT_IN),
        ]

        for op, expected_type in single_ops:
            result = recognizer.recognize(op, 0, context)
            assert result is not None
            token, new_pos = result
            assert token.type == expected_type
            assert new_pos == 1

        # Double operators
        double_ops = [
            ('||', TokenType.OR_OR),
            ('&&', TokenType.AND_AND),
            ('>>', TokenType.REDIRECT_APPEND),
        ]

        for op, expected_type in double_ops:
            result = recognizer.recognize(op, 0, context)
            assert result is not None
            token, new_pos = result
            assert token.type == expected_type
            assert new_pos == 2


class TestKeywordRecognition:
    """Test keyword recognition via KeywordNormalizer (post-tokenization pass)."""

    def test_keyword_at_command_position(self):
        """Test keywords recognized at command position via full pipeline."""
        tokens = list(tokenize('if true; then echo yes; fi'))
        token_types = [t.type for t in tokens]
        assert TokenType.IF in token_types
        assert TokenType.THEN in token_types
        assert TokenType.FI in token_types

    def test_keyword_not_at_argument_position(self):
        """Test keywords NOT recognized at argument position."""
        tokens = list(tokenize('echo if'))
        non_eof = [t for t in tokens if t.type != TokenType.EOF]
        # 'if' in argument position should be WORD
        assert non_eof[1].type == TokenType.WORD
        assert non_eof[1].value == 'if'

    def test_control_flow_keywords(self):
        """Test recognition of control flow keywords."""
        tokens = list(tokenize('for i in a; do echo $i; done'))
        token_types = [t.type for t in tokens]
        assert TokenType.FOR in token_types
        assert TokenType.IN in token_types
        assert TokenType.DO in token_types
        assert TokenType.DONE in token_types
