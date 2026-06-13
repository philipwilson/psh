"""
Unit tests for the lexer package structure and API.

These tests verify that the lexer package exposes the correct public API
and that all components can be imported and used as expected.
"""

import sys
from pathlib import Path

# Add PSH to path
PSH_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PSH_ROOT))

from psh.lexer import (
    LexerConfig,
    LexerError,
    ModularLexer,
    tokenize,
    tokenize_with_heredocs,
)


class TestLexerPublicAPI:
    """Test the declared public API (__all__) of the lexer package."""

    def test_all_exports(self):
        """Test that __all__ contains exactly the declared public API."""
        import psh.lexer as lexer_pkg
        expected = {
            'ModularLexer', 'tokenize', 'tokenize_with_heredocs',
            'LexerConfig',
            'LexerError', 'UnclosedQuoteError',
        }
        assert set(lexer_pkg.__all__) == expected

    def test_main_imports(self):
        """Test that public API components can be imported from psh.lexer."""
        assert tokenize is not None
        assert tokenize_with_heredocs is not None
        assert LexerConfig is not None
        assert LexerError is not None
        assert ModularLexer is not None

    def test_tokenize_function_basic(self):
        """Test the main tokenize function with basic input."""
        # Simple command
        tokens = list(tokenize('echo hello'))
        assert len(tokens) == 3  # echo, hello, EOF
        assert tokens[0].value == 'echo'
        assert tokens[1].value == 'hello'
        assert tokens[2].type.name == 'EOF'

        # Empty input
        tokens = list(tokenize(''))
        assert len(tokens) == 1  # Just EOF
        assert tokens[0].type.name == 'EOF'

        # With operators
        tokens = list(tokenize('echo hello | grep world'))
        assert any(t.value == '|' for t in tokens)
        assert any(t.value == 'echo' for t in tokens)
        assert any(t.value == 'grep' for t in tokens)

    def test_modular_lexer_basic_usage(self):
        """Test ModularLexer class basic functionality."""
        # Test instantiation
        lexer = ModularLexer('echo test')
        assert lexer is not None

        # Test tokenization
        tokens = lexer.tokenize()
        assert len(tokens) == 3  # echo, test, EOF
        assert tokens[0].value == 'echo'
        assert tokens[1].value == 'test'
        assert tokens[2].type.name == 'EOF'

        # Test with different input
        lexer = ModularLexer('ls -la | grep ".txt"')
        tokens = lexer.tokenize()
        assert any(t.value == 'ls' for t in tokens)
        assert any(t.value == '-la' for t in tokens)
        assert any(t.value == '|' for t in tokens)
        assert any(t.value == 'grep' for t in tokens)
        assert any('.txt' in t.value for t in tokens)

    def test_lexer_config_usage(self):
        """Test lexer configuration options."""
        # Default config
        default_config = LexerConfig()
        assert default_config is not None
        assert hasattr(default_config, 'posix_mode')

        # Custom config
        config = LexerConfig(posix_mode=True)
        lexer = ModularLexer('echo test', config)
        tokens = lexer.tokenize()
        assert len(tokens) >= 2

        # Test that config affects lexing
        # (specific behavior would depend on what posix_mode does)
        lexer_default = ModularLexer('echo $VAR', LexerConfig())
        lexer_posix = ModularLexer('echo $VAR', LexerConfig(posix_mode=True))

        tokens_default = lexer_default.tokenize()
        tokens_posix = lexer_posix.tokenize()

        # Both should tokenize successfully
        assert len(tokens_default) >= 2
        assert len(tokens_posix) >= 2

    def test_lexer_error(self):
        """Test that LexerError is a proper exception class."""
        assert issubclass(LexerError, Exception)


class TestDemotedImports:
    """Test that items removed from __all__ are still importable from psh.lexer."""

    def test_constants_importable(self):
        """Test that lexer constants are still importable as convenience imports."""
        from psh.lexer import KEYWORDS

        assert isinstance(KEYWORDS, (set, frozenset))
        assert len(KEYWORDS) > 0
        assert 'if' in KEYWORDS

    def test_unicode_helpers_importable(self):
        """Test that Unicode helper functions are still importable."""
        from psh.lexer import is_identifier_start, is_whitespace

        assert is_identifier_start('a') is True
        assert is_identifier_start('1') is False
        assert is_whitespace(' ') is True
        assert is_whitespace('a') is False

    def test_token_classes_importable(self):
        """Test that TokenPart and RichToken are still importable."""
        from psh.lexer import RichToken, TokenPart

        assert TokenPart is not None
        assert RichToken is not None

    def test_lexer_context_importable(self):
        """Test that LexerContext is still importable."""
        from psh.lexer import LexerContext

        assert LexerContext is not None

    def test_tier3_importable_from_submodules(self):
        """Test that Tier 3 items are importable from their submodule paths."""


class TestPackageInternals:
    """Test internal package structure (for migration verification)."""

    def test_internal_module_imports(self):
        """Verify internal modules can be imported directly."""
        from psh.lexer import KEYWORDS, is_identifier_start
        from psh.lexer.constants import KEYWORDS as internal_keywords
        from psh.lexer.modular_lexer import ModularLexer as internal_lexer
        from psh.lexer.token_parts import TokenPart as internal_token_part
        from psh.lexer.unicode_support import is_identifier_start as internal_is_id

        # Verify they're the same as convenience imports
        assert internal_keywords == KEYWORDS
        assert internal_is_id('a') == is_identifier_start('a')
        assert internal_token_part is not None
        assert internal_lexer is not None

    def test_modular_lexer_interface(self):
        """Test that ModularLexer has expected methods and attributes."""
        lexer = ModularLexer('test input')

        # Core methods
        assert hasattr(lexer, 'tokenize')
        assert callable(lexer.tokenize)
        assert hasattr(lexer, 'emit_token')
        assert callable(lexer.emit_token)

        # Position tracking
        assert hasattr(lexer, 'position')
        assert hasattr(lexer, 'current_char')

        # Configuration and context
        assert hasattr(lexer, 'config')
        assert hasattr(lexer, 'context')

        # State management
        assert hasattr(lexer, 'tokens')
        assert isinstance(lexer.tokens, list)


class TestLexerEdgeCases:
    """Test lexer behavior with edge cases."""

    def test_empty_and_whitespace(self):
        """Test lexer with empty and whitespace-only input."""
        # Empty string
        tokens = list(tokenize(''))
        assert len(tokens) == 1
        assert tokens[0].type.name == 'EOF'

        # Only whitespace
        tokens = list(tokenize('   \t\n  '))
        assert tokens[-1].type.name == 'EOF'
        # May have NEWLINE tokens
        non_eof = [t for t in tokens if t.type.name != 'EOF']
        assert all(t.type.name in ('NEWLINE', 'WHITESPACE') or t.value.isspace()
                  for t in non_eof)

    def test_unicode_input(self):
        """Test lexer with Unicode input."""
        # Basic Unicode
        tokens = list(tokenize('echo "Hello, 世界"'))
        assert any('世界' in t.value for t in tokens)

        # Unicode identifiers
        tokens = list(tokenize('café=123'))
        assert any('café' in t.value for t in tokens)

        # Mixed scripts
        tokens = list(tokenize('echo "αβγ" | grep "текст"'))
        assert any('αβγ' in t.value for t in tokens)
        assert any('текст' in t.value for t in tokens)

    def test_long_input(self):
        """Test lexer with long input."""
        # Generate a long command
        long_command = ' | '.join(f'echo "Line {i}"' for i in range(100))

        tokens = list(tokenize(long_command))

        # Should handle long input without issues
        assert len(tokens) > 200  # Many tokens
        assert tokens[-1].type.name == 'EOF'

        # Check some tokens are correct
        assert any(t.value == 'echo' for t in tokens)
        assert any(t.value == '|' for t in tokens)
        assert any('Line 50' in t.value for t in tokens)
