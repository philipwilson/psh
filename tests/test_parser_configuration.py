"""Tests for parser configuration system.

The production grammar is not feature-configurable (compound dispatch calls the
sub-parsers directly), so the former strict-POSIX/feature-gate façade was
removed. What remains is the error-collection configuration and the honest
clone() contract.
"""

import pytest

from psh.lexer import tokenize
from psh.parser import (
    ErrorHandlingMode,
    Parser,
    ParserConfig,
)


class TestParserConfig:
    """Test the ParserConfig class."""

    def test_default_config(self):
        """Test default configuration."""
        config = ParserConfig()

        assert config.error_handling == ErrorHandlingMode.STRICT
        assert config.max_errors == 10
        assert config.collect_errors is False

    def test_config_clone(self):
        """Test configuration cloning with overrides."""
        base_config = ParserConfig()
        modified_config = base_config.clone(max_errors=5, collect_errors=True)

        # Original should be unchanged
        assert base_config.max_errors == 10
        assert base_config.collect_errors is False

        # Modified should have overrides
        assert modified_config.max_errors == 5
        assert modified_config.collect_errors is True

    def test_clone_rejects_unknown_fields(self):
        """clone() now REJECTS unknown fields instead of silently ignoring them.

        The previous custom clone() dropped misspelled overrides without any
        signal (characterized as a defect). Delegating to dataclasses.replace
        makes a typo fail loudly.
        """
        config = ParserConfig()
        with pytest.raises(TypeError):
            config.clone(nonexistent_field=True)


class TestParserWithConfiguration:
    """Test parser behavior with different configurations."""

    def test_error_collection_configuration(self):
        """Test error collection based on configuration."""
        tokens = tokenize("echo hello")

        # Default does not collect errors
        default_parser = Parser(tokens, config=ParserConfig())
        assert not default_parser.ctx.config.collect_errors

        # Explicitly enabled collection is honored
        collecting_parser = Parser(tokens, config=ParserConfig(collect_errors=True))
        assert collecting_parser.ctx.config.collect_errors


class TestConfigurationIntegration:
    """Test integration of configuration with parsing features."""

    def test_configuration_inheritance(self):
        """Test that configuration is properly inherited by sub-parsers."""
        tokens = tokenize("if true; then echo hello; fi")
        config = ParserConfig(collect_errors=True)
        parser = Parser(tokens, config=config)

        # Main parser should have the config
        assert parser.config == config

        # Sub-parsers should reference the main parser with config
        assert parser.control_structures.parser == parser
        assert parser.statements.parser == parser


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
