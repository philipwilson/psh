"""
Unit tests for multi-line command history handling.
"""

from unittest.mock import patch

# NOTE: do NOT replace sys.modules['termios']/'tty' with Mocks here —
# importing them needs no TTY, and the poisoned modules leak into every
# later import in the process (it broke ptyprocess/pexpect during
# whole-tree collection). Per-test mocking via patch() is fine.
from psh.line_editor import LineEditor


class TestMultiLineHistory:
    """Test multi-line command handling in history."""

    def test_single_line_history(self):
        """Test that single-line commands work as before."""
        editor = LineEditor(history=['echo one', 'echo two'])
        editor.history_pos = 2  # At end of history

        # Mock stdin and stdout
        with patch('sys.stdout') as mock_stdout:
            # Simulate up arrow
            editor._history_up()

            # Should display the command normally
            calls = mock_stdout.write.call_args_list
            written = ''.join(call[0][0] for call in calls if call[0])
            assert 'echo two' in written
            assert '...' not in written

    def test_multiline_history_display(self):
        """Test that multi-line commands display as single line."""
        multiline_cmd = "for i in one two three\ndo\n  echo $i\ndone"
        editor = LineEditor(history=[multiline_cmd])
        editor.history_pos = 1  # At end of history

        with patch('sys.stdout') as mock_stdout:
            # Simulate up arrow
            editor._history_up()

            # Should display as single line with semicolons
            calls = mock_stdout.write.call_args_list
            written = ''.join(call[0][0] for call in calls if call[0])
            assert 'for i in one two three; do' in written
            assert 'echo $i' in written
            assert '; done' in written

            # Buffer should contain the single-line version
            buffer_content = ''.join(editor.buffer)
            assert 'for i in one two three; do' in buffer_content
            assert '; done' in buffer_content

    def test_multiline_history_execution(self):
        """Test that multi-line command is converted to single line."""
        multiline_cmd = "if true\nthen\n  echo 'it works'\nfi"
        editor = LineEditor(history=[multiline_cmd])
        editor.history_pos = 1

        # Navigate to history
        editor._history_up()

        # Buffer should contain single-line version
        buffer_content = ''.join(editor.buffer)
        assert 'if true; then' in buffer_content
        assert "echo 'it works'" in buffer_content
        assert '; fi' in buffer_content

        # Cursor should be at end of buffer
        assert editor.cursor_pos == len(editor.buffer)

    def test_history_navigation_mixed(self):
        """Test navigating through mixed single and multi-line history."""
        history = [
            'echo single',
            'for i in a b\ndo\n  echo $i\ndone',
            'ls -la',
            'if true\nthen\n  echo yes\nfi'
        ]
        editor = LineEditor(history=history)
        editor.history_pos = len(history)

        with patch('sys.stdout') as mock_stdout:
            # Go up through history
            editor._history_up()  # Should show if statement
            calls1 = [call[0][0] for call in mock_stdout.write.call_args_list if call[0]]
            written1 = ''.join(calls1)
            assert 'if true; then' in written1
            assert 'echo yes' in written1
            assert '; fi' in written1

            mock_stdout.write.reset_mock()

            editor._history_up()  # Should show ls
            calls2 = [call[0][0] for call in mock_stdout.write.call_args_list if call[0]]
            written2 = ''.join(calls2)
            assert 'ls -la' in written2

    def test_cursor_position_multiline(self):
        """Test cursor position is set correctly for multi-line commands."""
        multiline_cmd = "echo start\necho middle\necho end"
        editor = LineEditor(history=[multiline_cmd])

        # Convert and set line
        from psh.line_editor_helpers import convert_multiline_to_single
        single_line = convert_multiline_to_single(multiline_cmd)
        editor._replace_line(single_line)

        # Cursor should be at end of buffer
        assert editor.cursor_pos == len(editor.buffer)

    def test_history_down_multiline(self):
        """Test moving down in history with multi-line commands."""
        history = [
            'echo one',
            'for i in x\ndo\n  echo $i\ndone',
            'echo two'
        ]
        editor = LineEditor(history=history)
        editor.history_pos = 0  # At first item

        with patch('sys.stdout') as mock_stdout:
            # Move down to multi-line command
            editor._history_down()

            calls = mock_stdout.write.call_args_list
            written = ''.join(call[0][0] for call in calls if call[0])
            assert 'for i in x; do' in written
            assert 'echo $i' in written
            assert '; done' in written

            # Buffer has single-line command
            buffer_content = ''.join(editor.buffer)
            assert 'for i in x; do' in buffer_content
            assert '; done' in buffer_content
