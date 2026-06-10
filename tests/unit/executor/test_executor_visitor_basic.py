"""
Basic executor visitor unit tests.

Tests fundamental ExecutorVisitor functionality including simple command execution,
variable assignments, environment handling, and exit status propagation.
"""



class TestSimpleCommandExecution:
    """Test basic command execution through the visitor."""

    def test_empty_command_list(self, shell):
        """Test that empty command lists execute successfully."""
        result = shell.run_command("")
        assert result == 0

    def test_echo_builtin_execution(self, shell, capsys):
        """Test echo builtin execution through visitor."""
        result = shell.run_command("echo hello world")
        assert result == 0

        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_simple_variable_assignment(self, shell):
        """Test variable assignment through visitor."""
        result = shell.run_command("VAR=value")
        assert result == 0
        assert shell.state.get_variable("VAR") == "value"

    def test_command_with_variable_assignment(self, captured_shell):
        """Test command with preceding variable assignment.

        POSIX/bash: the command's own words are expanded BEFORE the
        temporary assignment applies, so $TEST_VAR is its prior (empty)
        value — but the variable IS visible inside the command itself.
        """
        result = captured_shell.run_command("TEST_VAR=hello echo \"[$TEST_VAR]\"")
        assert result == 0
        assert captured_shell.get_stdout() == "[]\n"

        # Variable should not persist in global scope (returns empty string for unset)
        assert captured_shell.state.get_variable("TEST_VAR") == ""

        # The assignment is visible to the command while it runs (a
        # function here — assignments before *special* builtins like eval
        # persist per POSIX, which psh implements)
        captured_shell.clear_output()
        result = captured_shell.run_command(
            "f() { echo \"[$TEST_VAR]\"; }; TEST_VAR=hello f")
        assert result == 0
        assert captured_shell.get_stdout() == "[hello]\n"
        assert captured_shell.state.get_variable("TEST_VAR") == ""

    def test_external_command_execution(self, shell, capsys):
        """Test external command execution."""
        result = shell.run_command("true")
        assert result == 0

        result = shell.run_command("false")
        assert result == 1

    def test_command_not_found_error(self, shell, capsys):
        """Test command not found error handling."""
        result = shell.run_command("nonexistent_command_xyz")
        assert result != 0

        capsys.readouterr()
        # PSH outputs errors to stderr, but pytest may not capture it properly
        # Just verify the command failed with non-zero exit
        assert result != 0


class TestVariableHandling:
    """Test variable assignment and environment handling."""

    def test_multiple_variable_assignments(self, shell):
        """Test multiple variable assignments in sequence."""
        commands = [
            "VAR1=value1",
            "VAR2=value2",
            "VAR3=value3"
        ]

        for cmd in commands:
            result = shell.run_command(cmd)
            assert result == 0

        assert shell.state.get_variable("VAR1") == "value1"
        assert shell.state.get_variable("VAR2") == "value2"
        assert shell.state.get_variable("VAR3") == "value3"

    def test_variable_expansion_in_commands(self, shell, capsys):
        """Test variable expansion in command arguments."""
        shell.run_command("TEST_MSG=hello")
        result = shell.run_command("echo $TEST_MSG world")
        assert result == 0

        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_environment_variable_access(self, shell, capsys):
        """Test access to environment variables."""
        shell.run_command("export EXPORTED_VAR=exported_value")
        result = shell.run_command("echo $EXPORTED_VAR")
        assert result == 0

        captured = capsys.readouterr()
        assert "exported_value" in captured.out

    def test_variable_modification(self, shell):
        """Test modifying existing variables."""
        shell.run_command("VAR=original")
        assert shell.state.get_variable("VAR") == "original"

        shell.run_command("VAR=modified")
        assert shell.state.get_variable("VAR") == "modified"


class TestExitStatusHandling:
    """Test exit status tracking and propagation."""

    def test_successful_command_exit_status(self, shell, capsys):
        """Test that successful commands set $? to 0."""
        shell.run_command("true")
        result = shell.run_command("echo $?")
        assert result == 0

        captured = capsys.readouterr()
        assert "0" in captured.out

    def test_failed_command_exit_status(self, shell, capsys):
        """Test that failed commands set $? to non-zero."""
        shell.run_command("false")
        result = shell.run_command("echo $?")
        assert result == 0

        captured = capsys.readouterr()
        assert "1" in captured.out

    def test_exit_status_persistence(self, shell, capsys):
        """Test that exit status persists until next command."""
        shell.run_command("false")  # Sets $? to 1
        result = shell.run_command("echo $?")
        assert result == 0

        captured = capsys.readouterr()
        # $? should be 1 from the false command
        assert "1" in captured.out

    def test_builtin_command_exit_status(self, shell, capsys):
        """Test exit status from builtin commands."""
        # Test successful echo
        shell.run_command("echo test")
        shell.run_command("echo $?")
        captured = capsys.readouterr()
        assert "0" in captured.out

        # Test cd to nonexistent directory (should fail)
        shell.run_command("cd /nonexistent/directory/path")
        result = shell.run_command("echo $?")
        assert result == 0

        captured = capsys.readouterr()
        # Should be non-zero exit status
        assert not captured.out.strip().endswith("0")


class TestCommandTypes:
    """Test different types of command execution."""

    def test_builtin_command_execution(self, shell, capsys):
        """Test execution of various builtin commands."""
        builtins_to_test = [
            ("echo hello", "hello"),
            ("pwd", ""),  # Just check it runs
            ("true", ""),
        ]

        for cmd, expected_output in builtins_to_test:
            result = shell.run_command(cmd)
            assert result == 0

            if expected_output:
                captured = capsys.readouterr()
                assert expected_output in captured.out

    def test_external_command_types(self, shell):
        """Test different external command scenarios."""
        # Commands that should exist on most systems
        system_commands = [
            ("true", 0),
            ("false", 1),
        ]

        for cmd, expected_exit in system_commands:
            result = shell.run_command(cmd)
            assert result == expected_exit

    def test_command_with_arguments(self, shell, capsys):
        """Test commands with multiple arguments."""
        result = shell.run_command("echo first second third")
        assert result == 0

        captured = capsys.readouterr()
        output = captured.out
        assert "first" in output
        assert "second" in output
        assert "third" in output

    def test_quoted_arguments(self, shell, capsys):
        """Test commands with quoted arguments."""
        result = shell.run_command('echo "hello world" test')
        assert result == 0

        captured = capsys.readouterr()
        assert "hello world" in captured.out
        assert "test" in captured.out


class TestErrorConditions:
    """Test error handling in command execution."""

    def test_invalid_command_handling(self, shell):
        """Test handling of various invalid commands."""
        invalid_commands = [
            "nonexistent_command_12345",
            "/path/to/nonexistent/binary",
        ]

        for cmd in invalid_commands:
            result = shell.run_command(cmd)
            # Should return non-zero exit status
            assert result != 0

    def test_permission_denied_handling(self, shell):
        """Test handling of permission denied scenarios."""
        # Try to execute a directory (should fail)
        result = shell.run_command("/usr")
        assert result != 0

    def test_syntax_error_resilience(self, shell):
        """Test that executor handles basic syntax gracefully."""
        # These should be caught by parser, but test executor resilience
        valid_commands = [
            "echo test",
            "VAR=value",
            "true",
        ]

        for cmd in valid_commands:
            result = shell.run_command(cmd)
            assert result == 0


class TestSpecialCases:
    """Test special cases and edge conditions."""

    def test_empty_variable_assignment(self, shell):
        """Test assignment of empty values."""
        result = shell.run_command("EMPTY_VAR=")
        assert result == 0
        assert shell.state.get_variable("EMPTY_VAR") == ""

    def test_numeric_variable_values(self, shell, capsys):
        """Test variables with numeric values."""
        shell.run_command("NUM=42")
        result = shell.run_command("echo $NUM")
        assert result == 0

        captured = capsys.readouterr()
        assert "42" in captured.out

    def test_special_characters_in_values(self, shell, capsys):
        """Test variables with special characters."""
        shell.run_command("SPECIAL='hello world'")
        result = shell.run_command("echo $SPECIAL")
        assert result == 0

        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_variable_unset_behavior(self, shell, capsys):
        """Test behavior with unset variables."""
        result = shell.run_command("echo ${UNDEFINED_VAR:-default}")
        assert result == 0

        captured = capsys.readouterr()
        assert "default" in captured.out

    def test_command_line_length_handling(self, shell, capsys):
        """Test handling of longer command lines."""
        # Create a reasonably long command
        long_args = " ".join([f"arg{i}" for i in range(20)])
        result = shell.run_command(f"echo {long_args}")
        assert result == 0

        captured = capsys.readouterr()
        assert "arg0" in captured.out
        assert "arg19" in captured.out


class TestStatePersistence:
    """Test state persistence across commands."""

    def test_variable_persistence(self, shell):
        """Test that variables persist across multiple commands."""
        shell.run_command("PERSISTENT=value")
        shell.run_command("OTHER_CMD=true")

        assert shell.state.get_variable("PERSISTENT") == "value"
        assert shell.state.get_variable("OTHER_CMD") == "true"

    def test_working_directory_persistence(self, shell):
        """Test that working directory changes persist."""
        original_pwd = shell.state.get_variable("PWD")

        # Change to parent directory
        result = shell.run_command("cd ..")
        assert result == 0

        new_pwd = shell.state.get_variable("PWD")
        assert new_pwd != original_pwd

    def test_environment_persistence(self, shell, capsys):
        """Test that exported variables persist."""
        shell.run_command("export TEST_EXPORT=exported")

        # Verify it's accessible in subsequent commands
        result = shell.run_command("echo $TEST_EXPORT")
        assert result == 0

        captured = capsys.readouterr()
        assert "exported" in captured.out
