"""Conformance tests for escaped dollar followed by parenthesis."""

import os
import sys

# Add parent directory to path for framework import
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestEscapedDollarConformance(ConformanceTest):
    """Test that PSH matches bash behavior for escaped dollar with parenthesis."""

    def test_escaped_dollar_paren_syntax_error(self):
        r"""Test that \$( is a syntax error matching bash."""
        # Both bash and PSH reject this as a syntax error with exit code 2
        # The error message format differs slightly between shells
        result = self.framework.compare_behavior(r'echo \$(echo test)')

        # Both should fail with exit code 2
        assert result.psh_result.exit_code == 2, f"PSH should exit with code 2, got {result.psh_result.exit_code}"
        assert result.bash_result.exit_code == 2, f"Bash should exit with code 2, got {result.bash_result.exit_code}"

        # Both should have syntax error in stderr
        assert "syntax error" in result.psh_result.stderr, f"PSH should report syntax error: {result.psh_result.stderr}"
        assert "syntax error" in result.bash_result.stderr, f"Bash should report syntax error: {result.bash_result.stderr}"

    def test_triple_backslash_dollar_paren_syntax_error(self):
        r"""Test that \\\$( is also a syntax error."""
        # Both bash and PSH reject this as a syntax error with exit code 2
        result = self.framework.compare_behavior(r'echo \\\$(echo test)')

        # Both should fail with exit code 2
        assert result.psh_result.exit_code == 2, f"PSH should exit with code 2, got {result.psh_result.exit_code}"
        assert result.bash_result.exit_code == 2, f"Bash should exit with code 2, got {result.bash_result.exit_code}"

        # Both should have syntax error in stderr
        assert "syntax error" in result.psh_result.stderr, f"PSH should report syntax error: {result.psh_result.stderr}"
        assert "syntax error" in result.bash_result.stderr, f"Bash should report syntax error: {result.bash_result.stderr}"

    def test_escaped_dollar_alone(self):
        r"""Test that \$ alone works correctly."""
        self.assert_identical_behavior(r'echo \$')

    def test_double_backslash_command_sub(self):
        r"""Test that \\$(cmd) is command substitution after literal backslash."""
        self.assert_identical_behavior(r'echo \\$(echo test)')

    def test_escaped_dollar_escaped_parens(self):
        r"""Test that \$\(cmd\) produces literal text."""
        # PSH now matches bash behavior: both output $(echo test)
        self.assert_identical_behavior(r'echo \$\(echo test\)')

    def test_escaped_dollar_in_double_quotes(self):
        r"""Test that "\$(cmd)" is literal in double quotes."""
        self.assert_identical_behavior(r'echo "\$(echo test)"')

    def test_escaped_dollar_in_single_quotes(self):
        r"""Test that '\$(cmd)' is completely literal in single quotes."""
        self.assert_identical_behavior(r"echo '\$(echo test)'")
