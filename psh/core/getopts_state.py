"""The getopts continuation cursor as one typed object.

``getopts optstring name [args...]`` parses one option per call; a clustered
word like ``-abc`` is walked one character per call, so the within-word cursor
must persist ACROSS calls. bash (``lib/sh/getopt.c``) keys that cursor to the
argument source, the current OPTIND, and whether the script reassigned OPTIND.

The old model tracked only ``(char_offset, optind)`` on two loose ShellState
attributes, which broke two ways (core-state appraisal A3 / builtins P1.8):

* a shorter next word at the same OPTIND overran the stale offset
  (``getopts ab o -ab; getopts ab o -b`` -> "string index out of range");
* a manual ``OPTIND=1`` mid-cluster did not restart the scan.

``GetoptsState`` records enough to reproduce bash exactly (probed, bash 5.2):
the cursor is preserved ONLY while the scan continues on the SAME argument
source and the SAME OPTIND, and while the script has not ASSIGNED OPTIND since
getopts last wrote it. Any assignment to OPTIND — even to the same value
(``OPTIND=$OPTIND``) — restarts the scan; that is detected with a write
counter the scope manager bumps on every OPTIND assignment (getopts records
the counter value right after its own write, so a later mismatch means the
script wrote OPTIND).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class GetoptsState:
    """Continuation cursor for the getopts builtin (see module docstring)."""

    # Within-word character cursor: 1 = the first char after the leading '-'.
    char_offset: int = 1
    # The argument SOURCE the cursor indexes into (the explicit arg list, or
    # the positional parameters) as a tuple, so a source or word change is
    # detected by identity of contents.
    cursor_source: Optional[Tuple[str, ...]] = None
    # The OPTIND value the cursor is valid at.
    cursor_optind: int = 0
    # Total assignments to OPTIND observed (bumped by the scope manager's
    # variable-changed observer). getopts records the value right after its
    # OWN OPTIND write in ``expected_writes``; a later mismatch means the
    # script reassigned OPTIND, which restarts the scan (bash).
    optind_writes: int = 0
    expected_writes: int = 0

    def cursor_valid_for(self, source: Tuple[str, ...], optind: int) -> bool:
        """True if the saved within-word cursor still applies to this call:
        same source, same OPTIND, and no script assignment to OPTIND since
        getopts last wrote it."""
        return (self.cursor_source == source
                and self.cursor_optind == optind
                and self.optind_writes == self.expected_writes)

    def advance(self, source: Tuple[str, ...], optind: int,
                char_offset: int) -> None:
        """Record the cursor after processing one option. Call AFTER the
        OPTIND write (which bumps ``optind_writes`` via the observer), so
        ``expected_writes`` captures getopts' own write and only a LATER
        script assignment invalidates the cursor."""
        self.cursor_source = source
        self.cursor_optind = optind
        self.char_offset = char_offset
        self.expected_writes = self.optind_writes

    def copy(self) -> "GetoptsState":
        """Independent copy for a subshell-style child (a clustered-option
        walk spans into children — bash: ``set -- -ab; getopts ab o;
        $(getopts ab o; echo $o)`` sees ``b``). The write counters carry over
        equal, so the child sees the inherited cursor as valid."""
        return GetoptsState(
            char_offset=self.char_offset,
            cursor_source=self.cursor_source,
            cursor_optind=self.cursor_optind,
            optind_writes=self.optind_writes,
            expected_writes=self.expected_writes,
        )
