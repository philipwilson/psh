"""In-process unit tests for LineEditor buffer operations and the
KeyEvent dispatch policy (escape-sequence PARSING lives in KeyDecoder
since R2 — see test_key_decoder.py for the pipe-fed byte-level tests).

These exercise the editor's pure logic directly — no TTY, no raw mode,
no PTY — following the approach of tests/unit/test_line_editor_unit.py.
Rendering output goes to pytest's captured stdout and is ignored.

NOTE: do NOT replace sys.modules['termios']/'tty' with Mocks here —
importing them needs no TTY, and poisoned modules leak into every later
import in the process. Per-test patch() is fine.
"""

import pytest

from psh.interactive.key_decoder import ESCAPE, Key, KeyDecoder, Meta
from psh.interactive.keybindings import EditMode
from psh.interactive.line_editor import LineEditor


@pytest.fixture
def editor():
    """A fresh emacs-mode editor with an empty history."""
    return LineEditor(history=[])


def set_line(ed, text, cursor=None):
    """Load *text* into the editor buffer with the cursor at *cursor*
    (default: end of line)."""
    ed.edit_buffer.chars = list(text)
    ed.edit_buffer.cursor = len(text) if cursor is None else cursor


def line(ed):
    return ''.join(ed.edit_buffer.chars)


class TestBufferEditing:
    """Insert/delete/kill/yank/transpose at the boundaries."""

    def test_insert_at_end_appends(self, editor):
        set_line(editor, "ech")
        editor._insert_char('o')
        assert line(editor) == "echo"
        assert editor.edit_buffer.cursor == 4

    def test_insert_mid_line(self, editor):
        set_line(editor, "eco", cursor=2)
        editor._insert_char('h')
        assert line(editor) == "echo"
        assert editor.edit_buffer.cursor == 3

    def test_backspace_at_start_is_noop(self, editor):
        set_line(editor, "abc", cursor=0)
        editor._backspace()
        assert line(editor) == "abc"
        assert editor.edit_buffer.cursor == 0

    def test_delete_at_end_is_noop(self, editor):
        set_line(editor, "abc")
        editor._delete_char()
        assert line(editor) == "abc"
        assert editor.edit_buffer.cursor == 3

    def test_kill_line_then_yank_round_trip(self, editor):
        set_line(editor, "echo hello world", cursor=5)
        editor._kill_line()
        assert line(editor) == "echo "
        assert editor.edit_buffer.kill_ring[-1] == "hello world"
        editor._yank()
        assert line(editor) == "echo hello world"
        assert editor.edit_buffer.cursor == 16

    def test_kill_whole_line_then_yank(self, editor):
        set_line(editor, "ls -la", cursor=3)
        editor._kill_whole_line()
        assert line(editor) == ""
        assert editor.edit_buffer.cursor == 0
        assert editor.edit_buffer.kill_ring[-1] == "ls -la"
        editor._yank()
        assert line(editor) == "ls -la"

    def test_kill_to_beginning_preserves_text_after_cursor(self, editor):
        # R14.B: Ctrl-U is unix-line-discard — kill from the cursor back to the
        # start, KEEPING text after the cursor (not kill-whole-line).
        set_line(editor, "ls -la", cursor=3)
        editor._kill_to_beginning()
        assert line(editor) == "-la"
        assert editor.edit_buffer.cursor == 0
        assert editor.edit_buffer.kill_ring[-1] == "ls "

    def test_kill_to_beginning_at_bol_is_noop(self, editor):
        set_line(editor, "abc", cursor=0)
        assert editor.edit_buffer.kill_to_beginning() is False
        assert line(editor) == "abc"

    def test_ctrl_u_is_bound_to_kill_to_beginning(self):
        from psh.interactive.keybindings import EmacsKeyBindings
        kb = EmacsKeyBindings()
        assert kb.bindings[kb.CTRL_U] == 'kill_to_beginning'

    def test_lf_and_cr_both_accept_line_emacs(self):
        # reappraisal #16 H8a: readline accepts on LF (Ctrl-J / a pasted
        # newline) as well as CR, so a multi-line paste is split into
        # commands instead of being merged.
        from psh.interactive.keybindings import EmacsKeyBindings
        kb = EmacsKeyBindings()
        assert kb.bindings['\r'] == 'accept_line'
        assert kb.bindings['\n'] == 'accept_line'

    def test_lf_accepts_line_vi_insert_and_normal(self):
        from psh.interactive.keybindings import ViKeyBindings
        kb = ViKeyBindings()
        assert kb.insert_bindings['\n'] == 'accept_line'
        assert kb.normal_bindings['\n'] == 'accept_line'

    def test_yank_inserts_at_cursor_mid_line(self, editor):
        editor.edit_buffer.kill_ring.append("XY")
        set_line(editor, "abcd", cursor=2)
        editor._yank()
        assert line(editor) == "abXYcd"
        assert editor.edit_buffer.cursor == 4

    def test_transpose_at_end_swaps_last_two(self, editor):
        set_line(editor, "sl")  # cursor at end
        editor._transpose_chars()
        assert line(editor) == "ls"
        assert editor.edit_buffer.cursor == 2

    def test_transpose_mid_line(self, editor):
        # readline: drag the char BEFORE point over the char AT point, advance
        # point. "abcd" with point at 1 -> "bacd", point 2 (bash). (psh used to
        # swap at-point with the next char, giving "acbd".)
        set_line(editor, "abcd", cursor=1)
        editor._transpose_chars()
        assert line(editor) == "bacd"
        assert editor.edit_buffer.cursor == 2

    def test_transpose_at_start_is_noop(self, editor):
        # readline rings the bell at beginning-of-line — no change.
        set_line(editor, "ab", cursor=0)
        editor._transpose_chars()
        assert line(editor) == "ab"
        assert editor.edit_buffer.cursor == 0

    def test_transpose_single_char_is_noop(self, editor):
        set_line(editor, "a", cursor=1)
        editor._transpose_chars()
        assert line(editor) == "a"


class TestWordMovement:
    """word-left / word-right semantics (whitespace-delimited words)."""

    def test_word_forward_skips_word_then_spaces(self, editor):
        set_line(editor, "echo   foo bar", cursor=0)
        editor._move_word_forward()
        assert editor.edit_buffer.cursor == 7  # past "echo" and the run of spaces

    def test_word_forward_at_end_is_noop(self, editor):
        set_line(editor, "echo")
        editor._move_word_forward()
        assert editor.edit_buffer.cursor == 4

    def test_word_backward_skips_spaces_then_word(self, editor):
        set_line(editor, "echo   foo", cursor=7)
        editor._move_word_backward()
        assert editor.edit_buffer.cursor == 0

    def test_word_backward_from_mid_word(self, editor):
        set_line(editor, "echo foo", cursor=7)  # inside "foo"
        editor._move_word_backward()
        assert editor.edit_buffer.cursor == 5  # start of "foo"

    def test_word_backward_at_start_is_noop(self, editor):
        set_line(editor, "echo", cursor=0)
        editor._move_word_backward()
        assert editor.edit_buffer.cursor == 0


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


class TestEscapeEventDispatch:
    """_dispatch_escape_event: the mode-policy layer for KeyDecoder
    events. Sequence PARSING moved to KeyDecoder in R2 (pipe-fed tests
    in test_key_decoder.py); these pin what each event MEANS per mode.
    """

    def test_emacs_up_key_walks_history(self):
        ed = LineEditor(history=['ls -la'])
        ed.history_pos = 1
        ed._dispatch_escape_event(Key('up'))
        assert line(ed) == 'ls -la'

    def test_emacs_delete_key_deletes_at_cursor(self, editor):
        set_line(editor, "abc", cursor=0)
        editor._dispatch_escape_event(Key('delete'))
        assert line(editor) == "bc"

    def test_delete_key_on_empty_line_is_not_eof(self, editor):
        # Ctrl-D on an empty line means EOF; the Delete KEY must not
        # (the action runs with char '\x1b', never '\x04').
        assert editor._dispatch_escape_event(Key('delete')) is None

    def test_unrecognized_sequence_event_is_ignored(self, editor):
        # Key(None): a complete but unrecognized CSI (e.g. Ctrl-Right)
        # was swallowed by the decoder; the editor does nothing.
        set_line(editor, "abc", cursor=1)
        assert editor._dispatch_escape_event(Key(None)) is None
        assert line(editor) == "abc"
        assert editor.edit_buffer.cursor == 1

    def test_emacs_meta_f_moves_word_forward(self, editor):
        set_line(editor, "echo foo", cursor=0)
        editor._dispatch_escape_event(Meta('f'))
        assert editor.edit_buffer.cursor == 5  # past "echo" and the space

    def test_emacs_unbound_meta_is_ignored(self, editor):
        set_line(editor, "abc", cursor=1)
        assert editor._dispatch_escape_event(Meta('z')) is None
        assert line(editor) == "abc"

    def test_vi_bare_escape_enters_normal_mode(self):
        ed = LineEditor(history=[], edit_mode='vi')
        set_line(ed, "ab")
        ed._dispatch_escape_event(ESCAPE)
        assert ed.mode == EditMode.VI_NORMAL
        assert ed.edit_buffer.cursor == 1  # vi moves the cursor back one

    def test_emacs_bare_escape_is_ignored(self, editor):
        # Can only arise in probing mode; emacs has no bare-ESC binding.
        assert editor._dispatch_escape_event(ESCAPE) is None
        assert editor.mode == EditMode.EMACS

    def test_vi_meta_runs_follower_as_normal_mode_command(self):
        # ESC + x in one burst: enter normal mode (cursor backs up one),
        # then 'x' deletes the character under the cursor.
        ed = LineEditor(history=[], edit_mode='vi')
        set_line(ed, "abc")  # cursor at 3
        ed._dispatch_escape_event(Meta('x'))
        assert ed.mode == EditMode.VI_NORMAL
        assert line(ed) == "ab"

    def test_vi_meta_enter_accepts_line(self):
        ed = LineEditor(history=[], edit_mode='vi')
        set_line(ed, "echo hi")
        assert ed._dispatch_escape_event(Meta('\r')) == 'accept'

    def test_vi_meta_escape_hands_second_esc_back_to_decoder(self):
        # ESC ESC: the second ESC may introduce its own sequence, so it
        # goes back to the decoder for full disambiguation.
        ed = LineEditor(history=[], edit_mode='vi')
        ed.decoder = KeyDecoder(-1, esc_timeout=0.01)
        assert ed._dispatch_escape_event(Meta('\x1b')) is None
        assert ed.mode == EditMode.VI_NORMAL
        assert ed.decoder._char_buf == ['\x1b']

    def test_vi_arrow_in_insert_mode_stays_in_insert_mode(self):
        # The v0.283 fix, restated as events: an arrow in vi insert mode
        # is a Key event, never an ESC that flips to normal mode.
        ed = LineEditor(history=['first'], edit_mode='vi')
        ed.history_pos = 1
        ed._dispatch_escape_event(Key('up'))
        assert line(ed) == 'first'
        assert ed.mode == EditMode.VI_INSERT

    def test_escape_event_accepts_active_search(self):
        # In search mode any ESC-introduced event first accepts the
        # search (the pre-decoder fall-through behavior), then acts.
        ed = LineEditor(history=['echo match'])
        ed.history_pos = 1
        ed._start_reverse_search()
        for ch in "match":
            ed._handle_search_char(ch)
        assert ed.search_mode
        ed._dispatch_escape_event(Key('left'))
        assert not ed.search_mode
        assert line(ed) == 'echo match'
