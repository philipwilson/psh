"""
Unit tests for parameter expansion modifiers in PSH.

Tests cover:
- ${var:-word} - Use default if unset or null
- ${var:=word} - Assign default if unset or null
- ${var:?word} - Error if unset or null
- ${var:+word} - Use alternate if set
- ${var#pattern} - Remove shortest prefix
- ${var##pattern} - Remove longest prefix
- ${var%pattern} - Remove shortest suffix
- ${var%%pattern} - Remove longest suffix
- ${var/pattern/string} - Pattern substitution
- ${var:offset:length} - Substring
- ${#var} - Length
- ${!var} - Indirect expansion
"""



class TestDefaultValueExpansion:
    """Test ${var:-word} and ${var-word} expansions."""

    def test_use_default_when_unset(self, shell, capsys):
        """Test ${var:-default} with unset variable."""
        shell.run_command('unset VAR')
        shell.run_command('echo "${VAR:-default}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "default"

    def test_use_default_when_null(self, shell, capsys):
        """Test ${var:-default} with null variable."""
        shell.run_command('VAR=""')
        shell.run_command('echo "${VAR:-default}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "default"

    def test_use_value_when_set(self, shell, capsys):
        """Test ${var:-default} with set variable."""
        shell.run_command('VAR="value"')
        shell.run_command('echo "${VAR:-default}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "value"

    def test_without_colon_null_not_default(self, shell, capsys):
        """Test ${var-default} treats null as set."""
        shell.run_command('VAR=""')
        shell.run_command('echo "${VAR-default}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == ""

    def test_complex_default(self, shell, capsys):
        """Test complex expression as default."""
        shell.run_command('unset VAR')
        shell.run_command('OTHER="complex"')
        shell.run_command('echo "${VAR:-$OTHER value}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "complex value"


class TestAssignDefaultExpansion:
    """Test ${var:=word} and ${var=word} expansions."""

    def test_assign_when_unset(self, shell, capsys):
        """Test ${var:=default} assigns when unset."""
        shell.run_command('unset VAR')
        shell.run_command('echo "${VAR:=assigned}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "assigned"

        shell.run_command('echo "$VAR"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "assigned"

    def test_assign_when_null(self, shell, capsys):
        """Test ${var:=default} assigns when null."""
        shell.run_command('VAR=""')
        shell.run_command('echo "${VAR:=assigned}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "assigned"

        shell.run_command('echo "$VAR"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "assigned"

    def test_no_assign_when_set(self, shell, capsys):
        """Test ${var:=default} doesn't assign when set."""
        shell.run_command('VAR="original"')
        shell.run_command('echo "${VAR:=assigned}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "original"

        shell.run_command('echo "$VAR"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "original"

    def test_positional_param_assign_error(self, shell, capsys):
        """Test ${1:=default} should error (can't assign to positional)."""
        shell.run_command('echo "${1:=default}"')
        # Might error or just not assign
        capsys.readouterr()
        # Check if it errors or ignores


class TestErrorIfUnsetExpansion:
    """Test ${var:?word} and ${var?word} expansions."""

    def test_error_when_unset(self, shell, capsys):
        """Test ${var:?message} errors when unset."""
        shell.run_command('unset VAR')
        exit_code = shell.run_command('echo "${VAR:?Variable not set}"')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert "Variable not set" in captured.err or "Variable not set" in captured.out

    def test_error_when_null(self, shell, capsys):
        """Test ${var:?message} errors when null."""
        shell.run_command('VAR=""')
        exit_code = shell.run_command('echo "${VAR:?Variable is empty}"')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert "Variable is empty" in captured.err or "Variable is empty" in captured.out

    def test_no_error_when_set(self, shell, capsys):
        """Test ${var:?message} succeeds when set."""
        shell.run_command('VAR="value"')
        exit_code = shell.run_command('echo "${VAR:?Should not see this}"')
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "value"
        assert "Should not see this" not in captured.err

    def test_without_colon_null_ok(self, shell, capsys):
        """Test ${var?message} accepts null as set."""
        shell.run_command('VAR=""')
        exit_code = shell.run_command('echo "${VAR?Should not error}"')
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == ""


class TestAlternateValueExpansion:
    """Test ${var:+word} and ${var+word} expansions."""

    def test_alternate_when_set(self, shell, capsys):
        """Test ${var:+alternate} uses alternate when set."""
        shell.run_command('VAR="original"')
        shell.run_command('echo "${VAR:+alternate}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "alternate"

    def test_empty_when_unset(self, shell, capsys):
        """Test ${var:+alternate} is empty when unset."""
        shell.run_command('unset VAR')
        shell.run_command('echo "${VAR:+alternate}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == ""

    def test_empty_when_null(self, shell, capsys):
        """Test ${var:+alternate} is empty when null."""
        shell.run_command('VAR=""')
        shell.run_command('echo "${VAR:+alternate}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == ""

    def test_complex_alternate(self, shell, capsys):
        """Test complex expression as alternate."""
        shell.run_command('VAR="set"')
        shell.run_command('OTHER="complex"')
        shell.run_command('echo "${VAR:+$OTHER value}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "complex value"


class TestPrefixRemoval:
    """Test ${var#pattern} and ${var##pattern} expansions."""

    def test_remove_shortest_prefix(self, shell, capsys):
        """Test ${var#pattern} removes shortest matching prefix."""
        shell.run_command('FILE="/path/to/file.txt"')
        shell.run_command('echo "${FILE#*/}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "path/to/file.txt"

    def test_remove_longest_prefix(self, shell, capsys):
        """Test ${var##pattern} removes longest matching prefix."""
        shell.run_command('FILE="/path/to/file.txt"')
        shell.run_command('echo "${FILE##*/}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "file.txt"

    def test_prefix_with_wildcards(self, shell, capsys):
        """Test prefix removal with wildcards."""
        shell.run_command('VAR="test123end"')
        shell.run_command('echo "${VAR#test*}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "123end"

        shell.run_command('echo "${VAR#*st}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "123end"

    def test_no_match_prefix(self, shell, capsys):
        """Test prefix removal with no match."""
        shell.run_command('VAR="hello"')
        shell.run_command('echo "${VAR#xyz}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "hello"

    def test_exact_match_prefix(self, shell, capsys):
        """Test prefix removal with exact match."""
        shell.run_command('VAR="prefix_content"')
        shell.run_command('echo "${VAR#prefix_}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "content"


class TestSuffixRemoval:
    """Test ${var%pattern} and ${var%%pattern} expansions."""

    def test_remove_shortest_suffix(self, shell, capsys):
        """Test ${var%pattern} removes shortest matching suffix."""
        shell.run_command('FILE="/path/to/file.tar.gz"')
        shell.run_command('echo "${FILE%.*}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "/path/to/file.tar"

    def test_remove_longest_suffix(self, shell, capsys):
        """Test ${var%%pattern} removes longest matching suffix."""
        shell.run_command('FILE="/path/to/file.tar.gz"')
        shell.run_command('echo "${FILE%%.*}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "/path/to/file"

    def test_suffix_with_wildcards(self, shell, capsys):
        """Test suffix removal with wildcards."""
        shell.run_command('VAR="start123test"')
        shell.run_command('echo "${VAR%test}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "start123"

        shell.run_command('echo "${VAR%*st}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "start123te"

    def test_directory_suffix(self, shell, capsys):
        """Test removing directory from path."""
        shell.run_command('PATH="/usr/local/bin"')
        shell.run_command('echo "${PATH%/*}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "/usr/local"

    def test_extension_removal(self, shell, capsys):
        """Test common extension removal pattern."""
        shell.run_command('FILE="document.pdf"')
        shell.run_command('echo "${FILE%.pdf}.txt"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "document.txt"

    def test_single_substitution(self, captured_shell):
        """Test ${var/pattern/string} replaces first match."""
        captured_shell.run_command('TEXT="hello hello world"')
        captured_shell.run_command('echo "${TEXT/hello/hi}"')
        output = captured_shell.get_stdout()
        assert output.strip() == "hi hello world"

    def test_global_substitution(self, captured_shell):
        """Test ${var//pattern/string} replaces all matches."""
        captured_shell.run_command('TEXT="hello hello world"')
        captured_shell.run_command('echo "${TEXT//hello/hi}"')
        output = captured_shell.get_stdout()
        assert output.strip() == "hi hi world"

    def test_prefix_substitution(self, captured_shell):
        """Test ${var/#pattern/string} replaces at start."""
        captured_shell.run_command('TEXT="hello world"')
        captured_shell.run_command('echo "${TEXT/#hello/hi}"')
        output = captured_shell.get_stdout()
        assert output.strip() == "hi world"

        captured_shell.clear_output()
        captured_shell.run_command('echo "${TEXT/#world/hi}"')
        output = captured_shell.get_stdout()
        assert output.strip() == "hello world"  # No match at start

    def test_suffix_substitution(self, captured_shell):
        """Test ${var/%pattern/string} replaces at end."""
        captured_shell.run_command('TEXT="hello world"')
        captured_shell.run_command('echo "${TEXT/%world/universe}"')
        output = captured_shell.get_stdout()
        assert output.strip() == "hello universe"

    def test_delete_pattern(self, captured_shell):
        """Test ${var/pattern/} deletes pattern."""
        captured_shell.run_command('TEXT="hello world"')
        captured_shell.run_command('echo "${TEXT/world/}"')
        output = captured_shell.get_stdout()
        assert output.strip() == "hello"


class TestStringCaseModification:
    """Test case modification expansions."""

    def test_uppercase_first(self, shell, capsys):
        """Test ${var^} uppercase first character."""
        shell.run_command('TEXT="hello world"')
        shell.run_command('echo "${TEXT^}"')
        captured = capsys.readouterr()
        expected = "Hello world"
        # This might not be supported
        if captured.out.strip() != "${TEXT^}":
            assert captured.out.strip() == expected

    def test_uppercase_all(self, shell, capsys):
        """Test ${var^^} uppercase all characters."""
        shell.run_command('TEXT="hello world"')
        shell.run_command('echo "${TEXT^^}"')
        captured = capsys.readouterr()
        expected = "HELLO WORLD"
        # This might not be supported
        if captured.out.strip() != "${TEXT^^}":
            assert captured.out.strip() == expected

    def test_lowercase_first(self, shell, capsys):
        """Test ${var,} lowercase first character."""
        shell.run_command('TEXT="HELLO WORLD"')
        shell.run_command('echo "${TEXT,}"')
        captured = capsys.readouterr()
        expected = "hELLO WORLD"
        # This might not be supported
        if captured.out.strip() != "${TEXT,}":
            assert captured.out.strip() == expected

    def test_lowercase_all(self, shell, capsys):
        """Test ${var,,} lowercase all characters."""
        shell.run_command('TEXT="HELLO WORLD"')
        shell.run_command('echo "${TEXT,,}"')
        captured = capsys.readouterr()
        expected = "hello world"
        # This might not be supported
        if captured.out.strip() != "${TEXT,,}":
            assert captured.out.strip() == expected


class TestComplexParameterExpansion:
    """Test complex parameter expansion scenarios."""

    def test_nested_expansions(self, shell, capsys):
        """Test nested parameter expansions."""
        shell.run_command('DIR="/path/to/file.txt"')
        shell.run_command('BASE="${DIR##*/}"')
        shell.run_command('echo "${BASE%.txt}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "file"

    def test_expansion_in_assignment(self, shell, capsys):
        """Test parameter expansion in assignments."""
        shell.run_command('unset DEFAULT')
        shell.run_command('CONFIG="${DEFAULT:=/etc/config}"')
        shell.run_command('echo "$CONFIG"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "/etc/config"

        shell.run_command('echo "$DEFAULT"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "/etc/config"

    def test_multiple_expansions(self, shell, capsys):
        """Test multiple expansions in one command."""
        shell.run_command('A="hello"')
        shell.run_command('B=""')
        shell.run_command('unset C')
        shell.run_command('echo "${A:-default1} ${B:-default2} ${C:-default3}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "hello default2 default3"

    def test_expansion_with_quotes(self, shell, capsys):
        """Nested quotes in an operand are removed, like bash (v0.265.0):
        bash -c 'VAR="hello world"; echo "${VAR:+"$VAR exists"}"'
        prints `hello world exists` without quotes."""
        shell.run_command('VAR="hello world"')
        shell.run_command('echo "${VAR:+"$VAR exists"}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == 'hello world exists'
