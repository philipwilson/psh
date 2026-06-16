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
    # Kill / yank
    # ------------------------------------------------------------------

    def kill_to_end(self) -> bool:
        """Kill from cursor to end of line (Ctrl-K)."""
        if self.cursor >= len(self.chars):
            return False
        self.save_undo_state()
        self.kill_ring.append(''.join(self.chars[self.cursor:]))
        self.chars = self.chars[:self.cursor]
        return True

    def kill_whole_line(self) -> None:
        """Kill the entire line. Unconditional: an empty kill still pushes ''
        onto the ring, as it always has."""
        self.save_undo_state()
        self.kill_ring.append(''.join(self.chars))
        self.chars = []
        self.cursor = 0

    def kill_to_beginning(self) -> bool:
        """Kill from the cursor back to the start of the line (readline
        ``unix-line-discard`` / Ctrl-U). Text after the cursor is preserved
        (this is NOT kill-whole-line)."""
        if self.cursor <= 0:
            return False
        self.save_undo_state()
        self.kill_ring.append(''.join(self.chars[:self.cursor]))
        self.chars = self.chars[self.cursor:]
        self.cursor = 0
        return True

    def kill_word_backward(self) -> bool:
        """Kill spaces then the word before the cursor (Ctrl-W)."""
        if self.cursor <= 0:
            return False
        self.save_undo_state()
        start = self.cursor
        while self.cursor > 0 and self.chars[self.cursor - 1].isspace():
            self.cursor -= 1
        while self.cursor > 0 and not self.chars[self.cursor - 1].isspace():
            self.cursor -= 1
        self.kill_ring.append(''.join(self.chars[self.cursor:start]))
        del self.chars[self.cursor:start]
        return True

    def kill_word_forward(self) -> bool:
        """Kill the word after the cursor, then trailing spaces (M-d)."""
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
        self.kill_ring.append(''.join(self.chars[start:self.cursor]))
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
