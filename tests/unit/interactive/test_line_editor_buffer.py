"""In-process unit tests for LineEditor buffer operations and the
centralized escape-sequence reader (v0.283 `_read_escape_sequence`).

These exercise the editor's pure logic directly — no TTY, no raw mode,
no PTY — following the approach of tests/unit/test_line_editor_unit.py.
Rendering output goes to pytest's captured stdout and is ignored.

NOTE: do NOT replace sys.modules['termios']/'tty' with Mocks here —
importing them needs no TTY, and poisoned modules leak into every later
import in the process. Per-test patch() is fine.
"""

from unittest.mock import patch

import pytest

from psh.interactive.line_editor import LineEditor


@pytest.fixture
def editor():
    """A fresh emacs-mode editor with an empty history."""
    return LineEditor(history=[])


def set_line(ed, text, cursor=None):
    """Load *text* into the editor buffer with the cursor at *cursor*
    (default: end of line)."""
    ed.buffer = list(text)
    ed.cursor_pos = len(text) if cursor is None else cursor


def line(ed):
    return ''.join(ed.buffer)


class TestBufferEditing:
    """Insert/delete/kill/yank/transpose at the boundaries."""

    def test_insert_at_end_appends(self, editor):
        set_line(editor, "ech")
        editor._insert_char('o')
        assert line(editor) == "echo"
        assert editor.cursor_pos == 4

    def test_insert_mid_line(self, editor):
        set_line(editor, "eco", cursor=2)
        editor._insert_char('h')
        assert line(editor) == "echo"
        assert editor.cursor_pos == 3

    def test_backspace_at_start_is_noop(self, editor):
        set_line(editor, "abc", cursor=0)
        editor._backspace()
        assert line(editor) == "abc"
        assert editor.cursor_pos == 0

    def test_delete_at_end_is_noop(self, editor):
        set_line(editor, "abc")
        editor._delete_char()
        assert line(editor) == "abc"
        assert editor.cursor_pos == 3

    def test_kill_line_then_yank_round_trip(self, editor):
        set_line(editor, "echo hello world", cursor=5)
        editor._kill_line()
        assert line(editor) == "echo "
        assert editor.kill_ring[-1] == "hello world"
        editor._yank()
        assert line(editor) == "echo hello world"
        assert editor.cursor_pos == 16

    def test_kill_whole_line_then_yank(self, editor):
        set_line(editor, "ls -la", cursor=3)
        editor._kill_whole_line()
        assert line(editor) == ""
        assert editor.cursor_pos == 0
        assert editor.kill_ring[-1] == "ls -la"
        editor._yank()
        assert line(editor) == "ls -la"

    def test_yank_inserts_at_cursor_mid_line(self, editor):
        editor.kill_ring.append("XY")
        set_line(editor, "abcd", cursor=2)
        editor._yank()
        assert line(editor) == "abXYcd"
        assert editor.cursor_pos == 4

    def test_transpose_at_end_swaps_last_two(self, editor):
        set_line(editor, "sl")  # cursor at end
        editor._transpose_chars()
        assert line(editor) == "ls"
        assert editor.cursor_pos == 2

    def test_transpose_mid_line(self, editor):
        set_line(editor, "abcd", cursor=1)
        editor._transpose_chars()
        assert line(editor) == "acbd"
        assert editor.cursor_pos == 3

    def test_transpose_at_start(self, editor):
        set_line(editor, "ab", cursor=0)
        editor._transpose_chars()
        assert line(editor) == "ba"
        assert editor.cursor_pos == 1

    def test_transpose_single_char_is_noop(self, editor):
        set_line(editor, "a", cursor=1)
        editor._transpose_chars()
        assert line(editor) == "a"


class TestWordMovement:
    """word-left / word-right semantics (whitespace-delimited words)."""

    def test_word_forward_skips_word_then_spaces(self, editor):
        set_line(editor, "echo   foo bar", cursor=0)
        editor._move_word_forward()
        assert editor.cursor_pos == 7  # past "echo" and the run of spaces

    def test_word_forward_at_end_is_noop(self, editor):
        set_line(editor, "echo")
        editor._move_word_forward()
        assert editor.cursor_pos == 4

    def test_word_backward_skips_spaces_then_word(self, editor):
        set_line(editor, "echo   foo", cursor=7)
        editor._move_word_backward()
        assert editor.cursor_pos == 0

    def test_word_backward_from_mid_word(self, editor):
        set_line(editor, "echo foo", cursor=7)  # inside "foo"
        editor._move_word_backward()
        assert editor.cursor_pos == 5  # start of "foo"

    def test_word_backward_at_start_is_noop(self, editor):
        set_line(editor, "echo", cursor=0)
        editor._move_word_backward()
        assert editor.cursor_pos == 0


class TestHistoryNavigation:
    """History browsing preserves the in-progress line."""

    def test_up_then_down_restores_current_line(self):
        ed = LineEditor(history=['first', 'second'])
        ed.history_pos = 2
        set_line(ed, "typed but not run")
        ed._history_up()
        assert line(ed) == "second"
        ed._history_up()
        assert line(ed) == "first"
        ed._history_down()
        assert line(ed) == "second"
        ed._history_down()
        assert line(ed) == "typed but not run"
        assert ed.history_pos == 2

    def test_up_stops_at_oldest_entry(self):
        ed = LineEditor(history=['only'])
        ed.history_pos = 1
        ed._history_up()
        ed._history_up()  # extra Up must not underflow
        assert ed.history_pos == 0
        assert line(ed) == "only"

    def test_history_first_and_last(self):
        ed = LineEditor(history=['a', 'b', 'c'])
        ed.history_pos = 3
        set_line(ed, "wip")
        ed._history_first()
        assert line(ed) == "a"
        assert ed.history_pos == 0
        ed._history_last()
        assert line(ed) == "wip"
        assert ed.history_pos == 3

    def test_down_at_bottom_is_noop(self):
        ed = LineEditor(history=['x'])
        ed.history_pos = 1
        set_line(ed, "wip")
        ed._history_down()
        assert line(ed) == "wip"
        assert ed.history_pos == 1


class TestUndoRedo:
    def test_undo_redo_round_trip(self, editor):
        for ch in "abc":
            editor._insert_char(ch)
        assert line(editor) == "abc"
        editor.undo()
        assert line(editor) == "ab"
        editor.undo()
        assert line(editor) == "a"
        editor.redo()
        assert line(editor) == "ab"
        editor.redo()
        assert line(editor) == "abc"

    def test_divergent_edits_clear_redo_stack(self, editor):
        for ch in "ab":
            editor._insert_char(ch)
        editor.undo()
        assert line(editor) == "a"
        # Diverge from the undone branch. save_undo_state() dedupes the
        # pre-edit snapshot, so the redo stack is cleared on the first
        # edit that actually pushes a new state (the second keystroke).
        editor._insert_char('X')
        editor._insert_char('Y')
        assert line(editor) == "aXY"
        editor.redo()  # nothing to redo any more
        assert line(editor) == "aXY"


def feed(ed, chars):
    """Queue *chars* as pending decoded input.  _read_char() pops from
    _char_buf before touching the fd; patching os.read to return b''
    makes exhaustion look like EOF instead of reading fd -1."""
    ed._char_buf = list(chars)


class TestEscapeSequenceReader:
    """_read_escape_sequence: the single input-side ANSI parser."""

    @pytest.fixture(autouse=True)
    def no_fd_reads(self):
        with patch('psh.interactive.line_editor.os.read', return_value=b''):
            yield

    @pytest.mark.parametrize("final,key", [
        ('A', 'up'), ('B', 'down'), ('C', 'right'), ('D', 'left'),
        ('H', 'home'), ('F', 'end'),
    ])
    def test_csi_final_keys(self, editor, final, key):
        feed(editor, final)
        assert editor._read_escape_sequence('[') == key

    @pytest.mark.parametrize("params,key", [
        ('1~', 'home'), ('3~', 'delete'), ('4~', 'end'),
        ('7~', 'home'), ('8~', 'end'),
    ])
    def test_csi_tilde_keys(self, editor, params, key):
        feed(editor, params)
        assert editor._read_escape_sequence('[') == key

    @pytest.mark.parametrize("final,key", [
        ('A', 'up'), ('B', 'down'), ('C', 'right'), ('D', 'left'),
        ('H', 'home'), ('F', 'end'),
    ])
    def test_ss3_keys(self, editor, final, key):
        feed(editor, final)
        assert editor._read_escape_sequence('O') == key

    def test_unrecognized_csi_consumed_in_full(self, editor):
        # Ctrl-Right (xterm modifier form): unknown, but must be fully
        # consumed so 'C' never leaks into the edit buffer.
        feed(editor, '1;5C')
        assert editor._read_escape_sequence('[') is None
        assert editor._char_buf == []

    def test_eof_mid_sequence_returns_none(self, editor):
        feed(editor, '1;')  # stream ends before the final byte
        assert editor._read_escape_sequence('[') is None

    def test_emacs_arrow_maps_to_history_action(self, editor):
        feed(editor, '[A')
        assert editor._get_key_action('\x1b') == 'previous_history'

    def test_emacs_delete_csi_tilde(self, editor):
        feed(editor, '[3~')
        assert editor._get_key_action('\x1b') == 'delete_char'

    def test_emacs_meta_key(self, editor):
        feed(editor, 'f')
        assert editor._get_key_action('\x1b') == 'move_word_forward'

    def test_vi_bare_esc_enters_normal_mode(self):
        ed = LineEditor(history=[], edit_mode='vi')
        # No pending input: this is a human ESC keypress, not a sequence.
        with patch.object(ed, '_input_pending', return_value=False):
            assert ed._get_key_action('\x1b') == 'enter_normal_mode'

    def test_vi_arrow_uses_shared_escape_actions(self):
        ed = LineEditor(history=[], edit_mode='vi')
        feed(ed, '[B')
        with patch.object(ed, '_input_pending', return_value=True), \
             patch('psh.interactive.line_editor.os.read', return_value=b''):
            assert ed._get_key_action('\x1b') == 'next_history'

    def test_vi_esc_plus_key_requeues_key(self):
        ed = LineEditor(history=[], edit_mode='vi')
        feed(ed, 'x')
        with patch.object(ed, '_input_pending', return_value=True):
            assert ed._get_key_action('\x1b') == 'enter_normal_mode'
        # The follower must be requeued for normal-mode dispatch.
        assert ed._char_buf == ['x']
