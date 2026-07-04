"""Kill-ring coalescing and meta word boundaries (reappraisal #17 M4/M5).

Pinned to bash 5.2/readline via PTY truth tables
(tmp/probes-r17t2-interactive/probe_killring_words2.py):

- Consecutive kills merge into ONE ring entry: forward kills (C-k, M-d)
  APPEND to the top entry, backward kills (C-w, C-u, M-DEL) PREPEND —
  so `echo alpha beta` + C-w C-w C-y restores `alpha beta`.
- Any non-kill command (movement, typing, yank) breaks the chain.
- readline coalesces in emacs mode only, never in vi mode.
- The meta word commands (M-f/M-b/M-d/M-DEL) use ALNUM word boundaries
  (`aa.bb` is two words; accented letters stay in-word), while C-w
  (unix-word-rubout) stays whitespace-based.
"""

import pytest

from psh.interactive.edit_buffer import EditBuffer
from psh.interactive.line_editor import LineEditor


@pytest.fixture
def editor():
    return LineEditor(history=[])


def load(editor, text, cursor=None):
    editor.edit_buffer.chars = list(text)
    editor.edit_buffer.cursor = len(text) if cursor is None else cursor


def act(editor, *actions):
    for action in actions:
        editor._execute_action(action, '')


class TestKillRingCoalescing:
    """Consecutive kills merge into one yankable entry (emacs mode)."""

    def test_two_backward_kills_prepend(self, editor):
        # bash: 'echo alpha beta' C-w C-w C-y -> 'echo alpha beta'
        load(editor, "echo alpha beta")
        act(editor, 'kill_word_backward', 'kill_word_backward')
        assert editor.edit_buffer.kill_ring == ["alpha beta"]
        act(editor, 'yank')
        assert editor.edit_buffer.text == "echo alpha beta"

    def test_three_backward_kills(self, editor):
        load(editor, "echo aa bb cc")
        act(editor, 'kill_word_backward', 'kill_word_backward',
            'kill_word_backward')
        assert editor.edit_buffer.kill_ring == ["aa bb cc"]

    def test_two_forward_kills_append(self, editor):
        # bash: point after 'echo': M-d M-d kills ' aa' then ' bb',
        # appended -> one entry ' aa bb'
        load(editor, "echo aa bb cc", cursor=4)
        act(editor, 'kill_word', 'kill_word')
        assert editor.edit_buffer.kill_ring == [" aa bb"]
        assert editor.edit_buffer.text == "echo cc"

    def test_mixed_directions_ck_then_cw(self, editor):
        # bash: 'echo ab cd', point before 'cd': C-k kills 'cd',
        # C-w prepends 'ab ' -> 'ab cd'
        load(editor, "echo ab cd", cursor=8)
        act(editor, 'kill_line', 'kill_word_backward')
        assert editor.edit_buffer.kill_ring == ["ab cd"]

    def test_cw_then_cu_coalesce_backward(self, editor):
        load(editor, "echo one two")
        act(editor, 'kill_word_backward', 'kill_to_beginning')
        assert editor.edit_buffer.kill_ring == ["echo one two"]

    def test_movement_breaks_chain(self, editor):
        load(editor, "echo one two")
        act(editor, 'kill_word_backward', 'move_beginning_of_line',
            'move_end_of_line', 'kill_word_backward')
        assert editor.edit_buffer.kill_ring == ["two", "one "]

    def test_typing_breaks_chain(self, editor):
        load(editor, "echo one two")
        act(editor, 'kill_word_backward')
        editor._dispatch_char('x')
        act(editor, 'backward_delete_char', 'kill_word_backward')
        assert editor.edit_buffer.kill_ring == ["two", "one "]

    def test_yank_breaks_chain(self, editor):
        # bash: C-w, C-y, C-w C-w -> the post-yank kills start a NEW
        # entry ('two' again), then coalesce ('one two').
        load(editor, "echo one two")
        act(editor, 'kill_word_backward', 'yank',
            'kill_word_backward', 'kill_word_backward')
        assert editor.edit_buffer.kill_ring == ["two", "one two"]
        act(editor, 'yank')
        assert editor.edit_buffer.text == "echo one two"

    def test_no_coalescing_in_vi_mode(self, editor):
        # readline: _rl_last_command_was_kill only applies outside vi mode
        editor.set_edit_mode('vi')
        load(editor, "echo alpha beta")
        act(editor, 'kill_word_backward', 'kill_word_backward')
        assert editor.edit_buffer.kill_ring == ["beta", "alpha "]

    def test_fresh_read_line_breaks_chain(self, editor):
        load(editor, "echo one two")
        act(editor, 'kill_word_backward')
        # read_line resets the chain; simulate its state reset
        editor._last_action_was_kill = False
        load(editor, "echo x y")
        act(editor, 'kill_word_backward')
        assert editor.edit_buffer.kill_ring == ["two", "y"]


class TestPushKillPrimitive:
    """EditBuffer._push_kill direction semantics (direct unit level)."""

    def test_default_no_coalescing(self):
        buf = EditBuffer()
        buf.chars = list("one two")
        buf.cursor = 7
        buf.kill_word_backward()
        buf.kill_word_backward()
        assert buf.kill_ring == ["two", "one "]

    def test_forward_appends_when_armed(self):
        buf = EditBuffer()
        buf.kill_ring = ["AA"]
        buf.chars = list("bb")
        buf.cursor = 0
        buf.coalesce_next_kill = True
        buf.kill_to_end()
        assert buf.kill_ring == ["AAbb"]

    def test_backward_prepends_when_armed(self):
        buf = EditBuffer()
        buf.kill_ring = ["BB"]
        buf.chars = list("aa")
        buf.cursor = 2
        buf.coalesce_next_kill = True
        buf.kill_to_beginning()
        assert buf.kill_ring == ["aaBB"]

    def test_armed_but_empty_ring_pushes(self):
        buf = EditBuffer()
        buf.chars = list("aa")
        buf.cursor = 2
        buf.coalesce_next_kill = True
        buf.kill_to_beginning()
        assert buf.kill_ring == ["aa"]


class TestAlnumWordBoundaries:
    """M-f/M-b/M-d/M-DEL word rules (readline alnum; bash-pinned)."""

    def test_backward_kill_word_stops_at_dot(self):
        # bash: 'echo aa.bb' M-DEL kills just 'bb'
        buf = EditBuffer()
        buf.chars = list("echo aa.bb")
        buf.cursor = 10
        assert buf.backward_kill_word()
        assert buf.text == "echo aa."
        assert buf.kill_ring == ["bb"]

    def test_backward_kill_word_twice_coalesced(self):
        # bash: M-DEL M-DEL C-y restores 'aa.bb'
        buf = EditBuffer()
        buf.chars = list("echo aa.bb")
        buf.cursor = 10
        buf.backward_kill_word()
        buf.coalesce_next_kill = True
        buf.backward_kill_word()
        assert buf.text == "echo "
        assert buf.kill_ring == ["aa.bb"]

    def test_backward_kill_word_spans_space(self):
        # bash: 'echo aa.bb cc' M-DEL M-DEL kills 'cc' then 'bb ' -> 'bb cc'
        buf = EditBuffer()
        buf.chars = list("echo aa.bb cc")
        buf.cursor = 13
        buf.backward_kill_word()
        assert buf.kill_ring == ["cc"]
        buf.coalesce_next_kill = True
        buf.backward_kill_word()
        assert buf.text == "echo aa."
        assert buf.kill_ring == ["bb cc"]

    def test_forward_word_lands_at_word_end(self):
        # bash: 'echo aa.bb cc' from 0: M-f -> 4, M-f -> 7 (end of 'aa'),
        # M-f -> 10 (end of 'bb')
        buf = EditBuffer()
        buf.chars = list("echo aa.bb cc")
        buf.cursor = 0
        assert buf.forward_word()
        assert buf.cursor == 4
        assert buf.forward_word()
        assert buf.cursor == 7
        assert buf.forward_word()
        assert buf.cursor == 10

    def test_backward_word_lands_at_word_start(self):
        # bash: from end, M-b -> before 'cc' (11), M-b -> before 'bb' (8)
        buf = EditBuffer()
        buf.chars = list("echo aa.bb cc")
        buf.cursor = 13
        assert buf.backward_word()
        assert buf.cursor == 11
        assert buf.backward_word()
        assert buf.cursor == 8

    def test_kill_word_takes_separator_and_word(self):
        # bash: 'echo zz aa.bb', point after 'echo': M-d kills ' zz'
        buf = EditBuffer()
        buf.chars = list("echo zz aa.bb")
        buf.cursor = 4
        assert buf.kill_word()
        assert buf.text == "echo aa.bb"
        assert buf.kill_ring == [" zz"]

    def test_utf8_accents_stay_in_word(self):
        # bash: 'echo café.naïve' M-DEL kills 'naïve' only
        buf = EditBuffer()
        buf.chars = list("echo café.naïve")
        buf.cursor = len(buf.chars)
        buf.backward_kill_word()
        assert buf.text == "echo café."
        assert buf.kill_ring == ["naïve"]

    def test_ctrl_w_stays_whitespace_based(self):
        # C-w (unix-word-rubout) on 'echo aa.bb' kills all of 'aa.bb'
        buf = EditBuffer()
        buf.chars = list("echo aa.bb")
        buf.cursor = 10
        buf.kill_word_backward()
        assert buf.text == "echo "
        assert buf.kill_ring == ["aa.bb"]

    def test_no_op_at_boundaries(self):
        buf = EditBuffer()
        buf.chars = list("ab")
        buf.cursor = 0
        assert not buf.backward_word()
        assert not buf.backward_kill_word()
        buf.cursor = 2
        assert not buf.forward_word()
        assert not buf.kill_word()
        assert buf.kill_ring == []

    def test_editor_meta_bindings_use_alnum_actions(self, editor):
        # The emacs meta map must route b/f/d/DEL to the alnum variants
        # (C-w stays on the whitespace kill).
        meta = editor.key_handler.meta_bindings
        assert meta['b'] == 'backward_word'
        assert meta['f'] == 'forward_word'
        assert meta['d'] == 'kill_word'
        assert meta['\x7f'] == 'backward_kill_word'
        assert editor.key_handler.bindings['\x17'] == 'kill_word_backward'
