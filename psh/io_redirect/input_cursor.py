"""Owned open-file-description identity and the per-shell input-cursor registry
(campaign I1; the deferred dup/temp-frame fidelity closed in slot 4B.4).

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

The registry consumes that identity for the whole life cycle of an fd binding:

* **SAME-fd persistence** — a ``read``/``mapfile`` finds the same cursor across
  invocations on one description, so a ``read -N`` that split a malformed
  multibyte leaves its surplus for the next read on that description
  (``InputCursor`` owns the decoded queue).
* **Rebind** — a permanent ``exec 0<file`` assigns the fd a NEW description via
  :meth:`InputCursorRegistry.rebind`; the old cursor is dropped.
* **Dup** — ``exec 3<&0`` makes one description wear two fds, so
  :meth:`InputCursorRegistry.bind_dup` ALIASES the instance and both fds share
  one cursor.
* **Temporary frames** — ``read x < file`` points an fd at another description
  for one command, so :meth:`InputCursorRegistry.push_frame` /
  :meth:`~InputCursorRegistry.pop_frame` scope the binding to the frame.
* **Fork** — a child starts empty (``ShellState.clone_for_child``), matching
  bash, which inherits no userspace read buffer.

Dup sharing and temp-frame isolation were DEFERRED by the I1 ruling on the
argument that "the kernel offset is the complete shared state in both shells",
so the extra fidelity exceeded the oracle. Slot 4B.4 measured that argument
false. Because the cursor can hold userspace state the kernel offset does not
carry — a decoder mid-character after a ``-t`` timeout, or a lookahead byte read
to classify a malformed lead — an unscoped fd key let that state cross into a
different source's read (a stranded stdin byte prepended to a read from a FILE,
and the mirror: a file's surplus prepended to the next read of real stdin) or
vanish entirely (a byte consumed on fd 0's cursor was invisible to its own dup
on fd 3, so it reached no reader at all). Both directions are now closed and
pinned; the previously documented I1 deliberate-loss cases (b) and (c') hold
exact C-locale-bash parity.

One divergence from bash REMAINS BY DESIGN and is not a gap here: at a ``-t``
timeout bash assigns a stranded partial multibyte to the read that timed out
while psh holds it on the cursor and resumes it on the next read of the SAME
description. That is a value-placement difference with identical exit status,
and the scoping above is what makes it safe — the held bytes can no longer
reach another source or be lost. See
``docs/user_guide/17_differences_from_bash.md``.
"""
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple

from ..builtins.input_reader import make_reader

if TYPE_CHECKING:
    from ..ast_nodes import Redirect
    from ..builtins.input_reader import InputCursor
    from ..protocols import IOContext


def dup_alias_fds(redirect: 'Redirect') -> Optional[Tuple[int, int]]:
    """``(target_fd, source_fd)`` if ``redirect`` ALIASES an existing open file
    description, else ``None``.

    The ONE place this slot's "is this a dup, and between which fds" question is
    answered, so the three application paths that must alias a cursor — the
    ``exec`` permanent path, the in-process builtin frame, and the named-fd
    (``{v}<&n``) allocator — cannot drift apart on it.

    ``None`` means "not an aliasing operation", and every caller treats that as
    the safe case (drop/scope the binding rather than share it):

    * a CLOSE (``<&-``) has no source;
    * a dynamic dup whose source has not resolved to a plain fd number.

    Named-fd dups (``{v}<&0``) pass ``target_fd`` explicitly because the fd was
    allocated at application time and is not on the node.
    """
    if redirect.type not in ('<&', '>&'):
        return None
    source = redirect.dup_fd
    if source is None:
        target_text = redirect.target
        if target_text is None or not str(target_text).isdigit():
            return None
        source = int(target_text)
    target = redirect.fd
    if target is None:
        target = 0 if redirect.type.startswith('<') else 1
    return target, source


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

    Two maps, ``fd -> OpenDescription -> InputCursor``, so an fd's cursor is
    reached only through the description that fd currently names. The
    indirection is the whole point: it is what lets a dup ALIAS a cursor, a
    temporary redirect SCOPE one, and a rebind DROP one, without any of them
    being able to hand another source's buffered bytes to a reader.

    Process-local — a forked child starts empty
    (``ShellState.clone_for_child`` installs a fresh registry, like the stream
    bindings), matching bash, which inherits no userspace read buffer across a
    fork.
    """

    def __init__(self) -> None:
        self._fd_to_desc: Dict[int, OpenDescription] = {}
        self._desc_to_cursor: Dict[OpenDescription, "InputCursor"] = {}
        # Open redirect frames, innermost last. Tracked (as well as returned to
        # the caller) so an fd whose NUMBER only exists at apply time can still
        # be scoped into the frame it belongs to — see `scope_fd`.
        self._frames: List[Dict[int, Optional[OpenDescription]]] = []

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
        if desc is None:
            desc = OpenDescription(f"fd{fd}")
            self._fd_to_desc[fd] = desc
        # else: REUSE the description already recorded for this fd rather than
        # replacing it. :meth:`bind_dup` records a description for an fd BEFORE
        # anything has read it, so the "have a description but no cursor yet"
        # state is the normal state of a freshly dup'd fd. Overwriting it here
        # would silently undo the alias — each fd would build its own cursor and
        # a surplus held on one would be invisible to the other.
        self._desc_to_cursor[desc] = cursor
        return cursor

    def _release(self, desc: Optional[OpenDescription]) -> None:
        """Drop ``desc``'s cursor IFF no fd still names ``desc``.

        A description can wear several fds at once (that is what a dup IS), so
        "this fd stopped naming it" and "this description is finished" are
        different facts and only the second may destroy buffered bytes. Dropping
        on the first is how a cursor holding a real byte gets destroyed while
        another fd is still reading through it — the byte then reaches NO
        reader, which is the exact defect class this registry exists to prevent.

        Reference counting is done by asking the map rather than by keeping a
        counter: ``_fd_to_desc`` IS the set of live references, so it cannot
        drift out of step with itself the way a parallel count can.
        """
        if desc is None:
            return
        for live in self._fd_to_desc.values():
            if live is desc:          # identity: OpenDescription is opaque
                return
        self._desc_to_cursor.pop(desc, None)

    def _unbind(self, fd: int) -> None:
        """Remove ``fd``'s binding, releasing its description if that was the
        last fd naming it."""
        self._release(self._fd_to_desc.pop(fd, None))

    def rebind(self, fd: int) -> None:
        """Note that ``fd`` now names a NEW open description (``exec 0<file``).

        The old description's cursor is dropped so the next
        :meth:`cursor_for_fd` builds a fresh cursor over the rebound fd —
        UNLESS another fd still names that description, in which case the
        cursor is still live and dropping it would destroy bytes a reader can
        still legitimately reach (``exec 3<&0; exec 3<&-`` is the ordinary
        idiom that does this). Keying by the description rather than the bare
        fd is what makes both halves correct.
        """
        self._unbind(fd)

    def bind_dup(self, new_fd: int, old_fd: int) -> None:
        """Note that ``new_fd`` now names the SAME description as ``old_fd``.

        ``exec 3<&0`` does not create an open file description — it makes a
        second fd name the existing one, so both fds share one kernel offset.
        Aliasing the :class:`OpenDescription` INSTANCE (identity, never a value
        comparison) makes them share one cursor too, so a surplus byte read
        through either fd is visible through the other.

        ``old_fd`` may have no description yet — the registry is populated
        lazily by :meth:`cursor_for_fd`, and a dup normally happens before
        anything has read the fd. The source description is therefore
        MATERIALIZED here when absent, so the alias exists from the moment the
        dup does rather than from the first read.
        """
        desc = self._fd_to_desc.get(old_fd)
        if desc is None:
            desc = OpenDescription(f"fd{old_fd}")
            self._fd_to_desc[old_fd] = desc
        # `new_fd` may already name something (`exec 3<f; exec 3<&0`). Take the
        # binding away FIRST so the release below sees the true reference set,
        # then install the alias — otherwise a description whose last fd this
        # was would keep an unreachable cursor in `_desc_to_cursor` forever.
        previous = self._fd_to_desc.get(new_fd)
        self._fd_to_desc[new_fd] = desc
        if previous is not None and previous is not desc:
            self._release(previous)

    def push_frame(self, fds: Iterable[int]) -> Dict[int, Optional[OpenDescription]]:
        """Enter a redirect frame that temporarily rebinds ``fds``.

        A temporary redirect (``read x < file``, ``{ ...; } < file``) points an
        fd at a different description for the frame's lifetime, so a read inside
        the frame must NOT find the outer cursor and a read after it must not
        find the frame's. Both directions are real leaks: the outer surplus
        would prepend itself to the frame's data, and the frame's surplus would
        prepend itself to the outer source's next read.

        The outer bindings are set aside and returned; pass the result to
        :meth:`pop_frame`. The token is ALSO tracked here, because not every fd
        a frame re-points is knowable when the frame opens — see
        :meth:`scope_fd`.
        """
        token: Dict[int, Optional[OpenDescription]] = {}
        self._frames.append(token)
        for fd in fds:
            self._scope_into(token, fd)
        return token

    def _scope_into(self, token: Dict[int, Optional[OpenDescription]],
                    fd: int) -> None:
        """Set ``fd``'s binding aside into ``token``, first touch winning.

        First-touch-wins mirrors the fd save/restore frames: an fd re-pointed
        twice inside one frame must restore the OUTER binding, not the
        intermediate one.
        """
        if fd in token:
            return
        token[fd] = self._fd_to_desc.pop(fd, None)

    def scope_fd(self, fd: int) -> None:
        """Scope ``fd`` into the innermost open frame, if there is one.

        A named-fd redirect (``{v}<&0``, ``{v}<file``) does not know its fd
        when the frame opens: the shell allocates a free descriptor >= 10 at
        APPLY time and stores the number in the variable. Deriving a target
        from the redirect node is therefore impossible for this spelling, and
        guessing one is worse than not scoping at all — it scopes an fd the
        redirect never touches (fd 0, by the input-default rule) while leaving
        the fd it really created unscoped.

        So the allocator calls this at the moment the number exists. Outside a
        frame — a permanent ``exec {v}<&0``, or a forked child — there is
        nothing to scope to and this is correctly a no-op.
        """
        if self._frames:
            self._scope_into(self._frames[-1], fd)

    def pop_frame(self,
                  saved: Dict[int, Optional[OpenDescription]]) -> None:
        """Leave a frame entered by :meth:`push_frame`, restoring ``saved``.

        Anything the frame bound goes away and the outer bindings go back
        untouched, so a surplus the outer cursor was holding is still there for
        the next read on that description.

        Restoring every binding before releasing any description is deliberate
        but DEFENSIVE, not load-bearing: :meth:`_release` consults the live
        binding map, and an alias a frame created always has its source fd
        outside the frame (``bind_dup`` materializes a fresh description when
        the source's own binding has been lifted), so no reachable state was
        found in which the reverse order destroys a live cursor. The ordering
        costs nothing and removes a class of reasoning; the REFERENCE CHECK is
        what actually protects the bytes.
        """
        for i in range(len(self._frames) - 1, -1, -1):
            if self._frames[i] is saved:
                del self._frames[i]
                break
        dropped = []
        for fd, desc in saved.items():
            inner = self._fd_to_desc.pop(fd, None)
            if inner is not None:
                dropped.append(inner)
            if desc is not None:
                self._fd_to_desc[fd] = desc
        for inner in dropped:
            self._release(inner)
