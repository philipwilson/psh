#!/usr/bin/env python3
"""Enhanced line editor with vi/emacs key bindings and history search."""

import os
import re
import select
import shutil
import sys
from typing import Callable, List, Optional

from .keybindings import EditMode, EmacsKeyBindings, ViKeyBindings
from .tab_completion import CompletionEngine, TerminalManager


class LineEditor:
    """Interactive line editor with vi/emacs key bindings, tab completion, and history search."""

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
        self.edit_mode = edit_mode.lower()
        if self.edit_mode == 'vi':
            self.key_handler = ViKeyBindings()
            self.mode = EditMode.VI_INSERT
        else:
            self.key_handler = EmacsKeyBindings()
            self.mode = EditMode.EMACS

        # Kill ring for cut/paste operations
        self.kill_ring = []
        self.kill_ring_pos = 0

        # Search state
        self.search_mode = False
        self.search_pattern = ""
        self.search_direction = 1  # 1 for forward, -1 for backward
        self.search_start_pos = 0

        # Vi specific state
        self.vi_repeat_count = ""
        self.vi_pending_motion = None
        self.vi_last_change = None
        self.vi_registers = {'"': ''}
        self.vi_current_register = '"'
        self.vi_mark_start = -1  # For visual mode

        # Undo/redo support
        self.undo_stack = []
        self.redo_stack = []
        self.save_undo_state()

        # Raw fd reading state — bypasses Python's BufferedReader so that
        # select() and reads stay in sync (see _read_char).
        self._stdin_fd = -1
        self._char_buf: List[str] = []

    def _query_cursor_row(self) -> int:
        """Query the terminal for the cursor's current row (0-indexed).

        Sends the DSR (Device Status Report) sequence ``ESC[6n`` and
        reads the ``ESC[row;colR`` response directly from the raw fd.
        Returns -1 if the query fails or times out.
        """
        if self._stdin_fd < 0:
            return -1

        sys.stdout.write('\033[6n')
        sys.stdout.flush()

        buf: List[bytes] = []
        try:
            for _ in range(20):  # safety limit on response length
                ready, _, _ = select.select([self._stdin_fd], [], [], 0.1)
                if not ready:
                    break
                data = os.read(self._stdin_fd, 1)
                if not data:
                    break
                buf.append(data)
                if data == b'R':
                    break
        except OSError:
            pass

        response = b''.join(buf).decode('ascii', errors='replace')
        m = re.match(r'\x1b\[(\d+);(\d+)R', response)
        if m:
            return int(m.group(1)) - 1  # convert to 0-indexed

        # Response wasn't a DSR reply; push characters back
        if response:
            self._char_buf = list(response) + self._char_buf
        return -1

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
        # Print prompt
        sys.stdout.write(prompt)
        sys.stdout.flush()

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

        # Reset vi mode to insert
        if self.edit_mode == 'vi':
            self.mode = EditMode.VI_INSERT
            self.vi_repeat_count = ""
            self.vi_pending_motion = None

        # Build list of fds to monitor
        stdin_fd = sys.stdin.fileno()
        self._stdin_fd = stdin_fd
        self._char_buf = []
        watch_fds = [stdin_fd]
        if sigwinch_fd >= 0:
            watch_fds.append(sigwinch_fd)

        with self.terminal:
            # Record the row where the prompt was drawn so that
            # redraw_line() can detect cursor displacement on resize.
            row = self._query_cursor_row()
            if row >= 0:
                prompt_vis = self._visible_length(prompt)
                w = self._term_width if self._term_width > 0 else 80
                # Cursor is at end of prompt; prompt started further up
                # if it wrapped.
                self._prompt_draw_row = max(0, row - prompt_vis // w)
            else:
                self._prompt_draw_row = -1

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
                        # Try to restore terminal before failing
                        try:
                            self.terminal.restore()
                        except OSError:
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
                        line = ''.join(self.buffer)
                        if line.strip():
                            # Don't add history expansion commands to history
                            import re
                            history_pattern = r'(?:^|\s)!(?:!|[0-9]+|-[0-9]+|[a-zA-Z][a-zA-Z0-9]*|\?[^?]*\?)(?:\s|$)'
                            if not re.search(history_pattern, line):
                                self.history.append(line)
                        return line
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
        """Get the action for a key based on current mode."""
        if self.edit_mode == 'vi':
            return self.key_handler.get_action(char)
        else:
            # Emacs mode
            if char == '\x1b':  # ESC - check for Meta combinations
                next_char = self._read_char()
                if next_char == '[':
                    # Arrow key sequence
                    return self._handle_arrow_sequence()
                else:
                    # Meta key combination
                    return self.key_handler.meta_bindings.get(next_char)
            else:
                return self.key_handler.bindings.get(char)

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

    def _handle_arrow_sequence(self) -> Optional[str]:
        """Handle arrow key sequences."""
        seq = self._read_char()

        if seq == 'A':  # Up arrow
            return 'previous_history'
        elif seq == 'B':  # Down arrow
            return 'next_history'
        elif seq == 'C':  # Right arrow
            return 'move_forward_char'
        elif seq == 'D':  # Left arrow
            return 'move_backward_char'
        elif seq == 'H':  # Home
            return 'move_beginning_of_line'
        elif seq == 'F':  # End
            return 'move_end_of_line'

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

        # Redraw the line from cursor position
        sys.stdout.write(char)

        # If we're not at the end, redraw the rest and move cursor back
        if self.cursor_pos < len(self.buffer):
            rest = ''.join(self.buffer[self.cursor_pos:])
            sys.stdout.write(rest)
            sys.stdout.write('\b' * len(rest))

        sys.stdout.flush()

    def _backspace(self):
        """Delete character before cursor."""
        if self.cursor_pos > 0:
            self.save_undo_state()
            self.cursor_pos -= 1
            del self.buffer[self.cursor_pos]

            # Move cursor back
            sys.stdout.write('\b')

            # Redraw from cursor to end of line
            rest = ''.join(self.buffer[self.cursor_pos:])
            sys.stdout.write(rest + ' ')
            sys.stdout.write('\b' * (len(rest) + 1))
            sys.stdout.flush()

    def _delete_char(self):
        """Delete character at cursor."""
        if self.cursor_pos < len(self.buffer):
            self.save_undo_state()
            del self.buffer[self.cursor_pos]

            # Redraw from cursor to end of line
            rest = ''.join(self.buffer[self.cursor_pos:])
            sys.stdout.write(rest + ' ')
            sys.stdout.write('\b' * (len(rest) + 1))
            sys.stdout.flush()

    def _move_left(self):
        """Move cursor left."""
        if self.cursor_pos > 0:
            self.cursor_pos -= 1
            sys.stdout.write('\b')
            sys.stdout.flush()

    def _move_right(self):
        """Move cursor right."""
        if self.cursor_pos < len(self.buffer):
            sys.stdout.write(self.buffer[self.cursor_pos])
            self.cursor_pos += 1
            sys.stdout.flush()

    def _move_home(self):
        """Move cursor to beginning of line."""
        if self.cursor_pos > 0:
            sys.stdout.write('\b' * self.cursor_pos)
            self.cursor_pos = 0
            sys.stdout.flush()

    def _move_end(self):
        """Move cursor to end of line."""
        if self.cursor_pos < len(self.buffer):
            rest = ''.join(self.buffer[self.cursor_pos:])
            sys.stdout.write(rest)
            self.cursor_pos = len(self.buffer)
            sys.stdout.flush()

    def _move_word_forward(self):
        """Move cursor forward by one word."""
        # Skip current word
        while self.cursor_pos < len(self.buffer) and not self.buffer[self.cursor_pos].isspace():
            self._move_right()
        # Skip whitespace
        while self.cursor_pos < len(self.buffer) and self.buffer[self.cursor_pos].isspace():
            self._move_right()

    def _move_word_backward(self):
        """Move cursor backward by one word."""
        # Skip whitespace
        while self.cursor_pos > 0 and self.buffer[self.cursor_pos - 1].isspace():
            self._move_left()
        # Skip word
        while self.cursor_pos > 0 and not self.buffer[self.cursor_pos - 1].isspace():
            self._move_left()

    def _kill_line(self):
        """Kill from cursor to end of line."""
        if self.cursor_pos < len(self.buffer):
            self.save_undo_state()
            killed = ''.join(self.buffer[self.cursor_pos:])
            self.kill_ring.append(killed)
            self.buffer = self.buffer[:self.cursor_pos]

            # Clear to end of line
            sys.stdout.write('\033[K')
            sys.stdout.flush()

    def _kill_whole_line(self):
        """Kill the entire line."""
        self.save_undo_state()
        self._move_home()
        killed = ''.join(self.buffer)
        self.kill_ring.append(killed)
        self.buffer = []
        self.cursor_pos = 0

        # Clear line
        sys.stdout.write('\033[K')
        sys.stdout.flush()

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

            # Move cursor and clear
            sys.stdout.write('\b' * (start - self.cursor_pos))
            rest = ''.join(self.buffer[self.cursor_pos:])
            sys.stdout.write(rest + ' ' * (start - self.cursor_pos))
            sys.stdout.write('\b' * (len(rest) + start - self.cursor_pos))
            sys.stdout.flush()

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

            # Redraw
            rest = ''.join(self.buffer[self.cursor_pos:])
            sys.stdout.write(rest + ' ' * len(killed))
            sys.stdout.write('\b' * (len(rest) + len(killed)))
            sys.stdout.flush()

    def _yank(self):
        """Yank (paste) from kill ring."""
        if self.kill_ring:
            self.save_undo_state()
            text = self.kill_ring[-1]
            for char in text:
                self.buffer.insert(self.cursor_pos, char)
                self.cursor_pos += 1

            # Display yanked text
            sys.stdout.write(text)
            if self.cursor_pos < len(self.buffer):
                rest = ''.join(self.buffer[self.cursor_pos:])
                sys.stdout.write(rest)
                sys.stdout.write('\b' * len(rest))
            sys.stdout.flush()

    def _transpose_chars(self):
        """Transpose characters around cursor."""
        if len(self.buffer) >= 2:
            self.save_undo_state()

            # Special cases:
            # 1. If at beginning of line (pos 0), transpose first two chars
            # 2. If at end of line, transpose last two chars
            # 3. Otherwise, transpose char at cursor with char after cursor

            if self.cursor_pos == 0:
                # At beginning, transpose first two characters
                if len(self.buffer) >= 2:
                    self.buffer[0], self.buffer[1] = self.buffer[1], self.buffer[0]
                    # Redraw
                    sys.stdout.write(''.join(self.buffer[0:2]))
                    sys.stdout.write('\b')  # Position after first char
                    self.cursor_pos = 1
            elif self.cursor_pos >= len(self.buffer):
                # At or past end, transpose last two characters
                pos = len(self.buffer) - 1
                self.buffer[pos - 1], self.buffer[pos] = self.buffer[pos], self.buffer[pos - 1]
                # Move to position before last two chars
                move_back = self.cursor_pos - (pos - 1)
                if move_back > 0:
                    sys.stdout.write('\b' * move_back)
                # Redraw last two chars
                sys.stdout.write(''.join(self.buffer[pos - 1:pos + 1]))
                self.cursor_pos = pos + 1
            else:
                # Normal case: transpose char at cursor with next char
                if self.cursor_pos < len(self.buffer) - 1:
                    self.buffer[self.cursor_pos], self.buffer[self.cursor_pos + 1] = \
                        self.buffer[self.cursor_pos + 1], self.buffer[self.cursor_pos]

                    # Redraw the two swapped characters
                    sys.stdout.write(''.join(self.buffer[self.cursor_pos:self.cursor_pos + 2]))

                    # Move cursor forward past the transposed pair
                    self.cursor_pos += 2

                    # If not at end, redraw remaining chars and reposition
                    if self.cursor_pos < len(self.buffer):
                        rest = ''.join(self.buffer[self.cursor_pos:])
                        sys.stdout.write(rest)
                        sys.stdout.write('\b' * len(rest))
                else:
                    # Only one char after cursor, transpose with char before
                    if self.cursor_pos > 0:
                        self.buffer[self.cursor_pos - 1], self.buffer[self.cursor_pos] = \
                            self.buffer[self.cursor_pos], self.buffer[self.cursor_pos - 1]
                        # Move back and redraw
                        sys.stdout.write('\b')
                        sys.stdout.write(''.join(self.buffer[self.cursor_pos - 1:self.cursor_pos + 1]))
                        self.cursor_pos += 1

            sys.stdout.flush()

    def _history_up(self):
        """Move up in history."""
        if self.history_pos > 0:
            # Save current line if at bottom of history
            if self.history_pos == len(self.history):
                self.original_line = ''.join(self.buffer)

            # Clear current line
            self._clear_current_line()

            # Update to previous history entry
            self.history_pos -= 1
            history_entry = self.history[self.history_pos]

            # For multi-line commands, convert to single line for editing
            if '\n' in history_entry:
                # Multi-line command - convert to single line with semicolons
                # Join lines with appropriate separators
                single_line = self._convert_multiline_to_single(history_entry)
                self._replace_line(single_line)
                sys.stdout.write(''.join(self.buffer))
            else:
                # Single line command
                self._replace_line(history_entry)
                sys.stdout.write(''.join(self.buffer))

            sys.stdout.flush()

    def _history_down(self):
        """Move down in history."""
        if self.history_pos < len(self.history):
            # Clear current line
            self._clear_current_line()

            self.history_pos += 1

            if self.history_pos == len(self.history):
                # Restore original line
                self._replace_line(self.original_line)
                sys.stdout.write(''.join(self.buffer))
            else:
                history_entry = self.history[self.history_pos]

                # Handle multi-line commands
                if '\n' in history_entry:
                    # Convert to single line for editing
                    single_line = self._convert_multiline_to_single(history_entry)
                    self._replace_line(single_line)
                    sys.stdout.write(''.join(self.buffer))
                else:
                    # Single line command
                    self._replace_line(history_entry)
                    sys.stdout.write(''.join(self.buffer))

            sys.stdout.flush()

    def _history_first(self):
        """Move to first history entry."""
        if self.history and self.history_pos > 0:
            # Save current line if at bottom of history
            if self.history_pos == len(self.history):
                self.original_line = ''.join(self.buffer)

            self._clear_current_line()
            self.history_pos = 0
            self._replace_line(self.history[0])
            sys.stdout.write(''.join(self.buffer))
            sys.stdout.flush()

    def _history_last(self):
        """Move to last history entry (current line)."""
        if self.history_pos < len(self.history):
            self._clear_current_line()
            self.history_pos = len(self.history)
            self._replace_line(self.original_line)
            sys.stdout.write(''.join(self.buffer))
            sys.stdout.flush()

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
            self._clear_current_line()
            self._replace_line(self.history[self.history_pos])
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
        """Update the search prompt display."""
        # Clear current line
        self._move_home()
        sys.stdout.write('\033[K')

        # Display search prompt
        direction = "bck" if self.search_direction < 0 else "fwd"
        if failed:
            prompt = f"(failed-{direction}-i-search)`{self.search_pattern}': "
        else:
            prompt = f"({direction}-i-search)`{self.search_pattern}': "

        sys.stdout.write(prompt)

        # Display current match
        if self.history_pos < len(self.history):
            line = self.history[self.history_pos]
            sys.stdout.write(line)

            # Position cursor at match
            match_pos = line.find(self.search_pattern)
            if match_pos >= 0:
                self.cursor_pos = match_pos + len(self.search_pattern)
                move_back = len(line) - self.cursor_pos
                if move_back > 0:
                    sys.stdout.write('\b' * move_back)

        sys.stdout.flush()

    def _abort_search(self):
        """Abort search and restore original state."""
        self.search_mode = False
        self.history_pos = self.search_start_pos

        # Restore display
        self._clear_current_line()
        sys.stdout.write(self.current_prompt)
        self._replace_line(self.original_line)
        sys.stdout.write(''.join(self.buffer))

        # Position cursor
        if self.cursor_pos < len(self.buffer):
            sys.stdout.write('\b' * (len(self.buffer) - self.cursor_pos))

        sys.stdout.flush()

    def _accept_search(self):
        """Accept current search result."""
        self.search_mode = False

        # Update buffer with found line
        if self.history_pos < len(self.history):
            self._replace_line(self.history[self.history_pos])

        # Restore normal prompt
        self._clear_current_line()
        sys.stdout.write(self.current_prompt)
        sys.stdout.write(''.join(self.buffer))

        # Position cursor
        if self.cursor_pos < len(self.buffer):
            sys.stdout.write('\b' * (len(self.buffer) - self.cursor_pos))

        sys.stdout.flush()

    def _enter_vi_normal_mode(self):
        """Enter vi normal mode."""
        if self.mode != EditMode.VI_NORMAL:
            self.mode = EditMode.VI_NORMAL
            # Move cursor back one position (vi behavior)
            if self.cursor_pos > 0:
                self._move_left()

    def _enter_vi_insert_mode(self):
        """Enter vi insert mode."""
        self.mode = EditMode.VI_INSERT

    def _clear_screen(self):
        """Clear screen and redraw current line."""
        # Clear screen
        sys.stdout.write('\033[2J\033[H')

        # Redraw prompt and current line
        sys.stdout.write(self.current_prompt)
        sys.stdout.write(''.join(self.buffer))

        # Position cursor
        if self.cursor_pos < len(self.buffer):
            sys.stdout.write('\b' * (len(self.buffer) - self.cursor_pos))

        sys.stdout.flush()

    @staticmethod
    def _visible_length(text: str) -> int:
        """Calculate visible length of text, stripping ANSI escape sequences."""
        return len(re.sub(r'\033\[[0-9;]*[a-zA-Z]', '', text))

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

        # Move to column 0, then clear from here to end of screen
        sys.stdout.write('\r\033[J')

        # Redraw prompt and buffer
        sys.stdout.write(self.current_prompt)
        sys.stdout.write(''.join(self.buffer))

        # Reposition cursor if it isn't at the end of the buffer
        if self.cursor_pos < len(self.buffer):
            end_pos = prompt_len + len(self.buffer)
            cur_pos = prompt_len + self.cursor_pos

            if new_width > 0:
                rows_back = end_pos // new_width - cur_pos // new_width
                target_col = cur_pos % new_width
            else:
                rows_back = 0
                target_col = cur_pos

            if rows_back > 0:
                sys.stdout.write(f'\033[{rows_back}A')

            # Move to the exact column
            sys.stdout.write('\r')
            if target_col > 0:
                sys.stdout.write(f'\033[{target_col}C')

        # Update prompt draw row for the next resize
        actual_row = self._query_cursor_row()
        if actual_row >= 0:
            cur_row_in_content = (prompt_len + self.cursor_pos) // new_width if new_width > 0 else 0
            self._prompt_draw_row = max(0, actual_row - cur_row_in_content)

        self._term_width = new_width
        sys.stdout.flush()

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
            word_start = self.completion_engine._find_word_start(line, self.cursor_pos)
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
        word_start = self.completion_engine._find_word_start(line, self.cursor_pos)

        # Check if we need to escape the completion
        if word_start == 0 or line[word_start-1] not in '"\'':
            # Not in quotes, escape special characters
            completion = self.completion_engine.escape_path(completion)

        # Calculate what we need to erase
        chars_to_erase = self.cursor_pos - word_start

        # Move cursor back to word start
        if chars_to_erase > 0:
            sys.stdout.write('\b' * chars_to_erase)

        # Clear from cursor to end of line
        sys.stdout.write('\033[K')

        # Write the completion
        sys.stdout.write(completion)

        # Write any remaining text after the cursor
        if self.cursor_pos < len(line):
            remaining = line[self.cursor_pos:]
            sys.stdout.write(remaining)
            # Move cursor back to end of completion
            sys.stdout.write('\b' * len(remaining))

        sys.stdout.flush()

        # Update buffer and cursor position
        new_line = line[:word_start] + completion
        if self.cursor_pos < len(line):
            new_line += line[self.cursor_pos:]

        self.buffer = list(new_line)
        self.cursor_pos = word_start + len(completion)

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
        sys.stdout.write(self.current_prompt)
        sys.stdout.write(''.join(self.buffer))

        # Position cursor correctly
        if self.cursor_pos < len(self.buffer):
            sys.stdout.write('\b' * (len(self.buffer) - self.cursor_pos))

        sys.stdout.flush()

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

    def _clear_current_line(self):
        """Clear the current input line."""
        # Move cursor to beginning of input
        if self.cursor_pos > 0:
            sys.stdout.write('\b' * self.cursor_pos)
        # Clear from cursor to end of line
        sys.stdout.write('\033[K')
        sys.stdout.flush()

    def _replace_line(self, new_line: str):
        """Replace the current line with new text."""
        self.buffer = list(new_line)
        self.cursor_pos = len(self.buffer)

    def _convert_multiline_to_single(self, multiline_cmd: str) -> str:
        """Convert a multi-line command to a single line representation."""
        # Split into lines and strip whitespace
        lines = [line.strip() for line in multiline_cmd.split('\n')]

        # Analyze the command structure to determine proper joining
        first_line = lines[0] if lines else ""

        # For control structures, join with semicolons
        if any(first_line.startswith(kw) for kw in ['for ', 'while ', 'if ', 'case ']):
            result = []
            i = 0
            while i < len(lines):
                line = lines[i]
                if not line:  # Skip empty lines
                    i += 1
                    continue

                # Handle for loops specially
                if line.startswith('for ') and i + 1 < len(lines) and lines[i + 1] == 'do':
                    result.append(line + '; do')
                    i += 2  # Skip the 'do' line
                elif line.startswith('while ') and i + 1 < len(lines) and lines[i + 1] == 'do':
                    result.append(line + '; do')
                    i += 2  # Skip the 'do' line
                elif line == 'do':
                    # Standalone 'do' - was already handled
                    i += 1
                elif line == 'done':
                    result.append('; done')
                    i += 1
                elif line == 'then':
                    result[-1] += '; then'
                    i += 1
                elif line == 'else':
                    result.append('; else')
                    i += 1
                elif line == 'fi':
                    result.append('; fi')
                    i += 1
                elif line == 'esac':
                    result.append('; esac')
                    i += 1
                elif line.endswith(';;'):
                    # Don't add extra semicolon
                    if result and not result[-1].endswith((';', 'then', 'do', 'else', ')')):
                        result.append('; ' + line)
                    else:
                        result.append(' ' + line)
                    i += 1
                elif line.endswith(')') and not line.startswith('('):
                    # Case pattern
                    if result and result[-1] != first_line:
                        result.append(' ' + line)
                    else:
                        result.append(' ' + line)
                    i += 1
                else:
                    # Regular command line
                    if result and not result[-1].endswith((';', 'then', 'do', 'else')):
                        result.append('; ' + line)
                    else:
                        result.append(' ' + line if result else line)
                    i += 1

            return ''.join(result)

        # For function definitions
        elif first_line.endswith('()') or first_line.endswith('() {'):
            # Join function body with semicolons
            if first_line.endswith('()'):
                result = first_line + ' { '
                body_start = 1
            else:
                result = first_line + ' '
                body_start = 1

            for i in range(body_start, len(lines)):
                line = lines[i]
                if line == '}':
                    result += '; }'
                elif line:
                    if not result.endswith((' { ', '; ')):
                        result += '; '
                    result += line

            return result

        # For simple multi-line with backslash continuation
        else:
            # Just join with spaces
            return ' '.join(lines)

    def save_undo_state(self):
        """Save current buffer state for undo."""
        state = (''.join(self.buffer), self.cursor_pos)
        if not self.undo_stack or self.undo_stack[-1] != state:
            self.undo_stack.append(state)
            self.redo_stack.clear()

    def undo(self):
        """Undo last change."""
        if len(self.undo_stack) > 1:
            # Save current state to redo stack
            self.redo_stack.append(self.undo_stack.pop())

            # Restore previous state
            text, pos = self.undo_stack[-1]
            self._clear_current_line()
            self.buffer = list(text)
            self.cursor_pos = pos

            # Redraw
            sys.stdout.write(text)
            if pos < len(text):
                sys.stdout.write('\b' * (len(text) - pos))
            sys.stdout.flush()

    def redo(self):
        """Redo last undone change."""
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)

            text, pos = state
            self._clear_current_line()
            self.buffer = list(text)
            self.cursor_pos = pos

            # Redraw
            sys.stdout.write(text)
            if pos < len(text):
                sys.stdout.write('\b' * (len(text) - pos))
            sys.stdout.flush()
