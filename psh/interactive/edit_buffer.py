"""Pure line-editing model: text + cursor, kill ring, undo/redo.

EditBuffer is the single source of truth for the line being edited.
It knows nothing about terminals, key bindings, or history — every
operation is a pure state transition on (chars, cursor), so the whole
class is unit-testable without a tty (Textbook B8, Release 1).

Mutating operations return True when state actually changed, which is
exactly the signal the LineEditor needs to decide whether to repaint.
The text is stored as a list of single characters: honest about the
O(n) cost of mid-line edits, and trivially correct.

Undo policy: each mutating operation snapshots the PRE-edit state via
save_undo_state() (deduplicated, so repeated snapshots of the same
state collapse). undo() treats the live buffer as the implicit top of
the stack; any new edit clears the redo stack.
"""

from typing import List, Tuple


class EditBuffer:
    """Text + cursor model with kill ring and undo/redo stacks."""

    def __init__(self) -> None:
        self.chars: List[str] = []
        self.cursor: int = 0
        self.kill_ring: List[str] = []
        # readline kill-ring coalescing: when the PREVIOUS edit command
        # was also a kill, the LineEditor arms this flag before
        # dispatching the next one and the killed text merges into the
        # top ring entry (append for forward kills, prepend for backward
        # kills) instead of pushing a new entry. The editor rewrites the
        # flag before every dispatched command; direct EditBuffer users
        # set it explicitly (default: no coalescing).
        self.coalesce_next_kill: bool = False
        self.undo_stack: List[Tuple[str, int]] = []
        self.redo_stack: List[Tuple[str, int]] = []
        self.save_undo_state()

    @property
    def text(self) -> str:
        """The buffer contents as a string."""
        return ''.join(self.chars)

    def __len__(self) -> int:
        return len(self.chars)

    def reset(self) -> None:
        """Empty the buffer for a fresh read (stacks are kept: undo
        history deliberately survives across reads, as it always has)."""
        self.chars = []
        self.cursor = 0

    # ------------------------------------------------------------------
    # Insert / delete
    # ------------------------------------------------------------------

    def insert(self, char: str) -> None:
        """Insert *char* at the cursor; cursor advances past it."""
        self.save_undo_state()
        self.chars.insert(self.cursor, char)
        self.cursor += 1

    def delete_backward(self) -> bool:
        """Backspace: delete the character before the cursor."""
        if self.cursor <= 0:
            return False
        self.save_undo_state()
        self.cursor -= 1
        del self.chars[self.cursor]
        return True

    def delete_forward(self) -> bool:
        """Delete the character at the cursor."""
        if self.cursor >= len(self.chars):
            return False
        self.save_undo_state()
        del self.chars[self.cursor]
        return True

    def replace_all(self, text: str) -> None:
        """Replace the whole line (history recall / search accept);
        cursor moves to end. Not an undoable edit, matching readline."""
        self.chars = list(text)
        self.cursor = len(self.chars)

    # ------------------------------------------------------------------
    # Movement (pure cursor changes; True if the cursor moved)
    # ------------------------------------------------------------------

    def move_left(self) -> bool:
        if self.cursor <= 0:
            return False
        self.cursor -= 1
        return True

    def move_right(self) -> bool:
        if self.cursor >= len(self.chars):
            return False
        self.cursor += 1
        return True

    def move_home(self) -> bool:
        if self.cursor <= 0:
            return False
        self.cursor = 0
        return True

    def move_end(self) -> bool:
        if self.cursor >= len(self.chars):
            return False
        self.cursor = len(self.chars)
        return True

    def move_word_forward(self) -> bool:
        """Forward past the current word, then any following spaces."""
        pos = self.cursor
        while pos < len(self.chars) and not self.chars[pos].isspace():
            pos += 1
        while pos < len(self.chars) and self.chars[pos].isspace():
            pos += 1
        if pos == self.cursor:
            return False
        self.cursor = pos
        return True

    def move_word_backward(self) -> bool:
        """Backward over any spaces, then to the start of the word."""
        pos = self.cursor
        while pos > 0 and self.chars[pos - 1].isspace():
            pos -= 1
        while pos > 0 and not self.chars[pos - 1].isspace():
            pos -= 1
        if pos == self.cursor:
            return False
        self.cursor = pos
        return True

    # ------------------------------------------------------------------
    # Meta word commands (alnum boundaries)
    #
    # readline's M-f/M-b/M-d/M-DEL treat a word as a run of ALPHANUMERIC
    # characters (str.isalnum() — UTF-8 accented letters stay in-word),
    # so ``aa.bb`` is two words. The whitespace-based operations above
    # stay for C-w (unix-word-rubout) and vi's w/b, which really are
    # whitespace-delimited. Pinned to bash 5.2 by
    # tests/unit/interactive/test_edit_buffer_killring.py.
    # ------------------------------------------------------------------

    def _forward_word_target(self) -> int:
        """Where forward-word lands: past any non-alnum characters, then
        to the END of the next alnum run (readline, unlike
        move_word_forward which stops at the START of the next word)."""
        pos = self.cursor
        while pos < len(self.chars) and not self.chars[pos].isalnum():
            pos += 1
        while pos < len(self.chars) and self.chars[pos].isalnum():
            pos += 1
        return pos

    def _backward_word_target(self) -> int:
        """Where backward-word lands: back over any non-alnum characters,
        then to the START of the previous alnum run."""
        pos = self.cursor
        while pos > 0 and not self.chars[pos - 1].isalnum():
            pos -= 1
        while pos > 0 and self.chars[pos - 1].isalnum():
            pos -= 1
        return pos

    def forward_word(self) -> bool:
        """Move to the end of the next word (readline forward-word, M-f)."""
        pos = self._forward_word_target()
        if pos == self.cursor:
            return False
        self.cursor = pos
        return True

    def backward_word(self) -> bool:
        """Move to the start of the previous word (readline backward-word,
        M-b)."""
        pos = self._backward_word_target()
        if pos == self.cursor:
            return False
        self.cursor = pos
        return True

    # ------------------------------------------------------------------
    # Kill / yank
    # ------------------------------------------------------------------

    def _push_kill(self, text: str, forward: bool) -> None:
        """Record killed text on the kill ring (readline rules).

        A kill immediately following another kill coalesces into the top
        ring entry — a forward kill (C-k, M-d) APPENDS, a backward kill
        (C-w, C-u, M-DEL) PREPENDS — so C-w C-w C-y restores
        ``alpha beta``, not just ``alpha ``. Whether this kill is
        "consecutive" is the editor's call (coalesce_next_kill); any
        non-kill command in between breaks the chain."""
        if self.coalesce_next_kill and self.kill_ring:
            if forward:
                self.kill_ring[-1] += text
            else:
                self.kill_ring[-1] = text + self.kill_ring[-1]
        else:
            self.kill_ring.append(text)

    def kill_to_end(self) -> bool:
        """Kill from cursor to end of line (Ctrl-K)."""
        if self.cursor >= len(self.chars):
            return False
        self.save_undo_state()
        self._push_kill(''.join(self.chars[self.cursor:]), forward=True)
        self.chars = self.chars[:self.cursor]
        return True

    def kill_whole_line(self) -> None:
        """Kill the entire line. Unconditional: an empty kill still pushes ''
        onto the ring, as it always has."""
        self.save_undo_state()
        self._push_kill(''.join(self.chars), forward=True)
        self.chars = []
        self.cursor = 0

    def kill_to_beginning(self) -> bool:
        """Kill from the cursor back to the start of the line (readline
        ``unix-line-discard`` / Ctrl-U). Text after the cursor is preserved
        (this is NOT kill-whole-line)."""
        if self.cursor <= 0:
            return False
        self.save_undo_state()
        self._push_kill(''.join(self.chars[:self.cursor]), forward=False)
        self.chars = self.chars[self.cursor:]
        self.cursor = 0
        return True

    def kill_word_backward(self) -> bool:
        """Kill spaces then the word before the cursor (Ctrl-W,
        whitespace-delimited unix-word-rubout)."""
        if self.cursor <= 0:
            return False
        self.save_undo_state()
        start = self.cursor
        while self.cursor > 0 and self.chars[self.cursor - 1].isspace():
            self.cursor -= 1
        while self.cursor > 0 and not self.chars[self.cursor - 1].isspace():
            self.cursor -= 1
        self._push_kill(''.join(self.chars[self.cursor:start]), forward=False)
        del self.chars[self.cursor:start]
        return True

    def kill_word_forward(self) -> bool:
        """Kill the whitespace-delimited word after the cursor, then
        trailing spaces (historical psh binding; readline's M-d is
        kill_word below)."""
        if self.cursor >= len(self.chars):
            return False
        self.save_undo_state()
        start = self.cursor
        while (self.cursor < len(self.chars)
               and not self.chars[self.cursor].isspace()):
            self.cursor += 1
        while (self.cursor < len(self.chars)
               and self.chars[self.cursor].isspace()):
            self.cursor += 1
        self._push_kill(''.join(self.chars[start:self.cursor]), forward=True)
        del self.chars[start:self.cursor]
        self.cursor = start
        return True

    def kill_word(self) -> bool:
        """Kill to the end of the next word (readline kill-word, M-d;
        alnum boundaries)."""
        end = self._forward_word_target()
        if end == self.cursor:
            return False
        self.save_undo_state()
        self._push_kill(''.join(self.chars[self.cursor:end]), forward=True)
        del self.chars[self.cursor:end]
        return True

    def backward_kill_word(self) -> bool:
        """Kill to the start of the previous word (readline
        backward-kill-word, M-DEL; alnum boundaries — on ``aa.bb`` it
        kills just ``bb``, where C-w kills all of ``aa.bb``)."""
        start = self._backward_word_target()
        if start == self.cursor:
            return False
        self.save_undo_state()
        self._push_kill(''.join(self.chars[start:self.cursor]), forward=False)
        del self.chars[start:self.cursor]
        self.cursor = start
        return True

    def yank(self) -> bool:
        """Insert the most recent kill at the cursor (Ctrl-Y)."""
        if not self.kill_ring:
            return False
        self.save_undo_state()
        for char in self.kill_ring[-1]:
            self.chars.insert(self.cursor, char)
            self.cursor += 1
        return True

    # ------------------------------------------------------------------
    # Transpose
    # ------------------------------------------------------------------

    def transpose(self) -> bool:
        """Transpose characters around the cursor (readline ``transpose-chars``
        / Ctrl-T). bash semantics: at beginning-of-line it is a no-op (readline
        rings the bell); at end-of-line it transposes the two characters BEFORE
        point (point unchanged); otherwise it drags the char before point
        forward over the char at point, advancing point by one."""
        if len(self.chars) < 2 or self.cursor == 0:
            return False
        self.save_undo_state()
        if self.cursor >= len(self.chars):
            # End-of-line: swap the last two characters; point stays at end.
            pos = len(self.chars) - 1
            self.chars[pos - 1], self.chars[pos] = (
                self.chars[pos], self.chars[pos - 1])
        else:
            # Swap the char before point with the char at point, advance point.
            self.chars[self.cursor - 1], self.chars[self.cursor] = (
                self.chars[self.cursor], self.chars[self.cursor - 1])
            self.cursor += 1
        return True

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------

    def save_undo_state(self) -> None:
        """Snapshot the current state (deduplicated). Any edit that
        pushes a genuinely new state invalidates the redo branch."""
        state = (self.text, self.cursor)
        if not self.undo_stack or self.undo_stack[-1] != state:
            self.undo_stack.append(state)
            self.redo_stack.clear()

    def undo(self) -> bool:
        """Undo the last change; True if a state was restored.

        The live buffer is the implicit top of the stack: if it differs
        from the last saved state, undoing first parks it on the redo
        stack (otherwise the most recent edit would be skipped).
        """
        current = (self.text, self.cursor)
        if self.undo_stack and self.undo_stack[-1] != current:
            self.redo_stack.append(current)
        elif len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
        else:
            return False
        text, pos = self.undo_stack[-1]
        self.chars = list(text)
        self.cursor = pos
        return True

    def redo(self) -> bool:
        """Redo the last undone change; True if a state was restored."""
        if not self.redo_stack:
            return False
        state = self.redo_stack.pop()
        self.undo_stack.append(state)
        text, pos = state
        self.chars = list(text)
        self.cursor = pos
        return True
