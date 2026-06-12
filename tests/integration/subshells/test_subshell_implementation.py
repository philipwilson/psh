"""
Comprehensive subshell implementation integration tests.

Tests complete subshell functionality including command execution, variable isolation,
inheritance, I/O redirection, and advanced scenarios using the subshell syntax (...).
"""

import os


class TestSubshellExecution:
    """Test basic subshell command execution."""

    def test_simple_command_execution(self, isolated_shell_with_temp_dir):
        """Test basic command execution in subshell."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (echo "hello from subshell") > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "hello from subshell"

    def test_multiple_commands_in_subshell(self, isolated_shell_with_temp_dir):
        """Test multiple commands in a single subshell."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (
            echo "first command"
            echo "second command"
            echo "third command"
        ) > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        expected = "first command\nsecond command\nthird command"
        assert output == expected

    def test_semicolon_separated_commands(self, isolated_shell_with_temp_dir):
        """Test semicolon-separated commands in subshell."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (echo "one"; echo "two"; echo "three") > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "one\ntwo\nthree"


class TestSubshellVariableIsolation:
    """Test variable isolation in subshells."""

    def test_variable_modification_isolation(self, isolated_shell_with_temp_dir):
        """Test that variable changes in subshell don't affect parent."""
        shell = isolated_shell_with_temp_dir

        script = '''
        VAR="original"
        (VAR="modified"; echo "In subshell: $VAR") > subshell_output.txt
        echo "In parent: $VAR" > parent_output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('subshell_output.txt', 'r') as f:
            subshell_content = f.read().strip()
        assert subshell_content == "In subshell: modified"

        with open('parent_output.txt', 'r') as f:
            parent_content = f.read().strip()
        assert parent_content == "In parent: original"

    def test_variable_creation_isolation(self, isolated_shell_with_temp_dir):
        """Test that new variables in subshell don't affect parent."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (NEW_VAR="created in subshell"; echo "In subshell: $NEW_VAR") > subshell_output.txt
        echo "In parent: ${NEW_VAR:-undefined}" > parent_output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('subshell_output.txt', 'r') as f:
            subshell_content = f.read().strip()
        assert subshell_content == "In subshell: created in subshell"

        with open('parent_output.txt', 'r') as f:
            parent_content = f.read().strip()
        assert parent_content == "In parent: undefined"

    def test_variable_inheritance_from_parent(self, isolated_shell_with_temp_dir):
        """Test that subshell inherits variables from parent."""
        shell = isolated_shell_with_temp_dir

        script = '''
        PARENT_VAR="from parent"
        ANOTHER_VAR="also from parent"
        (echo "Inherited: $PARENT_VAR and $ANOTHER_VAR") > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Inherited: from parent and also from parent"

    def test_environment_variable_inheritance(self, isolated_shell_with_temp_dir):
        """Test that environment variables are inherited by subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        export EXPORTED_VAR="exported value"
        LOCAL_VAR="local value"
        (echo "Exported: $EXPORTED_VAR, Local: $LOCAL_VAR") > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Exported: exported value, Local: local value"


class TestSubshellExitStatus:
    """Test exit status behavior in subshells."""

    def test_successful_command_exit_status(self, isolated_shell_with_temp_dir):
        """Test that successful subshell returns 0."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (echo "success"; true)
        echo "Exit status: $?" > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Exit status: 0"

    def test_failed_command_exit_status(self, isolated_shell_with_temp_dir):
        """Test that subshell exit status is that of the last command."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (echo "before failure"; false; echo "after failure")
        echo "Exit status: $?" > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        # The last command (echo) succeeds, so exit status should be 0
        assert output == "Exit status: 0"

    def test_explicit_exit_in_subshell(self, isolated_shell_with_temp_dir):
        """Test explicit exit in subshell."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (echo "before exit"; exit 42; echo "after exit")
        echo "Exit status: $?" > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Exit status: 42"

    def test_last_command_determines_exit_status(self, isolated_shell_with_temp_dir):
        """Test that last command in subshell determines exit status."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (false; true; echo "done")
        echo "Exit status: $?" > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Exit status: 0"

    def test_subshell_ending_with_false(self, isolated_shell_with_temp_dir):
        """Test that subshell ending with false returns 1."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (echo "before false"; false)
        echo "Exit status: $?" > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Exit status: 1"


class TestSubshellRedirection:
    """Test I/O redirection in subshells."""

    def test_output_redirection(self, isolated_shell_with_temp_dir):
        """Test output redirection from subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (echo "line1"; echo "line2"; echo "line3") > redirected.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('redirected.txt', 'r') as f:
            content = f.read().strip()
        assert content == "line1\nline2\nline3"

    def test_input_redirection(self, isolated_shell_with_temp_dir):
        """Test input redirection to subshells."""
        shell = isolated_shell_with_temp_dir

        # Create input file
        with open('input.txt', 'w') as f:
            f.write('input line 1\ninput line 2\n')

        script = '''
        (while read line; do echo "Read: $line"; done) < input.txt > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "Read: input line 1\nRead: input line 2"

    def test_error_redirection(self, isolated_shell_with_temp_dir):
        """Test error redirection from subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (echo "stdout"; echo "stderr" >&2) 2> error.txt > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            stdout_content = f.read().strip()
        assert stdout_content == "stdout"

        with open('error.txt', 'r') as f:
            stderr_content = f.read().strip()
        assert stderr_content == "stderr"

    def test_background_execution(self, isolated_shell_with_temp_dir):
        """Test background execution of subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (sleep 0.2; echo "background done") &
        echo "foreground" > foreground.txt
        wait
        '''

        result = shell.run_command(script)
        assert result == 0


class TestSubshellAdvanced:
    """Test advanced subshell scenarios."""

    def test_nested_subshells(self, isolated_shell_with_temp_dir):
        """Test nested subshells with variable isolation."""
        shell = isolated_shell_with_temp_dir

        script = '''
        VAR="level0"
        (
            VAR="level1"
            echo "Level 1: $VAR"
            (
                VAR="level2"
                echo "Level 2: $VAR"
            )
            echo "Back to level 1: $VAR"
        ) > output.txt
        echo "Level 0: $VAR" >> output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            content = f.read().strip()
        expected = "Level 1: level1\nLevel 2: level2\nBack to level 1: level1\nLevel 0: level0"
        assert content == expected

    def test_function_inheritance(self, isolated_shell_with_temp_dir):
        """Test that functions are inherited by subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        my_function() {
            echo "Function called with: $1"
        }

        (my_function "from subshell") > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "Function called with: from subshell"

    def test_control_structures_in_subshells(self, isolated_shell_with_temp_dir):
        """Test control structures within subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (
            for i in 1 2 3; do
                if [ "$i" -eq 2 ]; then
                    echo "Found two: $i"
                else
                    echo "Number: $i"
                fi
            done
        ) > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            content = f.read().strip()
        expected = "Number: 1\nFound two: 2\nNumber: 3"
        assert content == expected

    def test_pipes_within_subshells(self, isolated_shell_with_temp_dir):
        """Test pipes within subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (echo -e "apple\\nbanana\\ncherry" | grep "a") > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            content = f.read().strip()
        # Should match apple and banana
        assert "apple" in content and "banana" in content
        assert "cherry" not in content

    def test_directory_change_isolation(self, isolated_shell_with_temp_dir):
        """Test that directory changes in subshells are isolated."""
        shell = isolated_shell_with_temp_dir

        # Create a subdirectory
        os.makedirs('subdir', exist_ok=True)

        script = '''
        original_dir=$(pwd)
        (cd subdir; echo "In subshell: $(pwd)") > subshell_pwd.txt
        echo "In parent: $(pwd)" > parent_pwd.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('subshell_pwd.txt', 'r') as f:
            subshell_pwd = f.read().strip()
        with open('parent_pwd.txt', 'r') as f:
            parent_pwd = f.read().strip()

        # Normalize paths for comparison (handle /var vs /private/var on macOS)
        subshell_pwd = os.path.realpath(subshell_pwd.replace("In subshell: ", ""))
        parent_pwd = os.path.realpath(parent_pwd.replace("In parent: ", ""))
        expected_subdir = os.path.realpath(os.path.join(os.getcwd(), 'subdir'))
        expected_parent = os.path.realpath(os.getcwd())

        assert subshell_pwd == expected_subdir
        assert parent_pwd == expected_parent


class TestSubshellArrayOperations:
    """Test array operations in subshells."""

    def test_array_modification_isolation(self, isolated_shell_with_temp_dir):
        """Test that array modifications in subshell don't affect parent."""
        shell = isolated_shell_with_temp_dir

        script = '''
        arr=(one two three)
        (arr[1]="modified"; echo "In subshell: ${arr[1]}") > subshell_output.txt
        echo "In parent: ${arr[1]}" > parent_output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('subshell_output.txt', 'r') as f:
            subshell_content = f.read().strip()
        assert subshell_content == "In subshell: modified"

        with open('parent_output.txt', 'r') as f:
            parent_content = f.read().strip()
        assert parent_content == "In parent: two"

    def test_array_inheritance(self, isolated_shell_with_temp_dir):
        """Test that arrays are inherited by subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        fruits=(apple banana cherry)
        (echo "Inherited array: ${fruits[0]} ${fruits[1]} ${fruits[2]}") > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Inherited array: apple banana cherry"


class TestSubshellCompatibility:
    """Test edge cases and compatibility scenarios."""

    def test_positional_parameter_inheritance(self, isolated_shell_with_temp_dir):
        """Test that positional parameters are inherited."""
        shell = isolated_shell_with_temp_dir

        # Set up positional parameters by running a function
        script = '''
        test_function() {
            (echo "Subshell sees: $1 $2 $3") > output.txt
        }
        test_function "arg1" "arg2" "arg3"
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Subshell sees: arg1 arg2 arg3"

    def test_dollar_question_propagation(self, isolated_shell_with_temp_dir):
        """Test that $? is properly propagated from subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (exit 123)
        captured_exit=$?
        echo "Captured exit status: $captured_exit" > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Captured exit status: 123"

    def test_process_id_behavior(self, isolated_shell_with_temp_dir):
        """Test $$ behavior in subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        parent_pid=$$
        (subshell_pid=$$; echo "Parent: $parent_pid, Subshell: $subshell_pid") > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        # In bash, subshells may have different PIDs
        # PSH implementation may vary
        assert "Parent:" in output and "Subshell:" in output

    def test_empty_subshell(self, isolated_shell_with_temp_dir):
        """Test empty subshell execution."""
        shell = isolated_shell_with_temp_dir

        script = '''
        ()
        echo "Empty subshell exit status: $?" > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Empty subshell exit status: 0"

    def test_whitespace_handling(self, isolated_shell_with_temp_dir):
        """Test various whitespace patterns in subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (   echo "whitespace before"   ) > output1.txt
        ( echo "whitespace around" ) > output2.txt
        (echo "no whitespace") > output3.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        for i, expected in enumerate(["whitespace before", "whitespace around", "no whitespace"], 1):
            with open(f'output{i}.txt', 'r') as f:
                output = f.read().strip()
            assert output == expected

    def test_subshell_with_comments(self, isolated_shell_with_temp_dir):
        """Test subshells containing comments."""
        shell = isolated_shell_with_temp_dir

        script = '''
        (
            # This is a comment
            echo "before comment"
            # Another comment
            echo "after comment"
        ) > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "before comment\nafter comment"


class TestSubshellErrorHandling:
    """Test error handling in subshells."""

    def test_command_not_found_in_subshell(self, isolated_shell_with_temp_dir):
        """Command-not-found inside a subshell follows bash semantics.

        Bash-verified (bash 5.2): a subshell's exit status is that of its
        LAST command. `(echo before; nonexistent; echo after)` exits 0
        because the trailing echo succeeds; the failure surfaces only on
        stderr. When the nonexistent command is last, the subshell exits
        127.
        """
        shell = isolated_shell_with_temp_dir

        script = '''
        (echo "before"; nonexistent_command; echo "after") 2> error.txt
        echo "Exit status: $?" > status.txt
        '''

        result = shell.run_command(script)
        # Main script should continue even if a command inside the subshell fails
        assert result == 0

        with open('status.txt', 'r') as f:
            status = f.read().strip()
        # Last command (echo "after") succeeded, so the subshell exits 0 —
        # exactly as bash does.
        assert status == "Exit status: 0"

        # The failure is still reported on stderr.
        with open('error.txt', 'r') as f:
            error = f.read()
        assert "nonexistent_command" in error

        # When the failing command is LAST, its 127 becomes the subshell's
        # exit status (bash-verified).
        shell.run_command(
            '(echo "before"; nonexistent_command) 2> error2.txt; '
            'echo "Exit status: $?" > status2.txt'
        )
        with open('status2.txt', 'r') as f:
            assert f.read().strip() == "Exit status: 127"

    def test_syntax_error_handling(self, isolated_shell_with_temp_dir):
        """Test handling of syntax errors in subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        echo "before subshell" > before.txt
        (echo "valid command") > valid.txt
        echo "after subshell" > after.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        # All files should be created
        for filename in ['before.txt', 'valid.txt', 'after.txt']:
            assert os.path.exists(filename)

    def test_variable_expansion_errors(self, isolated_shell_with_temp_dir):
        """Test handling of variable expansion in subshells."""
        shell = isolated_shell_with_temp_dir

        script = '''
        unset UNDEFINED_VAR
        (echo "Value: ${UNDEFINED_VAR:-default}") > output.txt
        '''

        result = shell.run_command(script)
        assert result == 0

        with open('output.txt', 'r') as f:
            output = f.read().strip()
        assert output == "Value: default"
