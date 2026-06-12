"""Terminal rendering for the line editor: the ONLY writer of ANSI.

LineRenderer owns everything the line editor sends to the terminal —
the wrap-aware paint/redraw/cursor-move trio, the SIGWINCH repaint, the
insert fast path, accept/interrupt/bell output, and the completion
column display. No other module in psh/interactive writes escape
sequences for line editing (Textbook B8, Release 1); the snapshot suite
in tests/unit/interactive/test_line_renderer_snapshots.py pins the
exact byte sequences this class emits.

It holds the SCREEN state only: the terminal width and where the
physical cursor is believed to be (as a buffer position + prompt
width). The line being edited lives in EditBuffer; callers pass the
current (prompt, text, cursor) into each paint. All geometry is pure
math from line_layout.py.

The output stream is injectable for testing; when none is given,
writes resolve sys.stdout dynamically so that test code patching
sys.stdout still captures them.
"""

import shutil
import sys
from typing import IO, List, Optional

from . import line_layout as L


class LineRenderer:
    """Wrap-aware renderer for a prompt + single logical line."""

    def __init__(self, stream: Optional[IO[str]] = None) -> None:
        self._stream = stream
        self.term_width: int = 80
        # Physical-cursor tracking: the buffer position and prompt
        # width the on-screen cursor corresponds to.
        self.screen_cursor_pos: int = 0
        self.screen_prompt_len: int = 0

    @property
    def _out(self) -> IO[str]:
        return self._stream if self._stream is not None else sys.stdout

    @property
    def _width(self) -> int:
        return self.term_width if self.term_width > 0 else 80

    def update_width(self) -> None:
        """Refresh the cached terminal width (start of each read)."""
        try:
            self.term_width = shutil.get_terminal_size().columns
        except (OSError, ValueError):
            self.term_width = 80

    # ------------------------------------------------------------------
    # The wrap-aware paint / redraw / move trio
    # ------------------------------------------------------------------

    def paint(self, prompt: str, text: str, cursor: int) -> None:
        """Write prompt + text starting at the CURRENT cursor location
        (assumed to be the prompt origin: its first row, column 0),
        then place the physical cursor at buffer position *cursor*.

        Wrap-aware: when the content ends exactly at the right margin
        the auto-wrap is committed (space + CR + erase) so the cursor's
        position stays deterministic for later relative moves.
        """
        out = self._out
        w = self._width
        plen = L.visible_prompt_length(prompt)

        out.write(L.displayable_prompt(prompt))
        out.write(text)

        blen = len(text)
        if L.at_row_boundary(plen, blen, w):
            # Commit the pending wrap deterministically
            out.write(' \r\033[K')

        end_row, _ = L.position(plen, blen, w)
        cur_row, cur_col = L.position(plen, cursor, w)
        if end_row > cur_row:
            out.write(f'\033[{end_row - cur_row}A')
        out.write('\r')
        if cur_col > 0:
            out.write(f'\033[{cur_col}C')

        self.screen_prompt_len = plen
        self.screen_cursor_pos = cursor
        out.flush()

    def redraw(self, prompt: str, text: str, cursor: int) -> None:
        """THE central wrap-aware repaint.

        Moves from wherever the physical cursor is (tracked via
        screen_cursor_pos/screen_prompt_len) up to the prompt origin,
        clears to end of screen, and repaints. Every mutating edit
        operation funnels through here; pure cursor movement uses
        move_cursor_to.
        """
        out = self._out
        rows_up, _ = L.position(self.screen_prompt_len,
                                self.screen_cursor_pos, self._width)
        if rows_up > 0:
            out.write(f'\033[{rows_up}A')
        out.write('\r\033[J')
        self.paint(prompt, text, cursor)

    def move_cursor_to(self, pos: int) -> None:
        """Move the physical cursor to buffer position *pos* without
        rewriting any text (wrap-aware relative movement)."""
        out = self._out
        w = self._width
        plen = self.screen_prompt_len
        from_row, from_col = L.position(plen, self.screen_cursor_pos, w)
        to_row, to_col = L.position(plen, pos, w)
        if to_row < from_row:
            out.write(f'\033[{from_row - to_row}A')
        elif to_row > from_row:
            out.write(f'\033[{to_row - from_row}B')
        if to_col != from_col:
            out.write('\r')
            if to_col > 0:
                out.write(f'\033[{to_col}C')
        self.screen_cursor_pos = pos
        out.flush()

    def redraw_after_resize(self, prompt: str, text: str,
                            cursor: int) -> None:
        """Redraw the prompt and input line in place after a terminal
        resize (SIGWINCH).

        After a resize the terminal has already reflowed all content at
        the new width, so saved absolute row positions are stale.
        Instead we compute how many rows the prompt+input spans at the
        **new** width (which matches the reflow) and move up by that
        amount from wherever the cursor currently sits. This avoids
        clearing previously-output command results that the terminal
        correctly reflowed.
        """
        out = self._out
        prompt_len = L.visible_prompt_length(prompt)

        try:
            new_width = shutil.get_terminal_size().columns
        except (OSError, ValueError):
            new_width = 80

        # After reflow the terminal has repositioned the cursor at the
        # correct content offset. The number of rows from the prompt
        # start to the cursor matches the new width layout.
        if new_width > 0:
            rows_up = (prompt_len + cursor) // new_width
        else:
            rows_up = 0

        if rows_up > 0:
            out.write(f'\033[{rows_up}A')

        # Move to column 0, clear to end of screen, repaint (wrap-aware)
        out.write('\r\033[J')
        self.term_width = new_width
        self.paint(prompt, text, cursor)

    # ------------------------------------------------------------------
    # The insert fast path
    # ------------------------------------------------------------------

    def at_wrap_boundary(self, content_len: int) -> bool:
        """True when prompt + *content_len* ends exactly at the right
        margin — appending must repaint to commit the wrap."""
        return L.at_row_boundary(self.screen_prompt_len, content_len,
                                 self._width)

    def echo_char(self, char: str, cursor: int) -> None:
        """Fast path for appending before the right margin: echo the
        character and track the cursor — no repaint needed."""
        out = self._out
        out.write(char)
        self.screen_cursor_pos = cursor
        out.flush()

    # ------------------------------------------------------------------
    # Line-completion and notification output
    # ------------------------------------------------------------------

    def finish_line(self) -> None:
        """Leave the edited line on screen and move below it
        (accept-line and EOF)."""
        out = self._out
        out.write('\r\n')
        out.flush()

    def show_interrupt(self) -> None:
        """Clear the line and echo ^C (Ctrl-C)."""
        out = self._out
        out.write('\r')
        out.write('\033[K')
        out.write('^C\r\n')
        out.flush()

    def bell(self) -> None:
        """Audible bell (aborts, failed completion)."""
        out = self._out
        out.write('\a')
        out.flush()

    def clear_screen(self, prompt: str, text: str, cursor: int) -> None:
        """Clear the screen, home the cursor, repaint (Ctrl-L)."""
        self._out.write('\033[2J\033[H')
        self.paint(prompt, text, cursor)

    # ------------------------------------------------------------------
    # Completion column display
    # ------------------------------------------------------------------

    def newline(self) -> None:
        """Move to a fresh line (around the completion listing). No
        flush: the listing or repaint that follows flushes."""
        self._out.write('\r\n')

    def display_in_columns(self, items: List[str]) -> None:
        """Display completion candidates in columns (cooked mode)."""
        if not items:
            return
        out = self._out

        try:
            term_width = shutil.get_terminal_size().columns
        except (OSError, ValueError):
            term_width = 80

        # Calculate column width (add 2 for spacing)
        max_len = max(len(item) for item in items)
        col_width = max_len + 2

        # Calculate number of columns
        num_cols = max(1, term_width // col_width)

        # Display items
        for i, item in enumerate(sorted(items)):
            out.write(item.ljust(col_width))
            if (i + 1) % num_cols == 0:
                out.write('\n')

        if len(items) % num_cols != 0:
            out.write('\n')

        out.flush()
