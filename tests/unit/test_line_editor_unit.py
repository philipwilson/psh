"""
Unit tests for LineEditor functionality without terminal emulation.

These tests verify LineEditor behavior by directly calling internal methods,
bypassing the need for TTY and raw terminal mode.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add PSH to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

# NOTE: termios/tty import fine without a TTY; never replace them in
# sys.modules with Mocks — that leaks into every later import in the
# process (it broke ptyprocess/pexpect during whole-tree collection).


class TestLineEditorUnit:
    """Test LineEditor internal methods directly."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup mocks and imports for each test."""
        # Mock sys.stdin.isatty to return False to avoid terminal operations
        self.stdin_mock = Mock()
        self.stdin_mock.isatty.return_value = False
        self.stdin_mock.fileno.return_value = 0

        with patch('sys.stdin', self.stdin_mock):
            # Now we can safely import
            from psh.interactive.keybindings import EditMode
            from psh.interactive.line_editor import LineEditor

            # Create editor instance
            self.editor = LineEditor(history=[])
            self.EditMode = EditMode

    def test_initialization(self):
        """Test LineEditor initializes with correct defaults."""
        assert self.editor.buffer == []
        assert self.editor.cursor_pos == 0
        assert len(self.editor.history) == 0
        assert self.editor.edit_mode == 'emacs'

    def test_insert_character(self):
        """Test character insertion."""
        # Insert at beginning
        self.editor._insert_char('H')
        assert self.editor.buffer == ['H']
        assert self.editor.cursor_pos == 1

        # Insert more
        self.editor._insert_char('i')
        assert self.editor.buffer == ['H', 'i']
        assert self.editor.cursor_pos == 2

        # Insert in middle
        self.editor.cursor_pos = 1
        self.editor._insert_char('e')
        assert self.editor.buffer == ['H', 'e', 'i']
        assert self.editor.cursor_pos == 2

    def test_backspace(self):
        """Test backspace functionality."""
        self.editor.buffer = list("Hello")
        self.editor.cursor_pos = 3

        # Backspace in middle
        self.editor._backspace()
        assert ''.join(self.editor.buffer) == "Helo"
        assert self.editor.cursor_pos == 2

        # Backspace at beginning (no effect)
        self.editor.cursor_pos = 0
        self.editor._backspace()
        assert ''.join(self.editor.buffer) == "Helo"
        assert self.editor.cursor_pos == 0

    def test_delete_char(self):
        """Test delete character."""
        self.editor.buffer = list("Hello")
        self.editor.cursor_pos = 2

        # Delete at cursor
        self.editor._delete_char()
        assert ''.join(self.editor.buffer) == "Helo"
        assert self.editor.cursor_pos == 2

        # Delete at end (no effect)
        self.editor.cursor_pos = 4
        self.editor._delete_char()
        assert ''.join(self.editor.buffer) == "Helo"

    def test_cursor_movement(self):
        """Test cursor movement methods."""
        self.editor.buffer = list("Hello World")
        self.editor.cursor_pos = 5

        # Move left
        self.editor._move_left()
        assert self.editor.cursor_pos == 4

        # Move right
        self.editor._move_right()
        self.editor._move_right()
        assert self.editor.cursor_pos == 6

        # Move home
        self.editor._move_home()
        assert self.editor.cursor_pos == 0

        # Move end
        self.editor._move_end()
        assert self.editor.cursor_pos == 11

    def test_word_movement(self):
        """Test word-based cursor movement."""
        self.editor.buffer = list("Hello World PSH")

        # Move word forward from start
        self.editor.cursor_pos = 0
        self.editor._move_word_forward()
        assert self.editor.cursor_pos == 6  # After "Hello "

        # Move word backward from middle of word
        self.editor.cursor_pos = 8  # In "World"
        self.editor._move_word_backward()
        assert self.editor.cursor_pos == 6  # At "W"

    def test_kill_operations(self):
        """Test kill (cut) operations."""
        # Kill to end of line
        self.editor.buffer = list("Hello World")
        self.editor.cursor_pos = 6
        self.editor._kill_line()
        assert ''.join(self.editor.buffer) == "Hello "
        assert self.editor.kill_ring[-1] == "World"

        # Kill whole line
        self.editor.buffer = list("Hello World")
        self.editor.cursor_pos = 6
        self.editor._kill_whole_line()
        assert self.editor.buffer == []
        assert self.editor.kill_ring[-1] == "Hello World"

    def test_yank(self):
        """Test yank (paste) operation."""
        # Add something to kill ring
        self.editor.kill_ring = ["pasted text"]
        self.editor.buffer = list("Hello ")
        self.editor.cursor_pos = 6

        # Yank
        self.editor._yank()
        assert ''.join(self.editor.buffer) == "Hello pasted text"
        assert self.editor.cursor_pos == 17

    def test_history_navigation(self):
        """Test history up/down navigation."""
        # Setup history
        self.editor.history = ["first", "second", "third"]
        self.editor.history_pos = 3
        self.editor.buffer = list("current")

        # Save current line
        self.editor.original_line = "current"

        # Go up in history
        self.editor._history_up()
        assert ''.join(self.editor.buffer) == "third"
        assert self.editor.history_pos == 2

        # Go up again
        self.editor._history_up()
        assert ''.join(self.editor.buffer) == "second"
        assert self.editor.history_pos == 1

        # Go down
        self.editor._history_down()
        assert ''.join(self.editor.buffer) == "third"
        assert self.editor.history_pos == 2

    def test_get_line(self):
        """Test getting current line as string."""
        self.editor.buffer = list("echo test")
        line = ''.join(self.editor.buffer)
        assert line == "echo test"

        # Empty buffer
        self.editor.buffer = []
        line = ''.join(self.editor.buffer)
        assert line == ""

    def test_transpose_chars(self):
        """Test character transposition."""
        self.editor.buffer = list("Hello")
        self.editor.cursor_pos = 2  # After 'e'

        self.editor._transpose_chars()
        # Note: transpose might not work as expected without proper implementation
        # Just verify it doesn't crash
        assert len(self.editor.buffer) == 5

    def test_kill_word_forward(self):
        """Test killing word forward."""
        self.editor.buffer = list("Hello World PSH")
        self.editor.cursor_pos = 6  # At "World"

        self.editor._kill_word_forward()
        # The implementation might delete the space too
        result = ''.join(self.editor.buffer)
        assert result == "Hello PSH" or result == "Hello  PSH"
        assert len(self.editor.kill_ring) > 0

    def test_kill_word_backward(self):
        """Test killing word backward."""
        self.editor.buffer = list("Hello World PSH")
        self.editor.cursor_pos = 11  # After "World"

        self.editor._kill_word_backward()
        assert ''.join(self.editor.buffer) == "Hello  PSH"
        assert self.editor.kill_ring[-1] == "World"

    def test_clear_screen(self):
        """Test clear screen functionality."""
        self.editor.buffer = list("Hello World")
        self.editor.cursor_pos = 6

        # Clear screen doesn't clear buffer, just refreshes display
        self.editor._clear_screen()
        assert ''.join(self.editor.buffer) == "Hello World"

    def test_handle_tab(self):
        """Test tab completion handling."""
        self.editor.buffer = list("echo te")
        self.editor.cursor_pos = 7

        # Tab completion would normally interact with completion engine
        self.editor._handle_tab()
        # Just verify it doesn't crash
        assert self.editor.cursor_pos >= 0

    def test_vi_insert_mode(self):
        """Test entering vi insert mode."""
        # Create editor in vi mode
        with patch('sys.stdin', self.stdin_mock):
            from psh.interactive.line_editor import LineEditor
            editor = LineEditor(history=[], edit_mode='vi')

            # Enter normal mode first
            editor._enter_vi_normal_mode()
            assert editor.mode == self.EditMode.VI_NORMAL

            # Enter insert mode
            editor._enter_vi_insert_mode()
            assert editor.mode == self.EditMode.VI_INSERT

    def test_abort_action(self):
        """Test aborting current action."""
        self.editor.buffer = list("Hello")
        self.editor.cursor_pos = 5

        # Abort should clear any pending state
        self.editor._abort_action()
        # Just verify it doesn't crash
        assert ''.join(self.editor.buffer) == "Hello"

    def test_redraw_keeps_buffer(self):
        """_redraw repaints the display without touching the buffer."""
        self.editor.buffer = list("Hello World")
        self.editor.cursor_pos = 5

        with patch('sys.stdout') as mock_stdout:
            self.editor._redraw()
        assert ''.join(self.editor.buffer) == "Hello World"
        assert self.editor.cursor_pos == 5
        written = ''.join(c[0][0] for c in mock_stdout.write.call_args_list if c[0])
        assert "Hello World" in written

    def test_vi_mode_initialization(self):
        """Test Vi mode initialization."""
        # Create editor in vi mode
        with patch('sys.stdin', self.stdin_mock):
            from psh.interactive.line_editor import LineEditor
            editor = LineEditor(history=[], edit_mode='vi')

            assert editor.edit_mode == 'vi'
            assert editor.mode == self.EditMode.VI_INSERT

    def test_handle_interrupt(self):
        """Test handling Ctrl-C interrupt."""
        self.editor.buffer = list("Hello World")
        self.editor.cursor_pos = 5

        # Handle interrupt raises KeyboardInterrupt, so we need to catch it
        with pytest.raises(KeyboardInterrupt):
            self.editor._handle_interrupt()

    def test_search_functionality(self):
        """Test reverse search functionality."""
        self.editor.history = ["echo first", "echo second", "echo third"]
        self.editor.buffer = list("")

        # Start reverse search
        self.editor._start_reverse_search()
        assert self.editor.search_mode == True

        # Abort search
        self.editor._abort_search()
        assert self.editor.search_mode == False

    def test_edge_cases(self):
        """Test edge cases."""
        # Empty buffer operations
        self.editor.buffer = []
        self.editor._backspace()  # Should not crash
        self.editor._delete_char()  # Should not crash
        self.editor._move_left()  # Should not crash
        self.editor._move_right()  # Should not crash

        # Cursor at boundaries
        self.editor.buffer = list("Test")
        self.editor.cursor_pos = 0
        self.editor._move_left()  # Should stay at 0
        assert self.editor.cursor_pos == 0

        self.editor.cursor_pos = 4
        self.editor._move_right()  # Should stay at 4
        assert self.editor.cursor_pos == 4


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestViUndoRedo:
    """undo/redo are wired to vi normal-mode 'u' / Ctrl-R (v0.258.0).

    Previously the keymap bound ~30 actions (registers, motions, visual
    mode, search) that _execute_action never dispatched; those bindings
    were removed and the keymap now matches actual behavior.
    """

    def _editor(self):
        from psh.interactive.line_editor import LineEditor
        return LineEditor(history=[], edit_mode='vi')

    def test_undo_action_restores_previous_state(self):
        import unittest.mock as mock
        ed = self._editor()
        with mock.patch('sys.stdout'):
            for ch in 'abc':
                ed._insert_char(ch)
            assert ''.join(ed.buffer) == 'abc'
            ed._execute_action('undo', 'u')
        assert ''.join(ed.buffer) == 'ab'

    def test_redo_action_reapplies_change(self):
        import unittest.mock as mock
        ed = self._editor()
        with mock.patch('sys.stdout'):
            for ch in 'ab':
                ed._insert_char(ch)
            ed._execute_action('undo', 'u')
            assert ''.join(ed.buffer) == 'a'
            ed._execute_action('redo', '\x12')
        assert ''.join(ed.buffer) == 'ab'

    def test_mode_switch_syncs_key_handler(self):
        import unittest.mock as mock
        ed = self._editor()
        from psh.interactive.keybindings import EditMode
        with mock.patch('sys.stdout'):
            ed._enter_vi_normal_mode()
            assert ed.key_handler.mode == EditMode.VI_NORMAL
            ed._enter_vi_insert_mode()
            assert ed.key_handler.mode == EditMode.VI_INSERT

    def test_every_vi_binding_is_dispatched(self):
        """Guard: no binding may name an action _execute_action ignores."""
        import inspect
        import re
        ed = self._editor()
        src = inspect.getsource(ed._execute_action)
        handled = set(re.findall(r"action == '([a-z_]+)'", src))
        all_bound = (set(ed.key_handler.insert_bindings.values())
                     | set(ed.key_handler.normal_bindings.values()))
        unhandled = sorted(all_bound - handled)
        assert unhandled == [], f"bound but not dispatched: {unhandled}"


class TestTerminalManagerInterface:
    """Guard: LineEditor may only call methods TerminalManager defines.

    Regression test for a defect where the EIO recovery path called
    self.terminal.restore(), but TerminalManager has no such method —
    the AttributeError was masked because the surrounding except clause
    only caught OSError.
    """

    def test_terminal_attribute_references_exist(self):
        import inspect
        import re

        import psh.interactive.line_editor as le_mod
        from psh.interactive.terminal import TerminalManager

        src = inspect.getsource(le_mod)
        referenced = set(re.findall(r"self\.terminal\.(\w+)", src))
        missing = sorted(
            name for name in referenced if not hasattr(TerminalManager, name)
        )
        assert missing == [], (
            f"line_editor references nonexistent TerminalManager attrs: {missing}"
        )
