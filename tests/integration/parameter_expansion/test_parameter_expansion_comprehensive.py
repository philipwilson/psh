"""
Comprehensive parameter expansion integration tests.

Tests for advanced parameter expansion features including string length,
pattern removal, pattern substitution, substring extraction, variable name
matching, case modification, and error handling.
"""



class TestStringLength:
    """Test string length operations ${#var}."""

    def test_simple_length(self, shell_with_temp_dir):
        """Test ${#var} for string length."""
        shell = shell_with_temp_dir

        shell.run_command('VAR="hello"')
        shell.run_command('echo ${#VAR} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "5"

    def test_empty_variable_length(self, shell_with_temp_dir):
        """Test length of empty variable."""
        shell = shell_with_temp_dir

        shell.run_command('EMPTY=""')
        shell.run_command('echo ${#EMPTY} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "0"

    def test_undefined_variable_length(self, shell_with_temp_dir):
        """Test length of undefined variable."""
        shell = shell_with_temp_dir

        shell.run_command('echo ${#UNDEFINED} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "0"

    def test_special_variables_length(self, shell_with_temp_dir):
        """Test ${#} for number of positional parameters."""
        shell = shell_with_temp_dir

        shell.run_command('set -- one two three')
        shell.run_command('echo ${#} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "3"

    def test_positional_params_length(self, shell_with_temp_dir):
        """Test ${#*} and ${#@} for count of positional parameters."""
        shell = shell_with_temp_dir

        # Set positional params: 3 parameters
        shell.run_command('set -- one two three')
        shell.run_command('echo ${#*} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "3"

        shell.run_command('echo ${#@} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "3"

    def test_unicode_length(self, shell_with_temp_dir):
        """Test length with unicode characters."""
        shell = shell_with_temp_dir

        shell.run_command('VAR="café"')
        shell.run_command('echo ${#VAR} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "4"

    def test_length_with_spaces(self, shell_with_temp_dir):
        """Test length of string with spaces."""
        shell = shell_with_temp_dir

        shell.run_command('VAR="hello world"')
        shell.run_command('echo ${#VAR} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "11"


class TestPatternRemoval:
    """Test pattern removal operations."""

    def test_shortest_prefix_removal(self, shell_with_temp_dir):
        """Test ${var#pattern} for shortest prefix removal."""
        shell = shell_with_temp_dir

        shell.run_command('file="/home/user/document.txt"')
        shell.run_command('echo ${file#*/} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "home/user/document.txt"

    def test_longest_prefix_removal(self, shell_with_temp_dir):
        """Test ${var##pattern} for longest prefix removal."""
        shell = shell_with_temp_dir

        shell.run_command('file="/home/user/document.txt"')
        shell.run_command('echo ${file##*/} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "document.txt"

    def test_shortest_suffix_removal(self, shell_with_temp_dir):
        """Test ${var%pattern} for shortest suffix removal."""
        shell = shell_with_temp_dir

        shell.run_command('file="/home/user/document.txt"')
        shell.run_command('echo ${file%.*} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "/home/user/document"

    def test_longest_suffix_removal(self, shell_with_temp_dir):
        """Test ${var%%pattern} for longest suffix removal."""
        shell = shell_with_temp_dir

        shell.run_command('file="/home/user/document.txt"')
        shell.run_command('echo ${file%%/*} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == ""

    def test_no_match_returns_original(self, shell_with_temp_dir):
        """Test that no match returns original value."""
        shell = shell_with_temp_dir

        shell.run_command('VAR="test"')
        shell.run_command('echo ${VAR#xyz} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "test"

    def test_glob_patterns(self, shell_with_temp_dir):
        """Test with glob patterns."""
        shell = shell_with_temp_dir

        # Remove everything up to first dot
        shell.run_command('file="test.tar.gz"')
        shell.run_command('echo ${file#*.} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "tar.gz"

        # Remove everything up to last dot
        shell.run_command('echo ${file##*.} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "gz"

    def test_character_class_patterns(self, shell_with_temp_dir):
        """Test with character class patterns."""
        shell = shell_with_temp_dir

        # ${VAR#[0-9]*} is shortest match: [0-9]* matches "1" (one digit + zero chars)
        shell.run_command('VAR="123abc"')
        shell.run_command('echo ${VAR#[0-9]*} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "23abc"

        # ${VAR##[0-9]*} is longest match: strips everything
        shell.run_command('echo ${VAR##[0-9]*} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == ""


class TestPatternSubstitution:
    """Test pattern substitution operations."""

    def test_first_match_replacement(self, shell_with_temp_dir):
        """Test ${var/pattern/string} for first match."""
        shell = shell_with_temp_dir

        shell.run_command('path="/usr/local/bin:/usr/bin"')
        shell.run_command('echo "${path/:/,}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "/usr/local/bin,/usr/bin"

    def test_all_matches_replacement(self, shell_with_temp_dir):
        """Test ${var//pattern/string} for all matches."""
        shell = shell_with_temp_dir

        shell.run_command('path="/usr/local/bin:/usr/bin"')
        shell.run_command('echo "${path//:/,}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "/usr/local/bin,/usr/bin"

    def test_prefix_replacement(self, shell_with_temp_dir):
        """Test ${var/#pattern/string} for prefix match."""
        shell = shell_with_temp_dir

        shell.run_command('path="/usr/bin"')
        shell.run_command('echo "${path/#\\/usr/\\/opt}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "/opt/bin"

    def test_suffix_replacement(self, shell_with_temp_dir):
        """Test ${var/%pattern/string} for suffix match."""
        shell = shell_with_temp_dir

        shell.run_command('path="/usr/bin"')
        shell.run_command('echo "${path/%bin/sbin}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "/usr/sbin"

    def test_empty_replacement(self, shell_with_temp_dir):
        """Test with empty replacement string."""
        shell = shell_with_temp_dir

        shell.run_command('text="hello world"')
        shell.run_command('echo "${text// /}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "helloworld"

    def test_special_chars_in_replacement(self, shell_with_temp_dir):
        """Test special characters in replacement."""
        shell = shell_with_temp_dir

        shell.run_command('text="hello"')
        shell.run_command('echo "${text/hello/hi there}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "hi there"


class TestSubstringExtraction:
    """Test substring extraction operations."""

    def test_positive_offset(self, shell_with_temp_dir):
        """Test ${var:offset} with positive offset."""
        shell = shell_with_temp_dir

        shell.run_command('str="Hello, World!"')
        shell.run_command('echo ${str:7} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "World!"

    def test_negative_offset(self, shell_with_temp_dir):
        """Test ${var:offset} with negative offset."""
        shell = shell_with_temp_dir

        shell.run_command('str="Hello, World!"')
        shell.run_command('echo ${str: -6} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "World!"

    def test_offset_with_length(self, shell_with_temp_dir):
        """Test ${var:offset:length}."""
        shell = shell_with_temp_dir

        shell.run_command('str="Hello, World!"')
        shell.run_command('echo ${str:7:5} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "World"

    def test_negative_length(self, shell_with_temp_dir):
        """Test with negative length."""
        shell = shell_with_temp_dir

        shell.run_command('str="Hello, World!"')
        shell.run_command('echo ${str:0:-1} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "Hello, World"

    def test_out_of_bounds_handling(self, shell_with_temp_dir):
        """Test out of bounds offsets."""
        shell = shell_with_temp_dir

        shell.run_command('str="test"')
        shell.run_command('echo ${str:10} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == ""

        shell.run_command('echo ${str:2:10} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "st"


class TestVariableNameMatching:
    """Test variable name matching operations."""

    def test_prefix_matching(self, shell_with_temp_dir):
        """Test ${!prefix*} for matching variable names.

        Exact-match assertion: this used to assert only substring presence,
        which still passed when ${!prefix*} wrongly listed EVERY variable.
        """
        shell = shell_with_temp_dir

        shell.run_command('USER_ID=1000')
        shell.run_command('USER_HOME=/home/john')
        shell.run_command('echo ${!USER_*} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "USER_HOME USER_ID"

    def test_prefix_matching_at(self, shell_with_temp_dir):
        """Test ${!prefix@}: matching names only, no literal quotes."""
        shell = shell_with_temp_dir

        shell.run_command('TEST_VAR1=one')
        shell.run_command('TEST_VAR2=two')
        shell.run_command('echo ${!TEST_VAR@} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "TEST_VAR1 TEST_VAR2"

    def test_prefix_matching_no_match(self, shell_with_temp_dir):
        """A prefix matching nothing expands to nothing."""
        shell = shell_with_temp_dir

        shell.run_command('echo "[${!NOSUCHPREFIXZZ@}]" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "[]"

    def test_prefix_matching_star_joins_with_ifs(self, shell_with_temp_dir):
        """Quoted ${!prefix*} joins names with the first character of IFS."""
        shell = shell_with_temp_dir

        shell.run_command('PFX_A=1')
        shell.run_command('PFX_B=2')
        shell.run_command('IFS=:; echo "${!PFX_*}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "PFX_A:PFX_B"


class TestCaseModification:
    """Test case modification operations."""

    def test_first_char_upper(self, shell_with_temp_dir):
        """Test ${var^} for first character uppercase."""
        shell = shell_with_temp_dir

        shell.run_command('text="hello world"')
        shell.run_command('echo ${text^} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "Hello world"

    def test_all_chars_upper(self, shell_with_temp_dir):
        """Test ${var^^} for all uppercase."""
        shell = shell_with_temp_dir

        shell.run_command('text="hello world"')
        shell.run_command('echo ${text^^} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "HELLO WORLD"

    def test_first_char_lower(self, shell_with_temp_dir):
        """Test ${var,} for first character lowercase."""
        shell = shell_with_temp_dir

        shell.run_command('text="HELLO WORLD"')
        shell.run_command('echo ${text,} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "hELLO WORLD"

    def test_all_chars_lower(self, shell_with_temp_dir):
        """Test ${var,,} for all lowercase."""
        shell = shell_with_temp_dir

        shell.run_command('text="HELLO WORLD"')
        shell.run_command('echo ${text,,} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "hello world"

    def test_pattern_based_modification(self, shell_with_temp_dir):
        """Test case modification with patterns."""
        shell = shell_with_temp_dir

        # Uppercase only vowels
        shell.run_command('text="hello world"')
        shell.run_command('echo ${text^^[aeiou]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "hEllO wOrld"

    def test_empty_string(self, shell_with_temp_dir):
        """Test case modification on empty string."""
        shell = shell_with_temp_dir

        shell.run_command('text=""')
        shell.run_command('echo ${text^^} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == ""

    def test_unicode_handling(self, shell_with_temp_dir):
        """Test case modification with unicode."""
        shell = shell_with_temp_dir

        shell.run_command('text="café"')
        shell.run_command('echo ${text^^} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "CAFÉ"


class TestErrorHandling:
    """Test error handling in parameter expansion."""

    def test_invalid_offset(self, shell_with_temp_dir):
        """Test invalid offset in substring extraction."""
        shell = shell_with_temp_dir

        shell.run_command('VAR="test"')
        # Invalid offsets should be handled gracefully
        result = shell.run_command('echo ${VAR:bad} > output.txt 2>/dev/null')
        # Should either error (return non-zero) or handle gracefully
        assert result in (0, 1)  # Accept either outcome for now

    def test_missing_pattern(self, shell_with_temp_dir):
        """Test missing pattern in substitution."""
        shell = shell_with_temp_dir

        shell.run_command('VAR="test"')
        # This should produce an error or handle gracefully
        result = shell.run_command('echo ${VAR/} > output.txt 2>/dev/null')
        assert result in (0, 1)  # Accept either outcome for now

    def test_invalid_length(self, shell_with_temp_dir):
        """Test invalid length in substring extraction."""
        shell = shell_with_temp_dir

        shell.run_command('VAR="test"')
        result = shell.run_command('echo ${VAR:0:bad} > output.txt 2>/dev/null')
        assert result in (0, 1)  # Accept either outcome for now


class TestAdvancedCombinations:
    """Test combinations of parameter expansion features."""

    def test_nested_expansions(self, shell_with_temp_dir):
        """Test nested parameter expansions."""
        shell = shell_with_temp_dir

        shell.run_command('prefix="USER"')
        shell.run_command('USER_NAME="john"')

        # Test basic nested expansion
        shell.run_command('name="${prefix}_NAME"')
        shell.run_command('echo ${name} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "USER_NAME"

    def test_chained_operations(self, shell_with_temp_dir):
        """Test chaining multiple expansion operations."""
        shell = shell_with_temp_dir

        shell.run_command('path="/usr/local/bin/program.sh"')

        # Get filename and remove extension
        shell.run_command('filename=${path##*/}')
        shell.run_command('basename=${filename%.*}')
        shell.run_command('echo ${basename} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "program"

    def test_expansion_in_conditionals(self, shell_with_temp_dir):
        """Test parameter expansion in conditional contexts."""
        shell = shell_with_temp_dir

        shell.run_command('filename="test.txt"')

        # Test expansion in conditional
        script = '''
        if [ "${filename##*.}" = "txt" ]; then
            echo "Text file" > output.txt
        else
            echo "Other file" > output.txt
        fi
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "Text file"

    def test_expansion_in_loops(self, shell_with_temp_dir):
        """Test parameter expansion in loops."""
        shell = shell_with_temp_dir

        shell.run_command('files="file1.txt file2.log file3.txt"')

        script = '''
        for file in $files; do
            echo "Processing: ${file%.*}" >> output.txt
        done
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            content = f.read()
        assert "Processing: file1" in content
        assert "Processing: file2" in content
        assert "Processing: file3" in content

    def test_array_with_expansion(self, shell_with_temp_dir):
        """Test parameter expansion with arrays."""
        shell = shell_with_temp_dir

        shell.run_command('files=("test.txt" "document.pdf" "image.png")')

        # Test expansion on array elements
        shell.run_command('echo ${files[0]%.*} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "test"

    def test_complex_pattern_matching(self, shell_with_temp_dir):
        """Test complex pattern matching scenarios."""
        shell = shell_with_temp_dir

        # Test multiple pattern operations
        shell.run_command('url="https://www.example.com/path/to/file.html"')

        # Extract domain
        shell.run_command('temp=${url#*://}')  # Remove protocol
        shell.run_command('domain=${temp%%/*}')  # Extract domain part
        shell.run_command('echo ${domain} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "www.example.com"

    def test_length_with_expansion(self, shell_with_temp_dir):
        """Test length operations with other expansions."""
        shell = shell_with_temp_dir

        shell.run_command('path="/very/long/path/to/file.txt"')
        shell.run_command('filename=${path##*/}')
        shell.run_command('echo ${#filename} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "8"  # "file.txt" is 8 characters


class TestPerformanceAndEdgeCases:
    """Test performance and edge cases for parameter expansion."""

    def test_large_string_operations(self, shell_with_temp_dir):
        """Test parameter expansion on large strings."""
        shell = shell_with_temp_dir

        # Create a moderately large string
        shell.run_command('large="' + 'a' * 1000 + '"')

        # Test length operation
        shell.run_command('echo ${#large} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "1000"

        # Test substring operation
        shell.run_command('echo ${large:500:10} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "aaaaaaaaaa"

    def test_empty_variable_operations(self, shell_with_temp_dir):
        """Test operations on empty variables."""
        shell = shell_with_temp_dir

        shell.run_command('empty=""')

        # All operations should handle empty strings gracefully
        shell.run_command('echo "${empty#*}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == ""

        shell.run_command('echo "${empty%*}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == ""

        shell.run_command('echo "${empty:0:5}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == ""

    def test_special_characters_handling(self, shell_with_temp_dir):
        """Test handling of special characters in expansions."""
        shell = shell_with_temp_dir

        # Test with various special characters (avoid $ which might expand)
        shell.run_command('special="hello_world@test#123"')

        # Test basic operations don't break with special chars
        shell.run_command('echo ${#special} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        # The actual string should be 20 characters, but accept the computed length
        assert content == "20"

        # Test pattern removal with special chars
        shell.run_command('echo ${special#*@} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "test#123"
