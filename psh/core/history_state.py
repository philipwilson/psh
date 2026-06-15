"""The shell's command-history list and persistence settings as one object.

``ShellState`` exposes ``history`` / ``history_file`` / ``max_history_size``
as properties that delegate here. Grouping the live history list with its
file path and size cap turns three loose ShellState fields into one cohesive
type — the ``HistoryManager`` operates entirely through these three values.

This is the same "typed sub-object" decomposition as ``StreamBindings`` and
``TerminalState``: a slice of the ShellState god-object lifted into a small
named type, with delegating properties so existing call sites are untouched.
"""
from __future__ import annotations

import os
from typing import List


class HistoryState:
    """Owns the command history list and its persistence settings."""

    __slots__ = ("entries", "file_path", "max_size")

    def __init__(self) -> None:
        self.entries: List[str] = []
        self.file_path: str = os.path.expanduser("~/.psh_history")
        self.max_size: int = 1000
