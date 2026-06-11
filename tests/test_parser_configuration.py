"""Tests for parser configuration system."""

import pytest

from psh.lexer import tokenize
from psh.parser import (
    ErrorHandlingMode,
    Parser,
    ParserConfig,
    ParsingMode,
)
from psh.parser.recursive_descent.helpers import ParseError


class TestParserConfig:
    """Test the ParserConfig class."""

    def test_default_config(self):
        """Test default configuration."""
        config = ParserConfig()

        assert config.parsing_mode == ParsingMode.BASH_COMPAT
        assert config.error_handling == ErrorHandlingMode.STRICT
        assert config.enable_arithmetic == True

    def test_strict_posix_preset(self):
        """Test strict POSIX preset configuration."""
        config = ParserConfig.strict_posix()

        assert config.parsing_mode == ParsingMode.STRICT_POSIX
        assert config.error_handling == ErrorHandlingMode.STRICT
        assert config.allow_bash_conditionals == False
        assert config.allow_bash_arithmetic == False

    def test_config_clone(self):
        """Test configuration cloning with overrides."""
        base_config = ParserConfig.strict_posix()
        modified_config = base_config.clone(
            enable_arithmetic=True,
            max_errors=5
        )

        # Original should be unchanged
        assert base_config.enable_arithmetic == True  # Default in strict_posix
        assert base_config.max_errors == 10

        # Modified should have overrides
        assert modified_config.enable_arithmetic == True
        assert modified_config.max_errors == 5

        # Other settings should be preserved
        assert modified_config.parsing_mode == ParsingMode.STRICT_POSIX

    def test_clone_ignores_unknown_fields(self):
        """Test that clone silently ignores unknown field overrides."""
        config = ParserConfig()
        cloned = config.clone(nonexistent_field=True)

        # Should succeed without error, unknown field is ignored
        assert cloned.parsing_mode == ParsingMode.BASH_COMPAT

    def test_feature_checking(self):
        """Test feature checking methods."""
        config = ParserConfig()

        assert config.is_feature_enabled('arithmetic') == True
        assert config.is_feature_enabled('nonexistent') == False

        assert config.should_allow('bash_conditionals') == True
        assert config.should_allow('nonexistent') == False


class TestParserWithConfiguration:
    """Test parser behavior with different configurations."""

    def test_parser_feature_checking(self):
        """Test parser feature checking methods."""
        tokens = tokenize("echo hello")
        config = ParserConfig(enable_arithmetic=False)
        parser = Parser(tokens, config=config)

        assert parser.is_feature_enabled('arithmetic') == False

        assert parser.should_collect_errors() == False

    def test_parser_require_feature(self):
        """Test parser feature requirement checking."""
        tokens = tokenize("$((1 + 2))")
        config = ParserConfig(enable_arithmetic=False)
        parser = Parser(tokens, config=config)

        with pytest.raises(ParseError) as exc_info:
            parser.require_feature('arithmetic')

        assert 'arithmetic is not enabled' in str(exc_info.value)

    def test_parser_posix_compliance_check(self):
        """Test POSIX compliance checking."""
        tokens = tokenize("[[ test ]]")
        config = ParserConfig.strict_posix()
        parser = Parser(tokens, config=config)

        with pytest.raises(ParseError) as exc_info:
            parser.check_posix_compliance('[[ ]] enhanced test syntax', '[ ] test command')

        assert 'not POSIX compliant' in str(exc_info.value)
        assert 'Use [ ] test command instead' in str(exc_info.value)

    def test_error_collection_configuration(self):
        """Test error collection based on configuration."""
        tokens = tokenize("echo hello")

        # Strict mode does not collect errors
        strict_parser = Parser(tokens, config=ParserConfig.strict_posix())
        assert not strict_parser.ctx.config.collect_errors

        # Explicitly enabled collection is honored
        collecting_parser = Parser(tokens, config=ParserConfig(collect_errors=True))
        assert collecting_parser.ctx.config.collect_errors


class TestConfigurationIntegration:
    """Test integration of configuration with parsing features."""

    def test_create_configured_parser(self):
        """Test creating a configured parser from an existing parser."""
        tokens1 = tokenize("echo hello")
        original_parser = Parser(tokens1)

        tokens2 = tokenize("echo world")
        new_parser = original_parser.create_configured_parser(tokens2)

        # Should have same configuration
        assert new_parser.config.parsing_mode == original_parser.config.parsing_mode

    def test_configuration_inheritance(self):
        """Test that configuration is properly inherited by sub-parsers."""
        tokens = tokenize("if true; then echo hello; fi")
        config = ParserConfig(parsing_mode=ParsingMode.STRICT_POSIX)
        parser = Parser(tokens, config=config)

        # Main parser should have the config
        assert parser.config == config

        # Sub-parsers should reference the main parser with config
        assert parser.control_structures.parser == parser
        assert parser.statements.parser == parser


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
