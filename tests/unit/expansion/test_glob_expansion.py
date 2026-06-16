"""
Unit tests for glob/pathname expansion in PSH.

Tests cover:
- Basic wildcards (*, ?, [...])
- Recursive globbing (**)
- Hidden file matching
- Character classes
- Glob with no matches
- Escaping glob characters
- Complex glob patterns
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path, monkeypatch):
    """Run every glob test in its own temp dir.

    These tests `touch`/`rm` files and glob `*` in the working directory. With
    the bare `shell` fixture that was the shared cwd (the repo root), which both
    littered the working tree and raced across xdist workers (e.g.
    test_hidden_files_not_matched flaking on `echo *`). psh globs by live
    os.getcwd(), so chdir-ing into a unique tmp_path isolates each test;
    monkeypatch.chdir restores the cwd on teardown.
    """
    monkeypatch.chdir(tmp_path)


class TestBasicGlobbing:
    """Test basic glob patterns."""

    def test_asterisk_wildcard(self, shell, capsys):
        """Test * wildcard matching."""
        # Create test files
        shell.run_command('touch file1.txt file2.txt file3.txt')

        shell.run_command('echo *.txt')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "file1.txt" in output
        assert "file2.txt" in output
        assert "file3.txt" in output

        # Clean up
        shell.run_command('rm -f *.txt')

    def test_question_wildcard(self, shell, capsys):
        """Test ? wildcard matching single character."""
        # Create test files
        shell.run_command('touch a1 a2 a3 abc')

        shell.run_command('echo a?')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "a1" in output
        assert "a2" in output
        assert "a3" in output
        assert "abc" not in output  # More than one char after 'a'

        # Clean up
        shell.run_command('rm -f a1 a2 a3 abc')

    def test_no_matches(self, shell, capsys):
        """Test glob with no matches."""
        shell.run_command('echo *.nonexistent')
        captured = capsys.readouterr()
        # Should return literal pattern when no matches
        assert captured.out.strip() == "*.nonexistent"

    def test_mixed_wildcards(self, shell, capsys):
        """Test combining * and ? wildcards."""
        # Create test files
        shell.run_command('touch test1.dat test12.dat test123.dat')

        shell.run_command('echo test?.dat')
        captured = capsys.readouterr()
        assert "test1.dat" in captured.out
        assert "test12.dat" not in captured.out

        shell.run_command('echo test*.dat')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "test1.dat" in output
        assert "test12.dat" in output
        assert "test123.dat" in output

        # Clean up
        shell.run_command('rm -f test*.dat')


class TestCharacterClasses:
    """Test [...] character class patterns."""

    def test_simple_character_class(self, shell, capsys):
        """Test simple character class."""
        # Create test files
        shell.run_command('touch a1 b1 c1 d1')

        shell.run_command('echo [abc]1')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "a1" in output
        assert "b1" in output
        assert "c1" in output
        assert "d1" not in output

        # Clean up
        shell.run_command('rm -f [abcd]1')

    def test_character_range(self, shell, capsys):
        """Test character range in class."""
        # Create test files
        shell.run_command('touch file1 file2 file3 filea fileb')

        shell.run_command('echo file[1-3]')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "file1" in output
        assert "file2" in output
        assert "file3" in output
        assert "filea" not in output

        shell.run_command('echo file[a-c]')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "filea" in output
        assert "fileb" in output

        # Clean up
        shell.run_command('rm -f file[123ab]')

    def test_negated_character_class(self, shell, capsys):
        """Test negated character class [!...]."""
        # Create test files
        shell.run_command('touch test1 test2 testa testb')

        shell.run_command('echo test[!12]')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "test1" not in output
        assert "test2" not in output
        assert "testa" in output
        assert "testb" in output

        # Clean up
        shell.run_command('rm -f test[12ab]')

    def test_multiple_ranges(self, shell, capsys):
        """Test multiple ranges in character class."""
        # Create test files
        shell.run_command('touch x1 x5 xa xe xz')

        shell.run_command('echo x[1-5a-e]')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "x1" in output
        assert "x5" in output
        assert "xa" in output
        assert "xe" in output
        assert "xz" not in output

        # Clean up
        shell.run_command('rm -f x[15aez]')


class TestHiddenFiles:
    """Test globbing with hidden files."""

    def test_hidden_files_not_matched(self, shell, capsys):
        """Test that * doesn't match hidden files by default."""
        # Create test files
        shell.run_command('touch .hidden visible')

        shell.run_command('echo *')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "visible" in output
        assert ".hidden" not in output

        # Clean up
        shell.run_command('rm -f .hidden visible')

    def test_explicit_hidden_pattern(self, shell, capsys):
        """Test explicit pattern for hidden files."""
        # Create test files
        shell.run_command('touch .hidden1 .hidden2 visible')

        shell.run_command('echo .*')
        captured = capsys.readouterr()
        output = captured.out.strip()
        # Should match hidden files (and . and ..)
        assert ".hidden1" in output or ". .." in output

        shell.run_command('echo .hidden*')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert ".hidden1" in output
        assert ".hidden2" in output

        # Clean up
        shell.run_command('rm -f .hidden1 .hidden2 visible')


class TestDirectoryGlobbing:
    """Test globbing with directories."""

    def test_directory_wildcard(self, shell, capsys):
        """Test wildcard matching directories."""
        # Create test directories
        shell.run_command('mkdir -p dir1 dir2 dir3')

        shell.run_command('echo dir*/')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "dir1/" in output
        assert "dir2/" in output
        assert "dir3/" in output

        # Clean up
        shell.run_command('rmdir dir1 dir2 dir3')

    def test_recursive_glob(self, shell, capsys):
        """Test ** recursive glob pattern."""
        # Create nested structure
        shell.run_command('mkdir -p a/b/c')
        shell.run_command('touch a/file1 a/b/file2 a/b/c/file3')

        # Note: ** might not be supported in all shells
        shell.run_command('echo a/**/file*')
        captured = capsys.readouterr()
        # If supported, should find all files recursively

        # Standard alternative
        shell.run_command('echo a/*/file*')
        captured = capsys.readouterr()
        assert "a/b/file2" in captured.out

        # Clean up
        shell.run_command('rm -rf a')

    def test_path_with_wildcards(self, shell, capsys):
        """Test wildcards in path components."""
        # Create test structure
        shell.run_command('mkdir -p test/sub1 test/sub2')
        shell.run_command('touch test/sub1/file.txt test/sub2/file.txt')

        shell.run_command('echo test/*/file.txt')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "test/sub1/file.txt" in output
        assert "test/sub2/file.txt" in output

        # Clean up
        shell.run_command('rm -rf test')


class TestGlobEscaping:
    """Test escaping glob characters."""

    def test_escaped_asterisk(self, shell, capsys):
        """Test escaped * character."""
        # Create test file with special name
        shell.run_command('touch "file*.txt"')

        shell.run_command('echo file\\*.txt')
        captured = capsys.readouterr()
        assert captured.out.strip() == "file*.txt"

        # Clean up
        shell.run_command('rm -f "file*.txt"')

    def test_quoted_patterns(self, shell, capsys):
        """Test quoted glob patterns."""
        # Create test files
        shell.run_command('touch file1.txt file2.txt')

        # Single quotes prevent globbing
        shell.run_command("echo '*.txt'")
        captured = capsys.readouterr()
        assert captured.out.strip() == "*.txt"

        # Double quotes prevent globbing
        shell.run_command('echo "*.txt"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "*.txt"

        # Clean up
        shell.run_command('rm -f file1.txt file2.txt')

    def test_partial_quoting(self, shell, capsys):
        """Test partial quoting of patterns."""
        # Create test files
        shell.run_command('touch test1.txt test2.txt')

        shell.run_command('echo test"*".txt')
        captured = capsys.readouterr()
        # The * is quoted, so no expansion
        assert captured.out.strip() == "test*.txt"

        shell.run_command('echo "test"*.txt')
        captured = capsys.readouterr()
        # The * is not quoted, so expansion happens
        output = captured.out.strip()
        assert "test1.txt" in output
        assert "test2.txt" in output

        # Clean up
        shell.run_command('rm -f test1.txt test2.txt')


class TestComplexGlobPatterns:
    """Test complex glob patterns."""

    def test_multiple_patterns(self, shell, capsys):
        """Test multiple glob patterns."""
        # Create test files
        shell.run_command('touch a.txt b.txt a.log b.log')

        shell.run_command('echo *.txt *.log')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "a.txt" in output
        assert "b.txt" in output
        assert "a.log" in output
        assert "b.log" in output

        # Clean up
        shell.run_command('rm -f *.txt *.log')

    def test_glob_with_brace_expansion(self, shell, capsys):
        """Test combining glob and brace expansion."""
        # Create test files
        shell.run_command('touch test.txt test.log test.bak')

        shell.run_command('echo test.{txt,log}')
        captured = capsys.readouterr()
        output = captured.out.strip()
        # Brace expansion happens first, then globbing
        assert "test.txt" in output
        assert "test.log" in output
        assert "test.bak" not in output

        # Clean up
        shell.run_command('rm -f test.*')

    def test_complex_character_class(self, shell, capsys):
        """Test complex character class patterns."""
        # Create test files
        shell.run_command('touch test_a test-b test.c test1 test2')

        shell.run_command('echo test[_.-]*')
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert "test_a" in output
        assert "test-b" in output
        assert "test.c" in output
        assert "test1" not in output

        # Clean up
        shell.run_command('rm -f test[_.-]* test[12]')


class TestGlobInContext:
    """Test glob expansion in various contexts."""

    def test_glob_in_for_loop(self, shell, capsys):
        """Test glob in for loop."""
        # Create test files
        shell.run_command('touch loop1.txt loop2.txt loop3.txt')

        cmd = '''
        for file in loop*.txt; do
            echo "Found: $file"
        done
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "Found: loop1.txt" in captured.out
        assert "Found: loop2.txt" in captured.out
        assert "Found: loop3.txt" in captured.out

        # Clean up
        shell.run_command('rm -f loop*.txt')

    def test_glob_with_variable(self, shell, capsys):
        """Test glob with variable expansion."""
        # Create test files
        shell.run_command('touch vartest1 vartest2')

        shell.run_command('PATTERN="vartest*"')
        shell.run_command('echo $PATTERN')
        captured = capsys.readouterr()
        # Variable expansion happens, then globbing
        output = captured.out.strip()
        assert "vartest1" in output
        assert "vartest2" in output

        # Clean up
        shell.run_command('rm -f vartest*')

    def test_glob_in_case_statement(self, shell, capsys):
        """Test glob patterns in case statement."""
        cmd = '''
        FILE="test.txt"
        case "$FILE" in
            *.txt) echo "Text file" ;;
            *.log) echo "Log file" ;;
            *) echo "Other file" ;;
        esac
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "Text file" in captured.out


class TestGlobOptions:
    """Test shell options affecting globbing."""

    def test_nullglob_behavior(self, shell, capsys):
        """Test behavior when no matches (nullglob option)."""
        # Default behavior - return pattern
        shell.run_command('echo *.nonexistent')
        captured = capsys.readouterr()
        assert captured.out.strip() == "*.nonexistent"

        # With nullglob (if supported)
        shell.run_command('shopt -s nullglob 2>/dev/null || true')
        shell.run_command('echo *.nonexistent')
        captured = capsys.readouterr()
        # Might be empty or unchanged depending on shell

    def test_failglob_no_match_fails_command(self, shell, capsys):
        """R13.B: shopt -s failglob makes a no-match glob fail the command
        (status 1) and print 'no match', instead of passing the pattern
        through (bash). The shell continues to the next command."""
        shell.run_command('shopt -s failglob')
        result = shell.run_command('echo /nonexistent_xyz_dir_*')
        captured = capsys.readouterr()
        assert result == 1
        assert 'no match' in captured.err
        # The pattern is NOT printed (the command did not run).
        assert '/nonexistent_xyz_dir_' not in captured.out

    def test_failglob_with_match_still_expands(self, shell, capsys):
        """failglob only affects no-match globs; a matching glob expands."""
        shell.run_command('touch fgmatch1.dat fgmatch2.dat')
        shell.run_command('shopt -s failglob')
        result = shell.run_command('echo fgmatch*.dat')
        captured = capsys.readouterr()
        assert result == 0
        assert 'fgmatch1.dat' in captured.out and 'fgmatch2.dat' in captured.out
        shell.run_command('rm -f fgmatch*.dat')

    def test_failglob_does_not_affect_assignment(self, shell, capsys):
        """A no-match glob in an assignment RHS is not globbed, so failglob
        does not fire (bash: x=/nonex_* keeps the literal pattern)."""
        shell.run_command('shopt -s failglob')
        result = shell.run_command('fgvar=/nonexistent_xyz_*')
        assert result == 0
        shell.run_command('echo "[$fgvar]"')
        assert capsys.readouterr().out.strip() == '[/nonexistent_xyz_*]'

    def test_dotglob_behavior(self, shell, capsys):
        """Test dotglob option for hidden files."""
        # Create test files
        shell.run_command('touch .hidden visible')

        # Default - no hidden files
        shell.run_command('echo *')
        captured = capsys.readouterr()
        assert ".hidden" not in captured.out
        assert "visible" in captured.out

        # Enable dotglob
        shell.state.options['dotglob'] = True
        shell.run_command('echo *')
        captured = capsys.readouterr()
        assert ".hidden" in captured.out
        assert "visible" in captured.out

        # Disable dotglob
        shell.state.options['dotglob'] = False
        shell.run_command('echo *')
        captured = capsys.readouterr()
        assert ".hidden" not in captured.out

        # Clean up
        shell.run_command('rm -f .hidden visible')
