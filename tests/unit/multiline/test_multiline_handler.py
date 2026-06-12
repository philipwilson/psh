"""
MultiLine handler unit tests.

The handler no longer decides completeness itself — that is the shared
CommandAccumulator's job (tests/unit/scripting/test_command_accumulator.py).
These tests pin the interactive glue: the read_command loop (one read_line
per physical line until the accumulator says Complete), EOF handling, and
the PS1/PS2/contextual continuation prompts.
"""

from unittest.mock import Mock, patch

from psh.interactive.line_editor import LineEditor

# PSH test setup will import these properly
from psh.interactive.multiline_handler import MultiLineInputHandler


def make_handler(shell):
    line_editor = Mock(spec=LineEditor)
    return line_editor, MultiLineInputHandler(line_editor, shell)


class TestMultilineInputHandling:
    """Test actual multiline input handling."""

    def test_read_simple_command(self, shell):
        """Test reading a simple single-line command."""
        line_editor, handler = make_handler(shell)
        line_editor.read_line.return_value = "echo hello"

        result = handler.read_command()

        assert result == "echo hello"
        assert line_editor.read_line.call_count == 1

    def test_read_multiline_command(self, shell):
        """Test reading a multi-line command."""
        line_editor, handler = make_handler(shell)

        # Mock multiple line inputs
        line_editor.read_line.side_effect = [
            "if true; then",
            "  echo hello",
            "fi"
        ]

        result = handler.read_command()

        assert result == "if true; then\n  echo hello\nfi"
        assert line_editor.read_line.call_count == 3

    def test_read_command_joins_line_continuation(self, shell):
        """A trailing backslash keeps reading; the result is joined."""
        line_editor, handler = make_handler(shell)
        line_editor.read_line.side_effect = ["echo one \\", "two"]

        result = handler.read_command()

        assert result == "echo one two"
        assert line_editor.read_line.call_count == 2

    def test_read_heredoc_command(self, shell):
        """Heredoc bodies are gathered until the delimiter."""
        line_editor, handler = make_handler(shell)
        line_editor.read_line.side_effect = ["cat <<EOF", "body", "EOF"]

        result = handler.read_command()

        assert result == "cat <<EOF\nbody\nEOF"
        assert line_editor.read_line.call_count == 3

    def test_invalid_command_returned_for_execution(self, shell):
        """A complete-but-invalid command is returned (the execution path
        reports the syntax error), never prompted for continuation."""
        line_editor, handler = make_handler(shell)
        line_editor.read_line.return_value = "echo )"

        result = handler.read_command()

        assert result == "echo )"
        assert line_editor.read_line.call_count == 1

    def test_read_command_eof(self, shell):
        """Test handling EOF during input."""
        line_editor, handler = make_handler(shell)
        line_editor.read_line.return_value = None

        result = handler.read_command()

        assert result is None

    def test_read_command_eof_in_multiline(self, shell):
        """Test handling EOF in middle of multi-line input."""
        line_editor, handler = make_handler(shell)
        line_editor.read_line.side_effect = [
            "if true; then",
            None  # EOF
        ]

        with patch('builtins.print') as mock_print:
            result = handler.read_command()

        assert result is None
        mock_print.assert_called_with("\npsh: syntax error: unexpected end of file")

    def test_reset_drops_partial_input(self, shell):
        """Ctrl-C path: reset() abandons the buffer; the next read starts
        a fresh command at PS1."""
        line_editor, handler = make_handler(shell)
        line_editor.read_line.side_effect = ["if true; then"]
        try:
            handler.read_command()
        except StopIteration:
            pass  # ran out of mocked lines mid-construct, as intended
        handler.reset()
        assert handler.accumulator.is_empty

        line_editor.read_line.side_effect = ["echo clean"]
        assert handler.read_command() == "echo clean"


class TestPromptHandling:
    """Test prompt handling for multiline input."""

    def test_get_primary_prompt(self, shell):
        """Test getting primary prompt (PS1)."""
        _, handler = make_handler(shell)

        shell.state.set_variable('PS1', 'test$ ')
        prompt = handler._get_prompt()
        assert 'test$' in prompt  # May be expanded

    def test_get_continuation_prompt(self, shell):
        """Mid-command without a construct hint (e.g. unclosed quote),
        the continuation prompt is PS2."""
        _, handler = make_handler(shell)

        shell.state.set_variable('PS2', '... ')
        handler.accumulator.feed('echo "one')  # NeedMore: unclosed quote
        handler._hint = None
        prompt = handler._get_prompt()
        assert prompt == '... '

    def test_contextual_continuation_prompt(self, shell):
        """The parser's open-construct trail renders as the continuation
        prompt ('if> ', 'then while> ')."""
        line_editor, handler = make_handler(shell)
        prompts = []

        def fake_read_line(prompt, *args, **kwargs):
            prompts.append(prompt)
            return {
                0: "if true; then",
                1: "while true; do",
                2: "echo hi",
                3: "done",
            }.get(len(prompts) - 1, "fi")

        line_editor.read_line.side_effect = fake_read_line
        result = handler.read_command()

        assert result == "if true; then\nwhile true; do\necho hi\ndone\nfi"
        assert prompts[1] == "then> "
        assert prompts[2] == "then while> "
        assert prompts[3] == "then while> "
        assert prompts[4] == "then> "

    def test_heredoc_uses_plain_ps2(self, shell):
        """Heredoc bodies prompt with PS2, not a construct context."""
        line_editor, handler = make_handler(shell)
        shell.state.set_variable('PS2', '> ')
        prompts = []

        def fake_read_line(prompt, *args, **kwargs):
            prompts.append(prompt)
            return ["cat <<EOF", "body", "EOF"][len(prompts) - 1]

        line_editor.read_line.side_effect = fake_read_line
        handler.read_command()

        assert prompts[1] == '> '
        assert prompts[2] == '> '
