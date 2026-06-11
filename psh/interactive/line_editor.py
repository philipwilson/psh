#!/usr/bin/env python3
"""Enhanced line editor with vi/emacs key bindings and history search."""

import os
import select
import shutil
import sys
import termios
from typing import Callable, List, Optional

from . import line_layout as L
from .keybindings import EditMode, EmacsKeyBindings, ViKeyBindings
from .line_editor_helpers import convert_multiline_to_single
from .tab_completion import CompletionEngine, TerminalManager


class LineEditor:
    """Interactive line editor with vi/emacs key bindings, tab completion, and history search."""

    # Actions for the symbolic keys produced by _read_escape_sequence.
    # Shared by emacs mode and BOTH vi modes (bash vi-mode behaves the
    # same: arrows move the cursor / walk history in insert and normal
    # mode alike).
    ESCAPE_KEY_ACTIONS = {
        'up': 'previous_history',
        'down': 'next_history',
        'right': 'move_forward_char',
        'left': 'move_backward_char',
        'home': 'move_beginning_of_line',
        'end': 'move_end_of_line',
        'delete': 'delete_char',
    }

    # CSI final bytes with no parameters: ESC [ X
    _CSI_FINAL_KEYS = {
        'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left',
        'H': 'home', 'F': 'end',
    }
    # CSI tilde sequences: ESC [ params ~
    _CSI_TILDE_KEYS = {
        '1': 'home', '3': 'delete', '4': 'end', '7': 'home', '8': 'end',
    }
    # SS3 sequences (application cursor mode): ESC O X
    _SS3_KEYS = {
        'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left',
        'H': 'home', 'F': 'end',
    }

    def __init__(self, history: Optional[List[str]] = None, edit_mode: str = 'emacs'):
        self.buffer = []
        self.cursor_pos = 0
        self.history = history or []
        self.history_pos = len(self.history)
        self.completion_engine = CompletionEngine()
        self.terminal = TerminalManager()
        self.original_line = ""
        self.completion_state = None
        self.current_prompt = ""

        # Key binding setup
        self.edit_mode = ''
        self.set_edit_mode(edit_mode)

        # Kill ring for cut/paste operations
        self.kill_ring = []

        # Search state
        self.search_mode = False
        self.search_pattern = ""
        self.search_direction = 1  # 1 for forward, -1 for backward
        self.search_start_pos = 0

        # Vi specific state
        self.vi_repeat_count = ""

        # Undo/redo support
        self.undo_stack = []
        self.redo_stack = []
        self.save_undo_state()

        # Raw fd reading state — bypasses Python's BufferedReader so that
        # select() and reads stay in sync (see _read_char).
        self._stdin_fd = -1
        self._char_buf: List[str] = []

        # Physical-cursor tracking for wrap-aware rendering: the buffer
        # position and prompt width the on-screen cursor corresponds to.
        self._screen_cursor_pos = 0
        self._screen_prompt_len = 0
        self._term_width = 80

    def set_edit_mode(self, edit_mode: str) -> None:
        """Select 'vi' or 'emacs' key bindings.

        Called between reads so that ``set -o vi`` / ``set -o emacs``
        issued mid-session takes effect at the next prompt (previously
        the mode was frozen at REPL startup).
        """
        edit_mode = edit_mode.lower()
        if edit_mode == self.edit_mode:
            return
        self.edit_mode = edit_mode
        if edit_mode == 'vi':
            self.key_handler = ViKeyBindings()
            self.mode = EditMode.VI_INSERT
        else:
            self.key_handler = EmacsKeyBindings()
            self.mode = EditMode.EMACS

    def _read_char(self) -> str:
        """Read one character from stdin via the raw file descriptor.

        Uses os.read() instead of sys.stdin.read(1) to bypass Python's
        internal BufferedReader.  When text is pasted, BufferedReader
        consumes all available bytes from the fd into its buffer but
        returns only one character, making the rest invisible to
        select().  By reading the raw fd ourselves and buffering decoded
        characters in _char_buf, select() and reads stay in sync.
        """
        if self._char_buf:
            return self._char_buf.pop(0)

        data = os.read(self._stdin_fd, 4096)
        if not data:
            return ''

        chars = data.decode('utf-8', errors='replace')
        if len(chars) > 1:
            self._char_buf.extend(chars[1:])
        return chars[0] if chars else ''

    def read_line(self, prompt: str = "", sigwinch_fd: int = -1,
                   sigwinch_drain: Optional[Callable[[], bool]] = None,
                   on_resize: Optional[Callable[[], None]] = None) -> Optional[str]:
        """Read a line with editing and key binding support.

        Args:
            prompt: The prompt string to display
            sigwinch_fd: File descriptor for SIGWINCH notifications (-1 to disable)
            sigwinch_drain: Callback to drain SIGWINCH notifications (returns True if any)
            on_resize: Optional callback invoked after a terminal resize redraw
        """
        self.buffer = []
        self.cursor_pos = 0
        self.history_pos = len(self.history)
        self.original_line = ""
        self.completion_state = None
        self.current_prompt = prompt
        self.search_mode = False
        try:
            self._term_width = shutil.get_terminal_size().columns
        except (OSError, ValueError):
            self._term_width = 80

        # Paint the prompt (wrap-aware; strips \x01/\x02 markers)
        self._paint()

        # Reset vi mode to insert
        if self.edit_mode == 'vi':
            self.mode = EditMode.VI_INSERT
            if hasattr(self.key_handler, 'mode'):
                self.key_handler.mode = EditMode.VI_INSERT
            self.vi_repeat_count = ""

        # Build list of fds to monitor
        stdin_fd = sys.stdin.fileno()
        self._stdin_fd = stdin_fd
        self._char_buf = []
        watch_fds = [stdin_fd]
        if sigwinch_fd >= 0:
            watch_fds.append(sigwinch_fd)

        with self.terminal:
            while True:
                try:
                    # Only call select() when our character buffer is empty.
                    # Python's BufferedReader may consume multiple bytes from
                    # the fd on a single sys.stdin.read(1) call, making them
                    # invisible to select().  By reading via os.read() into
                    # our own buffer we keep select() and reads in sync.
                    if sigwinch_fd >= 0 and not self._char_buf:
                        readable, _, _ = select.select(watch_fds, [], [])

                        # Check for resize notification
                        if sigwinch_fd in readable:
                            if sigwinch_drain:
                                sigwinch_drain()
                            self.redraw_line()
                            if on_resize:
                                on_resize()
                            # Don't continue - also check if stdin is readable
                            if stdin_fd not in readable:
                                continue

                    char = self._read_char()
                except OSError as e:
                    # Handle I/O errors (e.g., terminal disconnected)
                    if e.errno == 5:  # EIO
                        # Try to restore terminal before failing.
                        # tcsetattr on a disconnected terminal raises
                        # termios.error (not an OSError subclass).
                        try:
                            self.terminal.exit_raw_mode()
                        except (termios.error, OSError):
                            pass
                    raise  # Re-raise the exception

                # Handle EOF (empty string from read)
                if not char:
                    return None

                # Handle search mode input
                if self.search_mode:
                    if self._handle_search_char(char):
                        continue

                # Get action for this key
                action = self._get_key_action(char)

                if action:
                    result = self._execute_action(action, char)
                    if result == 'accept':
                        sys.stdout.write('\r\n')
                        sys.stdout.flush()
                        # History is recorded by ONE writer — the
                        # source processor (shell.add_history), which
                        # sees the complete logical command.  self.history
                        # aliases state.history, so the entry is visible
                        # for Up-arrow recall at the next read_line.
                        return ''.join(self.buffer)
                    elif result == 'eof':
                        sys.stdout.write('\r\n')
                        sys.stdout.flush()
                        return None
                elif ord(char) >= 32:  # Printable character
                    if self.mode == EditMode.VI_NORMAL:
                        # In vi normal mode, check for motion/command characters
                        if char.isdigit() and char != '0':
                            self.vi_repeat_count += char
                        else:
                            # Try to execute as a vi command
                            self._handle_vi_normal_char(char)
                    else:
                        # Insert mode or emacs mode
                        self._insert_char(char)
                        self.completion_state = None

    def _get_key_action(self, char: str) -> Optional[str]:
        """Get the action for a key based on current mode.

        ESC is intercepted BEFORE the emacs/vi mode split so that escape
        sequences (arrow keys, Home/End/Delete) are consumed by one
        reader and behave identically in every mode.  Previously CSI
        parsing lived only in the emacs branch, so an Up-arrow in vi
        insert mode decomposed into ESC (enter normal mode), '['
        (unbound) and 'A' (append-at-end), corrupting the edit state.
        """
        if char == '\x1b':
            return self._handle_escape()
        if self.edit_mode == 'vi':
            return self.key_handler.get_action(char)
        return self.key_handler.bindings.get(char)

    def _handle_escape(self) -> Optional[str]:
        """Resolve a key event that started with ESC (any mode).

        - ESC [ ... / ESC O x: full sequence consumed by
          _read_escape_sequence; the symbolic key maps to the same
          action in emacs mode and both vi modes.
        - vi mode, bare ESC (no pending input): enter normal mode.
        - vi mode, ESC + ordinary key: enter normal mode and re-queue
          the key so it is processed as a normal-mode command.
        - emacs mode, ESC + ordinary key: Meta combination.
        """
        if self.edit_mode == 'vi':
            if not self._input_pending():
                return 'enter_normal_mode'
            next_char = self._read_char()
            if next_char in ('[', 'O'):
                key = self._read_escape_sequence(next_char)
                return self.ESCAPE_KEY_ACTIONS.get(key) if key else None
            if next_char:
                self._char_buf.insert(0, next_char)
            return 'enter_normal_mode'

        # Emacs mode: terminals send the whole sequence in one burst, so
        # reading the follower blocks only for a human-typed Meta combo.
        next_char = self._read_char()
        if next_char in ('[', 'O'):
            key = self._read_escape_sequence(next_char)
            return self.ESCAPE_KEY_ACTIONS.get(key) if key else None
        return self.key_handler.meta_bindings.get(next_char)

    def _input_pending(self, timeout: float = 0.05) -> bool:
        """True if more input is already buffered or arrives within
        *timeout* seconds (used to tell a bare ESC keypress from the
        ESC that introduces a sequence — terminals transmit sequences
        in a single burst)."""
        if self._char_buf:
            return True
        if self._stdin_fd < 0:
            return False
        try:
            ready, _, _ = select.select([self._stdin_fd], [], [], timeout)
        except OSError:
            return False
        return bool(ready)

    def _read_escape_sequence(self, intro: str) -> Optional[str]:
        """THE escape-sequence reader: the only input-side ANSI parser.

        Called with ESC and the intro byte ('[' for CSI, 'O' for SS3)
        already consumed.  Reads the remainder of the sequence and
        returns a symbolic key name ('up', 'down', 'left', 'right',
        'home', 'end', 'delete') or None.  Unrecognized sequences are
        consumed in full so they never leak into the edit buffer.
        """
        if intro == 'O':
            # SS3: exactly one final byte
            return self._SS3_KEYS.get(self._read_char())

        # CSI: parameter/intermediate bytes, then a final byte @ .. ~
        params: List[str] = []
        while True:
            ch = self._read_char()
            if not ch:
                return None
            if '\x40' <= ch <= '\x7e':
                final = ch
                break
            params.append(ch)

        if not params:
            return self._CSI_FINAL_KEYS.get(final)
        if final == '~':
            return self._CSI_TILDE_KEYS.get(''.join(params))
        # Parameterised sequences we don't handle (modifiers, CPR
        # responses ESC[r;cR, ...) are silently discarded.
        return None

    def _execute_action(self, action: str, char: str) -> Optional[str]:
        """Execute a key binding action."""
        # Movement actions
        if action == 'move_beginning_of_line':
            self._move_home()
        elif action == 'move_end_of_line':
            self._move_end()
        elif action == 'move_forward_char':
            self._move_right()
        elif action == 'move_backward_char':
            self._move_left()
        elif action == 'move_word_forward':
            self._move_word_forward()
        elif action == 'move_word_backward':
            self._move_word_backward()

        # Editing actions
        elif action == 'delete_char':
            if not self.buffer and char == '\x04':  # Ctrl-D on empty line
                return 'eof'
            self._delete_char()
        elif action == 'backward_delete_char':
            self._backspace()
        elif action == 'kill_line':
            self._kill_line()
        elif action == 'kill_whole_line':
            self._kill_whole_line()
        elif action == 'kill_word_backward':
            self._kill_word_backward()
        elif action == 'kill_word_forward':
            self._kill_word_forward()
        elif action == 'yank':
            self._yank()
        elif action == 'transpose_chars':
            self._transpose_chars()

        # History actions
        elif action == 'previous_history':
            self._history_up()
        elif action == 'next_history':
            self._history_down()
        elif action == 'reverse_search_history':
            self._start_reverse_search()
        elif action == 'move_to_first_history':
            self._history_first()
        elif action == 'move_to_last_history':
            self._history_last()

        # Vi mode actions
        elif action == 'enter_normal_mode':
            self._enter_vi_normal_mode()
        elif action == 'enter_insert_mode':
            self._enter_vi_insert_mode()
        elif action == 'enter_insert_mode_at_beginning':
            self._move_home()
            self._enter_vi_insert_mode()
        elif action == 'append_mode':
            self._move_right()
            self._enter_vi_insert_mode()
        elif action == 'append_mode_at_end':
            self._move_end()
            self._enter_vi_insert_mode()

        elif action == 'undo':
            self.undo()
        elif action == 'redo':
            self.redo()

        # Other actions
        elif action == 'complete':
            self._handle_tab()
        elif action == 'accept_line':
            return 'accept'
        elif action == 'interrupt':
            self._handle_interrupt()
        elif action == 'clear_screen':
            self._clear_screen()
        elif action == 'abort':
            self._abort_action()

        return None

    def _handle_vi_normal_char(self, char: str):
        """Handle a character in vi normal mode."""
        # Check if this completes a command
        repeat = int(self.vi_repeat_count) if self.vi_repeat_count else 1

        # Reset repeat count unless we're building a number
        if not (char.isdigit() and self.vi_repeat_count):
            self.vi_repeat_count = ""

        # Get the action for this character
        action = self.key_handler.normal_bindings.get(char)
        if action:
            for _ in range(repeat):
                self._execute_action(action, char)

    def _insert_char(self, char: str):
        """Insert a character at the cursor position."""
        self.save_undo_state()
        self.buffer.insert(self.cursor_pos, char)
        self.cursor_pos += 1

        w = self._term_width if self._term_width > 0 else 80
        if (self.cursor_pos == len(self.buffer)
                and not L.at_row_boundary(self._screen_prompt_len,
                                          len(self.buffer), w)):
            # Fast path: appending before the right margin — just echo.
            sys.stdout.write(char)
            self._screen_cursor_pos = self.cursor_pos
            sys.stdout.flush()
        else:
            # Mid-line insert or wrap boundary: full wrap-aware repaint.
            self._redraw()

    def _backspace(self):
        """Delete character before cursor."""
        if self.cursor_pos > 0:
            self.save_undo_state()
            self.cursor_pos -= 1
            del self.buffer[self.cursor_pos]
            self._redraw()

    def _delete_char(self):
        """Delete character at cursor."""
        if self.cursor_pos < len(self.buffer):
            self.save_undo_state()
            del self.buffer[self.cursor_pos]
            self._redraw()

    def _move_left(self):
        """Move cursor left."""
        if self.cursor_pos > 0:
            self.cursor_pos -= 1
            self._move_cursor_to(self.cursor_pos)

    def _move_right(self):
        """Move cursor right."""
        if self.cursor_pos < len(self.buffer):
            self.cursor_pos += 1
            self._move_cursor_to(self.cursor_pos)

    def _move_home(self):
        """Move cursor to beginning of line."""
        if self.cursor_pos > 0:
            self.cursor_pos = 0
            self._move_cursor_to(0)

    def _move_end(self):
        """Move cursor to end of line."""
        if self.cursor_pos < len(self.buffer):
            self.cursor_pos = len(self.buffer)
            self._move_cursor_to(self.cursor_pos)

    def _move_word_forward(self):
        """Move cursor forward by one word."""
        pos = self.cursor_pos
        while pos < len(self.buffer) and not self.buffer[pos].isspace():
            pos += 1
        while pos < len(self.buffer) and self.buffer[pos].isspace():
            pos += 1
        if pos != self.cursor_pos:
            self.cursor_pos = pos
            self._move_cursor_to(pos)

    def _move_word_backward(self):
        """Move cursor backward by one word."""
        pos = self.cursor_pos
        while pos > 0 and self.buffer[pos - 1].isspace():
            pos -= 1
        while pos > 0 and not self.buffer[pos - 1].isspace():
            pos -= 1
        if pos != self.cursor_pos:
            self.cursor_pos = pos
            self._move_cursor_to(pos)

    def _kill_line(self):
        """Kill from cursor to end of line."""
        if self.cursor_pos < len(self.buffer):
            self.save_undo_state()
            killed = ''.join(self.buffer[self.cursor_pos:])
            self.kill_ring.append(killed)
            self.buffer = self.buffer[:self.cursor_pos]
            self._redraw()

    def _kill_whole_line(self):
        """Kill the entire line."""
        self.save_undo_state()
        killed = ''.join(self.buffer)
        self.kill_ring.append(killed)
        self.buffer = []
        self.cursor_pos = 0
        self._redraw()

    def _kill_word_backward(self):
        """Kill the word before cursor."""
        if self.cursor_pos > 0:
            self.save_undo_state()
            start = self.cursor_pos

            # Skip whitespace
            while self.cursor_pos > 0 and self.buffer[self.cursor_pos - 1].isspace():
                self.cursor_pos -= 1
            # Skip word
            while self.cursor_pos > 0 and not self.buffer[self.cursor_pos - 1].isspace():
                self.cursor_pos -= 1

            killed = ''.join(self.buffer[self.cursor_pos:start])
            self.kill_ring.append(killed)
            del self.buffer[self.cursor_pos:start]
            self._redraw()

    def _kill_word_forward(self):
        """Kill the word after cursor."""
        if self.cursor_pos < len(self.buffer):
            self.save_undo_state()
            start = self.cursor_pos

            # Skip current word
            while self.cursor_pos < len(self.buffer) and not self.buffer[self.cursor_pos].isspace():
                self.cursor_pos += 1
            # Skip whitespace
            while self.cursor_pos < len(self.buffer) and self.buffer[self.cursor_pos].isspace():
                self.cursor_pos += 1

            killed = ''.join(self.buffer[start:self.cursor_pos])
            self.kill_ring.append(killed)
            del self.buffer[start:self.cursor_pos]
            self.cursor_pos = start
            self._redraw()

    def _yank(self):
        """Yank (paste) from kill ring."""
        if self.kill_ring:
            self.save_undo_state()
            text = self.kill_ring[-1]
            for char in text:
                self.buffer.insert(self.cursor_pos, char)
                self.cursor_pos += 1
            self._redraw()

    def _transpose_chars(self):
        """Transpose characters around cursor."""
        if len(self.buffer) >= 2:
            self.save_undo_state()

            if self.cursor_pos == 0:
                # At beginning, transpose first two characters
                self.buffer[0], self.buffer[1] = self.buffer[1], self.buffer[0]
                self.cursor_pos = 1
            elif self.cursor_pos >= len(self.buffer):
                # At or past end, transpose last two characters
                pos = len(self.buffer) - 1
                self.buffer[pos - 1], self.buffer[pos] = self.buffer[pos], self.buffer[pos - 1]
                self.cursor_pos = pos + 1
            elif self.cursor_pos < len(self.buffer) - 1:
                # Normal case: transpose char at cursor with next char
                self.buffer[self.cursor_pos], self.buffer[self.cursor_pos + 1] = \
                    self.buffer[self.cursor_pos + 1], self.buffer[self.cursor_pos]
                self.cursor_pos += 2
            elif self.cursor_pos > 0:
                # Only one char after cursor: transpose with char before
                self.buffer[self.cursor_pos - 1], self.buffer[self.cursor_pos] = \
                    self.buffer[self.cursor_pos], self.buffer[self.cursor_pos - 1]
                self.cursor_pos += 1

            self._redraw()

    def _history_up(self):
        """Move up in history."""
        if self.history_pos > 0:
            # Save current line if at bottom of history
            if self.history_pos == len(self.history):
                self.original_line = ''.join(self.buffer)

            self.history_pos -= 1
            entry = self.history[self.history_pos]
            # Multi-line commands edit as a single line with separators
            if '\n' in entry:
                entry = convert_multiline_to_single(entry)
            self._replace_line(entry)
            self._redraw()

    def _history_down(self):
        """Move down in history."""
        if self.history_pos < len(self.history):
            self.history_pos += 1

            if self.history_pos == len(self.history):
                entry = self.original_line
            else:
                entry = self.history[self.history_pos]
                if '\n' in entry:
                    entry = convert_multiline_to_single(entry)
            self._replace_line(entry)
            self._redraw()

    def _history_first(self):
        """Move to first history entry."""
        if self.history and self.history_pos > 0:
            if self.history_pos == len(self.history):
                self.original_line = ''.join(self.buffer)
            self.history_pos = 0
            self._replace_line(self.history[0])
            self._redraw()

    def _history_last(self):
        """Move to last history entry (current line)."""
        if self.history_pos < len(self.history):
            self.history_pos = len(self.history)
            self._replace_line(self.original_line)
            self._redraw()

    def _start_reverse_search(self):
        """Start reverse history search mode."""
        self.search_mode = True
        self.search_pattern = ""
        self.search_direction = -1
        self.search_start_pos = self.history_pos
        self._update_search_prompt()

    def _handle_search_char(self, char: str) -> bool:
        """Handle character input in search mode."""
        if char == '\x07':  # Ctrl-G - abort search
            self._abort_search()
            return True
        elif char == '\x12':  # Ctrl-R - search backward
            self._search_next(-1)
            return True
        elif char == '\x13':  # Ctrl-S - search forward
            self._search_next(1)
            return True
        elif char in ('\r', '\n'):  # Enter - accept search
            self._accept_search()
            return True
        elif char == '\x7f':  # Backspace
            if self.search_pattern:
                self.search_pattern = self.search_pattern[:-1]
                self._perform_search()
            return True
        elif ord(char) >= 32:  # Printable character
            self.search_pattern += char
            self._perform_search()
            return True
        else:
            # Exit search mode for other control characters
            self._accept_search()
            return False

    def _perform_search(self):
        """Perform the history search."""
        found = False
        start = self.history_pos

        # Search through history
        if self.search_direction < 0:
            # Backward search
            for i in range(self.history_pos - 1, -1, -1):
                if self.search_pattern in self.history[i]:
                    self.history_pos = i
                    found = True
                    break
        else:
            # Forward search
            for i in range(self.history_pos + 1, len(self.history)):
                if self.search_pattern in self.history[i]:
                    self.history_pos = i
                    found = True
                    break

        if found:
            self._update_search_prompt()
        else:
            # Pattern not found, restore position
            self.history_pos = start
            self._update_search_prompt(failed=True)

    def _search_next(self, direction: int):
        """Continue search in given direction."""
        self.search_direction = direction
        old_pos = self.history_pos

        # Move one position to avoid finding the same match
        if direction < 0 and self.history_pos > 0:
            self.history_pos -= 1
        elif direction > 0 and self.history_pos < len(self.history) - 1:
            self.history_pos += 1
        else:
            return

        self._perform_search()

        # If no match found, restore position
        if self.history_pos == old_pos:
            self._update_search_prompt(failed=True)

    def _update_search_prompt(self, failed: bool = False):
        """Update the search prompt display (wrap-aware)."""
        direction = "bck" if self.search_direction < 0 else "fwd"
        if failed:
            prompt = f"(failed-{direction}-i-search)`{self.search_pattern}': "
        else:
            prompt = f"({direction}-i-search)`{self.search_pattern}': "

        # Show the current match with the cursor just past the matched text
        if self.history_pos < len(self.history):
            line = self.history[self.history_pos]
            self.buffer = list(line)
            match_pos = line.find(self.search_pattern)
            if match_pos >= 0:
                self.cursor_pos = match_pos + len(self.search_pattern)
            else:
                self.cursor_pos = len(line)

        self._redraw(prompt)

    def _abort_search(self):
        """Abort search and restore original state."""
        self.search_mode = False
        self.history_pos = self.search_start_pos
        self._replace_line(self.original_line)
        self._redraw()

    def _accept_search(self):
        """Accept current search result."""
        self.search_mode = False

        # Update buffer with found line
        if self.history_pos < len(self.history):
            self._replace_line(self.history[self.history_pos])
        self._redraw()

    def _enter_vi_normal_mode(self):
        """Enter vi normal mode."""
        if self.mode != EditMode.VI_NORMAL:
            self.mode = EditMode.VI_NORMAL
            self.key_handler.mode = EditMode.VI_NORMAL
            # Move cursor back one position (vi behavior)
            if self.cursor_pos > 0:
                self._move_left()

    def _enter_vi_insert_mode(self):
        """Enter vi insert mode."""
        self.mode = EditMode.VI_INSERT
        self.key_handler.mode = EditMode.VI_INSERT

    def _clear_screen(self):
        """Clear screen and redraw current line."""
        sys.stdout.write('\033[2J\033[H')
        self._paint()

    @staticmethod
    def _visible_length(text: str) -> int:
        """Visible column width of prompt text.

        Understands readline's \\x01/\\x02 invisibility markers (from
        \\[ \\] in PS1) as well as bare ANSI CSI and OSC sequences —
        the old version only stripped CSI, so colored prompts using
        markers or title sequences threw off all cursor math.
        """
        return L.visible_prompt_length(text)

    def _paint(self, prompt: str = None):
        """Write prompt + buffer starting at the CURRENT cursor location
        (assumed to be the prompt origin: its first row, column 0), then
        place the physical cursor at self.cursor_pos.

        Wrap-aware: when the content ends exactly at the right margin the
        auto-wrap is committed (space + CR + erase) so the cursor's
        position stays deterministic for later relative moves.
        """
        if prompt is None:
            prompt = self.current_prompt
        w = self._term_width if self._term_width > 0 else 80
        plen = L.visible_prompt_length(prompt)

        sys.stdout.write(L.displayable_prompt(prompt))
        sys.stdout.write(''.join(self.buffer))

        blen = len(self.buffer)
        if L.at_row_boundary(plen, blen, w):
            # Commit the pending wrap deterministically
            sys.stdout.write(' \r\033[K')

        end_row, _ = L.position(plen, blen, w)
        cur_row, cur_col = L.position(plen, self.cursor_pos, w)
        if end_row > cur_row:
            sys.stdout.write(f'\033[{end_row - cur_row}A')
        sys.stdout.write('\r')
        if cur_col > 0:
            sys.stdout.write(f'\033[{cur_col}C')

        self._screen_prompt_len = plen
        self._screen_cursor_pos = self.cursor_pos
        sys.stdout.flush()

    def _redraw(self, prompt: str = None):
        """THE central wrap-aware repaint.

        Moves from wherever the physical cursor is (tracked via
        _screen_cursor_pos/_screen_prompt_len) up to the prompt origin,
        clears to end of screen, and repaints. Every mutating edit
        operation funnels through here; pure cursor movement uses
        _move_cursor_to. This replaces the old per-operation
        backspace/ESC[K arithmetic, which corrupted the display whenever
        the line wrapped past the terminal width.
        """
        w = self._term_width if self._term_width > 0 else 80
        rows_up, _ = L.position(self._screen_prompt_len,
                                self._screen_cursor_pos, w)
        if rows_up > 0:
            sys.stdout.write(f'\033[{rows_up}A')
        sys.stdout.write('\r\033[J')
        self._paint(prompt)

    def _move_cursor_to(self, pos: int):
        """Move the physical cursor to buffer position *pos* without
        rewriting any text (wrap-aware relative movement)."""
        w = self._term_width if self._term_width > 0 else 80
        plen = self._screen_prompt_len
        from_row, from_col = L.position(plen, self._screen_cursor_pos, w)
        to_row, to_col = L.position(plen, pos, w)
        if to_row < from_row:
            sys.stdout.write(f'\033[{from_row - to_row}A')
        elif to_row > from_row:
            sys.stdout.write(f'\033[{to_row - from_row}B')
        if to_col != from_col:
            sys.stdout.write('\r')
            if to_col > 0:
                sys.stdout.write(f'\033[{to_col}C')
        self._screen_cursor_pos = pos
        sys.stdout.flush()

    def redraw_line(self):
        """Redraw the current prompt and input line in place.

        Used after terminal resize (SIGWINCH) to fix display corruption.

        After a resize the terminal has already reflowed all content at the
        new width, so saved absolute row positions are stale.  Instead we
        compute how many rows the prompt+input spans at the **new** width
        (which matches the reflow) and move up by that amount from wherever
        the cursor currently sits.  This avoids clearing previously-output
        command results that the terminal correctly reflowed.
        """
        prompt_len = self._visible_length(self.current_prompt)

        try:
            new_width = shutil.get_terminal_size().columns
        except (OSError, ValueError):
            new_width = 80

        # After reflow the terminal has repositioned the cursor at the
        # correct content offset.  The number of rows from the prompt
        # start to the cursor matches the new width layout.
        if new_width > 0:
            rows_up = (prompt_len + self.cursor_pos) // new_width
        else:
            rows_up = 0

        if rows_up > 0:
            sys.stdout.write(f'\033[{rows_up}A')

        # Move to column 0, clear to end of screen, repaint (wrap-aware)
        sys.stdout.write('\r\033[J')
        self._term_width = new_width
        self._paint()

    def _handle_interrupt(self):
        """Handle Ctrl-C interrupt."""
        # Clear line and raise KeyboardInterrupt
        sys.stdout.write('\r')
        sys.stdout.write('\033[K')
        sys.stdout.write('^C\r\n')
        sys.stdout.flush()
        raise KeyboardInterrupt()

    def _abort_action(self):
        """Abort current action (Ctrl-G in emacs)."""
        # Just beep for now
        sys.stdout.write('\a')
        sys.stdout.flush()

    def _handle_tab(self):
        """Handle tab completion."""
        line = ''.join(self.buffer)

        # Get completions
        completions = self.completion_engine.get_completions(
            line[:self.cursor_pos], line, self.cursor_pos
        )

        if not completions:
            # No completions, just beep
            sys.stdout.write('\a')
            sys.stdout.flush()
            return

        if len(completions) == 1:
            # Single completion - use it
            self._apply_completion(completions[0])
        else:
            # Multiple completions
            common_prefix = self.completion_engine.find_common_prefix(completions)

            # Find the word being completed
            word_start = self.completion_engine.find_word_start(line, self.cursor_pos)
            current_word = line[word_start:self.cursor_pos]

            if len(common_prefix) > len(current_word):
                # Can expand to common prefix
                self._apply_completion(common_prefix)
            else:
                # Show all completions
                self._show_completions(completions)

    def _apply_completion(self, completion: str):
        """Apply a completion to the current line."""
        line = ''.join(self.buffer)

        # Find the word being completed
        word_start = self.completion_engine.find_word_start(line, self.cursor_pos)

        # Check if we need to escape the completion
        if word_start == 0 or line[word_start-1] not in '"\'':
            # Not in quotes, escape special characters
            completion = self.completion_engine.escape_path(completion)

        # Update buffer and cursor position, then repaint (wrap-aware)
        new_line = line[:word_start] + completion
        if self.cursor_pos < len(line):
            new_line += line[self.cursor_pos:]

        self.buffer = list(new_line)
        self.cursor_pos = word_start + len(completion)
        self._redraw()

    def _show_completions(self, completions: List[str]):
        """Display multiple completions."""
        # Save current line
        self.terminal.exit_raw_mode()

        # Display completions
        sys.stdout.write('\r\n')
        self._display_in_columns(completions)

        # Redraw prompt and current line
        self.terminal.enter_raw_mode()
        sys.stdout.write('\r\n')
        self._paint()

    def _display_in_columns(self, items: List[str]):
        """Display items in columns."""
        if not items:
            return

        # Get terminal width
        try:
            import shutil
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
            sys.stdout.write(item.ljust(col_width))
            if (i + 1) % num_cols == 0:
                sys.stdout.write('\n')

        if len(items) % num_cols != 0:
            sys.stdout.write('\n')

        sys.stdout.flush()

    def _replace_line(self, new_line: str):
        """Replace the current line with new text."""
        self.buffer = list(new_line)
        self.cursor_pos = len(self.buffer)

    def save_undo_state(self):
        """Save current buffer state for undo."""
        state = (''.join(self.buffer), self.cursor_pos)
        if not self.undo_stack or self.undo_stack[-1] != state:
            self.undo_stack.append(state)
            self.redo_stack.clear()

    def undo(self):
        """Undo last change.

        The live buffer is the implicit top of the stack: if it differs
        from the last saved state, undoing first parks it on the redo
        stack (otherwise the most recent edit would be skipped entirely).
        """
        current = (''.join(self.buffer), self.cursor_pos)
        if self.undo_stack and self.undo_stack[-1] != current:
            self.redo_stack.append(current)
        elif len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
        else:
            return

        # Restore previous state
        text, pos = self.undo_stack[-1]
        self.buffer = list(text)
        self.cursor_pos = pos
        self._redraw()

    def redo(self):
        """Redo last undone change."""
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)

            text, pos = state
            self.buffer = list(text)
            self.cursor_pos = pos
            self._redraw()
