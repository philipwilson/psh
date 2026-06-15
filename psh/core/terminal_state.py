"""The shell's controlling-terminal capabilities as one explicit object.

``ShellState`` exposes ``is_terminal``/``terminal_fd``/``supports_job_control``
as properties that delegate here. Grouping the three together with the
detection logic that populates them turns a slice of the ShellState
god-object into a small cohesive type (the same move as
``StreamBindings``): the state and the one function that derives it live in
one place.

The capabilities are detected once at startup from stdin (``detect()``) and
cached:

- ``is_terminal`` — stdin (fd 0) is a TTY.
- ``terminal_fd`` — the TTY fd (always 0 when present), else ``None``.
- ``supports_job_control`` — ``tcgetpgrp(0)`` succeeds. Some environments
  are TTYs without job control (e.g. emacs shell-mode), so this is a
  separate axis from ``is_terminal``.
"""
from __future__ import annotations

import os
import sys
from typing import Optional


class TerminalState:
    """Owns the shell's controlling-terminal / job-control capabilities."""

    __slots__ = ("is_terminal", "terminal_fd", "supports_job_control")

    def __init__(self) -> None:
        self.is_terminal: bool = False
        self.terminal_fd: Optional[int] = None
        self.supports_job_control: bool = False

    def detect(self, *, debug: bool = False) -> None:
        """Detect controlling-terminal and job-control support from stdin.

        Determines whether ``tcsetpgrp()``/``tcgetpgrp()`` are usable.
        Results are cached on this object. ``debug`` enables the
        ``debug-exec`` trace lines on stderr.
        """
        try:
            # Check if stdin is a TTY
            if os.isatty(0):
                self.is_terminal = True
                self.terminal_fd = 0

                # A TTY does not guarantee job control — some environments
                # (e.g. emacs shell-mode) are TTYs where tcgetpgrp() fails.
                try:
                    current_pgid = os.tcgetpgrp(0)
                    self.supports_job_control = True
                    if debug:
                        print(f"DEBUG: Terminal detected, job control available (pgid={current_pgid})",
                              file=sys.stderr)
                except OSError as e:
                    self.supports_job_control = False
                    if debug:
                        print(f"DEBUG: Terminal detected but job control unavailable: {e}",
                              file=sys.stderr)
            else:
                self.is_terminal = False
                self.supports_job_control = False
                if debug:
                    print("DEBUG: Not running on a terminal (stdin is not a TTY)",
                          file=sys.stderr)
        except (OSError, AttributeError):
            # Platform doesn't support TTY detection
            self.is_terminal = False
            self.supports_job_control = False
            if debug:
                print("DEBUG: Platform doesn't support TTY detection",
                      file=sys.stderr)
