"""
Word splitting and field separation integration tests.

Tests for word splitting functionality including:
- IFS (Internal Field Separator) handling
- Word splitting with different field separators
- Word splitting interaction with quotes
- Custom IFS values and edge cases
- Null field handling
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


class WordSplittingTestHelper:
    """Helper class for word splitting testing."""

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


class TestBasicWordSplitting:
    """Test basic word splitting functionality."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_default_ifs_space_splitting(self):
        """Test word splitting with default IFS (space, tab, newline)."""
        # Test space splitting
        result = WordSplittingTestHelper.run_psh_command([
            'set "one two three"',
            'for word in $1; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[two]' in result['stdout']
        assert '[three]' in result['stdout']

    def test_default_ifs_tab_splitting(self):
        """Test word splitting with tabs."""
        # Test tab splitting
        result = WordSplittingTestHelper.run_psh_command([
            'set "one\ttwo\tthree"',  # Tab-separated
            'for word in $1; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[two]' in result['stdout']
        assert '[three]' in result['stdout']

    def test_default_ifs_newline_splitting(self):
        """Test word splitting with newlines."""
        # Test newline splitting
        result = WordSplittingTestHelper.run_psh_command([
            'VAR="line1\nline2\nline3"',
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[line1]' in result['stdout']
        assert '[line2]' in result['stdout']
        assert '[line3]' in result['stdout']

    def test_mixed_whitespace_splitting(self):
        """Test word splitting with mixed whitespace."""
        result = WordSplittingTestHelper.run_psh_command([
            'VAR="  one \t two  \n three  "',  # Mixed whitespace
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[two]' in result['stdout']
        assert '[three]' in result['stdout']
        # Should not have empty fields from leading/trailing/multiple separators

    def test_no_splitting_in_quotes(self):
        """Test that word splitting doesn't occur inside quotes."""
        result = WordSplittingTestHelper.run_psh_command([
            'VAR="one two three"',
            'for word in "$VAR"; do echo "[$word]"; done'  # Quoted variable
        ])

        assert result['success']
        assert '[one two three]' in result['stdout']
        # Should be treated as single word when quoted


class TestCustomIFS:
    """Test custom IFS (Internal Field Separator) values."""

    def test_custom_ifs_comma(self):
        """Test word splitting with comma as IFS."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=","',
            'VAR="one,two,three"',
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[two]' in result['stdout']
        assert '[three]' in result['stdout']

    def test_custom_ifs_colon(self):
        """Test word splitting with colon as IFS (like PATH)."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=":"',
            'VAR="first:second:third"',
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[first]' in result['stdout']
        assert '[second]' in result['stdout']
        assert '[third]' in result['stdout']

    def test_custom_ifs_multiple_chars(self):
        """Test IFS with multiple separator characters."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=":,"',  # Both colon and comma
            'VAR="one:two,three:four"',
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[two]' in result['stdout']
        assert '[three]' in result['stdout']
        assert '[four]' in result['stdout']

    def test_ifs_with_special_characters(self):
        """Test IFS with special characters."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS="|"',
            'VAR="alpha|beta|gamma"',
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[alpha]' in result['stdout']
        assert '[beta]' in result['stdout']
        assert '[gamma]' in result['stdout']

    def test_empty_ifs(self):
        """Test behavior with empty IFS."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=""',  # Empty IFS
            'VAR="onetwothree"',
            'for char in $VAR; do echo "[$char]"; done'
        ])

        assert result['success']
        # With empty IFS, should split into individual characters
        # or treat as single word depending on implementation

    def test_ifs_reset_to_default(self):
        """Test resetting IFS to default behavior."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=","',  # Set custom IFS
            'VAR="one,two,three"',
            'for word in $VAR; do echo "custom:[$word]"; done',
            'IFS=" \t\n"',  # Reset to default
            'VAR2="a b c"',
            'for word in $VAR2; do echo "default:[$word]"; done'
        ])

        assert result['success']
        assert 'custom:[one]' in result['stdout']
        assert 'custom:[two]' in result['stdout']
        assert 'default:[a]' in result['stdout']
        assert 'default:[b]' in result['stdout']
        assert 'default:[c]' in result['stdout']


class TestEmptyAndNullFields:
    """Test handling of empty and null fields."""

    def test_empty_fields_with_custom_ifs(self):
        """Test empty fields with custom IFS."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=","',
            'VAR="one,,three,"',  # Empty fields
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[three]' in result['stdout']
        # Behavior with empty fields may vary - some shells preserve them

    def test_leading_trailing_separators(self):
        """Test behavior with leading and trailing separators."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=","',
            'VAR=",one,two,"',  # Leading and trailing commas
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[two]' in result['stdout']
        # Leading/trailing separators typically create empty fields

    def test_multiple_consecutive_separators(self):
        """Test behavior with multiple consecutive separators."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=" "',
            'VAR="one    two    three"',  # Multiple spaces
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[two]' in result['stdout']
        assert '[three]' in result['stdout']
        # Multiple whitespace typically collapses to single separator

    def test_only_separators(self):
        """Test variable containing only separators."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=","',
            'VAR=",,,,"',  # Only commas
            'COUNT=0',
            'for word in $VAR; do COUNT=$((COUNT + 1)); done',
            'echo "Count: $COUNT"'
        ])

        assert result['success']
        # Behavior may vary - some implementations produce empty fields

    def test_null_variable_splitting(self):
        """Test splitting of null/unset variables."""
        result = WordSplittingTestHelper.run_psh_command([
            'unset NULL_VAR',
            'COUNT=0',
            'for word in $NULL_VAR; do COUNT=$((COUNT + 1)); done',
            'echo "Count: $COUNT"'
        ])

        assert result['success']
        assert 'Count: 0' in result['stdout']


class TestWordSplittingContexts:
    """Test word splitting in different contexts."""

    def test_splitting_in_assignment(self):
        """Test word splitting in variable assignment context."""
        result = WordSplittingTestHelper.run_psh_command([
            'VAR="one two three"',
            'RESULT=$VAR',  # Assignment - no splitting
            'echo "[$RESULT]"'
        ])

        assert result['success']
        assert '[one two three]' in result['stdout']
        # In assignment context, no word splitting should occur

    def test_splitting_in_command_arguments(self):
        """Test word splitting in command arguments."""
        result = WordSplittingTestHelper.run_psh_command([
            'VAR="arg1 arg2 arg3"',
            'echo $VAR'  # Command arguments - splitting occurs
        ])

        assert result['success']
        # Should pass as separate arguments to echo
        output_words = result['stdout'].strip().split()
        assert 'arg1' in output_words
        assert 'arg2' in output_words
        assert 'arg3' in output_words

    def test_splitting_in_array_assignment(self):
        """Test word splitting in array assignment."""
        result = WordSplittingTestHelper.run_psh_command([
            'VAR="one two three"',
            'ARR=($VAR)',  # Array assignment - splitting occurs
            'echo "${ARR[0]}" "${ARR[1]}" "${ARR[2]}"'
        ])

        # Arrays are supported and this matches bash 5.2 exactly, so the
        # assertions are unconditional. Behind `if result['success']:` a
        # failure to split into the array at all passed silently.
        assert result['success']
        assert 'one' in result['stdout']
        assert 'two' in result['stdout']
        assert 'three' in result['stdout']

    def test_splitting_in_case_patterns(self):
        """Test word splitting in case statement patterns."""
        result = WordSplittingTestHelper.run_psh_command([
            'VAR="a|b"',
            'case "a" in',
            '  $VAR) echo "matched" ;;',  # Pattern expansion
            '  *) echo "not matched" ;;',
            'esac'
        ])

        assert result['success']
        # Behavior depends on how case patterns handle word splitting

    def test_splitting_in_for_loop(self):
        """Test word splitting in for loop iteration."""
        result = WordSplittingTestHelper.run_psh_command([
            'LIST="item1 item2 item3"',
            'for item in $LIST; do echo "Processing: $item"; done'
        ])

        assert result['success']
        assert 'Processing: item1' in result['stdout']
        assert 'Processing: item2' in result['stdout']
        assert 'Processing: item3' in result['stdout']


class TestWordSplittingWithExpansions:
    """Test word splitting interaction with other expansions."""

    def test_splitting_with_command_substitution(self):
        """Test word splitting with command substitution."""
        result = WordSplittingTestHelper.run_psh_command([
            'for word in $(echo "one two three"); do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[two]' in result['stdout']
        assert '[three]' in result['stdout']

    def test_splitting_with_parameter_expansion(self):
        """Test word splitting with parameter expansion."""
        result = WordSplittingTestHelper.run_psh_command([
            'VAR="hello world"',
            'for word in ${VAR}; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[hello]' in result['stdout']
        assert '[world]' in result['stdout']

    def test_splitting_with_arithmetic_expansion(self):
        """Test word splitting with arithmetic expansion."""
        result = WordSplittingTestHelper.run_psh_command([
            'NUMS="1 2 3"',
            'for num in $NUMS; do echo "Result: $((num * 2))"; done'
        ])

        assert result['success']
        assert 'Result: 2' in result['stdout']
        assert 'Result: 4' in result['stdout']
        assert 'Result: 6' in result['stdout']

    def test_splitting_with_glob_expansion(self):
        """Test word splitting interaction with glob expansion."""
        # Create test files
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            for name in ['file1.txt', 'file2.txt']:
                with open(os.path.join(temp_dir, name), 'w') as f:
                    f.write('test')

            result = WordSplittingTestHelper.run_psh_command([
                f'cd {temp_dir}',
                'PATTERN="*.txt"',
                'for file in $PATTERN; do echo "Found: $file"; done'
            ])

            assert result['success']
            # Should find both files (if glob expansion works)


class TestWordSplittingEdgeCases:
    """Test edge cases and special scenarios."""

    def test_ifs_with_backslash(self):
        """Test IFS containing backslash character."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS="\\\\"',  # Backslash as separator
            'VAR="one\\\\two\\\\three"',
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        # Should split on backslash

    def test_ifs_with_quote_characters(self):
        """Test IFS containing quote characters."""
        result = WordSplittingTestHelper.run_psh_command([
            "IFS='\"'",  # Double quote as separator
            'VAR=\'one"two"three\'',
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[two]' in result['stdout']
        assert '[three]' in result['stdout']

    def test_very_long_fields(self):
        """Test word splitting with very long fields."""
        long_word = 'a' * 10000  # 10KB word
        result = WordSplittingTestHelper.run_psh_command([
            f'VAR="{long_word} short"',
            'for word in $VAR; do echo "Length: ${#word}"; done'
        ])

        assert result['success']
        assert 'Length: 10000' in result['stdout']
        assert 'Length: 5' in result['stdout']

    def test_unicode_in_ifs(self):
        """Test IFS with Unicode characters."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS="•"',  # Unicode bullet as separator
            'VAR="one•two•three"',
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[one]' in result['stdout']
        assert '[two]' in result['stdout']
        assert '[three]' in result['stdout']

    def test_ifs_inheritance_in_subshells(self):
        """Test IFS inheritance in subshells."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=","',
            'VAR="a,b,c"',
            '(for word in $VAR; do echo "sub:[$word]"; done)',
            'IFS=" "',
            '(for word in $VAR; do echo "sub2:[$word]"; done)'
        ])

        assert result['success']
        assert 'sub:[a]' in result['stdout']
        assert 'sub:[b]' in result['stdout']
        assert 'sub:[c]' in result['stdout']
        # Second subshell inherits modified IFS


class TestWordSplittingCompatibility:
    """Test compatibility with other shell behaviors."""

    def test_posix_compliance_basic(self):
        """Test basic POSIX compliance for word splitting."""
        result = WordSplittingTestHelper.run_psh_command([
            'set "a b c"',
            'set -- $1',  # Word splitting in positional parameter assignment
            'echo "$#"'   # Should be 3 arguments
        ])

        assert result['success']
        assert '3' in result['stdout']

    def test_bash_compatibility_ifs(self):
        """Test bash-compatible IFS behavior."""
        result = WordSplittingTestHelper.run_psh_command([
            'IFS=" :"',  # Space and colon
            'VAR="a:b c:d"',
            'for word in $VAR; do echo "[$word]"; done'
        ])

        assert result['success']
        assert '[a]' in result['stdout']
        assert '[b]' in result['stdout']
        assert '[c]' in result['stdout']
        assert '[d]' in result['stdout']

    def test_field_splitting_with_read_builtin(self):
        """Test field splitting with read builtin (using here string to avoid pipeline subshell)."""
        result = WordSplittingTestHelper.run_psh_command([
            'read A B C <<< "one two three"',
            'echo "A=[$A] B=[$B] C=[$C]"'
        ])

        # If here strings aren't supported, test with direct input
        if not result['success'] or 'A=[one]' not in result['stdout']:
            result = WordSplittingTestHelper.run_psh_command([
                'echo "one two three" > /tmp/test_input',
                'read A B C < /tmp/test_input',
                'echo "A=[$A] B=[$B] C=[$C]"',
                'rm -f /tmp/test_input'
            ])

        assert result['success']
        assert 'A=[one]' in result['stdout']
        assert 'B=[two]' in result['stdout']
        assert 'C=[three]' in result['stdout']


# Test runner integration
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
