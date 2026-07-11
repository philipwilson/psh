"""Tests for parser configuration system.

The production grammar is not configurable: the former strict-POSIX /
feature-gate façade and the unsafe error-collection mode were removed, so
``ParserConfig`` now carries no options. What remains is the honest clone()
contract and the fact that a config threads through the sub-parsers (so a
future real option would take effect uniformly).
"""

import pytest

from psh.lexer import tokenize
from psh.parser import Parser, ParserConfig


class TestParserConfig:
    """Test the ParserConfig class."""

    def test_clone_returns_distinct_equal_copy(self):
        """clone() returns a new, equal object (never the same instance)."""
        config = ParserConfig()
        cloned = config.clone()

        assert cloned == config
        assert cloned is not config

    def test_clone_rejects_unknown_fields(self):
        """clone() REJECTS unknown fields instead of silently ignoring them.

        The previous custom clone() dropped misspelled overrides without any
        signal (characterized as a defect). Delegating to dataclasses.replace
        makes a typo fail loudly.
        """
        config = ParserConfig()
        with pytest.raises(TypeError):
            config.clone(nonexistent_field=True)


class TestConfigurationIntegration:
    """Test integration of configuration with parsing features."""

    def test_configuration_threads_to_sub_parsers(self):
        """The config object is shared by the main parser and its sub-parsers."""
        tokens = tokenize("if true; then echo hello; fi")
        config = ParserConfig()
        parser = Parser(tokens, config=config)

        # The config lives on the one shared context (parser.ctx.config); the
        # sub-parsers all reach it through the main parser.
        assert parser.ctx.config is config

        # Sub-parsers should reference the main parser (and thus its config)
        assert parser.control_structures.parser is parser
        assert parser.statements.parser is parser


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
