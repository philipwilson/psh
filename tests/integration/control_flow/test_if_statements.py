"""
Integration tests for if/then/else/elif/fi control structures.

Tests cover:
- Basic if/then/fi
- if/then/else/fi
- if/elif/else chains
- Nested if statements
- Complex conditions
"""



class TestIfStatements:
    """Test if statement functionality."""

    def test_basic_if_true(self, shell, capsys):
        """Test basic if with true condition."""
        cmd = '''
        if true; then
            echo "condition was true"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert captured.out.strip() == "condition was true"

    def test_basic_if_false(self, shell, capsys):
        """Test basic if with false condition."""
        cmd = '''
        if false; then
            echo "should not print"
        fi
        echo "after if"
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "should not print" not in captured.out
        assert "after if" in captured.out

    def test_if_else(self, shell, capsys):
        """Test if/then/else/fi."""
        cmd = '''
        if false; then
            echo "in then"
        else
            echo "in else"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert captured.out.strip() == "in else"

    def test_if_elif_else(self, shell, capsys):
        """Test if/elif/else chain."""
        cmd = '''
        X=2
        if [ $X -eq 1 ]; then
            echo "X is 1"
        elif [ $X -eq 2 ]; then
            echo "X is 2"
        else
            echo "X is something else"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert captured.out.strip() == "X is 2"

    def test_multiple_elif(self, shell, capsys):
        """Test multiple elif branches."""
        cmd = '''
        NUM=3
        if [ $NUM -eq 1 ]; then
            echo "one"
        elif [ $NUM -eq 2 ]; then
            echo "two"
        elif [ $NUM -eq 3 ]; then
            echo "three"
        elif [ $NUM -eq 4 ]; then
            echo "four"
        else
            echo "other"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert captured.out.strip() == "three"

    def test_nested_if(self, shell, capsys):
        """Test nested if statements."""
        cmd = '''
        X=1
        Y=2
        if [ $X -eq 1 ]; then
            echo "X is 1"
            if [ $Y -eq 2 ]; then
                echo "Y is 2"
            else
                echo "Y is not 2"
            fi
        else
            echo "X is not 1"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "X is 1\nY is 2" in captured.out

    def test_if_with_command_substitution(self, shell, capsys):
        """Test if with command substitution in condition."""
        cmd = '''
        if [ "$(echo hello)" = "hello" ]; then
            echo "command substitution works"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert captured.out.strip() == "command substitution works"

    def test_if_with_arithmetic(self, shell, capsys):
        """Test if with arithmetic condition."""
        cmd = '''
        if (( 5 > 3 )); then
            echo "5 is greater than 3"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "5 is greater than 3" in captured.out

    def test_if_with_exit_code(self, shell, capsys):
        """Test if based on command exit code."""
        cmd = '''
        if echo "test" > /dev/null; then
            echo "echo succeeded"
        fi

        if false; then
            echo "should not print"
        else
            echo "false failed"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "echo succeeded" in captured.out
        assert "false failed" in captured.out

    def test_if_with_pipeline(self, shell, capsys):
        """Test if with pipeline in condition."""
        cmd = '''
        if echo "hello" | grep -q "ello"; then
            echo "pattern found"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert captured.out.strip() == "pattern found"

    def test_if_with_logical_operators(self, shell, capsys):
        """Test if with && and || in condition."""
        cmd = '''
        if true && true; then
            echo "both true"
        fi

        if true || false; then
            echo "at least one true"
        fi

        if false && true; then
            echo "should not print"
        else
            echo "not both true"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "both true" in captured.out
        assert "at least one true" in captured.out
        assert "not both true" in captured.out
        assert "should not print" not in captured.out

    def test_if_oneline(self, shell, capsys):
        """Test if statement on single line."""
        shell.run_command('if true; then echo "oneline"; fi')
        captured = capsys.readouterr()
        assert captured.out.strip() == "oneline"

    def test_if_with_variable_test(self, shell, capsys):
        """Test if with various variable tests."""
        cmd = '''
        VAR="hello"
        EMPTY=""

        if [ -n "$VAR" ]; then
            echo "VAR is not empty"
        fi

        if [ -z "$EMPTY" ]; then
            echo "EMPTY is empty"
        fi

        if [ "$VAR" = "hello" ]; then
            echo "VAR equals hello"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "VAR is not empty" in captured.out
        assert "EMPTY is empty" in captured.out
        assert "VAR equals hello" in captured.out

    def test_if_with_file_test(self, isolated_shell_with_temp_dir, capsys):
        """Test if with file test operators.

        Uses isolated_shell_with_temp_dir (per-test cwd) so the fixed-name
        `testfile`/`testdir` can't collide with another xdist worker creating
        the same names in a shared cwd (that race made this flaky).
        """
        shell = isolated_shell_with_temp_dir
        cmd = '''
        touch testfile
        mkdir testdir

        if [ -e testfile ]; then
            echo "file exists"
        fi

        if [ -f testfile ]; then
            echo "is regular file"
        fi

        if [ -d testdir ]; then
            echo "is directory"
        fi

        rm -f testfile
        rmdir testdir
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "file exists" in captured.out
        assert "is regular file" in captured.out
        assert "is directory" in captured.out

    def test_if_with_functions(self, shell, capsys):
        """Test if with function calls."""
        cmd = '''
        check_value() {
            [ "$1" -eq 42 ]
        }

        if check_value 42; then
            echo "value is 42"
        fi

        if check_value 10; then
            echo "should not print"
        else
            echo "value is not 42"
        fi
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "value is 42" in captured.out
        assert "value is not 42" in captured.out
        assert "should not print" not in captured.out
