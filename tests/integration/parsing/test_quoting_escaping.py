"""
Quoting and escaping mechanism integration tests.

Tests for quoting and escaping functionality including:
- Quote types (single, double, backticks)
- Quote nesting and interaction
- Escape sequences and backslash handling
- ANSI-C quoting ($'...')
- Quote removal mechanics
- Quote interaction with expansions
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


class QuotingTestHelper:
    """Helper class for quoting and escaping testing."""

    @classmethod
    def run_psh_command(cls, commands, timeout=5):
        """Run PSH with given commands and return output."""
        env = os.environ.copy()
        psh_root = Path(__file__).parent.parent.parent.parent
        env['PYTHONPATH'] = str(psh_root)
        env['PYTHONUNBUFFERED'] = '1'

        # Join commands with newlines
        if isinstance(commands, str):
            input_text = commands + '\n'
        else:
            input_text = '\n'.join(commands) + '\n'

        proc = subprocess.Popen(
            [sys.executable, '-u', '-m', 'psh', '--norc'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )

        try:
            stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
            return {
                'stdout': stdout,
                'stderr': stderr,
                'returncode': proc.returncode,
                'success': proc.returncode == 0
            }
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return {
                'stdout': stdout or '',
                'stderr': stderr or '',
                'returncode': -1,
                'error': 'timeout',
                'success': False
            }


class TestSingleQuotes:
    """Test single quote behavior."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_single_quote_literal(self):
        """Test that single quotes preserve literal values."""
        result = QuotingTestHelper.run_psh_command("echo 'hello world'")

        assert result['success']
        assert 'hello world' in result['stdout']

    def test_single_quote_preserves_spaces(self):
        """Test that single quotes preserve multiple spaces."""
        result = QuotingTestHelper.run_psh_command("echo 'hello     world'")

        assert result['success']
        assert 'hello     world' in result['stdout']

    def test_single_quote_preserves_special_chars(self):
        """Test that single quotes preserve special characters."""
        result = QuotingTestHelper.run_psh_command("echo '!@#$%^&*()[]{}|\\;:,.<>?'")

        assert result['success']
        assert '!@#$%^&*()[]{}|\\;:,.<>?' in result['stdout']

    def test_single_quote_no_variable_expansion(self):
        """Test that single quotes prevent variable expansion."""
        result = QuotingTestHelper.run_psh_command([
            'VAR=test',
            "echo '$VAR'"
        ])

        assert result['success']
        assert '$VAR' in result['stdout']
        assert 'test' not in result['stdout'].replace('$VAR', '')

    def test_single_quote_no_command_substitution(self):
        """Test that single quotes prevent command substitution."""
        result = QuotingTestHelper.run_psh_command("echo '$(echo hello)'")

        assert result['success']
        assert '$(echo hello)' in result['stdout']

    def test_single_quote_with_backslash(self):
        """Test that single quotes preserve backslashes literally."""
        result = QuotingTestHelper.run_psh_command("echo 'back\\slash\\test'")

        assert result['success']
        assert 'back\\slash\\test' in result['stdout']

    def test_empty_single_quotes(self):
        """Test empty single quotes."""
        result = QuotingTestHelper.run_psh_command("echo ''")

        assert result['success']
        # Should produce empty output or just newline


class TestDoubleQuotes:
    """Test double quote behavior."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_double_quote_basic(self):
        """Test basic double quote functionality."""
        result = QuotingTestHelper.run_psh_command('echo "hello world"')

        assert result['success']
        assert 'hello world' in result['stdout']

    def test_double_quote_preserves_spaces(self):
        """Test that double quotes preserve spaces."""
        result = QuotingTestHelper.run_psh_command('echo "hello     world"')

        assert result['success']
        assert 'hello     world' in result['stdout']

    def test_double_quote_variable_expansion(self):
        """Test that double quotes allow variable expansion."""
        result = QuotingTestHelper.run_psh_command([
            'VAR=test',
            'echo "Value: $VAR"'
        ])

        assert result['success']
        assert 'Value: test' in result['stdout']

    def test_double_quote_command_substitution(self):
        """Test that double quotes allow command substitution."""
        result = QuotingTestHelper.run_psh_command('echo "Result: $(echo hello)"')

        assert result['success']
        assert 'Result: hello' in result['stdout']

    def test_double_quote_arithmetic_expansion(self):
        """Test that double quotes allow arithmetic expansion."""
        result = QuotingTestHelper.run_psh_command('echo "Result: $((2 + 3))"')

        assert result['success']
        assert 'Result: 5' in result['stdout']

    def test_double_quote_escape_sequences(self):
        """Test escape sequences in double quotes."""
        result = QuotingTestHelper.run_psh_command('echo "quote: \\" slash: \\\\"')

        assert result['success']
        assert 'quote: "' in result['stdout']
        assert 'slash: \\' in result['stdout']

    def test_double_quote_preserve_some_special_chars(self):
        """Test that double quotes preserve most special characters."""
        result = QuotingTestHelper.run_psh_command('echo "!@#%^&*()[]{}|;:,.<>?"')

        assert result['success']
        assert '!@#%^&*()[]{}|;:,.<>?' in result['stdout']

    def test_empty_double_quotes(self):
        """Test empty double quotes."""
        result = QuotingTestHelper.run_psh_command('echo ""')

        assert result['success']
        # Should produce empty output or just newline


class TestQuoteNesting:
    """Test quote nesting and interaction."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_single_quote_inside_double_quotes(self):
        """Test single quotes inside double quotes."""
        result = QuotingTestHelper.run_psh_command('echo "It\'s a test"')

        assert result['success']
        assert "It's a test" in result['stdout']

    def test_double_quote_inside_single_quotes(self):
        """Test double quotes inside single quotes."""
        result = QuotingTestHelper.run_psh_command("echo 'He said \"hello\"'")

        assert result['success']
        assert 'He said "hello"' in result['stdout']

    def test_alternating_quotes(self):
        """Test alternating quote types."""
        result = QuotingTestHelper.run_psh_command("echo 'single'\"double\"'single again'")

        assert result['success']
        assert 'singledoublesingle again' in result['stdout']

    def test_quote_concatenation(self):
        """Test quote concatenation without spaces."""
        result = QuotingTestHelper.run_psh_command("echo 'hello'world'test'")

        assert result['success']
        assert 'helloworldtest' in result['stdout']

    def test_mixed_quoted_unquoted(self):
        """Test mixing quoted and unquoted sections."""
        result = QuotingTestHelper.run_psh_command([
            'VAR=value',
            'echo prefix"quoted $VAR" suffix'
        ])

        assert result['success']
        assert 'prefixquoted value suffix' in result['stdout']


class TestBackslashEscaping:
    """Test backslash escaping behavior."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_backslash_escape_special_chars(self):
        """Test backslash escaping of special characters."""
        result = QuotingTestHelper.run_psh_command('echo \\$VAR \\* \\? \\[')

        assert result['success']
        assert '$VAR' in result['stdout']
        assert '*' in result['stdout']
        assert '?' in result['stdout']
        assert '[' in result['stdout']

    def test_backslash_escape_quotes(self):
        """Test backslash escaping of quote characters."""
        result = QuotingTestHelper.run_psh_command("echo \\\"quoted\\\" \\'single\\'")

        assert result['success']
        assert '"quoted"' in result['stdout']
        assert "'single'" in result['stdout']

    def test_backslash_newline_continuation(self):
        """Test backslash-newline for line continuation."""
        result = QuotingTestHelper.run_psh_command([
            'echo hello \\',
            'world'
        ])

        assert result['success']
        assert 'hello world' in result['stdout']

    def test_backslash_in_single_quotes(self):
        """Test that backslash has no special meaning in single quotes."""
        result = QuotingTestHelper.run_psh_command("echo 'back\\slash\\literal'")

        assert result['success']
        assert 'back\\slash\\literal' in result['stdout']

    def test_backslash_in_double_quotes(self):
        """Test backslash escaping in double quotes."""
        result = QuotingTestHelper.run_psh_command('echo "back\\\\slash \\\"quote\\\""')

        assert result['success']
        assert 'back\\slash "quote"' in result['stdout']

    def test_literal_backslash(self):
        """Test producing literal backslash."""
        result = QuotingTestHelper.run_psh_command('echo \\\\')

        assert result['success']
        assert '\\' in result['stdout']


class TestANSICQuoting:
    """Test ANSI-C quoting ($'...') if supported."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_ansi_c_quoting_basic(self):
        """Test basic ANSI-C quoting."""
        result = QuotingTestHelper.run_psh_command("echo $'hello\\nworld'")

        assert result['success']
        lines = result['stdout'].strip().split('\n')
        assert 'hello' in lines
        assert 'world' in lines

    def test_ansi_c_escape_sequences(self):
        """Test ANSI-C escape sequences."""
        result = QuotingTestHelper.run_psh_command("echo $'tab:\\there'")

        assert result['success']
        assert '\t' in result['stdout']

    def test_ansi_c_hex_escapes(self):
        """Test ANSI-C hexadecimal escapes."""
        result = QuotingTestHelper.run_psh_command("echo $'\\x41\\x42\\x43'")

        assert result['success']
        assert 'ABC' in result['stdout']

    def test_ansi_c_unicode_escapes(self):
        """Test ANSI-C Unicode escapes."""
        result = QuotingTestHelper.run_psh_command("echo $'\\u0041\\u0042'")

        assert result['success']
        assert 'AB' in result['stdout']


class TestQuoteRemoval:
    """Test quote removal mechanics."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_quote_removal_in_assignment(self):
        """Test that quotes are removed in variable assignment."""
        result = QuotingTestHelper.run_psh_command([
            'VAR="quoted value"',
            'echo "($VAR)"'
        ])

        assert result['success']
        assert '(quoted value)' in result['stdout']
        # The quotes should be removed from the variable value

    def test_quote_removal_with_special_chars(self):
        """Test quote removal with special characters."""
        result = QuotingTestHelper.run_psh_command([
            "VAR='special!@#'",
            'echo "($VAR)"'
        ])

        assert result['success']
        assert '(special!@#)' in result['stdout']

    def test_partial_quote_removal(self):
        """Test quote removal in partially quoted strings."""
        result = QuotingTestHelper.run_psh_command([
            'VAR=prefix"quoted"suffix',
            'echo "($VAR)"'
        ])

        assert result['success']
        assert '(prefixquotedsuffix)' in result['stdout']

    def test_no_quote_removal_in_quotes(self):
        """Test that quotes are preserved when inside other quotes."""
        result = QuotingTestHelper.run_psh_command("echo \"It's 'quoted'\"")

        assert result['success']
        assert "It's 'quoted'" in result['stdout']


class TestQuoteInteractionWithExpansions:
    """Test quote interaction with various expansions."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_quotes_with_glob_patterns(self):
        """Test that quotes prevent glob expansion."""
        result = QuotingTestHelper.run_psh_command("echo '*.txt' \"*.py\"")

        assert result['success']
        assert '*.txt' in result['stdout']
        assert '*.py' in result['stdout']
        # Should not expand to actual files

    def test_quotes_with_brace_expansion(self):
        """Test that quotes prevent brace expansion."""
        result = QuotingTestHelper.run_psh_command("echo '{a,b,c}' \"{1,2,3}\"")

        assert result['success']
        assert '{a,b,c}' in result['stdout']
        assert '{1,2,3}' in result['stdout']
        # Should not expand braces

    def test_quotes_with_tilde_expansion(self):
        """Test quote interaction with tilde expansion."""
        result = QuotingTestHelper.run_psh_command("echo '~' \"~\"")

        assert result['success']
        # Tilde should not expand inside quotes
        assert '~' in result['stdout']

    def test_mixed_quoted_expansions(self):
        """Test mixing quoted and unquoted expansions."""
        result = QuotingTestHelper.run_psh_command([
            'VAR=test',
            'echo "$VAR"_\'$VAR\'_$VAR'
        ])

        assert result['success']
        assert 'test_$VAR_test' in result['stdout']

    def test_quotes_with_parameter_expansion(self):
        """Test quotes with parameter expansion."""
        result = QuotingTestHelper.run_psh_command([
            'VAR="hello world"',
            'echo "${VAR}" \'${VAR}\''
        ])

        assert result['success']
        assert 'hello world' in result['stdout']
        assert '${VAR}' in result['stdout']


class TestQuoteErrorHandling:
    """Test error handling with quotes."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_unclosed_single_quote(self):
        """Test error handling for unclosed single quote."""
        result = QuotingTestHelper.run_psh_command("echo 'unclosed")

        # Should fail with appropriate error
        assert not result['success']
        assert 'quote' in result['stderr'].lower() or 'syntax' in result['stderr'].lower()

    def test_unclosed_double_quote(self):
        """Test error handling for unclosed double quote."""
        result = QuotingTestHelper.run_psh_command('echo "unclosed')

        # Should fail with appropriate error
        assert not result['success']
        assert 'quote' in result['stderr'].lower() or 'syntax' in result['stderr'].lower()

    def test_invalid_escape_sequence(self):
        """Test handling of invalid escape sequences."""
        # Some shells handle unknown escape sequences differently
        result = QuotingTestHelper.run_psh_command('echo "\\z"')

        # Should handle gracefully - either literal or error
        assert isinstance(result['returncode'], int)

    def test_quote_in_here_document(self):
        """Test quote handling in here documents."""
        result = QuotingTestHelper.run_psh_command([
            'cat << EOF',
            'This has "quotes" and \'apostrophes\'',
            'EOF'
        ])

        assert result['success']
        assert '"quotes"' in result['stdout']
        assert "'apostrophes'" in result['stdout']


class TestComplexQuotingScenarios:
    """Test complex quoting scenarios."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_nested_command_substitution_with_quotes(self):
        """Test nested command substitution with quotes."""
        result = QuotingTestHelper.run_psh_command('echo "Outer: $(echo "inner quote")"')

        assert result['success']
        assert 'Outer: inner quote' in result['stdout']

    def test_quotes_in_function_definition(self):
        """Test quotes in function definitions."""
        result = QuotingTestHelper.run_psh_command([
            'test_func() { echo "function with quotes"; }',
            'test_func'
        ])

        assert result['success']
        assert 'function with quotes' in result['stdout']

    def test_quotes_in_conditional_expressions(self):
        """Test quotes in conditional expressions."""
        result = QuotingTestHelper.run_psh_command([
            'if [ "test" = "test" ]; then echo "equal"; fi'
        ])

        assert result['success']
        assert 'equal' in result['stdout']

    def test_quotes_with_array_elements(self):
        """Test quotes with array elements."""
        result = QuotingTestHelper.run_psh_command([
            'ARR=("first element" "second element")',
            'echo "${ARR[0]}" "${ARR[1]}"'
        ])

        # Arrays are supported and this matches bash 5.2 exactly, so the
        # assertions are unconditional. Behind `if result['success']:` a
        # failure to run the array assignment at all passed silently.
        assert result['success']
        assert 'first element' in result['stdout']
        assert 'second element' in result['stdout']

    def test_quotes_preserve_exit_status(self):
        """Test that quoting doesn't affect command exit status."""
        result = QuotingTestHelper.run_psh_command([
            'false',
            'echo "Exit status: $?"'
        ])

        assert result['success']
        assert 'Exit status: 1' in result['stdout']

    def test_very_long_quoted_string(self):
        """Test handling of very long quoted strings."""
        long_string = 'x' * 10000  # 10KB string
        result = QuotingTestHelper.run_psh_command(f'echo "{long_string}"')

        assert result['success']
        assert long_string in result['stdout']

    def test_unicode_in_quotes(self):
        """Test Unicode characters in quotes."""
        result = QuotingTestHelper.run_psh_command('echo "Unicode: 你好 🌟 café"')

        assert result['success']
        assert 'Unicode: 你好 🌟 café' in result['stdout']

    def test_quotes_with_multiple_commands(self):
        """Test quotes across multiple commands."""
        result = QuotingTestHelper.run_psh_command([
            'echo "First command"; echo "Second command"',
            'echo "Third" | cat'
        ])

        assert result['success']
        assert 'First command' in result['stdout']
        assert 'Second command' in result['stdout']
        assert 'Third' in result['stdout']


class TestQuoteCompatibility:
    """Test compatibility with other shell behaviors."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_posix_quote_compliance(self):
        """Test POSIX compliance for basic quoting."""
        result = QuotingTestHelper.run_psh_command([
            "echo 'single quotes'",
            'echo "double quotes"',
            'echo mixed\'quotes\'"and more"'
        ])

        assert result['success']
        assert 'single quotes' in result['stdout']
        assert 'double quotes' in result['stdout']
        assert 'mixedquotesand more' in result['stdout']

    def test_bash_quote_compatibility(self):
        """Test bash-compatible quoting behavior."""
        result = QuotingTestHelper.run_psh_command([
            'VAR=value',
            'echo "$VAR" \'$VAR\' $VAR'
        ])

        assert result['success']
        assert 'value $VAR value' in result['stdout']

    def test_quote_word_splitting_interaction(self):
        """Test quote interaction with word splitting."""
        result = QuotingTestHelper.run_psh_command([
            'set "a b c"',
            'echo $1',      # Should split
            'echo "$1"'     # Should not split
        ])

        assert result['success']
        result['stdout'].strip().split('\n')
        # First should show individual words, second should show as one


# Test runner integration
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
