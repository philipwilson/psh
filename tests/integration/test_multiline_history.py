"""Integration tests for multi-line command history handling."""

# Import clean_shell from conftest is handled automatically by pytest


class TestMultiLineHistory:
    """Test multi-line command handling in history."""

    def test_multiline_for_loop_in_history(self, clean_shell, capsys):
        """Test that multi-line for loops are preserved in history."""
        # Execute a multi-line for loop
        result = clean_shell.run_command("""for i in one two three
do
    echo "Item: $i"
done""")
        assert result == 0

        captured = capsys.readouterr()
        assert "Item: one" in captured.out
        assert "Item: two" in captured.out
        assert "Item: three" in captured.out

        # The command should be in history as a single entry
        # Check the shell's internal history directly
        history = clean_shell.state.history
        assert len(history) > 0
        last_command = history[-1]
        assert "for i in one two three" in last_command
        assert "do" in last_command
        assert "done" in last_command

    def test_multiline_if_statement_in_history(self, clean_shell, capsys):
        """Test that multi-line if statements are preserved in history."""
        # Execute a multi-line if statement
        result = clean_shell.run_command("""if [ 1 -eq 1 ]
then
    echo "Math works"
fi""")
        assert result == 0

        captured = capsys.readouterr()
        assert "Math works" in captured.out

        # Check history
        history = clean_shell.state.history
        assert len(history) > 0
        last_command = history[-1]
        assert "if [ 1 -eq 1 ]" in last_command
        assert "then" in last_command
        assert "fi" in last_command

    def test_multiline_function_definition_in_history(self, clean_shell, capsys):
        """Test that function definitions are preserved in history."""
        # Define a function
        result = clean_shell.run_command("""greet() {
    echo "Hello, $1!"
}""")
        assert result == 0

        # Test the function
        test_result = clean_shell.run_command('greet "World"')
        assert test_result == 0
        captured = capsys.readouterr()
        assert "Hello, World!" in captured.out

        # Check history - should have function definition and test command
        history = clean_shell.state.history
        assert len(history) >= 2
        # Find the function definition in history
        found_greet = False
        for cmd in history:
            if "greet()" in cmd:
                found_greet = True
                assert "{" in cmd
                assert "}" in cmd
                break
        assert found_greet, "Function definition not found in history"

    def test_multiline_case_statement_in_history(self, clean_shell, capsys):
        """Test that case statements are preserved in history."""
        # Execute a multi-line case statement
        result = clean_shell.run_command("""x=apple
case $x in
    apple)
        echo "It's a fruit"
        ;;
    *)
        echo "Unknown"
        ;;
esac""")
        assert result == 0

        captured = capsys.readouterr()
        assert "It's a fruit" in captured.out

        # Check history - should see the case statement
        history = clean_shell.state.history
        assert len(history) > 0
        last_command = history[-1]
        assert "case $x in" in last_command
        assert "esac" in last_command

    def test_multiline_while_loop_in_history(self, clean_shell, capsys):
        """Test that while loops are preserved in history."""
        # Execute a while loop
        result = clean_shell.run_command("""count=0
while [ $count -lt 3 ]
do
    echo "Count: $count"
    count=$((count + 1))
done""")
        assert result == 0

        captured = capsys.readouterr()
        assert "Count: 0" in captured.out
        assert "Count: 1" in captured.out
        assert "Count: 2" in captured.out

        # Check history
        history = clean_shell.state.history
        assert len(history) > 0
        last_command = history[-1]
        assert "while [ $count -lt 3 ]" in last_command
        assert "do" in last_command
        assert "done" in last_command

    def test_multiline_with_line_continuation(self, clean_shell, capsys):
        """Test multi-line commands with explicit line continuation."""
        # Execute a command with line continuation
        result = clean_shell.run_command("""echo one \\
two \\
three""")
        assert result == 0

        captured = capsys.readouterr()
        assert "one two three" in captured.out

        # Check history
        history = clean_shell.state.history
        assert len(history) > 0
        last_command = history[-1]
        assert "echo one" in last_command
        # Line continuation should be preserved in the command
        assert "\\" in last_command or "two" in last_command

    def test_history_expansion_not_saved(self, clean_shell, capsys):
        """Test that history expansion commands are not saved to history."""
        # History expansion is interactive-only by default (bash); enable it
        # explicitly to exercise the !! expansion behavior in this test shell.
        clean_shell.state.options['histexpand'] = True
        # Execute some commands
        clean_shell.run_command("echo first")
        clean_shell.run_command("echo second")
        capsys.readouterr()  # Clear output

        # Use history expansion
        result = clean_shell.run_command("!!")  # Repeat last command
        assert result == 0
        captured = capsys.readouterr()
        assert "second" in captured.out

        # The !! command should not be in history
        history = clean_shell.state.history
        assert len(history) >= 2
        # Check last few commands
        last_commands = history[-3:]  # Get last 3 commands
        # !! should not be saved
        assert not any("!!" in cmd for cmd in last_commands)
        # But echo second should be there
        assert any("echo second" in cmd for cmd in last_commands)
