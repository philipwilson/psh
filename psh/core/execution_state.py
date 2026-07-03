"""Per-command execution scratch state as one cohesive object.

``ShellState`` exposes ``last_exit_code`` / ``last_bg_pid`` / ``foreground_pgid``
/ ``command_number`` / ``pipestatus`` / ``errexit_eligible`` /
``last_cmdsub_status`` / ``in_forked_child`` as properties that delegate here.
These are the values the executor reads and writes as it runs each command —
grouping them turns eight loose ShellState fields into one named type that
``ShellState.adopt()`` can copy as a unit (the v0.453 ``$!``-in-subshell bug was
a missed field in that copy; ``copy_into()`` makes such omissions structurally
hard).

Same "typed sub-object + delegating properties" decomposition as
``HistoryState``, ``TerminalState`` and ``StreamBindings``: a slice of the
ShellState god-object lifted into a small type, with delegating properties so
existing call sites are untouched.
"""
from __future__ import annotations

from typing import List, Optional


class ExecutionState:
    """The mutable per-command execution state the executor maintains."""

    __slots__ = (
        "last_exit_code",
        "last_bg_pid",
        "foreground_pgid",
        "command_number",
        "pipestatus",
        "errexit_eligible",
        "last_cmdsub_status",
        "in_forked_child",
        "in_substitution",
    )

    def __init__(self) -> None:
        # Exit status of the last foreground command ($?).
        self.last_exit_code: int = 0
        # PID of the most recent background command ($!); inherited by subshells.
        self.last_bg_pid: Optional[int] = None
        # Process group currently owning the terminal (job control).
        self.foreground_pgid: Optional[int] = None
        # Monotonic command counter (\# / \! prompt escapes, history numbering).
        self.command_number: int = 0
        # Exit statuses of the most recent foreground pipeline (PIPESTATUS); a
        # single command records a one-element list.
        self.pipestatus: List[int] = []
        # Whether the most recent command status may trigger `set -e` (False for
        # the errexit-exempt positions: condition contexts, non-final && / ||
        # members, !-negated pipelines).
        self.errexit_eligible: bool = True
        # Exit status of the most recent command substitution, or None (used as a
        # pure assignment's exit status — bash reports 0 unless a cmdsub ran).
        self.last_cmdsub_status: Optional[int] = None
        # True only inside a forked child (pipeline member, subshell,
        # command-substitution child, ...); leaf builtins consult it to choose
        # between fd-level writes (os.write) and shell.stdout.
        self.in_forked_child: bool = False
        # True inside a command/process substitution child (set by
        # run_child_shell). bash suppresses the abnormal-termination
        # diagnostic there but NOT in a ( ) subshell, so this flag —
        # unlike in_forked_child — must distinguish the two.
        self.in_substitution: bool = False

    def copy_into(self, other: "ExecutionState") -> None:
        """Copy the inheritable execution state into ``other`` (for subshell
        adoption). ``pipestatus`` is copied as a fresh list; ``in_forked_child``
        is deliberately NOT copied — the child sets it itself. ``in_substitution``
        IS copied so a ( ) subshell nested inside a command substitution inherits
        the suppression (bash is silent for the whole substitution).
        """
        other.last_exit_code = self.last_exit_code
        other.last_bg_pid = self.last_bg_pid
        other.foreground_pgid = self.foreground_pgid
        other.command_number = self.command_number
        other.pipestatus = list(self.pipestatus)
        other.errexit_eligible = self.errexit_eligible
        other.last_cmdsub_status = self.last_cmdsub_status
        other.in_substitution = self.in_substitution
