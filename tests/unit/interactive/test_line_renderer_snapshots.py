"""Renderer characterization snapshots (Textbook B8, Release 1).

These tests pin the EXACT byte sequences the line editor's rendering
emits for known (prompt, buffer, cursor, terminal-width) states:

- the wrap-boundary commit (``' \\r\\x1b[K'``) that normalizes the
  terminal's pending auto-wrap,
- multi-row paints and redraws,
- relative cursor moves across wrapped rows,
- the resize (SIGWINCH) repaint arithmetic.

They were written against the pre-split ``LineEditor._paint`` /
``_redraw`` / ``_move_cursor_to`` / ``redraw_line`` output and now run
against ``LineRenderer`` with an injected output stream — the renderer
is the ONLY writer of ANSI in the interactive package, and these
snapshots are the contract for that claim.  ``TestEditorWriteFunnel``
additionally pins the editor-level writes that funnel through the
renderer (insert fast path, ``^C``, bell, clear-screen).

Geometry derives from line_layout.py's pure math; the 16 tests in
tests/unit/test_line_layout.py are the map of edge cases pinned here.
"""

import io
import os
from unittest.mock import patch

import pytest

from psh.interactive import line_layout as L
from psh.interactive.line_editor import LineEditor
from psh.interactive.line_renderer import LineRenderer


class Surface:
    """Adapter exposing the rendering operations with captured output.

    Holds a known render state: prompt, buffer text, logical cursor,
    terminal width, plus the screen-tracking state (where the physical
    cursor is believed to be).  Each operation returns everything
    written to the output stream.
    """

    def __init__(self, prompt, text, cursor, width,
                 screen_cursor=None, screen_prompt_len=None):
        self.out = io.StringIO()
        self.renderer = LineRenderer(stream=self.out)
        self.renderer.term_width = width
        self.renderer.screen_prompt_len = (
            L.visible_prompt_length(prompt)
            if screen_prompt_len is None else screen_prompt_len)
        self.renderer.screen_cursor_pos = (
            cursor if screen_cursor is None else screen_cursor)
        self.prompt = prompt
        self.text = text
        self.cursor = cursor

    def _drain(self):
        value = self.out.getvalue()
        self.out.seek(0)
        self.out.truncate()
        return value

    def paint(self, prompt=None):
        self.renderer.paint(self.prompt if prompt is None else prompt,
                            self.text, self.cursor)
        return self._drain()

    def redraw(self, prompt=None):
        self.renderer.redraw(self.prompt if prompt is None else prompt,
                             self.text, self.cursor)
        return self._drain()

    def move_cursor_to(self, pos):
        self.renderer.move_cursor_to(pos)
        return self._drain()

    def resize(self, new_width):
        """Run the SIGWINCH repaint with the terminal reporting *new_width*."""
        size = os.terminal_size((new_width, 24))
        with patch('shutil.get_terminal_size', return_value=size):
            self.renderer.redraw_after_resize(self.prompt, self.text,
                                              self.cursor)
        return self._drain()

    @property
    def screen_cursor_pos(self):
        return self.renderer.screen_cursor_pos

    @property
    def screen_prompt_len(self):
        return self.renderer.screen_prompt_len


class TestPaintSnapshots:
    """_paint: prompt + buffer written from the prompt origin, then the
    physical cursor placed at the logical cursor position."""

    def test_simple_prompt_empty_buffer(self):
        s = Surface("$ ", "", 0, 80)
        assert s.paint() == "$ \r\x1b[2C"

    def test_buffer_cursor_at_end(self):
        s = Surface("PSH$ ", "echo hi", 7, 80)
        assert s.paint() == "PSH$ echo hi\r\x1b[12C"

    def test_cursor_mid_line(self):
        s = Surface("PSH$ ", "echo hi", 2, 80)
        assert s.paint() == "PSH$ echo hi\r\x1b[7C"

    def test_cursor_at_column_zero_emits_bare_cr(self):
        s = Surface("", "ab", 0, 80)
        assert s.paint() == "ab\r"

    def test_wrap_boundary_commit(self):
        # 5 + 75 = 80: content ends exactly at the right margin — the
        # pending auto-wrap is committed with ' \r ESC[K' so the cursor
        # lands deterministically at row 1, column 0.
        s = Surface("PSH$ ", "x" * 75, 75, 80)
        assert s.paint() == "PSH$ " + "x" * 75 + " \r\x1b[K" + "\r"

    def test_wrap_boundary_cursor_on_first_row(self):
        # Same boundary state, cursor back at position 10 (row 0, col 15):
        # commit the wrap, then move up one row and right 15 columns.
        s = Surface("PSH$ ", "x" * 75, 10, 80)
        assert s.paint() == ("PSH$ " + "x" * 75
                             + " \r\x1b[K" + "\x1b[1A\r\x1b[15C")

    def test_two_rows_cursor_at_end(self):
        s = Surface("PSH$ ", "x" * 100, 100, 80)
        assert s.paint() == "PSH$ " + "x" * 100 + "\r\x1b[25C"

    def test_two_rows_cursor_on_first_row(self):
        s = Surface("PSH$ ", "x" * 100, 10, 80)
        assert s.paint() == "PSH$ " + "x" * 100 + "\x1b[1A\r\x1b[15C"

    def test_three_rows_cursor_at_home(self):
        # 5 + 170 = 175 → rows 0..2; cursor at buffer 0 is (0, 5).
        s = Surface("PSH$ ", "x" * 170, 0, 80)
        assert s.paint() == "PSH$ " + "x" * 170 + "\x1b[2A\r\x1b[5C"

    def test_marked_color_prompt_strips_markers_keeps_ansi(self):
        # \x01...\x02 (readline \[ \]) bytes are never written; the
        # color sequences they bracket are; cursor math uses the
        # 4-column visible width ('ok$ ').
        prompt = "\x01\x1b[32m\x02ok\x01\x1b[0m\x02$ "
        s = Surface(prompt, "hi", 2, 80)
        assert s.paint() == "\x1b[32mok\x1b[0m$ hi\r\x1b[6C"

    def test_osc_title_prompt_zero_width(self):
        s = Surface("\x1b]0;t\x07$ ", "", 0, 80)
        assert s.paint() == "\x1b]0;t\x07$ \r\x1b[2C"

    def test_paint_updates_screen_tracking(self):
        s = Surface("PSH$ ", "abc", 2, 80,
                    screen_cursor=0, screen_prompt_len=0)
        s.paint()
        assert s.screen_prompt_len == 5
        assert s.screen_cursor_pos == 2


class TestRedrawSnapshots:
    """_redraw: move from the tracked physical cursor up to the prompt
    origin, clear to end of screen, repaint."""

    def test_single_row(self):
        s = Surface("PSH$ ", "abc", 3, 80)
        assert s.redraw() == "\r\x1b[J" + "PSH$ abc\r\x1b[8C"

    def test_from_wrapped_row_moves_up_first(self):
        # Physical cursor sits on row 1 (5 + 100 = 105 → row 1): one
        # ESC[1A before clearing, then the full two-row paint.
        s = Surface("PSH$ ", "x" * 100, 100, 80)
        assert s.redraw() == ("\x1b[1A\r\x1b[J"
                              + "PSH$ " + "x" * 100 + "\r\x1b[25C")

    def test_override_prompt_for_search(self):
        # Incremental search repaints with its own prompt while the
        # screen state still reflects the original prompt's geometry.
        s = Surface("PSH$ ", "ls -la", 6, 80, screen_prompt_len=5)
        out = s.redraw(prompt="(bck-i-search)`ls': ")
        assert out == "\r\x1b[J" + "(bck-i-search)`ls': ls -la\r\x1b[26C"


class TestMoveCursorSnapshots:
    """_move_cursor_to: pure relative movement, no text rewritten."""

    def test_left_within_row(self):
        s = Surface("PSH$ ", "x" * 20, 20, 80, screen_cursor=10)
        assert s.move_cursor_to(5) == "\r\x1b[10C"
        assert s.screen_cursor_pos == 5

    def test_to_column_zero(self):
        s = Surface("", "abcde", 5, 80, screen_cursor=5)
        assert s.move_cursor_to(0) == "\r"

    def test_up_across_wrapped_row(self):
        s = Surface("PSH$ ", "x" * 100, 100, 80, screen_cursor=100)
        assert s.move_cursor_to(10) == "\x1b[1A\r\x1b[15C"

    def test_down_across_wrapped_row(self):
        s = Surface("PSH$ ", "x" * 100, 100, 80, screen_cursor=10)
        assert s.move_cursor_to(100) == "\x1b[1B\r\x1b[25C"

    def test_same_position_writes_nothing(self):
        s = Surface("PSH$ ", "x" * 20, 20, 80, screen_cursor=7)
        assert s.move_cursor_to(7) == ""
        assert s.screen_cursor_pos == 7

    def test_same_column_different_row_moves_rows_only(self):
        # (0,15) → (1,15): row move only, no CR, no column move.
        s = Surface("PSH$ ", "x" * 100, 100, 80, screen_cursor=10)
        assert s.move_cursor_to(90) == "\x1b[1B"


class TestResizeSnapshots:
    """redraw_line after SIGWINCH: rows-up computed at the NEW width
    (matching the terminal's reflow), then clear + repaint."""

    def test_wider_no_rows_up(self):
        s = Surface("PSH$ ", "x" * 100, 100, 80)
        assert s.resize(120) == ("\r\x1b[J"
                                 + "PSH$ " + "x" * 100 + "\r\x1b[105C")

    def test_narrower_multi_row(self):
        # 105 columns at width 40 → cursor on row 2: up 2, clear, paint.
        s = Surface("PSH$ ", "x" * 100, 100, 80)
        assert s.resize(40) == ("\x1b[2A\r\x1b[J"
                                + "PSH$ " + "x" * 100 + "\r\x1b[25C")

    def test_resize_onto_wrap_boundary(self):
        # 105 % 35 == 0: the repaint at the new width must commit the
        # wrap and leave the cursor at (3, 0).
        s = Surface("PSH$ ", "x" * 100, 100, 80)
        assert s.resize(35) == ("\x1b[3A\r\x1b[J"
                                + "PSH$ " + "x" * 100 + " \r\x1b[K" + "\r")


class TestFunnelledWrites:
    """The writes that used to leak past the paint trio (accept's
    \\r\\n, ^C, the bell, the insert fast path) now have renderer
    methods; pin their exact bytes here."""

    def make(self):
        out = io.StringIO()
        return LineRenderer(stream=out), out

    def test_finish_line(self):
        r, out = self.make()
        r.finish_line()
        assert out.getvalue() == "\r\n"

    def test_show_interrupt(self):
        r, out = self.make()
        r.show_interrupt()
        assert out.getvalue() == "\r\x1b[K^C\r\n"

    def test_bell(self):
        r, out = self.make()
        r.bell()
        assert out.getvalue() == "\a"

    def test_echo_char_tracks_cursor(self):
        r, out = self.make()
        r.screen_cursor_pos = 2
        r.echo_char('c', 3)
        assert out.getvalue() == "c"
        assert r.screen_cursor_pos == 3

    def test_newline_for_completion_listing(self):
        r, out = self.make()
        r.newline()
        assert out.getvalue() == "\r\n"

    def test_display_in_columns_layout(self):
        r, out = self.make()
        size = os.terminal_size((20, 24))
        with patch('shutil.get_terminal_size', return_value=size):
            r.display_in_columns(['bb', 'aa', 'cc'])
        # col_width 4, 5 columns at width 20: one row, trailing newline.
        assert out.getvalue() == "aa  bb  cc  \n"


@pytest.fixture
def editor():
    ed = LineEditor(history=[])
    ed.current_prompt = "PSH$ "
    return ed


def sync_screen(ed, width=80):
    """Make the editor's screen tracking agree with its buffer state."""
    ed.renderer.term_width = width
    ed.renderer.screen_prompt_len = L.visible_prompt_length(ed.current_prompt)
    ed.renderer.screen_cursor_pos = ed.edit_buffer.cursor


def capture(fn, *args):
    out = io.StringIO()
    with patch('sys.stdout', out):
        fn(*args)
    return out.getvalue()


class TestEditorWriteFunnel:
    """Editor-level writes that must produce exactly these sequences
    (post-split, they all funnel through the LineRenderer)."""

    def test_insert_fast_path_echoes_only_the_char(self, editor):
        editor.edit_buffer.chars = list("ab")
        editor.edit_buffer.cursor = 2
        sync_screen(editor)
        assert capture(editor._insert_char, 'c') == "c"
        assert editor.renderer.screen_cursor_pos == 3

    def test_insert_reaching_wrap_boundary_repaints(self, editor):
        # 74 chars + 1 inserted = 75; 5 + 75 = 80 → boundary: the fast
        # path is bypassed and the full repaint commits the wrap.
        editor.edit_buffer.chars = list("x" * 74)
        editor.edit_buffer.cursor = 74
        sync_screen(editor)
        assert capture(editor._insert_char, 'x') == (
            "\r\x1b[J" + "PSH$ " + "x" * 75 + " \r\x1b[K" + "\r")

    def test_mid_line_insert_repaints(self, editor):
        editor.edit_buffer.chars = list("ad")
        editor.edit_buffer.cursor = 1
        sync_screen(editor)
        assert capture(editor._insert_char, 'b') == (
            "\r\x1b[J" + "PSH$ abd\r\x1b[7C")

    def test_ctrl_c_clears_line_and_echoes_caret_c(self, editor):
        out = io.StringIO()
        with patch('sys.stdout', out):
            with pytest.raises(KeyboardInterrupt):
                editor._handle_interrupt()
        assert out.getvalue() == "\r\x1b[K^C\r\n"

    def test_abort_rings_bell(self, editor):
        assert capture(editor._abort_action) == "\a"

    def test_clear_screen_homes_then_repaints(self, editor):
        editor.edit_buffer.chars = list("hi")
        editor.edit_buffer.cursor = 2
        sync_screen(editor)
        assert capture(editor._clear_screen) == (
            "\x1b[2J\x1b[H" + "PSH$ hi\r\x1b[7C")
