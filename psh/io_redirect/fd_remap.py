"""Collision-safe file-descriptor remapping for forked children.

A forked child (a pipeline member, a command/process-substitution child)
must wire a handful of *internal* descriptors — pipe endpoints — onto the
*standard* descriptors 0/1/2 the command will actually use, then drop every
internal descriptor it no longer needs. The naive recipe

    os.dup2(stdin_fd, 0); os.dup2(stdout_fd, 1)
    for fd in all_internal_fds: os.close(fd)

is unsafe in two ways, both of which surface only when descriptors 0, 1, or
2 began *closed* (``exec 0<&-``, ``exec 1>&-``):

1. **A source already sits on its destination.** When fd 0 is closed,
   ``os.pipe()`` hands back the read end as fd 0. ``dup2(0, 0)`` is a no-op,
   and the unconditional close loop then destroys the live endpoint.

2. **A source sits on *another* mapping's destination.** With fd 1 closed,
   a middle pipeline member can have its stdin on fd 1 (``{1 -> 0}``) while
   its stdout must land on fd 1 (``{w -> 1}``). ``dup2(w, 1)`` clobbers fd 1
   before it has been copied to fd 0 — a classic remapping cycle.

``remap_fds`` solves both with the textbook two-phase algorithm: dup every
distinct source up to a fresh descriptor above all destinations (and above
2), then ``dup2`` each relocated source onto its destination. Because every
source has been copied out of the destination range first, no destination
write can ever clobber a source that is still needed — cycles included.

Close-on-exec is deliberate: the temporary relocations are internal and are
opened close-on-exec (and closed here regardless), while ``dup2`` leaves each
final destination *inheritable* so the exec'd program receives it. Owned
descriptors — the caller's internal endpoints — are closed exactly once, and
never a final destination. On any failure every temporary and owned
descriptor is closed before the error propagates, so a partially applied
remap in a doomed child leaks nothing.
"""

import fcntl
import os
from typing import Dict, Iterable, List, Mapping, Set, Tuple, Union

# F_DUPFD_CLOEXEC is present on Linux and macOS; fall back defensively.
_F_DUPFD_CLOEXEC = getattr(fcntl, 'F_DUPFD_CLOEXEC', None)

# A source→destination remap, given either as a mapping {src: dst} or as an
# iterable of (src, dst) pairs. Pairs allow one source to feed several
# destinations (e.g. ``|&`` sends the pipe write end to both fd 1 and fd 2).
FdPairs = Union[Mapping[int, int], Iterable[Tuple[int, int]]]


def _close_quiet(fd: int) -> None:
    """Close ``fd``, ignoring an already-closed / invalid descriptor."""
    try:
        os.close(fd)
    except OSError:
        pass


def _dedupe(fds: Iterable[int]) -> List[int]:
    """Unique fds, preserving first-seen order (so each is closed once)."""
    return list(dict.fromkeys(fds))


def _dup_high(fd: int, base: int) -> int:
    """Duplicate ``fd`` onto the lowest free descriptor >= ``base``.

    The duplicate is close-on-exec where the platform supports it: it is an
    internal relocation, always closed before the child execs, so it must
    never leak into an exec'd program.
    """
    if _F_DUPFD_CLOEXEC is not None:
        return fcntl.fcntl(fd, _F_DUPFD_CLOEXEC, base)
    dup = fcntl.fcntl(fd, fcntl.F_DUPFD, base)
    flags = fcntl.fcntl(dup, fcntl.F_GETFD)
    fcntl.fcntl(dup, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
    return dup


def remap_fds(mappings: FdPairs, *,
              owned: Iterable[int] = ()) -> None:
    """Install ``mappings`` onto their destinations collision-safely.

    Args:
        mappings: source→destination remaps, as a dict or (src, dst) pairs.
            Each source's open file description is duplicated onto its
            destination descriptor. One source may appear with several
            destinations. Sources must be valid open descriptors.
        owned: internal descriptors the caller owns (pipe endpoints). Each is
            closed exactly once after the remap, EXCEPT any that is a
            destination (a live endpoint now serving one of the mappings).

    The destinations are left inheritable (``dup2`` clears close-on-exec) so
    an exec'd program receives them. On failure, all temporaries and owned
    descriptors are closed and the ``OSError`` propagates.
    """
    pairs: List[Tuple[int, int]]
    if isinstance(mappings, Mapping):
        pairs = list(mappings.items())
    else:
        pairs = list(mappings)

    dests: Set[int] = {dst for _src, dst in pairs}

    # Relocate every distinct source above all destinations (and above fd 2)
    # so no dup2 onto a destination can clobber a source still to be placed.
    base = max(dests | {2}) + 1
    temp_for: Dict[int, int] = {}
    created: List[int] = []
    try:
        for src, _dst in pairs:
            if src not in temp_for:
                temp = _dup_high(src, base)
                temp_for[src] = temp
                created.append(temp)

        # Phase two: place each relocated source onto its destination. dup2
        # is a no-op when the numbers coincide but still clears close-on-exec,
        # so every destination ends up inheritable.
        for src, dst in pairs:
            os.dup2(temp_for[src], dst)
    except OSError:
        # Doomed child: drop every temporary and every owned endpoint, then
        # let the caller map the failure to an exit status.
        for temp in created:
            _close_quiet(temp)
        for fd in _dedupe(owned):
            _close_quiet(fd)
        raise

    # Success: the temporaries have done their job, and each owned endpoint
    # that is not now serving a destination is released.
    for temp in created:
        _close_quiet(temp)
    for fd in _dedupe(owned):
        if fd in dests:
            continue
        _close_quiet(fd)
