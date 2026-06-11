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
``>``, ``>>``, ``>|``, ``&>`` to fd 1/2   stream swap (``_builtin_redirect_output_file`` / ``_builtin_redirect_combined``)
``2>&1``, ``1>&2``                        stream swap (``sys.stderr = sys.stdout``), so builtin writes interleave and honor ordering
``<``, ``<>``, heredoc, here-string       BOTH: the stream for the builtin itself (``read`` consumes ``sys.stdin``) AND a dup2 of fd 0 — saved and restored — so any child spawned during the builtin sees the redirected stdin
fd >= 3, other ``n>&m``, ``>&-``          fd level via FileRedirector (no Python stream counterpart exists)
========================================  =====================================

Restore (``restore_builtin_redirections``) is transactional and
order-aware: the ORIGINAL stream objects are recorded first-touch-wins
(same fd redirected twice must restore the original, not the intermediate),
exactly the files setup opened are closed (never whatever happens to be in
``sys.stdout`` — after ``cmd 2>&1`` that IS the shell's real stdout), and a
failure part-way through setup rolls back everything already applied.
"""
import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, List, Optional, TextIO, Tuple

from ..ast_nodes import Command, Redirect
from .file_redirect import FileRedirector
from .process_sub import ProcessSubstitutionHandler

if TYPE_CHECKING:
    from ..shell import Shell


class _BuiltinStreamSnapshot:
    """The Python streams (and the stdin fd) as they were BEFORE the first
    redirect touched them.

    First-touch-wins: with the same stream redirected twice
    (``echo hi >a >b``), restore must reinstate the ORIGINAL stream, not the
    file object the first redirect installed. ``note_*()`` records the
    current stream only if nothing was recorded yet; the four attributes are
    exactly the tuple ``setup_builtin_redirections`` returns and
    ``restore_builtin_redirections`` accepts.
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

    def as_tuple(self) -> Tuple:
        return self.stdin, self.stdout, self.stderr, self.stdin_fd


class IOManager:
    """Manages all I/O redirections including files, heredocs, and process substitutions."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Initialize sub-handlers (heredoc content is handled by FileRedirector)
        self.file_redirector = FileRedirector(shell)
        self.process_sub_handler = ProcessSubstitutionHandler(shell)

        # Track saved file descriptors for restoration
        self._saved_fds_list = []
        # File objects opened by setup_builtin_redirections; restore closes
        # exactly these (never whatever happens to be in sys.stdout/stderr)
        self._opened_streams = []


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
            try:
                yield
            finally:
                self.restore_redirections(saved_fds)

    def apply_redirections(self, redirects: List[Redirect]) -> List[Tuple[int, int]]:
        """Apply redirections and return list of saved FDs for restoration."""
        return self.file_redirector.apply_redirections(redirects)

    def restore_redirections(self, saved_fds: List[Tuple[int, int]]):
        """Restore file descriptors from saved list."""
        self.file_redirector.restore_redirections(saved_fds)

    def apply_permanent_redirections(self, redirects: List[Redirect]):
        """Apply redirections permanently (for exec builtin)."""
        return self.file_redirector.apply_permanent_redirections(redirects)

    def setup_builtin_redirections(self, command: Command) -> Tuple:
        """Set up redirections for a built-in command (see module docstring).

        Each redirect goes to the stream universe (fds 0/1/2, which builtins
        reach through Python stream objects) or the fd universe (fd >= 3,
        uncommon dups) — the dispatch table is in the module docstring.

        Returns ``(stdin_backup, stdout_backup, stderr_backup,
        stdin_fd_backup)`` for ``restore_builtin_redirections``.
        Transactional: a redirect failing part-way through (e.g.
        ``echo hi >a >/bad/x``) rolls back everything already applied so the
        shell's streams and fds are never left hijacked.
        """
        if self.state.options.get('debug-exec'):
            print("DEBUG IOManager: setup_builtin_redirections called", file=sys.stderr)
            print(f"DEBUG IOManager: Redirects: {[(r.type, r.target, r.fd) for r in command.redirects]}", file=sys.stderr)

        self._opened_streams = []
        snapshot = _BuiltinStreamSnapshot()

        try:
            for redirect in command.redirects:
                redirect = self.file_redirector._resolved(redirect)
                target = self.file_redirector._expand_redirect_target(redirect)
                target = self._builtin_procsub_target(target)

                if redirect.combined:
                    self._builtin_redirect_combined(target, redirect, snapshot)
                elif redirect.type in ('<', '<>', '<<', '<<-', '<<<'):
                    self._builtin_redirect_stdin(target, redirect, snapshot)
                elif redirect.type in ('>', '>>', '>|'):
                    self._builtin_redirect_output_file(target, redirect, snapshot)
                elif redirect.type == '>&':
                    self._builtin_redirect_dup(redirect, snapshot)
                elif redirect.type in ('<&', '>&-', '<&-'):
                    self._builtin_redirect_fd_level(redirect)
        except Exception:
            self.restore_builtin_redirections(*snapshot.as_tuple())
            raise

        return snapshot.as_tuple()

    def _builtin_procsub_target(self, target):
        """Resolve a process-substitution redirect target to its /dev/fd path.

        The substitution's parent fd and child pid are registered with the
        ProcessSubstitutionHandler; the enclosing process_sub_scope() owns
        their cleanup (NOT restore_builtin_redirections — see its docstring).
        """
        if not (target and target.startswith(('<(', '>(')) and target.endswith(')')):
            return target
        from .process_sub import create_process_substitution

        direction = 'in' if target.startswith('<(') else 'out'
        parent_fd, fd_path, pid = create_process_substitution(
            target[2:-1], direction, self.shell)
        self.process_sub_handler.active_fds.append(parent_fd)
        self.process_sub_handler.active_pids.append(pid)
        return fd_path

    def _builtin_redirect_stdin(self, target, redirect,
                                snapshot: _BuiltinStreamSnapshot):
        """``<``, ``<>``, heredoc, here-string for a builtin.

        Stdin is redirected in BOTH universes: the Python stream for the
        builtin itself (``read`` consumes ``sys.stdin``) and fd 0 — already
        dup2'd by the FileRedirector helpers called here — so any child
        spawned while the builtin runs inherits the redirected stdin. The
        snapshot's ``stdin_fd`` (a dup of the original fd 0) undoes the
        fd-level half on restore.
        """
        import io
        snapshot.note_stdin()
        if redirect.type == '<':
            self.file_redirector._redirect_input_from_file(target)
            f = open(target, 'r')
            self._opened_streams.append(f)
            sys.stdin = f
        elif redirect.type == '<>':
            self.file_redirector._redirect_readwrite(target, redirect)
            f = open(target, 'r+')
            self._opened_streams.append(f)
            sys.stdin = f
        elif redirect.type in ('<<', '<<-'):
            content = self.file_redirector._redirect_heredoc(redirect)
            sys.stdin = io.StringIO(content)
        else:  # '<<<'
            content = self.file_redirector._redirect_herestring(redirect)
            sys.stdin = io.StringIO(content)

    def _builtin_redirect_combined(self, target, redirect,
                                   snapshot: _BuiltinStreamSnapshot):
        """``&>`` / ``&>>`` for a builtin: one file object serves both streams."""
        snapshot.note_stdout()
        snapshot.note_stderr()
        is_append = redirect.type.endswith('>>')
        if not is_append and self.file_redirector._noclobber_blocks(target):
            raise OSError(f"cannot overwrite existing file: {target}")
        f = open(target, 'a' if is_append else 'w')
        self._opened_streams.append(f)
        sys.stdout = f
        sys.stderr = f

    def _builtin_redirect_output_file(self, target, redirect,
                                      snapshot: _BuiltinStreamSnapshot):
        """``>``, ``>>``, ``>|`` for a builtin.

        For fd 1/2 the Python stream object is swapped (builtins write to
        sys.stdout/sys.stderr, not raw fds); for fd >= 3 there is no stream
        counterpart, so the redirect happens at the descriptor level.
        """
        if redirect.type == '>':
            self.file_redirector._check_noclobber(target)
        mode = 'a' if redirect.type == '>>' else 'w'
        target_fd = redirect.fd if redirect.fd is not None else 1
        if target_fd == 1:
            snapshot.note_stdout()
            f = open(target, mode)
            self._opened_streams.append(f)
            sys.stdout = f
            if self.state.options.get('debug-exec'):
                print(f"DEBUG IOManager: redirected stdout to '{target}' "
                      f"(mode {mode!r}); sys.stdout is now {sys.stdout}",
                      file=sys.stderr)
        elif target_fd == 2:
            snapshot.note_stderr()
            f = open(target, mode)
            self._opened_streams.append(f)
            sys.stderr = f
        else:
            self._builtin_redirect_fd_level(redirect)

    def _builtin_redirect_dup(self, redirect,
                              snapshot: _BuiltinStreamSnapshot):
        """``>&`` fd duplication for a builtin.

        For the common ``2>&1`` / ``1>&2`` cases the Python stream objects
        are swapped, so a builtin's writes interleave correctly and honour
        redirect ordering. Any other dup (fd >= 3, ``n>&m``) is rare for a
        builtin and handled at the fd level.
        """
        if redirect.fd == 2 and redirect.dup_fd == 1:
            snapshot.note_stderr()
            sys.stderr = sys.stdout
        elif redirect.fd == 1 and redirect.dup_fd == 2:
            snapshot.note_stdout()
            sys.stdout = sys.stderr
        else:
            self._builtin_redirect_fd_level(redirect)

    def _builtin_redirect_fd_level(self, redirect):
        """Descriptor-level fallback for redirects with no stream counterpart.

        FileRedirector applies the redirect to the real fd; the (fd,
        saved_fd) pairs accumulate in ``self._saved_fds_list``, which
        ``restore_builtin_redirections`` drains first.
        """
        saved_fds = self.file_redirector.apply_redirections([redirect])
        self._saved_fds_list.extend(saved_fds)

    def restore_builtin_redirections(self, stdin_backup, stdout_backup, stderr_backup, stdin_fd_backup=None):
        """Restore original stdin/stdout/stderr after built-in execution"""
        # Restore any file descriptors saved by file_redirector
        if self._saved_fds_list:
            self.file_redirector.restore_redirections(self._saved_fds_list)
            self._saved_fds_list = []

        # Restore the original stream objects first, then close exactly the
        # files setup opened. Never close whatever happens to be in
        # sys.stdout/sys.stderr: after `cmd 2>&1`, sys.stderr IS the shell's
        # real stdout, and closing it used to kill all builtin output for the
        # rest of the session.
        if stderr_backup is not None:
            sys.stderr = stderr_backup
        if stdout_backup is not None:
            sys.stdout = stdout_backup
        if stdin_backup is not None:
            sys.stdin = stdin_backup

        for f in self._opened_streams:
            try:
                f.close()
            except OSError:
                pass
        self._opened_streams = []

        # Restore stdin file descriptor if it was saved
        if stdin_fd_backup is not None:
            os.dup2(stdin_fd_backup, 0)
            os.close(stdin_fd_backup)

        # Process substitution resources are NOT cleaned up here: they are
        # owned by the enclosing process_sub_scope() (see CommandExecutor),
        # so a builtin running inside a function called with a <(...)
        # argument cannot close the caller's still-needed fd.

    def setup_child_redirections(self, command: Command):
        """Set up redirections in child process (after fork) using dup2."""
        for redirect in command.redirects:
            try:
                redirect = self.file_redirector._resolved(redirect)
            except OSError as e:
                os.write(2, f"psh: {e}\n".encode('utf-8'))
                os._exit(1)
            target = self.file_redirector._expand_redirect_target(redirect)

            # Handle process substitution as redirect target
            proc_sub_fd_to_close = None
            if target and target.startswith(('<(', '>(')) and target.endswith(')'):
                path, fd_to_close, pid = self.process_sub_handler.handle_redirect_process_sub(target)
                target = path
                proc_sub_fd_to_close = fd_to_close

            try:
                if redirect.combined:
                    # &> or &>> — redirect both stdout and stderr in child
                    if not redirect.type.endswith('>>') and self.file_redirector._noclobber_blocks(target):
                        os.write(2, f"psh: cannot overwrite existing file: {target}\n".encode('utf-8'))
                        os._exit(1)
                    self.file_redirector._redirect_combined(target, redirect)
                elif redirect.type == '<':
                    self.file_redirector._redirect_input_from_file(target)
                elif redirect.type == '<>':
                    self.file_redirector._redirect_readwrite(target, redirect)
                elif redirect.type in ('<<', '<<-'):
                    self.file_redirector._redirect_heredoc(redirect)
                elif redirect.type == '<<<':
                    self.file_redirector._redirect_herestring(redirect)
                elif redirect.type == '>|':
                    self.file_redirector._redirect_clobber(target, redirect)
                elif redirect.type in ('>', '>>'):
                    # Child-process noclobber must exit, not raise
                    if redirect.type == '>' and self.file_redirector._noclobber_blocks(target):
                        os.write(2, f"psh: cannot overwrite existing file: {target}\n".encode('utf-8'))
                        os._exit(1)
                    self.file_redirector._redirect_output_to_file(target, redirect, check_noclobber=False)
                elif redirect.type == '>&':
                    # Child-process fd dup: must exit on error, not raise
                    if redirect.fd is not None and redirect.dup_fd is not None:
                        if not self.file_redirector._dup_fd_valid(redirect.dup_fd):
                            os.write(2, f"psh: {redirect.dup_fd}: Bad file descriptor\n".encode('utf-8'))
                            os._exit(1)
                        os.dup2(redirect.dup_fd, redirect.fd)
                    elif redirect.fd is not None and redirect.target == '-':
                        try:
                            os.close(redirect.fd)
                        except OSError:
                            pass
                elif redirect.type == '<&':
                    if redirect.fd is not None and redirect.dup_fd is not None:
                        if not self.file_redirector._dup_fd_valid(redirect.dup_fd):
                            os.write(2, f"psh: {redirect.dup_fd}: Bad file descriptor\n".encode('utf-8'))
                            os._exit(1)
                        os.dup2(redirect.dup_fd, redirect.fd)
                elif redirect.type in ('>&-', '<&-'):
                    self.file_redirector._redirect_close_fd(redirect)
            finally:
                if proc_sub_fd_to_close is not None:
                    try:
                        os.close(proc_sub_fd_to_close)
                    except OSError:
                        pass

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

