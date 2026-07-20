"""Owned open-file-description identity and the per-shell input-cursor registry
(campaign I1, SCOPED realization).

An :class:`~psh.builtins.input_reader.InputCursor` (the record reader) is keyed
to the KERNEL open file description it reads — the object that carries the
shared offset — not to a bare fd number. psh tracks that identity where it owns
the open/dup/close, because ``fstat`` dev/ino cannot distinguish two independent
``open()`` calls on one file (so kernel sniffing is not enough — the I1 design
caution).

:class:`OpenDescription` is that identity token. It is deliberately OPAQUE —
identity is object identity — so two fd bindings share a cursor iff they hold
the same instance. R1's here-input content (materialized once into one shared
open file description and handed to a builtin and its child via
``FileRedirector.dup_sharing_stream``) can ADOPT this token in a later fixup
slot so the two packages key by one type; **I1 creates the type, R1 does not
yet consume it** (the brief's premise that R1 already shipped an identity type
was incorrect — see the I1 ledger).

SCOPED realization (integrator ruling 2026-07-19): the registry consumes the
identity for SAME-fd persistence — a ``read``/``mapfile`` finds the same cursor
across invocations on one description, so a ``read -N`` that split a malformed
multibyte leaves its surplus for the next read on that description
(``InputCursor`` owns the decoded queue). A permanent rebind (``exec 0<file``)
assigns the fd a NEW ``OpenDescription`` via :meth:`InputCursorRegistry.rebind`
(the old cursor is dropped).

FULL fidelity — sharing a cursor across a ``dup`` (``exec 3<&0``) and isolating
it across a temporary-redirect frame — is a purely ADDITIVE future extension
(``bind_dup``/temp-frame hooks would populate these same maps). It is DEFERRED,
not lost: under strict never-over-read bash carries no cross-invocation decoder
pushback at all — the kernel offset is the complete shared state in both shells
— so that extra fidelity exceeds the oracle. The two deliberate-loss cases are
documented in the I1 ledger with discriminating bash probes.
"""
from typing import TYPE_CHECKING, Dict

from ..builtins.input_reader import make_reader

if TYPE_CHECKING:
    from ..builtins.input_reader import InputCursor
    from ..protocols import IOContext


class OpenDescription:
    """An owned open-file-description identity (campaign I1).

    Opaque: equality and hashing are object identity, so a value comparison can
    never accidentally alias two distinct descriptions. Create one per
    ``open()``/rebind psh performs on a descriptor; alias it (reuse the same
    instance) across a ``dup`` psh performs. The ``label`` is a debugging aid
    only and never participates in identity.

    Intended shared use: R1's here-input open file description (one temp file
    dup-shared by a builtin and its child) can be represented by an
    ``OpenDescription`` in a later fixup, giving I1 and R1 one identity type.
    """

    __slots__ = ("label",)

    def __init__(self, label: str = "") -> None:
        self.label = label

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"OpenDescription({self.label!r}@{id(self):#x})"


class InputCursorRegistry:
    """Per-shell map from an owned open-file-description identity to its cursor.

    Keyed by :class:`OpenDescription` from day one (FULL must stay additive):
    ``fd -> OpenDescription -> InputCursor``. Process-local — a forked child
    starts empty (``ShellState.clone_for_child`` installs a fresh registry, like
    the stream bindings), matching bash, which inherits no userspace read buffer
    across a fork.
    """

    def __init__(self) -> None:
        self._fd_to_desc: Dict[int, OpenDescription] = {}
        self._desc_to_cursor: Dict[OpenDescription, "InputCursor"] = {}

    def cursor_for_fd(self, io_ctx: "IOContext", fd: int) -> "InputCursor":
        """Return the persistent cursor reading ``fd``'s current description.

        ``io_ctx`` is the narrow :class:`~psh.protocols.IOContext` (the ``Shell``
        satisfies it — campaign Q1): only its ``.stdin`` is consulted, through
        ``make_reader``, not the whole shell.

        The cursor persists across builtin invocations (same-fd carryover). A
        stream-backed source (an injected test ``StringIO`` with no real fd)
        is NOT registered — the stream object itself holds the read position and
        there is no description to key nor byte-level surplus to carry — so it is
        returned fresh, matching the pre-registry per-call behavior.
        """
        desc = self._fd_to_desc.get(fd)
        if desc is not None:
            cursor = self._desc_to_cursor.get(desc)
            if cursor is not None:
                return cursor

        cursor = make_reader(io_ctx, fd)
        if cursor.fd is None:
            # Stream-backed (test injection): do not persist.
            return cursor
        desc = OpenDescription(f"fd{fd}")
        self._fd_to_desc[fd] = desc
        self._desc_to_cursor[desc] = cursor
        return cursor

    def rebind(self, fd: int) -> None:
        """Note that ``fd`` now names a NEW open description (``exec 0<file``).

        The old description's cursor is dropped, so the next
        :meth:`cursor_for_fd` builds a fresh cursor over the rebound fd. Keying
        by the description (not the bare fd) is what makes this correct: the old
        cursor's decoder/queue state cannot leak into the new description.
        """
        old = self._fd_to_desc.pop(fd, None)
        if old is not None:
            self._desc_to_cursor.pop(old, None)
