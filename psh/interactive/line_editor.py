#!/usr/bin/env python3
"""Enhanced line editor with vi/emacs key bindings and history search.

LineEditor is the COORDINATOR of five narrow components (Textbook B8):
it owns mode state (emacs / vi-insert / vi-normal, the vi repeat
count) and the dispatch table mapping key-binding action names to edit
operations, and it wires the components together — KeyDecoder (the
only reader of stdin) yields KeyEvents, the mode-policy layer decides
what each event MEANS, EditBuffer (the single source of truth for
text + cursor, kill ring, undo/redo) mutates, HistoryNavigator /
HistorySearch (history_nav.py) compute what history browsing and
Ctrl-R incremental search should display, and LineRenderer (the only
writer of ANSI) repaints. The completion-UI glue (tab handling,
applying a completion, listing candidates around a raw-mode toggle)
stays here deliberately: it is pure coordination between
CompletionEngine, TerminalManager and the renderer.
"""

import os
import sys
import termios
from typing import Callable, Dict, List, Optional

from .edit_buffer import EditBuffer
from .history_nav import HistoryNavigator, HistorySearch, SearchState
from .key_decoder import (
    ESC_FOLLOWER_TIMEOUT,
    Char,
    Eof,
    Escape,
    Key,
    KeyDecoder,
    KeyEvent,
    Meta,
    Resize,
)
from .keybindings import EditMode, EmacsKeyBindings, KeyBindings, ViKeyBindings
from .line_renderer import LineRenderer
from .tab_completion import CompletionEngine, TerminalManager


class LineEditor:
    """Interactive line editor with vi/emacs key bindings, tab completion, and history search."""

    # Actions for the symbolic keys decoded by KeyDecoder (Key events).
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

    # Kill commands participate in readline's kill-ring coalescing: two
    # kills in a row (emacs mode only, like readline) merge into one ring
    # entry instead of pushing two (see EditBuffer._push_kill). Any other
    # command — movement, typing, yank, history — breaks the chain.
    KILL_ACTIONS = frozenset({
        'kill_line', 'kill_whole_line', 'kill_to_beginning',
        'kill_word_backward', 'kill_word_forward',
        'kill_word', 'backward_kill_word',
    })

    def __init__(self, history: Optional[List[str]] = None, edit_mode: str = 'emacs'):
        # The components: the buffer model, the renderer, and the
        # history navigator, which keeps the injected list reference —
        # it aliases shell state and grows between reads. The identity
        # check (not truthiness) matters: a session starts with an EMPTY
        # state.history, and `history or []` would silently substitute a
        # private list, leaving up-arrow/Ctrl-R blind to every command
        # recorded afterwards (reappraisal #15 K1).
        self.edit_buffer = EditBuffer()
        self.renderer = LineRenderer()
        self.history_nav = HistoryNavigator(
            history if history is not None else [])

        self.completion_engine = CompletionEngine()
        self.terminal = TerminalManager()
        self.completion_state = None
        self.current_prompt = ""

        # Key binding setup
        self.edit_mode = ''
        self.set_edit_mode(edit_mode)

        # The active incremental search session, if any (Ctrl-R)
        self.search: Optional[HistorySearch] = None

        # Vi specific state
        self.vi_repeat_count = ""

        # True while the PREVIOUS dispatched command was a kill — arms
        # the kill-ring coalescing for a directly following kill.
        self._last_action_was_kill = False

        # The sole reader of stdin; created fresh per read_line (the fd
        # and the ESC-disambiguation policy are bound at read time).
        self.decoder: Optional[KeyDecoder] = None

        # Action-name -> handler dispatch table (see _build_action_table)
        self._actions = self._build_action_table()

    # ------------------------------------------------------------------
    # History state delegation (the navigator owns position + stash;
    # these names are the editor's stable API for tests and embedders)
    # ------------------------------------------------------------------

    @property
    def history(self) -> List[str]:
        """The history list (aliases shell state)."""
        return self.history_nav.history

    @history.setter
    def history(self, value: List[str]) -> None:
        self.history_nav.history = value

    @property
    def history_pos(self) -> int:
        return self.history_nav.pos

    @history_pos.setter
    def history_pos(self, value: int) -> None:
        self.history_nav.pos = value

    @property
    def original_line(self) -> str:
        return self.history_nav.original_line

    @original_line.setter
    def original_line(self, value: str) -> None:
        self.history_nav.original_line = value

    @property
    def search_mode(self) -> bool:
        """True while a Ctrl-R incremental search is active."""
        return self.search is not None

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
        self.key_handler: KeyBindings
        if edit_mode == 'vi':
            self.key_handler = ViKeyBindings()
            self.mode = EditMode.VI_INSERT
        else:
            self.key_handler = EmacsKeyBindings()
            self.mode = EditMode.EMACS

    def read_line(self, prompt: str = "", sigwinch_fd: int = -1,
                   on_resize: Optional[Callable[[], None]] = None) -> Optional[str]:
        """Read a line with editing and key binding support.

        Args:
            prompt: The prompt string to display
            sigwinch_fd: File descriptor for SIGWINCH notifications (-1
                to disable); the KeyDecoder multiplexes it with stdin
                and yields Resize events
            on_resize: Optional callback invoked after a terminal resize redraw
        """
        self.edit_buffer.reset()
        self.history_nav.reset()
        self.completion_state = None
        self.current_prompt = prompt
        self.search = None
        self._last_action_was_kill = False
        self.renderer.update_width()

        # Paint the prompt (wrap-aware; strips \x01/\x02 markers)
        self._paint()

        # Reset vi mode to insert
        if self.edit_mode == 'vi':
            self.mode = EditMode.VI_INSERT
            if hasattr(self.key_handler, 'mode'):
                self.key_handler.mode = EditMode.VI_INSERT
            self.vi_repeat_count = ""

        # A fresh decoder per read, but characters the previous read
        # buffered without consuming (the tail of a multi-line paste)
        # are carried over so their commands run in turn, as readline
        # does — rather than being dropped. The ESC disambiguation
        # policy is a decoder TIMING knob set per mode here — vi probes
        # 50 ms because ESC is a key of its own; emacs blocks because
        # ESC is only ever a Meta/sequence prefix. What the resulting
        # events MEAN stays mode policy in _dispatch_escape_event.
        carryover = self.decoder.take_buffered() if self.decoder is not None else []
        self.decoder = KeyDecoder(
            sys.stdin.fileno(),
            sigwinch_fd=sigwinch_fd if sigwinch_fd >= 0 else None,
            esc_timeout=ESC_FOLLOWER_TIMEOUT if self.edit_mode == 'vi' else None,
        )
        self.decoder.seed(carryover)

        with self.terminal:
            while True:
                try:
                    event = self.decoder.read_key()
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

                if isinstance(event, Eof):
                    return None

                if isinstance(event, Resize):
                    self.redraw_line()
                    if on_resize:
                        on_resize()
                    continue

                if isinstance(event, Char):
                    # Handle search mode input
                    if self.search is not None and self._handle_search_char(event.char):
                        continue
                    result = self._dispatch_char(event.char)
                else:
                    result = self._dispatch_escape_event(event)

                if result == 'accept':
                    self.renderer.finish_line()
                    # History is recorded by ONE writer — the
                    # source processor (shell.add_history), which
                    # sees the complete logical command.  self.history
                    # aliases state.history, so the entry is visible
                    # for Up-arrow recall at the next read_line.
                    return self.edit_buffer.text
                elif result == 'eof':
                    self.renderer.finish_line()
                    return None

    def _dispatch_char(self, char: str) -> Optional[str]:
        """Dispatch one literal character through the key bindings.

        Returns the action result ('accept', 'eof' or None) so the main
        loop can finish the line. Also the re-entry point for the
        follower of a vi-mode Meta event (see _dispatch_escape_event).
        """
        action = self._get_key_action(char)
        if action:
            return self._execute_action(action, char)
        if ord(char) >= 32:  # Printable character
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
                self._last_action_was_kill = False  # typing breaks the kill chain
        return None

    def _get_key_action(self, char: str) -> Optional[str]:
        """Mode-appropriate binding lookup for a literal key.

        ESC never reaches here: the KeyDecoder resolves every
        ESC-introduced byte run into a Key/Meta/Escape event before the
        editor sees it (see _dispatch_escape_event), so escape
        sequences behave identically in every mode and partial
        sequences never leak into the edit buffer.

        ``key_handler`` always matches ``edit_mode`` (set together in
        set_edit_mode), so its polymorphic ``get_action`` already does the
        right thing: ViKeyBindings dispatches on vi-normal/insert, and the base
        (emacs) ``get_action`` IS ``bindings.get``.
        """
        return self.key_handler.get_action(char)

    def _dispatch_escape_event(self, event: KeyEvent) -> Optional[str]:
        """Give an ESC-introduced KeyEvent its mode-dependent MEANING.

        The decoder reported what arrived (Key/Meta/Escape); this is
        the policy layer deciding what it means:

        - Key(name): the symbolic keys map to the same action in emacs
          mode and both vi modes (bash agrees: arrows move the cursor /
          walk history everywhere). Key(None) — a complete but
          unrecognized sequence — is ignored.
        - Escape (bare ESC): vi enters normal mode; emacs has no
          bare-ESC binding (with esc_timeout=None the decoder never
          produces one).
        - Meta(c) in vi: enter normal mode, then run c as a normal-mode
          command. Meta(c) in emacs: the Meta/Alt combination.

        An active incremental search is accepted first, matching the
        pre-decoder behavior where the raw ESC byte fell through
        _handle_search_char via _accept_search before escape resolution.
        """
        if self.search is not None:
            self._accept_search()

        if isinstance(event, Key):
            # Key(None) is a complete but unrecognized sequence: no action.
            action = self.ESCAPE_KEY_ACTIONS.get(event.name) if event.name else None
            return self._execute_action(action, '\x1b') if action else None

        if isinstance(event, Escape):
            if self.edit_mode == 'vi':
                return self._execute_action('enter_normal_mode', '\x1b')
            return None

        assert isinstance(event, Meta)
        if self.edit_mode == 'vi':
            self._execute_action('enter_normal_mode', '\x1b')
            if event.char == '\x1b':
                # ESC ESC: the second ESC needs full disambiguation (it
                # may introduce a sequence of its own) — hand it back to
                # the decoder instead of dispatching it as a key.
                assert self.decoder is not None
                self.decoder.pushback(event.char)
                return None
            return self._dispatch_char(event.char)

        action = self.key_handler.meta_bindings.get(event.char)
        return self._execute_action(action, '\x1b') if action else None

    # ------------------------------------------------------------------
    # Action dispatch: binding NAME -> handler, via one table
    # ------------------------------------------------------------------

    def _build_action_table(self) -> Dict[str, Callable[[str], Optional[str]]]:
        """Map every key-binding action name to its handler.

        Every handler takes the triggering character and returns the
        action result ('accept', 'eof' or None). Most operations don't
        care which key invoked them; ``op`` adapts those zero-argument
        methods (their bool return — "did anything change" — is a
        repaint signal, not an action result). The totality guard test
        asserts every name bound in keybindings.py resolves here.
        """
        def op(method: Callable[[], object]) -> Callable[[str], Optional[str]]:
            def handler(char: str) -> Optional[str]:
                method()
                return None
            return handler

        return {
            # Movement
            'move_beginning_of_line': op(self._move_home),
            'move_end_of_line': op(self._move_end),
            'move_forward_char': op(self._move_right),
            'move_backward_char': op(self._move_left),
            'move_word_forward': op(self._move_word_forward),
            'move_word_backward': op(self._move_word_backward),
            'forward_word': op(self._forward_word),
            'backward_word': op(self._backward_word),

            # Editing
            'delete_char': self._delete_char_action,
            'backward_delete_char': op(self._backspace),
            'kill_line': op(self._kill_line),
            'kill_whole_line': op(self._kill_whole_line),
            'kill_to_beginning': op(self._kill_to_beginning),
            'kill_word_backward': op(self._kill_word_backward),
            'kill_word_forward': op(self._kill_word_forward),
            'kill_word': op(self._kill_word),
            'backward_kill_word': op(self._backward_kill_word),
            'yank': op(self._yank),
            'transpose_chars': op(self._transpose_chars),

            # History
            'previous_history': op(self._history_up),
            'next_history': op(self._history_down),
            'reverse_search_history': op(self._start_reverse_search),
            'move_to_first_history': op(self._history_first),
            'move_to_last_history': op(self._history_last),

            # Vi mode transitions
            'enter_normal_mode': op(self._enter_vi_normal_mode),
            'enter_insert_mode': op(self._enter_vi_insert_mode),
            'enter_insert_mode_at_beginning': op(self._vi_insert_at_beginning),
            'append_mode': op(self._vi_append),
            'append_mode_at_end': op(self._vi_append_at_end),

            # Undo / redo
            'undo': op(self.undo),
            'redo': op(self.redo),

            # Other
            'complete': op(self._handle_tab),
            'accept_line': self._accept_line_action,
            'interrupt': op(self._handle_interrupt),
            'clear_screen': op(self._clear_screen),
            'abort': op(self._abort_action),
        }

    def _execute_action(self, action: str, char: str) -> Optional[str]:
        """Execute a key binding action by name (unknown names are
        ignored, as the old elif chain ignored them).

        Also tracks the kill chain: when a kill command directly follows
        another kill, EditBuffer's ring coalescing is armed so the two
        kills merge into one yankable entry. readline coalesces in emacs
        mode only (``_rl_last_command_was_kill && rl_editing_mode !=
        vi_mode``), and so does psh."""
        handler = self._actions.get(action)
        if handler is None:
            return None
        is_kill = action in self.KILL_ACTIONS
        self.edit_buffer.coalesce_next_kill = (
            is_kill and self._last_action_was_kill
            and self.edit_mode == 'emacs')
        result = handler(char)
        self._last_action_was_kill = is_kill
        return result

    def _delete_char_action(self, char: str) -> Optional[str]:
        """delete_char, except Ctrl-D on an empty line means EOF (the
        Delete KEY arrives as char ESC and never does)."""
        if not self.edit_buffer.chars and char == '\x04':
            return 'eof'
        self._delete_char()
        return None

    def _accept_line_action(self, char: str) -> Optional[str]:
        return 'accept'

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

    # ------------------------------------------------------------------
    # Edit operations: EditBuffer mutates, LineRenderer repaints
    # ------------------------------------------------------------------

    def _insert_char(self, char: str):
        """Insert a character at the cursor position."""
        self.edit_buffer.insert(char)
        if (self.edit_buffer.cursor == len(self.edit_buffer)
                and not self.renderer.at_wrap_boundary(len(self.edit_buffer))):
            # Fast path: appending before the right margin — just echo.
            self.renderer.echo_char(char, self.edit_buffer.cursor)
        else:
            # Mid-line insert or wrap boundary: full wrap-aware repaint.
            self._redraw()

    def _backspace(self):
        """Delete character before cursor."""
        if self.edit_buffer.delete_backward():
            self._redraw()

    def _delete_char(self):
        """Delete character at cursor."""
        if self.edit_buffer.delete_forward():
            self._redraw()

    def _move_left(self):
        """Move cursor left."""
        if self.edit_buffer.move_left():
            self._move_cursor_to(self.edit_buffer.cursor)

    def _move_right(self):
        """Move cursor right."""
        if self.edit_buffer.move_right():
            self._move_cursor_to(self.edit_buffer.cursor)

    def _move_home(self):
        """Move cursor to beginning of line."""
        if self.edit_buffer.move_home():
            self._move_cursor_to(self.edit_buffer.cursor)

    def _move_end(self):
        """Move cursor to end of line."""
        if self.edit_buffer.move_end():
            self._move_cursor_to(self.edit_buffer.cursor)

    def _move_word_forward(self):
        """Move cursor forward by one word."""
        if self.edit_buffer.move_word_forward():
            self._move_cursor_to(self.edit_buffer.cursor)

    def _move_word_backward(self):
        """Move cursor backward by one word."""
        if self.edit_buffer.move_word_backward():
            self._move_cursor_to(self.edit_buffer.cursor)

    def _forward_word(self):
        """Move to the end of the next word (M-f, alnum boundaries)."""
        if self.edit_buffer.forward_word():
            self._move_cursor_to(self.edit_buffer.cursor)

    def _backward_word(self):
        """Move to the start of the previous word (M-b, alnum boundaries)."""
        if self.edit_buffer.backward_word():
            self._move_cursor_to(self.edit_buffer.cursor)

    def _kill_line(self):
        """Kill from cursor to end of line."""
        if self.edit_buffer.kill_to_end():
            self._redraw()

    def _kill_whole_line(self):
        """Kill the entire line."""
        self.edit_buffer.kill_whole_line()
        self._redraw()

    def _kill_to_beginning(self):
        """Kill from the cursor back to the start of the line (unix-line-discard)."""
        if self.edit_buffer.kill_to_beginning():
            self._redraw()

    def _kill_word_backward(self):
        """Kill the word before cursor."""
        if self.edit_buffer.kill_word_backward():
            self._redraw()

    def _kill_word_forward(self):
        """Kill the word after cursor."""
        if self.edit_buffer.kill_word_forward():
            self._redraw()

    def _kill_word(self):
        """Kill to the end of the next word (M-d, alnum boundaries)."""
        if self.edit_buffer.kill_word():
            self._redraw()

    def _backward_kill_word(self):
        """Kill to the start of the previous word (M-DEL, alnum boundaries)."""
        if self.edit_buffer.backward_kill_word():
            self._redraw()

    def _yank(self):
        """Yank (paste) from kill ring."""
        if self.edit_buffer.yank():
            self._redraw()

    def _transpose_chars(self):
        """Transpose characters around cursor."""
        if self.edit_buffer.transpose():
            self._redraw()

    # ------------------------------------------------------------------
    # History browsing: the navigator computes, the editor applies
    # ------------------------------------------------------------------

    def _history_up(self):
        """Move up in history."""
        text = self.history_nav.up(self.edit_buffer.text)
        if text is not None:
            self._replace_line(text)
            self._redraw()

    def _history_down(self):
        """Move down in history."""
        text = self.history_nav.down()
        if text is not None:
            self._replace_line(text)
            self._redraw()

    def _history_first(self):
        """Move to first history entry."""
        text = self.history_nav.first(self.edit_buffer.text)
        if text is not None:
            self._replace_line(text)
            self._redraw()

    def _history_last(self):
        """Move to last history entry (current line)."""
        text = self.history_nav.last()
        if text is not None:
            self._replace_line(text)
            self._redraw()

    # ------------------------------------------------------------------
    # Incremental search: HistorySearch decides, the editor renders
    # ------------------------------------------------------------------

    def _start_reverse_search(self):
        """Start reverse history search mode (Ctrl-R)."""
        self.search = HistorySearch(self.history_nav.history,
                                    self.history_nav.pos,
                                    self.history_nav.original_line)
        self._apply_search_state(self.search.start())

    def _handle_search_char(self, char: str) -> bool:
        """Feed one character to the active search; returns False when
        the character must still be dispatched normally (an unbound
        control character accepts the search, then acts)."""
        assert self.search is not None
        state = self.search.feed(char)
        self._apply_search_state(state)
        return not state.redispatch

    def _accept_search(self):
        """Accept the current search result (Enter, or any
        ESC-introduced event during a search)."""
        if self.search is not None:
            self._apply_search_state(self.search.accept())

    def _abort_search(self):
        """Abort the search and restore the pre-search state (Ctrl-G)."""
        if self.search is not None:
            self._apply_search_state(self.search.abort())

    def _apply_search_state(self, state: SearchState) -> None:
        """Render a SearchState: sync the browse position, update the
        buffer, and repaint (with the search prompt while active)."""
        self.history_nav.pos = state.history_pos
        if not state.repaint:
            return
        if state.status == 'active':
            if state.line is not None:
                self.edit_buffer.chars = list(state.line)
                self.edit_buffer.cursor = state.cursor
            self._redraw(state.prompt)
        else:
            # accepted or aborted: leave search mode; the buffer takes
            # the result (cursor at end), painted under the normal prompt
            self.search = None
            if state.line is not None:
                self._replace_line(state.line)
            self._redraw()

    # ------------------------------------------------------------------
    # Vi mode transitions
    # ------------------------------------------------------------------

    def _enter_vi_normal_mode(self):
        """Enter vi normal mode."""
        if self.mode != EditMode.VI_NORMAL:
            self.mode = EditMode.VI_NORMAL
            self.key_handler.mode = EditMode.VI_NORMAL
            # Move cursor back one position (vi behavior)
            if self.edit_buffer.cursor > 0:
                self._move_left()

    def _enter_vi_insert_mode(self):
        """Enter vi insert mode."""
        self.mode = EditMode.VI_INSERT
        self.key_handler.mode = EditMode.VI_INSERT

    def _vi_insert_at_beginning(self):
        """Vi 'I': insert mode at the beginning of the line."""
        self._move_home()
        self._enter_vi_insert_mode()

    def _vi_append(self):
        """Vi 'a': insert mode after the cursor."""
        self._move_right()
        self._enter_vi_insert_mode()

    def _vi_append_at_end(self):
        """Vi 'A': insert mode at the end of the line."""
        self._move_end()
        self._enter_vi_insert_mode()

    # ------------------------------------------------------------------
    # Rendering delegation (the renderer owns the terminal)
    # ------------------------------------------------------------------

    def _paint(self, prompt: Optional[str] = None):
        """Paint prompt + buffer from the prompt origin (see
        LineRenderer.paint)."""
        if prompt is None:
            prompt = self.current_prompt
        self.renderer.paint(prompt, self.edit_buffer.text,
                            self.edit_buffer.cursor)

    def _redraw(self, prompt: Optional[str] = None):
        """Repaint after an edit (see LineRenderer.redraw)."""
        if prompt is None:
            prompt = self.current_prompt
        self.renderer.redraw(prompt, self.edit_buffer.text,
                             self.edit_buffer.cursor)

    def _move_cursor_to(self, pos: int):
        """Move the physical cursor to buffer position *pos*."""
        self.renderer.move_cursor_to(pos)

    def redraw_line(self):
        """Redraw the prompt and input line in place after a terminal
        resize (SIGWINCH; see LineRenderer.redraw_after_resize)."""
        self.renderer.redraw_after_resize(self.current_prompt,
                                          self.edit_buffer.text,
                                          self.edit_buffer.cursor)

    def _clear_screen(self):
        """Clear screen and redraw current line."""
        self.renderer.clear_screen(self.current_prompt,
                                   self.edit_buffer.text,
                                   self.edit_buffer.cursor)

    def _handle_interrupt(self):
        """Handle Ctrl-C interrupt."""
        # Clear line and raise KeyboardInterrupt
        self.renderer.show_interrupt()
        raise KeyboardInterrupt()

    def _abort_action(self):
        """Abort current action (Ctrl-G in emacs)."""
        # Just beep for now
        self.renderer.bell()

    # ------------------------------------------------------------------
    # Completion UI (deliberately in the coordinator: it glues
    # CompletionEngine, TerminalManager and the renderer together)
    # ------------------------------------------------------------------

    def _handle_tab(self):
        """Handle tab completion."""
        line = self.edit_buffer.text
        cursor = self.edit_buffer.cursor

        # Get completions AND the word boundary in one prefix scan; reuse
        # word_start below and in _apply_completion so the whole Tab press
        # computes find_word_start exactly once.
        word_start, completions = self.completion_engine.get_completions(line, cursor)

        if not completions:
            # No completions, just beep
            self.renderer.bell()
            return

        if len(completions) == 1:
            # Single completion - use it. bash finishes a UNIQUE match with a
            # trailing space, so the cursor is ready for the next word — except
            # a directory, which keeps its trailing '/' (no space) so you can
            # keep descending. Directory completions already carry the
            # separator; add the space only for non-directory matches.
            only = completions[0]
            self._apply_completion(only, word_start,
                                   add_trailing_space=not only.endswith(os.sep))
        else:
            # Multiple completions
            common_prefix = self.completion_engine.find_common_prefix(completions)
            current_word = line[word_start:cursor]

            if len(common_prefix) > len(current_word):
                # Can expand to common prefix
                self._apply_completion(common_prefix, word_start)
            else:
                # Show all completions
                self._show_completions(completions)

    def _apply_completion(self, completion: str, word_start: int,
                          add_trailing_space: bool = False):
        """Apply a completion to the current line.

        ``word_start`` is the boundary already computed by the caller (the one
        prefix scan per Tab press). ``add_trailing_space`` finishes a unique
        non-directory match with a space, matching bash. It applies only
        outside quotes (the quoted path does not escape or close the quote
        here, so leaving it untouched keeps that partial behavior unchanged).
        """
        line = self.edit_buffer.text
        cursor = self.edit_buffer.cursor

        # Check if we need to escape the completion
        if word_start == 0 or line[word_start-1] not in '"\'':
            # Not in quotes, escape special characters
            completion = self.completion_engine.escape_path(completion)
            if add_trailing_space:
                completion += ' '

        # Update buffer and cursor position, then repaint (wrap-aware)
        new_line = line[:word_start] + completion
        if cursor < len(line):
            new_line += line[cursor:]

        self.edit_buffer.chars = list(new_line)
        self.edit_buffer.cursor = word_start + len(completion)
        self._redraw()

    def _show_completions(self, completions: List[str]):
        """Display multiple completions below the line, then repaint.

        Raw-mode toggling is terminal CONTROL and stays here (the
        editor owns TerminalManager); the writes go via the renderer.
        """
        # Save current line
        self.terminal.exit_raw_mode()

        # Display completions
        self.renderer.newline()
        self.renderer.display_in_columns(completions)

        # Redraw prompt and current line
        self.terminal.enter_raw_mode()
        self.renderer.newline()
        self._paint()

    def _replace_line(self, new_line: str):
        """Replace the current line with new text."""
        self.edit_buffer.replace_all(new_line)

    # ------------------------------------------------------------------
    # Undo/redo triggering (the stacks live in EditBuffer)
    # ------------------------------------------------------------------

    def undo(self):
        """Undo last change."""
        if self.edit_buffer.undo():
            self._redraw()

    def redo(self):
        """Redo last undone change."""
        if self.edit_buffer.redo():
            self._redraw()
