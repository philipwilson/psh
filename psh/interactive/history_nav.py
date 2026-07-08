"""History navigation and incremental reverse search for the line editor.

Both classes here are PURE against an injected history list reference
(the editor's history aliases shell state and grows between reads):
they own browse/search STATE and compute what the buffer should show,
but never touch the terminal or the EditBuffer themselves (Textbook B8,
Release 3).

- HistoryNavigator owns the browse position and the stashed in-progress
  line; each movement returns the text the buffer should display (or
  None for "no move"), and the editor applies it via
  EditBuffer.replace_all + repaint.

- HistorySearch is the Ctrl-R incremental-search state machine. The
  editor feeds it one character at a time; each feed returns a
  SearchState describing exactly what to render (search prompt, buffer
  line, cursor) and whether the search is still active. The editor
  renders the state via LineRenderer's prompt-override repaint and
  decides mode transitions — the machine itself never draws.
"""

from dataclasses import dataclass
from typing import List, Literal, Optional

from .line_editor_helpers import convert_multiline_to_single


class HistoryNavigator:
    """Up/down/first/last browsing over an injected history list.

    Owns ``pos`` (the browse position; ``len(history)`` means "at the
    bottom", i.e. the in-progress line) and ``original_line`` (the
    in-progress line stashed when the user first leaves the bottom, so
    Down/Meta-> can restore it). ``reset()`` re-anchors at the bottom
    for each new read — the injected list reference is kept, because it
    aliases shell state and grows between reads.

    Movement methods return the text the buffer should show, or None
    when there is nothing to move to (the editor then does nothing —
    no repaint). Multi-line history entries are returned in their
    single-line editable form for up/down, exactly as before.
    """

    def __init__(self, history: List[str]) -> None:
        self.history = history
        self.pos: int = len(history)
        self.original_line: str = ""

    def reset(self) -> None:
        """Re-anchor at the bottom of history (start of each read)."""
        self.pos = len(self.history)
        self.original_line = ""

    @staticmethod
    def _editable(entry: str) -> str:
        """Multi-line commands edit as a single line with separators."""
        if '\n' in entry:
            return convert_multiline_to_single(entry)
        return entry

    def up(self, current_text: str) -> Optional[str]:
        """Move to the previous (older) entry; stash *current_text* as
        the original line when leaving the bottom."""
        if self.pos <= 0:
            return None
        if self.pos == len(self.history):
            self.original_line = current_text
        self.pos -= 1
        return self._editable(self.history[self.pos])

    def down(self) -> Optional[str]:
        """Move to the next (newer) entry; the bottom restores the
        stashed original line."""
        if self.pos >= len(self.history):
            return None
        self.pos += 1
        if self.pos == len(self.history):
            return self.original_line
        return self._editable(self.history[self.pos])

    def first(self, current_text: str) -> Optional[str]:
        """Jump to the oldest entry (Meta-<)."""
        if not self.history or self.pos <= 0:
            return None
        if self.pos == len(self.history):
            self.original_line = current_text
        self.pos = 0
        return self.history[0]

    def last(self) -> Optional[str]:
        """Jump back to the bottom (Meta->), restoring the original
        line."""
        if self.pos >= len(self.history):
            return None
        self.pos = len(self.history)
        return self.original_line


SearchStatus = Literal['active', 'accepted', 'aborted']


@dataclass(frozen=True)
class SearchState:
    """What the editor should render after feeding the search machine.

    - ``status``: 'active' (still searching), 'accepted' (leave search
      mode keeping the match), or 'aborted' (leave search mode
      restoring the pre-search line).
    - ``prompt``: the search prompt to paint while active (e.g.
      ``(reverse-i-search)`ls': ``); None means the normal prompt.
    - ``line``: the buffer text to show; None means "leave the buffer
      untouched" (no match landed yet, or nothing to restore).
    - ``cursor``: the cursor position within ``line`` while active
      (just past the matched text); for accepted/aborted states the
      editor uses EditBuffer.replace_all, which puts the cursor at the
      end.
    - ``repaint``: False when nothing changed (boundary Ctrl-R/Ctrl-S,
      backspace on an empty pattern) — the editor skips the redraw,
      matching the old in-editor behavior exactly.
    - ``redispatch``: True when an unbound control character accepted
      the search; the editor must then dispatch that character
      normally (e.g. Ctrl-A accepts the match, then moves home).
    """

    prompt: Optional[str]
    line: Optional[str]
    cursor: int
    status: SearchStatus
    history_pos: int
    repaint: bool = True
    redispatch: bool = False


class HistorySearch:
    """The Ctrl-R incremental reverse-search state machine.

    One instance per search session: constructed with the history list,
    the browse position to search backward from, and the original line
    to restore on abort. ``start()`` yields the initial prompt state;
    ``feed(char)`` advances the machine:

    - printable characters extend the pattern and re-search,
    - backspace shortens the pattern and re-searches,
    - Ctrl-R / Ctrl-S move to the next match backward / forward,
    - Ctrl-G aborts (restoring position and original line),
    - Enter accepts the current match AND executes it on this single
      keystroke (readline's accept-line), via the same redispatch path
      the control-key terminators use,
    - any other control character accepts AND asks the editor to
      re-dispatch it (``redispatch=True``).

    Re-search semantics match readline: EXTENDING or shortening the
    pattern re-searches from the current entry INCLUSIVE (if the entry
    we are sitting on still matches the refined pattern, we stay on it);
    only an explicit Ctrl-R/Ctrl-S step moves off the current entry to
    the next match.
    """

    def __init__(self, history: List[str], start_pos: int,
                 original_line: str) -> None:
        self.history = history
        self.pattern: str = ""
        self.direction: int = -1  # -1 backward (Ctrl-R), +1 forward (Ctrl-S)
        self.pos: int = start_pos
        self.start_pos: int = start_pos
        self.original_line = original_line

    def start(self) -> SearchState:
        """The initial ``(reverse-i-search)`': `` prompt state."""
        return self._state()

    def feed(self, char: str) -> SearchState:
        """Advance the machine by one input character."""
        if char == '\x07':                      # Ctrl-G - abort search
            return self.abort()
        if char == '\x12':                      # Ctrl-R - next match backward
            return self._next(-1)
        if char == '\x13':                      # Ctrl-S - next match forward
            return self._next(1)
        if char in ('\r', '\n'):                # Enter - accept AND execute
            # readline runs accept-line: the match executes on this single
            # Enter. Redispatch the Enter so the editor's accept_line binding
            # fires (accepts the match into the buffer, then finishes the
            # line). The ESC-terminated path (_accept_search) keeps the
            # accept-without-execute behavior, matching bash.
            return self.accept(redispatch=True)
        if char == '\x7f':                      # Backspace - shorten pattern
            if not self.pattern:
                return self._state(repaint=False)
            self.pattern = self.pattern[:-1]
            return self._perform()
        if ord(char) >= 32:                     # Printable - extend pattern
            self.pattern += char
            return self._perform()
        # Any other control character accepts the search; the editor
        # then dispatches the character normally.
        return self.accept(redispatch=True)

    def accept(self, redispatch: bool = False) -> SearchState:
        """Accept the current match into the buffer (also used when an
        ESC-introduced event arrives during a search)."""
        line = (self.history[self.pos]
                if self.pos < len(self.history) else None)
        return SearchState(prompt=None, line=line,
                           cursor=len(line) if line is not None else 0,
                           status='accepted', history_pos=self.pos,
                           redispatch=redispatch)

    def abort(self) -> SearchState:
        """Abort: restore the pre-search position and original line."""
        self.pos = self.start_pos
        return SearchState(prompt=None, line=self.original_line,
                           cursor=len(self.original_line),
                           status='aborted', history_pos=self.pos)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _perform(self, inclusive: bool = True) -> SearchState:
        """Search for the pattern in the current direction; on failure the
        position is restored and the failed- prompt shown.

        A pattern extension/shortening (``inclusive=True``) re-checks the
        entry we are sitting on first — so refining a pattern that still
        matches keeps us on it, as readline does. An explicit Ctrl-R/Ctrl-S
        step passes ``inclusive=False`` to move off the current entry.
        """
        start = self.pos
        if self.direction < 0:
            # pos may be len(history) (the bottom) before any match lands;
            # clamp so the first backward search checks the newest entry.
            first = min(self.pos, len(self.history) - 1) if inclusive else self.pos - 1
            candidates = range(first, -1, -1)
        else:
            first = self.pos if inclusive else self.pos + 1
            candidates = range(first, len(self.history))
        for i in candidates:
            if self.pattern in self.history[i]:
                self.pos = i
                return self._state()
        self.pos = start
        return self._state(failed=True)

    def _next(self, direction: int) -> SearchState:
        """Continue the search one match further in *direction* (Ctrl-R /
        Ctrl-S), exclusive of the current entry."""
        self.direction = direction
        return self._perform(inclusive=False)

    def _state(self, failed: bool = False, repaint: bool = True) -> SearchState:
        """The active-search render state: prompt text plus the current
        match with the cursor just past the matched text."""
        # bash/readline wording: backward is "reverse-i-search", forward is
        # plain "i-search"; the failed variants prepend "failed " with a space.
        base = "reverse-i-search" if self.direction < 0 else "i-search"
        if failed:
            prompt = f"(failed {base})`{self.pattern}': "
        else:
            prompt = f"({base})`{self.pattern}': "

        line: Optional[str] = None
        cursor = 0
        if self.pos < len(self.history):
            line = self.history[self.pos]
            match_pos = line.find(self.pattern)
            if match_pos >= 0:
                cursor = match_pos + len(self.pattern)
            else:
                cursor = len(line)
        return SearchState(prompt=prompt, line=line, cursor=cursor,
                           status='active', history_pos=self.pos,
                           repaint=repaint)
