"""Pure screen-layout computation for the line editor (v0.273.0).

These functions answer "where on screen is buffer position N?" for a
prompt + single-logical-line buffer rendered in a terminal of a given
width with auto-wrap. They contain no I/O so they can be unit-tested
directly; LineEditor's central redraw routine is built on them.

Prompt measurement understands the two invisibility conventions:
- readline bracket markers: \\x01 ... \\x02 (produced by \\[ \\] in PS1)
  delimit non-printing sequences — everything between them has zero
  width, and the marker bytes themselves are never written to the
  terminal.
- bare ANSI sequences outside markers: CSI (ESC [ ... letter) and OSC
  (ESC ] ... BEL or ESC \\) are zero-width.
"""

import re
from typing import Tuple

# CSI: ESC [ params letter | OSC: ESC ] ... (BEL | ESC \)
_ANSI_RE = re.compile(
    r'\x1b\[[0-9;?]*[a-zA-Z]'       # CSI
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'  # OSC (title sequences etc.)
)
_MARKED_RE = re.compile(r'\x01[^\x02]*\x02')


def displayable_prompt(prompt: str) -> str:
    """The prompt as it should be WRITTEN: marker bytes removed, the
    escape sequences they bracket kept."""
    return prompt.replace('\x01', '').replace('\x02', '')


def visible_prompt_length(prompt: str) -> int:
    """The number of terminal columns the prompt occupies.

    Strips \\x01...\\x02 spans wholesale, then bare ANSI CSI/OSC
    sequences, then any stray marker bytes.
    """
    text = _MARKED_RE.sub('', prompt)
    text = _ANSI_RE.sub('', text)
    text = text.replace('\x01', '').replace('\x02', '')
    return len(text)


def position(prompt_len: int, pos: int, width: int) -> Tuple[int, int]:
    """(row, col) of buffer position *pos*, rows counted from the
    prompt's first row. Valid for 0 <= pos <= buffer length."""
    if width <= 0:
        return (0, prompt_len + pos)
    offset = prompt_len + pos
    return (offset // width, offset % width)


def total_rows(prompt_len: int, buffer_len: int, width: int) -> int:
    """Number of screen rows prompt+buffer occupy (>= 1).

    Content ending exactly at a row boundary still occupies the next
    row conceptually (the editor commits the wrap so the cursor can sit
    at column 0 of that row).
    """
    if width <= 0:
        return 1
    return (prompt_len + buffer_len) // width + 1


def at_row_boundary(prompt_len: int, length: int, width: int) -> bool:
    """True when prompt+content ends exactly at the right margin —
    the auto-wrap 'pending' state the redraw must normalize."""
    if width <= 0:
        return False
    offset = prompt_len + length
    return offset > 0 and offset % width == 0
