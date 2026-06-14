"""The shell's three standard-stream overrides as one explicit object.

``ShellState`` exposes ``stdin``/``stdout``/``stderr`` as properties that
delegate here. The design point is *override, not snapshot*: each stream
defaults to the LIVE ``sys.std*`` object unless a caller explicitly installs
a replacement (a test capture buffer, a subshell pipe, an ``exec``-rebound
file stream). Reading a stream that has no override therefore always sees the
current ``sys.std*`` — including a replacement pytest installed after the
shell was constructed — exactly as the old dynamic ``_custom_*`` attributes
did.

The override state is one object with explicit ``snapshot()``/``restore()``,
replacing the ad-hoc juggling of ``_custom_*`` attributes (set, ``hasattr``,
``delattr``) scattered through the executor. ``snapshot()`` returns an opaque
token recording which streams are currently overridden (and to what), and
``restore(token)`` puts the override state back to exactly that — reinstating
overrides that were cleared and clearing overrides that were added since.
"""
from __future__ import annotations

import sys
from typing import Optional, TextIO, Tuple

# An opaque snapshot token: for each of (stdin, stdout, stderr), either the
# overriding stream object or None when that stream had no override. Treat it
# as opaque — only pass it back to ``restore``.
StreamSnapshot = Tuple[Optional[TextIO], Optional[TextIO], Optional[TextIO]]


class StreamBindings:
    """Owns the shell's stdin/stdout/stderr overrides.

    Each ``_<name>`` slot is ``None`` when there is no override (the getter
    falls back to the live ``sys.<name>``), or the overriding stream object.
    """

    __slots__ = ("_stdin", "_stdout", "_stderr")

    def __init__(self) -> None:
        self._stdin: Optional[TextIO] = None
        self._stdout: Optional[TextIO] = None
        self._stderr: Optional[TextIO] = None

    # -- stdout --------------------------------------------------------
    @property
    def stdout(self) -> TextIO:
        """The override if set, else the live ``sys.stdout``."""
        return self._stdout if self._stdout is not None else sys.stdout

    @stdout.setter
    def stdout(self, value: TextIO) -> None:
        self._stdout = value

    # -- stderr --------------------------------------------------------
    @property
    def stderr(self) -> TextIO:
        """The override if set, else the live ``sys.stderr``."""
        return self._stderr if self._stderr is not None else sys.stderr

    @stderr.setter
    def stderr(self, value: TextIO) -> None:
        self._stderr = value

    # -- stdin ---------------------------------------------------------
    @property
    def stdin(self) -> TextIO:
        """The override if set, else the live ``sys.stdin``."""
        return self._stdin if self._stdin is not None else sys.stdin

    @stdin.setter
    def stdin(self, value: TextIO) -> None:
        self._stdin = value

    # -- explicit snapshot / restore -----------------------------------
    def snapshot(self) -> StreamSnapshot:
        """Capture the current override state as an opaque token.

        Records the overriding objects (or ``None`` where a stream tracks
        ``sys.*``), so a later ``restore`` reproduces this exact state.
        """
        return (self._stdin, self._stdout, self._stderr)

    def restore(self, token: StreamSnapshot) -> None:
        """Restore the override state captured by :meth:`snapshot`.

        Reinstates overrides that were cleared and clears overrides that were
        added since the token was taken.
        """
        self._stdin, self._stdout, self._stderr = token
