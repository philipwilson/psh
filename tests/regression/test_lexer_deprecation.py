"""
Regression tests for lexer deprecation to ensure functionality preservation.

These tests verify that the Enhanced Lexer Deprecation Plan (Phases 1-3) did not
break existing functionality during the transition to unified token classes and
simplified architecture.
"""

from psh.lexer import LexerConfig, ModularLexer, tokenize
from psh.lexer.token_types import Token, TokenType
from psh.parser import parse


class TestUnifiedTokenSystem:
    """Test that the unified token system works correctly."""

    def test_token_creation(self):
        """Test that tokens are created correctly."""
        tokens = tokenize("echo hello")

        # Should have tokens
        assert len(tokens) > 0
        first_token = tokens[0]

        # Should be Token class
        assert isinstance(first_token, Token)
        assert type(first_token).__name__ == "Token"

        # Should have position information
        assert hasattr(first_token, 'position')
        assert hasattr(first_token, 'end_position')

    def test_token_backward_compatibility(self):
        """Test that tokens maintain backward compatibility."""
        tokens = tokenize("echo hello")
        first_token = tokens[0]

        # Core fields should exist
        assert hasattr(first_token, 'type')
        assert hasattr(first_token, 'value')
        assert hasattr(first_token, 'position')

        # Should work with parser
        assert first_token.type == TokenType.WORD
        assert first_token.value == "echo"

    def test_enhanced_features_built_in(self):
        """Test that enhanced features are built into standard tokens."""
        tokens = tokenize('VAR="hello world"')

        # Should have multiple tokens
        assert len(tokens) >= 2

        # Should have quote information preserved
        assignment_token = None
        for token in tokens:
            if '=' in token.value:
                assignment_token = token
                break

        assert assignment_token is not None
        # Enhanced features like quote handling should work


class TestLexerFunctionality:
    """Test core lexer functionality preservation."""

    def test_basic_tokenization(self):
        """Test basic command tokenization."""
        tokens = tokenize("echo hello world")

        assert len(tokens) == 4  # echo, hello, world, EOF
        assert tokens[0].type == TokenType.WORD
        assert tokens[0].value == "echo"
        assert tokens[1].value == "hello"
        assert tokens[2].value == "world"

    def test_complex_command_tokenization(self):
        """Test complex command tokenization."""
        command = 'echo "hello world" | grep hello && echo $HOME'
        tokens = tokenize(command)

        # Should tokenize without errors
        assert len(tokens) > 5

        # Should have string tokens (quotes are processed)
        string_tokens = [t for t in tokens if t.type == TokenType.STRING]
        assert len(string_tokens) > 0

    def test_special_characters(self):
        """Test special character handling."""
        tokens = tokenize("echo $VAR && (cd /tmp; ls)")

        # Should handle variables ($ is processed, token type is VARIABLE)
        var_tokens = [t for t in tokens if t.type == TokenType.VARIABLE]
        assert len(var_tokens) > 0

        # Should handle operators
        operator_tokens = [t for t in tokens if t.type in [TokenType.AND_AND, TokenType.LPAREN, TokenType.SEMICOLON]]
        assert len(operator_tokens) > 0

    def test_modular_lexer_direct(self):
        """Test ModularLexer directly."""
        config = LexerConfig.create_batch_config()
        lexer = ModularLexer("echo test", config=config)
        tokens = lexer.tokenize()

        assert len(tokens) >= 2
        assert tokens[0].type == TokenType.WORD
        assert tokens[0].value == "echo"


class TestParserIntegration:
    """Test parser integration with unified lexer."""

    def test_basic_parsing(self):
        """Test that parser works with unified tokens."""
        tokens = tokenize("echo hello")
        ast = parse(tokens)

        # Should parse successfully
        assert ast is not None

    def test_complex_parsing(self):
        """Test complex command parsing."""
        tokens = tokenize("if test -f file; then echo found; fi")
        ast = parse(tokens)

        # Should parse control structures
        assert ast is not None

    def test_pipeline_parsing(self):
        """Test pipeline parsing."""
        tokens = tokenize("echo hello | grep h")
        ast = parse(tokens)

        # Should parse pipelines
        assert ast is not None


class TestPerformanceRegression:
    """Test that performance hasn't regressed significantly."""

    def test_tokenization_performance(self):
        """Test that tokenization performance is reasonable."""
        import time

        # Simple command
        start = time.perf_counter()
        for _ in range(100):
            tokenize("echo hello world")
        end = time.perf_counter()

        # Should complete in reasonable time (less than 1 second for 100 iterations)
        duration = end - start
        assert duration < 1.0, f"Tokenization too slow: {duration:.3f}s for 100 iterations"

    def test_complex_tokenization_performance(self):
        """Test complex tokenization performance."""
        import time

        complex_command = 'for i in $(seq 1 10); do echo "Item $i: $(date)" >> /tmp/log; done'

        start = time.perf_counter()
        for _ in range(50):
            tokenize(complex_command)
        end = time.perf_counter()

        # Should complete in reasonable time
        duration = end - start
        assert duration < 2.0, f"Complex tokenization too slow: {duration:.3f}s for 50 iterations"


class TestAPIStability:
    """Test that public API remains stable."""

    def test_tokenize_function_signature(self):
        """Test tokenize function signature.

        The historical ``strict`` (batch/interactive) flag was retired in the
        lexer R2 refactor — it selected between identical configs. tokenize()
        now takes just the input string plus optional shell_options.
        """
        tokens1 = tokenize("echo test")
        tokens2 = tokenize("echo test", shell_options={'posix': True})

        assert len(tokens1) > 0
        assert len(tokens2) > 0

    def test_modular_lexer_api(self):
        """Test ModularLexer API stability."""
        # Should accept input and config
        lexer = ModularLexer("echo test")
        tokens = lexer.tokenize()
        assert len(tokens) > 0

        # Should accept config
        config = LexerConfig.create_interactive_config()
        lexer_with_config = ModularLexer("echo test", config=config)
        tokens_with_config = lexer_with_config.tokenize()
        assert len(tokens_with_config) > 0

    def test_parser_api(self):
        """Test parser API stability."""
        tokens = tokenize("echo test")

        # Should accept tokens
        ast1 = parse(tokens)
        assert ast1 is not None

        # Should accept tokens with config
        from psh.parser import ParserConfig
        config = ParserConfig()
        ast2 = parse(tokens, config)
        assert ast2 is not None


class TestEdgeCases:
    """Test edge cases that might have been affected by deprecation."""

    def test_empty_input(self):
        """Test empty input handling."""
        tokens = tokenize("")
        # Should handle gracefully
        assert isinstance(tokens, list)

    def test_whitespace_only(self):
        """Test whitespace-only input."""
        tokens = tokenize("   \t  \n  ")
        # Should handle gracefully
        assert isinstance(tokens, list)

    def test_special_characters_edge_cases(self):
        """Test special character edge cases."""
        test_cases = [
            '"unclosed quote',
            "echo $",
            "echo $()",
            "echo ${",
            "# comment only",
        ]

        for case in test_cases:
            try:
                tokens = tokenize(case)
                # Should not crash, but may have errors in tokens
                assert isinstance(tokens, list)
            except Exception as e:
                # Lexer errors are acceptable for malformed input
                error_str = str(e).lower()
                assert ("lexer" in error_str or "token" in error_str or
                        "unclosed" in error_str or "syntax" in error_str)

    def test_unicode_handling(self):
        """Test unicode character handling."""
        # Should handle unicode in commands
        tokens = tokenize("echo 'héllo wörld'")
        assert len(tokens) >= 2

        # Should handle unicode in variable names (if supported)
        try:
            tokens = tokenize("echo $tëst")
            assert len(tokens) >= 2
        except:
            # Unicode variable names might not be supported, that's OK
            pass


class TestDeprecationCleanup:
    """Test that deprecated functionality is properly cleaned up."""

    def test_unified_token_class(self):
        """Test that Token class has unified functionality."""
        token = Token(
            type=TokenType.WORD,
            value="test",
            position=0,
            end_position=4
        )

        # Should have parts and is_keyword flag
        assert hasattr(token, 'parts')
        assert hasattr(token, 'is_keyword')
        assert token.is_keyword is False

    def test_no_feature_flags(self):
        """Test that feature flags are no longer accessible."""
        try:
            from psh.lexer.feature_flags import feature_flags  # noqa: F401
            raise AssertionError("feature_flags should not be importable")
        except ImportError:
            # Expected - feature flags should be removed
            pass

    def test_simplified_lexer_api(self):
        """Test that lexer API is simplified."""
        # Should not have enhanced vs basic distinction
        from psh.lexer import tokenize

        # tokenize should not have enhanced-specific parameters
        tokens = tokenize("echo test")
        assert len(tokens) > 0

        # Should not import enhanced-specific classes
        try:
            from psh.lexer import EnhancedModularLexer  # noqa: F401
            raise AssertionError("EnhancedModularLexer should not be importable")
        except ImportError:
            # Expected - enhanced classes should be removed
            pass
