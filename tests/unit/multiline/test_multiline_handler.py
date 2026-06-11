"""
MultiLine handler unit tests.

Tests the MultiLineInputHandler class for command completion detection,
line continuation handling, and multi-line input management.
"""

from unittest.mock import Mock, patch

from psh.interactive.line_editor import LineEditor

# PSH test setup will import these properly
from psh.interactive.multiline_handler import MultiLineInputHandler


class TestCommandCompletion:
    """Test command completion detection."""

    def test_simple_complete_commands(self, shell):
        """Test detection of complete simple commands."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Complete commands
        assert handler._is_complete_command("echo hello")
        assert handler._is_complete_command("ls -la")
        assert handler._is_complete_command("")
        assert handler._is_complete_command("   ")

    def test_line_continuation_detection(self, shell):
        """Test detection of line continuation with backslash."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete due to line continuation
        assert not handler._is_complete_command("echo hello \\")
        assert not handler._is_complete_command("echo \\\n")

        # Complete - backslash is escaped
        assert handler._is_complete_command("echo hello \\\\")
        assert handler._is_complete_command("echo hello")

    def test_unclosed_quotes_detection(self, shell):
        """Test detection of unclosed quotes."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete due to unclosed quotes
        assert not handler._is_complete_command('echo "hello')
        assert not handler._is_complete_command("echo 'hello")

        # Complete - quotes are closed
        assert handler._is_complete_command('echo "hello"')
        assert handler._is_complete_command("echo 'hello'")

    def test_pipeline_operators_detection(self, shell):
        """Test detection of incomplete pipeline operators."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete due to operators at end
        assert not handler._is_complete_command("echo hello |")
        assert not handler._is_complete_command("echo hello &&")
        assert not handler._is_complete_command("echo hello ||")
        assert not handler._is_complete_command("echo hello | ")
        assert not handler._is_complete_command("echo hello && ")

        # Complete - operators have continuation
        assert handler._is_complete_command("echo hello | grep")
        assert handler._is_complete_command("true && echo success")

    def test_unclosed_command_substitution(self, shell):
        """Test detection of unclosed command substitution."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete command substitution
        assert not handler._is_complete_command("echo $(")
        assert not handler._is_complete_command("echo $(echo hello")
        assert not handler._is_complete_command("echo `echo hello")

        # Complete command substitution
        assert handler._is_complete_command("echo $(echo hello)")
        assert handler._is_complete_command("echo `echo hello`")


class TestControlStructureCompletion:
    """Test completion detection for control structures."""

    def test_if_statement_completion(self, shell):
        """Test detection of incomplete if statements."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete if statements
        assert not handler._is_complete_command("if true")
        assert not handler._is_complete_command("if true; then")
        assert not handler._is_complete_command("if true; then\necho hello")
        assert not handler._is_complete_command("if true; then ")

        # Complete if statements
        assert handler._is_complete_command("if true; then echo hello; fi")
        assert handler._is_complete_command("if true; then\necho hello\nfi")

    def test_while_loop_completion(self, shell):
        """Test detection of incomplete while loops."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete while loops
        assert not handler._is_complete_command("while true")
        assert not handler._is_complete_command("while true; do")
        assert not handler._is_complete_command("while true; do\necho hello")

        # Complete while loops
        assert handler._is_complete_command("while true; do echo hello; done")
        assert handler._is_complete_command("while true; do\necho hello\ndone")

    def test_for_loop_completion(self, shell):
        """Test detection of incomplete for loops."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete for loops
        assert not handler._is_complete_command("for i in 1 2 3")
        assert not handler._is_complete_command("for i in 1 2 3; do")
        assert not handler._is_complete_command("for i in 1 2 3; do\necho $i")

        # Complete for loops
        assert handler._is_complete_command("for i in 1 2 3; do echo $i; done")
        assert handler._is_complete_command("for i in 1 2 3; do\necho $i\ndone")

    def test_case_statement_completion(self, shell):
        """Test detection of incomplete case statements."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete case statements
        assert not handler._is_complete_command("case $x in")
        assert not handler._is_complete_command("case $x in\n1)")
        assert not handler._is_complete_command("case $x in\n1) echo one;;")

        # Complete case statements
        assert handler._is_complete_command("case $x in\n1) echo one;;\nesac")

    def test_function_definition_completion(self, shell):
        """Test detection of incomplete function definitions."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete function definitions
        assert not handler._is_complete_command("hello() {")
        assert not handler._is_complete_command("hello() {\necho hello")

        # Complete function definitions
        assert handler._is_complete_command("hello() { echo hello; }")
        assert handler._is_complete_command("hello() {\necho hello\n}")

    def test_nested_structure_completion(self, shell):
        """Test nested incomplete control structures."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Nested incomplete structures
        assert not handler._is_complete_command("if true; then\n  if false; then")
        assert not handler._is_complete_command("while true; do\n  for i in 1 2 3; do")

        # Nested complete structures
        assert handler._is_complete_command("if true; then\n  if false; then\n    echo nested\n  fi\nfi")


class TestHeredocCompletion:
    """Test heredoc completion detection."""

    def test_basic_heredoc_completion(self, shell):
        """Test detection of incomplete basic heredocs."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete basic heredoc
        assert not handler._is_complete_command("cat <<EOF")
        assert not handler._is_complete_command("cat <<EOF\nline1")
        assert not handler._is_complete_command("cat <<EOF\nline1\nline2")

        # Complete basic heredoc
        assert handler._is_complete_command("cat <<EOF\nline1\nEOF")

    def test_heredoc_with_dash(self, shell):
        """Test heredoc with dash (tab stripping)."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete heredoc with dash
        assert not handler._is_complete_command("cat <<-EOF")
        assert not handler._is_complete_command("cat <<-EOF\n\tline1")

        # Complete heredoc with dash
        assert handler._is_complete_command("cat <<-EOF\n\tline1\nEOF")
        assert handler._is_complete_command("cat <<-EOF\n\tline1\n\tEOF")

    def test_heredoc_with_quotes(self, shell):
        """Test heredoc with quoted delimiters."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete heredoc with quotes
        assert not handler._is_complete_command("cat <<'EOF'")
        assert not handler._is_complete_command('cat <<"EOF"')

        # Complete heredoc with quotes
        assert handler._is_complete_command("cat <<'EOF'\nline\nEOF")
        assert handler._is_complete_command('cat <<"EOF"\nline\nEOF')

    def test_multiple_heredocs(self, shell):
        """Test multiple heredocs in one command."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete multiple heredocs
        assert not handler._is_complete_command("cat <<EOF1 && cat <<EOF2")
        assert not handler._is_complete_command("cat <<EOF1 && cat <<EOF2\nline1\nEOF1")

        # Complete multiple heredocs
        assert handler._is_complete_command("cat <<EOF1 && cat <<EOF2\nline1\nEOF1\nline2\nEOF2")

    def test_escaped_heredoc_delimiter(self, shell):
        """Test heredoc with escaped delimiter."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Incomplete escaped heredoc
        assert not handler._is_complete_command("cat << \\EOF")
        assert not handler._is_complete_command("cat << \\EOF\nline1")

        # Complete escaped heredoc
        assert handler._is_complete_command("cat << \\EOF\nline1\nEOF")


class TestMultilineInputHandling:
    """Test actual multiline input handling."""

    def test_read_simple_command(self, shell):
        """Test reading a simple single-line command."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        line_editor.read_line.return_value = "echo hello"

        result = handler.read_command()

        assert result == "echo hello"
        assert line_editor.read_line.call_count == 1

    def test_read_multiline_command(self, shell):
        """Test reading a multi-line command."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        # Mock multiple line inputs
        line_editor.read_line.side_effect = [
            "if true; then",
            "  echo hello",
            "fi"
        ]

        result = handler.read_command()

        assert result == "if true; then\n  echo hello\nfi"
        assert line_editor.read_line.call_count == 3

    def test_read_command_eof(self, shell):
        """Test handling EOF during input."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        line_editor.read_line.return_value = None

        result = handler.read_command()

        assert result is None

    def test_read_command_eof_in_multiline(self, shell):
        """Test handling EOF in middle of multi-line input."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        line_editor.read_line.side_effect = [
            "if true; then",
            None  # EOF
        ]

        with patch('builtins.print') as mock_print:
            result = handler.read_command()

        assert result is None
        mock_print.assert_called_with("\npsh: syntax error: unexpected end of file")


class TestPromptHandling:
    """Test prompt handling for multiline input."""

    def test_get_primary_prompt(self, shell):
        """Test getting primary prompt (PS1)."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        shell.state.set_variable('PS1', 'test$ ')
        prompt = handler._get_prompt()
        assert 'test$' in prompt  # May be expanded

    def test_get_continuation_prompt(self, shell):
        """Test getting continuation prompt (PS2)."""
        line_editor = Mock(spec=LineEditor)
        handler = MultiLineInputHandler(line_editor, shell)

        shell.state.set_variable('PS2', '... ')
        handler.buffer = ['if true; then']  # Non-empty buffer
        prompt = handler._get_prompt()
        assert prompt == '... '
