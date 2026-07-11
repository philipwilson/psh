"""I/O redirection manager for handling all types of redirections.

The two redirection universes
=============================

PSH redirects I/O at two distinct levels, and which level applies depends
on WHO will do the writing:

* **The fd universe** — ``os.open``/``os.dup2`` on real descriptors.
  External commands run in forked children and inherit the process's file
  descriptors, so their redirections must be kernel-level. They are applied
  *after fork* (``setup_child_redirections``), so the parent shell's own
  fds are never touched.

* **The stream universe** — swapping the Python file *objects* in
  ``sys.stdout``/``sys.stderr``/``sys.stdin``. Builtins run in-process and
  write through those Python streams, not raw fds — and the streams may not
  be backed by fd 1 at all: an embedding harness (``captured_shell``) or
  pytest's capture installs plain ``StringIO`` objects. A ``dup2`` of fd 1
  would therefore not reach a builtin's output. Conversely, rewriting the
  shell's *own* fds around every builtin would be dangerous: in-process the
  shell shares fds with its host (under pytest-xdist fds carry the worker's
  execnet channel), and a crash mid-builtin could leave them hijacked.

``setup_builtin_redirections`` dispatches each redirect to the right
universe:

========================================  =====================================
Redirect                                  Universe
========================================  =====================================
``>``, ``>>``, ``>|``, ``&>`` to fd 1/2   BOTH: the stream swap (``_builtin_redirect_output_file`` / ``_builtin_redirect_combined``) for the builtin's own writes AND a dup2 of fd 1/2 — saved and restored — so a child the builtin spawns (``eval``/``source``/``command`` running an external) also writes to the target
``2>&1``, ``1>&2``                        BOTH: stream swap (``sys.stderr = sys.stdout``) so builtin writes interleave and honor ordering, AND a dup2 of fd 2/1 so children inherit it
``<``, ``<>``, heredoc, here-string       BOTH: the stream for the builtin itself (``read`` consumes ``sys.stdin``) AND a dup2 of fd 0 — saved and restored — so any child spawned during the builtin sees the redirected stdin
fd >= 3, other ``n>&m``, ``>&-``          fd level via FileRedirector (no Python stream counterpart exists)
========================================  =====================================

The dup2 for fd 1/2 shares the opened file's open description (so the
builtin's stream writes and a child's fd writes keep one offset — no
re-truncation), exactly like the ``exec`` rebind. It is per-command
(saved on the frame, restored when the command finishes); permanent
fd rewriting is reserved for ``exec`` alone.

Restore (``restore_builtin_redirections``) is transactional and
order-aware: the ORIGINAL stream objects are recorded first-touch-wins
(same fd redirected twice must restore the original, not the intermediate),
exactly the files setup opened are closed (never whatever happens to be in
``sys.stdout`` — after ``cmd 2>&1`` that IS the shell's real stdout), and a
failure part-way through setup rolls back everything already applied.

Nesting: per-invocation frames
==============================

Builtin redirections NEST: ``eval "echo one >&3" 3>&1`` opens a frame for
the eval, then the eval'd ``echo`` opens an inner frame while the outer is
still active (likewise ``source file 3>&1`` for the file's commands, and
trap handlers firing mid-builtin). Everything one invocation changed —
fd-level dup2 saves, opened file objects, the stream snapshot — therefore
lives in a :class:`BuiltinRedirectFrame` returned by setup and consumed by
restore, never on the shared IOManager (manager-level lists conflated
nested invocations: the inner restore drained the OUTER's saved fds,
re-pointing e.g. fd 3 at its exec-time file mid-eval — fixed in v0.302).
Frames are restored innermost-first; this LIFO discipline is guaranteed by
the paired try/finally in ``_execute_builtin_with_redirections``.
"""
import copy
import fcntl
import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, List, NoReturn, Optional, TextIO, Tuple, cast

from ..ast_nodes import Command, Redirect
from .file_redirect import FileRedirector
from .process_sub import ProcessSubstitutionHandler

if TYPE_CHECKING:
    from ..shell import Shell


class _ClosedStream:
    """A Python stream stand-in whose every write/flush raises EBADF.

    Installed in ``sys.stdout``/``sys.stderr`` (and ``shell.stdout``/
    ``shell.stderr``) for a builtin when its own output fd was closed with
    ``1>&-`` / ``2>&-`` / bare ``>&-``. The fd-level close alone does not
    reach a builtin, which writes through the Python stream object, so the
    stream must fail too — matching bash, where ``echo hi 1>&-`` produces no
    output and a ``write error: Bad file descriptor`` diagnostic. Builtins
    already translate this OSError into bash's message and exit 1 (see
    ``execute_builtin_guarded`` and echo/printf's own handlers).
    """

    def _bad_fd(self):
        raise OSError(9, os.strerror(9))  # EBADF

    def write(self, _text):
        self._bad_fd()

    def flush(self):
        self._bad_fd()

    def writelines(self, _lines):
        self._bad_fd()

    def close(self):
        # A no-op (not _bad_fd): the permanent-redirect rollback closes
        # whatever stream it finds in sys.stdout/stderr, which after an
        # `exec >&-` is this sentinel — closing a closed fd should be silent.
        pass


class _RawFdStream:
    """A minimal text stream that writes straight to a fixed fd via ``os.write``.

    Installed as ``sys.stdout``/``sys.stderr`` for a builtin after a PERMANENT
    ``exec >&-``/``2>&-`` closes fd 1/2 (see
    ``FileRedirector._rebind_closed_output_stream``). It threads a needle the
    natural ``TextIOWrapper`` and ``_ClosedStream`` each miss:

    * **No buffering** — a write goes straight to the fd; on a CLOSED fd it
      raises EBADF immediately and nothing is retained. The natural wrapper
      instead BUFFERS the write, its flush fails EBADF, and the retained bytes
      later flush into a REOPENED fd of the same number (the exec-close-then-
      reopen leak, MED-1). ``_RawFdStream`` can't leak because it never holds
      bytes.

    * **Transparent** — it names the fd NUMBER, so if a compound/function
      per-command redirect re-points that fd at a live target at the fd level
      (``f 1>&2``, ``{ ...; } >g``, ``{ ...; } &>f``) the write simply follows
      the fd, exactly as the natural wrapper did. ``_ClosedStream`` is opaque:
      it always raises, so it would sever those legitimate reopens.

    * **Owns nothing** — ``close()`` is a no-op and it never calls ``os.close``,
      so displacing it (a later ``exec >&3`` reopen, or a rollback) can never
      close the std fd out from under a fresh binding.

    A permanent reopen (``exec >&3``, ``exec >f``) still routes through
    ``_rebind_output_stream``, which installs a normal buffered fd-sharing
    stream and drops this one.
    """

    def __init__(self, fd: int) -> None:
        self._fd = fd

    def write(self, text) -> int:
        data = (text.encode('utf-8', 'surrogateescape')
                if isinstance(text, str) else text)
        view = memoryview(data)
        while view:
            view = view[os.write(self._fd, view):]
        return len(text)

    def writelines(self, lines) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def fileno(self) -> int:
        return self._fd

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        try:
            return os.isatty(self._fd)
        except OSError:
            return False


def _redirect_error_name(error: OSError, target: Optional[str]) -> str:
    """Pick the name bash prints in `psh: NAME: STRERROR` for a redirect error.

    Prefer the expanded redirect target; fall back to the OSError's own
    filename (set by os.open) when no target is available. Both checks are
    ``is not None``, NOT truthiness: an EMPTY target (``> ""``) is a real
    name and must print bash's ``psh: : No such file or directory``, not
    fall through to the errno number.
    """
    if target is not None:
        return target
    if error.filename is not None:
        return error.filename
    return str(error.errno)


def format_redirect_error(error: OSError, target: Optional[str] = None) -> str:
    """Format a redirect-setup ``OSError`` as bash's ``psh: TARGET: STRERROR``.

    This is the ONE message shape every redirect-failure site emits — simple
    command, in-process compound command, forked subshell, function call — so
    they no longer diverge (raw ``OSError`` repr vs prefixed message). A
    syscall failure (errno set: ENOENT/EISDIR/EACCES) becomes
    ``psh: <target>: <strerror>``; a custom-message redirect error (errno
    ``None``: noclobber, ambiguous redirect, bad fd) keeps its own message as
    ``psh: <message>``.
    """
    if error.errno is None:
        return f"psh: {error}"
    name = _redirect_error_name(error, target)
    return f"psh: {name}: {os.strerror(error.errno)}"


class _BuiltinStreamSnapshot:
    """The Python streams (and the stdin fd) as they were BEFORE the first
    redirect touched them.

    First-touch-wins: with the same stream redirected twice
    (``echo hi >a >b``), restore must reinstate the ORIGINAL stream, not the
    file object the first redirect installed. ``note_*()`` records the
    current stream only if nothing was recorded yet.
    """

    def __init__(self):
        self.stdin: Optional[TextIO] = None
        self.stdout: Optional[TextIO] = None
        self.stderr: Optional[TextIO] = None
        self.stdin_fd: Optional[int] = None  # os.dup(0), restored by dup2

    def note_stdin(self):
        if self.stdin is None:
            self.stdin = sys.stdin
            self.stdin_fd = os.dup(0)

    def note_stdout(self):
        if self.stdout is None:
            self.stdout = sys.stdout

    def note_stderr(self):
        if self.stderr is None:
            self.stderr = sys.stderr


class BuiltinRedirectFrame:
    """Everything ONE setup_builtin_redirections invocation changed.

    Builtin redirections nest (eval/source/trap handlers run further
    redirected builtins while an outer one is active), so this state must
    be per-invocation, not manager-level: setup returns a frame, restore
    consumes exactly that frame.

    Process substitutions used as redirect targets are deliberately NOT
    part of the frame — they are owned by the enclosing
    ``process_sub_scope()``, which already nests per command.
    """

    def __init__(self):
        # Pre-redirect Python streams + dup of fd 0 (first-touch-wins).
        self.snapshot = _BuiltinStreamSnapshot()
        # (fd, saved_fd) pairs from fd-level redirects (fd >= 3, rare dups).
        self.saved_fds: List[Tuple[int, int | None]] = []
        # File objects this setup opened; restore closes exactly these
        # (never whatever happens to be in sys.stdout/stderr).
        self.opened_streams: List[TextIO] = []


class IOManager:
    """Manages all I/O redirections including files, heredocs, and process substitutions."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Initialize sub-handlers (heredoc content is handled by FileRedirector)
        self.file_redirector = FileRedirector(shell)
        self.process_sub_handler = ProcessSubstitutionHandler(shell)

        # Stack of active builtin redirection frames (innermost last).
        # Used only to check the LIFO discipline documented on
        # restore_builtin_redirections; the state itself lives in the frames.
        self._builtin_frame_stack: List[BuiltinRedirectFrame] = []


    @contextmanager
    def with_redirections(self, redirects: List[Redirect]):
        """Context manager for applying redirections temporarily.

        Also owns any process substitutions used as redirect targets
        (e.g. `while ...; done < <(cmd)`): their parent-side fds are
        closed and children reaped when the redirected region ends.
        """
        if not redirects:
            yield
            return
        with self.process_sub_handler.scope():
            saved_fds = self.apply_redirections(redirects)
            stream_restore = self._swap_closed_output_streams(redirects)
            try:
                yield
            finally:
                stream_restore()
                self.restore_redirections(saved_fds)

    @contextmanager
    def guarded_redirections(self, redirects: List[Redirect]):
        """Like :meth:`with_redirections`, but a redirect SETUP failure is
        turned into bash's diagnostic instead of an escaping ``OSError``.

        This is the ONE chokepoint for the in-process COMPOUND commands
        (brace group, ``if``/``for``/``while``/``until``/``case``, ``[[ ]]``,
        ``(( ))``): a bad redirect target must print ``psh: TARGET: STRERROR``,
        NOT run the body, and let the command fail with status 1 so
        ``|| fallback`` runs — matching bash. It yields:

        * ``True``  — redirects applied cleanly; run the body.
        * ``False`` — a redirect FAILED (message already printed); the caller
          must skip the body and ``return 1``.

        Only the redirect SETUP is guarded: once the body runs it is outside
        the ``try``, so a body exception is not misreported as a redirect
        error. Simple commands keep their own per-strategy handling
        (:meth:`setup_builtin_redirections` / ``setup_child_redirections``).
        """
        if not redirects:
            yield True
            return
        with self.process_sub_handler.scope():
            try:
                saved_fds = self.apply_redirections(redirects)
                stream_restore = self._swap_closed_output_streams(redirects)
            except OSError as e:
                # apply_redirections already rolled back its own partial state.
                print(format_redirect_error(e), file=self.state.stderr)
                yield False
                return
            try:
                yield True
            finally:
                stream_restore()
                self.restore_redirections(saved_fds)

    @staticmethod
    def output_close_fd(redirect: Redirect) -> Optional[int]:
        """The OUTPUT fd (1 or 2) a redirect closes with ``>&-``, else ``None``.

        Shared classifier for the three sites that must reach the stream
        universe when a builtin-visible output fd is closed
        (``_swap_closed_output_streams``, ``_builtin_redirect_close``, and the
        permanent-exec close branch). Returns ``None`` for an input close
        (``<&-``), a close of fd >= 3 (no Python stream counterpart), a
        ``{v}>&-`` named-fd close (acts on the variable's fd, not stdout/
        stderr), or any redirect that is not a ``>&-`` close.
        """
        if redirect.var_fd:
            return None
        if redirect.type != '>&-':
            return None
        target_fd = redirect.fd if redirect.fd is not None else 1
        return target_fd if target_fd in (1, 2) else None

    @staticmethod
    def swap_output_stream_closed(target_fd: int) -> TextIO:
        """Point fd 1's/2's Python stream at a ``_ClosedStream`` (write→EBADF)
        and RETURN the stream it displaced.

        The single stream-universe primitive behind an output-fd close, shared
        by all three sites. The temporary callers (``_swap_closed_output_streams``
        for compound commands, ``_builtin_redirect_close`` for simple-command
        builtins) SAVE the displaced stream and restore it when the redirect
        region ends; the permanent ``exec`` caller instead CLOSES it to drop
        the now-orphaned dup an earlier ``exec >file`` had installed. The
        fd-level close is done separately (``_redirect_close_fd``); this only
        makes the Python stream fail, so a builtin's write raises EBADF exactly
        as bash does rather than leaking into the old destination.
        """
        if target_fd == 1:
            displaced = sys.stdout
            sys.stdout = cast(TextIO, _ClosedStream())
            return displaced
        displaced = sys.stderr
        sys.stderr = cast(TextIO, _ClosedStream())
        return displaced

    @staticmethod
    def swap_output_stream_reopenable(target_fd: int) -> TextIO:
        """Point fd 1's/2's Python stream at a ``_RawFdStream`` and RETURN the
        stream it displaced.

        The permanent-``exec``-close counterpart of ``swap_output_stream_closed``.
        A per-command close is temporary and never reopens the fd within the
        command, so ``_ClosedStream`` (write→EBADF) is right there. A permanent
        ``exec >&-`` is different: the fd may be REOPENED later (``exec >&3``) or
        transiently by a compound/function body's own redirect (``f 1>&2``), and
        the natural buffering wrapper it replaced would leak buffered bytes into
        such a reopen. ``_RawFdStream`` writes straight to the fd number, so it
        fails cleanly while the fd is closed yet follows it when a reopen makes
        it live again — no buffer to leak, no legitimate reopen severed.
        """
        if target_fd == 1:
            displaced = sys.stdout
            sys.stdout = cast(TextIO, _RawFdStream(target_fd))
            return displaced
        displaced = sys.stderr
        sys.stderr = cast(TextIO, _RawFdStream(target_fd))
        return displaced

    def _swap_closed_output_streams(self, redirects: List[Redirect]):
        """For ``>&-`` closing fd 1/2, point the Python stream at a stream
        that raises EBADF, and return a closure that restores it.

        This is the stream-universe half of an output-fd close in the
        in-process compound path (brace groups, functions, control flow run
        via ``with_redirections``). The fd-level close alone does not reach a
        builtin running inside, which writes through ``sys.stdout`` /
        ``sys.stderr``; without this it would keep writing to the still-open
        stream and leak (``{ echo a; } 1>&-`` printing ``a``). Mirrors
        ``_builtin_redirect_close`` for the simple-command builtin path.
        """
        saved: List[Tuple[int, TextIO]] = []
        for redirect in redirects:
            target_fd = self.output_close_fd(redirect)
            if target_fd is None:
                continue
            saved.append((target_fd, self.swap_output_stream_closed(target_fd)))

        def restore():
            for fd, stream in reversed(saved):
                if fd == 1:
                    sys.stdout = stream
                else:
                    sys.stderr = stream

        return restore

    def apply_redirections(self, redirects: List[Redirect]) -> List[Tuple[int, int | None]]:
        """Apply redirections and return list of saved FDs for restoration."""
        return self.file_redirector.apply_redirections(redirects)

    def restore_redirections(self, saved_fds: List[Tuple[int, int | None]]):
        """Restore file descriptors from saved list."""
        self.file_redirector.restore_redirections(saved_fds)

    def apply_permanent_redirections(self, redirects: List[Redirect]):
        """Apply redirections permanently (for exec builtin)."""
        return self.file_redirector.apply_permanent_redirections(redirects)

    def setup_builtin_redirections(self, command: Command) -> BuiltinRedirectFrame:
        """Set up redirections for a built-in command (see module docstring).

        Each redirect goes to the stream universe (fds 0/1/2, which builtins
        reach through Python stream objects) or the fd universe (fd >= 3,
        uncommon dups) — the dispatch table is in the module docstring.

        Returns the :class:`BuiltinRedirectFrame` recording everything this
        invocation changed; pass it to ``restore_builtin_redirections``.
        Transactional: a redirect failing part-way through (e.g.
        ``echo hi >a >/bad/x``) rolls back this frame — and only this
        frame — so the shell's streams and fds (including any outer
        invocation's) are never left hijacked.
        """
        if self.state.options.get('debug-exec'):
            print("DEBUG IOManager: setup_builtin_redirections called",
                  file=sys.stderr)
            redirects = [(r.type, r.target, r.fd) for r in command.redirects]
            print(f"DEBUG IOManager: Redirects: {redirects}",
                  file=sys.stderr)

        frame = BuiltinRedirectFrame()
        self._builtin_frame_stack.append(frame)

        # Fd-level closes (`>&-`/`<&-`) are deferred until every other
        # redirect in this command has been applied: an immediate os.close()
        # would free a low fd number (e.g. fd 1) that a LATER redirect's
        # open() in this same command would then reuse — so `cmd 1>&- 2>file`
        # would open the file ONTO fd 1, then close it on restore and corrupt
        # the shell's stdout. bash opens redirect targets on high fds for the
        # same reason; deferring the close gives the same result. The
        # stream-universe swap (so the builtin's write fails) still happens in
        # textual order via _builtin_redirect_close.
        deferred_closes: List[Redirect] = []

        try:
            for redirect in command.redirects:
                if redirect.var_fd:
                    # Named fd: persistent allocation in this process (the
                    # builtin runs in-process), stored in the variable.
                    self.file_redirector.apply_var_fd_redirect(redirect)
                    continue
                plan = self.file_redirector.planner.plan(redirect)
                redirect = plan.redirect
                target = plan.target
                # A builtin runs in-process and reads /dev/fd/N, so its
                # process-substitution read end must outlive this single
                # redirect: hand it to the enclosing process_sub_scope() for
                # deferred close rather than closing it after the dup2 (the
                # close_procsub() path the external/permanent backends use).
                plan.hand_procsub_to_scope(self.process_sub_handler)

                if redirect.combined:
                    self._builtin_redirect_combined(target, redirect, frame)
                elif redirect.type in ('<', '<>', '<<', '<<-', '<<<'):
                    self._builtin_redirect_stdin(target, redirect, frame)
                elif redirect.type in ('>', '>>', '>|'):
                    self._builtin_redirect_output_file(target, redirect, frame)
                elif redirect.type in ('>&', '<&'):
                    # A move (`n>&m-`) is a dup of m onto n followed by closing
                    # the source m (unless m == n). Apply the dup with the
                    # existing helpers, then DEFER the source close so it reuses
                    # the same stream-swap + late-close machinery as `>&-`.
                    dup_step, close_step = self._split_move_dup(redirect)
                    if redirect.type == '>&':
                        self._builtin_redirect_dup(dup_step, frame)
                    else:
                        self._builtin_redirect_fd_level(dup_step, frame)
                    if close_step is not None:
                        self._builtin_redirect_close(close_step, frame)
                        deferred_closes.append(close_step)
                elif redirect.type in ('>&-', '<&-'):
                    self._builtin_redirect_close(redirect, frame)
                    deferred_closes.append(redirect)

            # Apply the deferred fd-level closes now that all opens are done.
            for redirect in deferred_closes:
                self._builtin_redirect_fd_level(redirect, frame)
        except Exception:
            self.restore_builtin_redirections(frame)
            raise

        return frame

    def _builtin_redirect_stdin(self, target, redirect,
                                frame: BuiltinRedirectFrame):
        """``<``, ``<>``, heredoc, here-string for a builtin.

        Stdin (fd 0) is redirected in BOTH universes: the Python stream for
        the builtin itself (``read`` consumes ``sys.stdin``) and fd 0 —
        already dup2'd by the FileRedirector helpers called here — so any
        child spawned while the builtin runs inherits the redirected stdin.
        The frame snapshot's ``stdin_fd`` (a dup of the original fd 0) undoes
        the fd-level half on restore.

        An explicit fd prefix (``5<<EOF``, ``5<file``) materializes on that
        fd instead; the builtin's own ``sys.stdin`` must be left alone, so
        the stream swap is skipped and the fd-level redirect is saved/restored
        through the frame's fd-save list (``_builtin_redirect_fd_level``).
        """
        import io
        target_fd = redirect.fd if redirect.fd is not None else 0
        if target_fd != 0:
            # Body/file goes to a non-stdin fd: pure fd-level redirect, no
            # stream swap (the builtin keeps its own sys.stdin).
            self._builtin_redirect_fd_level(redirect, frame)
            return
        frame.snapshot.note_stdin()
        if redirect.type == '<':
            # target_fd is 0 here (the non-zero case returned above); pass the
            # redirect anyway so the fd source stays consistent across paths.
            self.file_redirector.redirect_input_from_file(target, redirect)
            f = open(target, 'r')
            frame.opened_streams.append(f)
            sys.stdin = f
        elif redirect.type == '<>':
            self.file_redirector.redirect_readwrite(target, redirect)
            f = open(target, 'r+')
            frame.opened_streams.append(f)
            sys.stdin = f
        elif redirect.type in ('<<', '<<-'):
            content = self.file_redirector.redirect_heredoc(redirect)
            sys.stdin = io.StringIO(content)
        else:  # '<<<'
            content = self.file_redirector.redirect_herestring(redirect)
            sys.stdin = io.StringIO(content)

    @staticmethod
    def _open_output_off_low_fds(target: str, mode: str) -> TextIO:
        """``open()`` a builtin's output target, keeping it off fds 0/1/2.

        Python's ``open`` takes the lowest free descriptor. After ``exec 1>&-``
        (or ``2>&-``) that free slot is fd 1 (or 2), which a stale
        ``sys.stdout``/``sys.stderr`` wrapper still names — the builtin's own
        writes would then silently land in THIS file instead of failing with
        EBADF (bash: ``write error: Bad file descriptor``). bash opens redirect
        targets on high fds for exactly this reason. Relocate onto fd >= 3
        (``F_DUPFD`` shares the open file description, so the truncation the
        original ``open`` already did stands) and drop the low slot.
        """
        # surrogateescape so a builtin can write shell values carrying
        # non-UTF-8 bytes (surrogate escapes, e.g. from `x=$(printf '\xff')`)
        # to a redirected file, matching bash's byte transparency and the
        # sys.stdout/stderr policy set at psh's entry point.
        f = open(target, mode, errors='surrogateescape')
        if f.fileno() >= 3:
            return cast(TextIO, f)
        high_fd = fcntl.fcntl(f.fileno(), fcntl.F_DUPFD, 3)
        f.close()  # frees the low slot; high_fd keeps the file open
        return cast(TextIO, os.fdopen(high_fd, mode, errors='surrogateescape'))

    def _dup_output_fd_for_children(self, source_fd: int, target_fd: int,
                                    frame: BuiltinRedirectFrame):
        """fd-level half of a builtin output redirect to fd 1/2.

        A builtin writes through ``sys.stdout``/``sys.stderr`` (the stream
        half), but a CHILD it spawns — ``eval``/``source`` running an external
        command, ``command ext`` — inherits raw fd 1/2, so those must be
        redirected too. This mirrors the stdin BOTH-universe treatment (see the
        module docstring): ``dup2`` ``source_fd`` (the opened file's fd) onto
        ``target_fd``, saving the original on the frame for restore. The dup2
        shares the open file description, so the builtin's stream writes and the
        child's fd writes keep one file offset (no re-truncation).

        The backup is forced onto a high fd (>= 10) via ``F_DUPFD``, like
        ``FileRedirector._save_fd_high``: a plain ``os.dup`` takes the lowest
        free slot, which after ``exec 1>&-`` is fd 1 — and the stale
        ``sys.stdout`` wrapper still names fd 1, so it would then write into
        this backup instead of failing with EBADF (bash keeps fd 1 closed).
        ``target_fd``'s original is saved tolerantly (None when it was closed,
        e.g. after ``exec 1>&-``), matching ``_save_fd_high``.
        """
        try:
            saved: Optional[int] = fcntl.fcntl(target_fd, fcntl.F_DUPFD, 10)
        except OSError:
            saved = None  # target_fd was not open — close it again on restore
        frame.saved_fds.append((target_fd, saved))
        os.dup2(source_fd, target_fd)

    def _builtin_redirect_combined(self, target, redirect,
                                   frame: BuiltinRedirectFrame):
        """``&>`` / ``&>>`` for a builtin: one file object serves both streams."""
        frame.snapshot.note_stdout()
        frame.snapshot.note_stderr()
        is_append = redirect.type.endswith('>>')
        if not is_append:
            self.file_redirector.check_noclobber(target)
        f = self._open_output_off_low_fds(target, 'a' if is_append else 'w')
        frame.opened_streams.append(f)
        sys.stdout = f
        sys.stderr = f
        # fd level too, so children the builtin spawns see both fds redirected.
        self._dup_output_fd_for_children(f.fileno(), 1, frame)
        self._dup_output_fd_for_children(f.fileno(), 2, frame)

    def _builtin_redirect_output_file(self, target, redirect,
                                      frame: BuiltinRedirectFrame):
        """``>``, ``>>``, ``>|`` for a builtin.

        For fd 1/2 the Python stream object is swapped (builtins write to
        sys.stdout/sys.stderr, not raw fds); for fd >= 3 there is no stream
        counterpart, so the redirect happens at the descriptor level.
        """
        if redirect.type == '>':
            self.file_redirector.check_noclobber(target)
        mode = 'a' if redirect.type == '>>' else 'w'
        target_fd = redirect.fd if redirect.fd is not None else 1
        if target_fd == 1:
            frame.snapshot.note_stdout()
            f = self._open_output_off_low_fds(target, mode)
            frame.opened_streams.append(f)
            sys.stdout = f
            # fd 1 too, so children the builtin spawns write to the file.
            self._dup_output_fd_for_children(f.fileno(), 1, frame)
            if self.state.options.get('debug-exec'):
                print(f"DEBUG IOManager: redirected stdout to '{target}' "
                      f"(mode {mode!r}); sys.stdout is now {sys.stdout}",
                      file=sys.stderr)
        elif target_fd == 2:
            frame.snapshot.note_stderr()
            f = self._open_output_off_low_fds(target, mode)
            frame.opened_streams.append(f)
            sys.stderr = f
            # fd 2 too, so children the builtin spawns write to the file.
            self._dup_output_fd_for_children(f.fileno(), 2, frame)
        else:
            self._builtin_redirect_fd_level(redirect, frame)

    def _builtin_redirect_dup(self, redirect,
                              frame: BuiltinRedirectFrame):
        """``>&`` fd duplication for a builtin (``2>&1``, ``1>&2``, ``1>&m``…).

        ``n>&m`` targeting fd 1/2 needs BOTH universes:

        * the fd-level dup (``_builtin_redirect_fd_level``) so a child the
          builtin spawns inherits it AND — crucially — so fd n becomes an
          INDEPENDENT duplicate of m's CURRENT target: a later ``m>file`` in
          the same command reassigns fd m without disturbing fd n, exactly
          as bash's descriptors behave;
        * a stream swap so the builtin's own writes go to the same place,
          bound to ``os.dup(m)`` — a fresh snapshot of m's current open file
          description — NOT an alias of the ``sys.stdout``/``sys.stderr``
          OBJECT. Aliasing the object (``sys.stdout = sys.stderr``) breaks
          ``echo hi 1>&2 2>file``: that object stays backed by real fd 2,
          which the later ``2>file`` clobbers out from under it, so the
          builtin's output lands in the file instead of on the old fd-2
          target (bash keeps it on the old target). ``os.dup`` shares m's
          offset/O_APPEND; line buffering interleaves with fd-level writers
          — same pattern as ``FileRedirector._stream_sharing_fd`` for
          ``exec``. It also covers ``1>&m``/``2>&m`` with m >= 3
          (``eval "echo x >&3" >/dev/null``), where the dup2 alone would be
          invisible because sys.stdout may be a swapped object not backed by
          fd 1.

        Dups of fds >= 3 (``3>&1``) have no stream counterpart and are purely
        fd level.
        """
        if redirect.fd in (1, 2) and redirect.dup_fd is not None:
            # Validates dup_fd and dup2's m onto fd n (independent of a later
            # reassignment of m); fd n's target is now a snapshot of m's.
            self._builtin_redirect_fd_level(redirect, frame)
            f = os.fdopen(os.dup(redirect.dup_fd), 'w', buffering=1,
                          errors='surrogateescape')
            frame.opened_streams.append(f)
            if redirect.fd == 1:
                frame.snapshot.note_stdout()
                sys.stdout = f
            else:
                frame.snapshot.note_stderr()
                sys.stderr = f
        else:
            self._builtin_redirect_fd_level(redirect, frame)

    @staticmethod
    def _split_move_dup(redirect):
        """Split a move (`[n]>&m-`) into its dup step and source-close step.

        A plain dup returns ``(redirect, None)``. A move returns a
        move-cleared dup plus a ``>&-``/``<&-`` close of the source fd — or
        ``None`` for the close when source == destination, which bash leaves
        open (`echo x 1>&1-` keeps stdout).
        """
        if not redirect.move:
            return redirect, None
        dup_only = copy.copy(redirect)
        dup_only.move = False
        close_step = None
        if redirect.dup_fd is not None and redirect.dup_fd != redirect.fd:
            close_step = Redirect(type=redirect.type + '-', target=None,
                                  fd=redirect.dup_fd)
        return dup_only, close_step

    def _builtin_redirect_close(self, redirect,
                                frame: BuiltinRedirectFrame):
        """``>&-`` / ``<&-`` fd close for a builtin.

        The fd is closed at the descriptor level (so children the builtin
        spawns inherit the closed fd, matching bash). But a builtin writes
        through the Python stream object, not the raw fd, so closing fd 1/2
        alone would let the builtin keep writing to the still-open stream and
        LEAK output (``echo hi 1>&-`` printing ``hi``). When the builtin's
        OWN output fd is closed — ``1>&-``/bare ``>&-`` (fd 1) or ``2>&-``
        (fd 2) — also swap the corresponding Python stream to one whose write
        raises EBADF, so the builtin's write fails exactly as bash's does
        (empty output + ``write error: Bad file descriptor`` + exit 1).

        ``<&-`` (input close) and closes of fd >= 3 have no output-stream
        counterpart and stay purely fd level.

        Only the STREAM swap happens here, in textual order; the fd-level
        close is deferred by setup_builtin_redirections (see the comment
        there) so a later redirect's open() cannot grab the freed fd number.
        """
        target_fd = self.output_close_fd(redirect)
        if target_fd is None:
            return
        # Record the pre-close stream on the frame (first-touch-wins) BEFORE
        # swapping, so restore reinstates the original.
        if target_fd == 1:
            frame.snapshot.note_stdout()
        else:
            frame.snapshot.note_stderr()
        self.swap_output_stream_closed(target_fd)

    def _builtin_redirect_fd_level(self, redirect,
                                   frame: BuiltinRedirectFrame):
        """Descriptor-level fallback for redirects with no stream counterpart.

        FileRedirector applies the redirect to the real fd; the (fd,
        saved_fd) pairs accumulate in ``frame.saved_fds``, which
        ``restore_builtin_redirections`` drains first. They must live on
        the frame, not the manager: a nested invocation (eval'd builtin
        inside a redirected eval) restoring manager-level saves would
        prematurely undo the OUTER command's fd redirects.
        """
        saved_fds = self.file_redirector.apply_redirections([redirect])
        frame.saved_fds.extend(saved_fds)

    def restore_builtin_redirections(self, frame: BuiltinRedirectFrame):
        """Undo exactly what ``setup_builtin_redirections`` did for *frame*.

        Frames must be restored innermost-first (LIFO). This is guaranteed
        by construction — every setup is paired with a restore in a
        ``try/finally`` (``_execute_builtin_with_redirections`` and the
        rollback path in setup), so even with eval/source/trap-handler
        nesting the Python call stack enforces the order. Out-of-order
        restore would re-point fds 0-2 underneath a still-active inner
        frame; it indicates a caller bug, so it is tolerated (each frame
        owns its own state) but the stack bookkeeping below keeps the
        invariant observable.
        """
        if self._builtin_frame_stack and self._builtin_frame_stack[-1] is frame:
            self._builtin_frame_stack.pop()
        elif frame in self._builtin_frame_stack:
            # Caller bug (see docstring); still restore this frame's own
            # state rather than leak fds/streams.
            self._builtin_frame_stack.remove(frame)

        # Restore any file descriptors this frame saved (fd >= 3 etc.)
        if frame.saved_fds:
            self.file_redirector.restore_redirections(frame.saved_fds)
            frame.saved_fds = []

        # Restore the original stream objects first, then close exactly the
        # files setup opened. Never close whatever happens to be in
        # sys.stdout/sys.stderr: after `cmd 2>&1`, sys.stderr IS the shell's
        # real stdout, and closing it used to kill all builtin output for the
        # rest of the session.
        snapshot = frame.snapshot
        if snapshot.stderr is not None:
            sys.stderr = snapshot.stderr
        if snapshot.stdout is not None:
            sys.stdout = snapshot.stdout
        if snapshot.stdin is not None:
            sys.stdin = snapshot.stdin

        for f in frame.opened_streams:
            try:
                f.close()
            except OSError:
                pass
        frame.opened_streams = []

        # Restore stdin file descriptor if it was saved
        if snapshot.stdin_fd is not None:
            os.dup2(snapshot.stdin_fd, 0)
            os.close(snapshot.stdin_fd)
            snapshot.stdin_fd = None

        # Process substitution resources are NOT cleaned up here: they are
        # owned by the enclosing process_sub_scope() (see CommandExecutor),
        # so a builtin running inside a function called with a <(...)
        # argument cannot close the caller's still-needed fd.

    @staticmethod
    def _child_redirect_error(error: OSError,
                              target: Optional[str] = None) -> NoReturn:
        """Emit a child redirect-setup failure through the ONE message shape and
        exit 1 — the forked-child counterpart of ``format_redirect_error``.

        Every failure site in ``setup_child_redirections`` routes here so a
        forked child never leaks a raw ``[Errno N] ...`` OSError repr where the
        parent (and bash) print ``psh: TARGET: STRERROR``. It cannot ``raise``
        (it runs after fork, past the point a normal exception can unwind), so
        it writes the formatted message with ``os.write`` and ``os._exit(1)``.
        """
        os.write(2, (format_redirect_error(error, target) + "\n")
                 .encode('utf-8'))
        os._exit(1)

    def setup_child_redirections(self, command: Command):
        """Set up redirections in child process (after fork) using dup2."""
        for redirect in command.redirects:
            if redirect.var_fd:
                # Named fd for a forked command (external / subshell): bash
                # allocates it INSIDE the child, so the variable is set in the
                # child (lost on exit) and the parent neither gets the variable
                # nor leaks the fd.
                try:
                    self.file_redirector.apply_var_fd_redirect(redirect)
                except OSError as e:
                    self._child_redirect_error(e)
                continue
            try:
                plan = self.file_redirector.planner.plan(redirect)
            except OSError as e:
                self._child_redirect_error(e)
            redirect = plan.redirect
            target = plan.target
            applied = False

            try:
                self.file_redirector.apply_fd_plan(plan)
                applied = True
            except OSError as e:
                # A real syscall failure opening/duping the redirect target
                # (ENOENT/EISDIR/EACCES) becomes bash's `psh: TARGET: STRERROR`;
                # an errno-None OSError (noclobber/ambiguous/bad-fd) keeps its
                # own message — both via the shared format_redirect_error shape.
                self._child_redirect_error(e, target)
            finally:
                plan.close_procsub(applied=applied)

    def create_process_substitution_for_expansion(self, direction: str,
                                                  command: str) -> str:
        """Create one process substitution during word expansion.

        Returns the /dev/fd/N path; the fd/pid are owned by the enclosing
        process_sub_scope().
        """
        return self.process_sub_handler.create_for_expansion(direction, command)

    def process_sub_scope(self):
        """Context manager owning process substitutions created within it.

        On exit, parent-side fds are closed and finished children are
        reaped with WNOHANG; still-running children are re-polled at later
        scope exits, so the shell never blocks on a substitution that
        outlives its command and never accumulates zombies.
        """
        return self.process_sub_handler.scope()
