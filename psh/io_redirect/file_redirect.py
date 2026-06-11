"""File redirection implementation."""
import copy
import fcntl
import os
import stat
import sys
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..ast_nodes import Redirect

if TYPE_CHECKING:
    from ..shell import Shell


def _dup2_preserve_target(opened_fd: int, target_fd: int):
    """dup2() helper that avoids closing target_fd when FDs already match."""
    if opened_fd == target_fd:
        return
    os.dup2(opened_fd, target_fd)
    os.close(opened_fd)


class FileRedirector:
    """Handles file-based I/O redirections."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state
        self._saved_stdout = None
        self._saved_stderr = None
        self._saved_stdin = None

    def _noclobber_blocks(self, target) -> bool:
        """True when noclobber forbids `>` to this target (bash semantics).

        noclobber protects only existing REGULAR files: `> /dev/null` and
        writes to FIFOs or other device files are always allowed, because
        opening a non-regular file for write destroys nothing. A dangling
        symlink also blocks — bash opens with O_CREAT|O_EXCL when the stat
        target is missing, and the link itself makes that open fail EEXIST.

        Shared predicate for every redirect path; the response differs (raise in
        the parent, os._exit in a forked child), but the condition is one place.
        """
        if not self.state.options.get('noclobber', False):
            return False
        try:
            st = os.stat(target)  # follows symlinks, like bash's stat()
        except OSError:
            # Target doesn't stat: nonexistent (allowed — the redirect will
            # create it) unless it's a dangling symlink (blocked, see above).
            return os.path.islink(target)
        return stat.S_ISREG(st.st_mode)

    def _dup_fd_valid(self, dup_fd: int) -> bool:
        """True when dup_fd is currently an open file descriptor (for >&/<&)."""
        try:
            fcntl.fcntl(dup_fd, fcntl.F_GETFD)
            return True
        except OSError:
            return False

    def _check_noclobber(self, target):
        """Raise OSError if noclobber is set and target exists."""
        if self._noclobber_blocks(target):
            raise OSError(f"cannot overwrite existing file: {target}")

    def _expand_redirect_target(self, redirect):
        """Expand variables and tilde in a redirect target."""
        target = redirect.target
        if not target or (redirect.type not in ('<', '>', '>>', '<>', '>|') and not redirect.combined):
            return target
        if not (hasattr(redirect, 'quote_type') and redirect.quote_type == "'"):
            target = self.shell.expansion_manager.expand_string_variables(target)
        if target.startswith('~'):
            target = self.shell.expansion_manager.expand_tilde(target)
        return target

    def _redirect_input_from_file(self, target, redirect=None):
        """Open file for input and dup2 to the redirect's fd (default 0).

        Honors an explicit source fd — ``exec 5<file`` must open fd 5,
        not clobber stdin. Returns the target fd.
        """
        target_fd = (redirect.fd if redirect is not None and
                     redirect.fd is not None else 0)
        fd = os.open(target, os.O_RDONLY)
        _dup2_preserve_target(fd, target_fd)
        return target_fd

    def _stdin_from_content(self, content: str):
        """Point stdin at `content` via an anonymous (unlinked) temp file.

        A pipe would deadlock for content larger than the kernel pipe buffer
        (~64KB on most systems) because the whole body is written before any
        reader exists. Bash uses a temporary file for heredocs for the same
        reason.
        """
        import tempfile
        tmp = tempfile.TemporaryFile()
        tmp.write(content.encode())
        tmp.flush()
        tmp.seek(0)
        os.dup2(tmp.fileno(), 0)
        tmp.close()  # fd 0 keeps the underlying file open

    def _redirect_heredoc(self, redirect):
        """Point stdin at the heredoc content. Returns the expanded content."""
        content = redirect.heredoc_content or ''
        if content and not getattr(redirect, 'heredoc_quoted', False):
            content = self.shell.expansion_manager.expand_string_variables(content)
        self._stdin_from_content(content)
        return content

    def _redirect_herestring(self, redirect):
        """Point stdin at the here-string content. Returns the content."""
        if hasattr(redirect, 'quote_type') and redirect.quote_type == "'":
            expanded = redirect.target
        else:
            expanded = self.shell.expansion_manager.expand_string_variables(redirect.target)
        content = expanded + '\n'
        self._stdin_from_content(content)
        return content

    def _redirect_output_to_file(self, target, redirect, check_noclobber=True):
        """Open file for output and dup2 to target fd. Returns target_fd."""
        target_fd = redirect.fd if redirect.fd is not None else 1
        if redirect.type == '>' and check_noclobber:
            self._check_noclobber(target)
        flags = os.O_WRONLY | os.O_CREAT
        flags |= os.O_TRUNC if redirect.type == '>' else os.O_APPEND
        fd = os.open(target, flags, 0o644)
        _dup2_preserve_target(fd, target_fd)
        return target_fd

    def _resolved(self, redirect):
        """Resolve a dynamic fd-dup target (e.g. ``>&$fd``, ``2>&$((n+1))``).

        For ``>&``/``<&`` redirects whose source fd is given by an expansion,
        the parser leaves ``dup_fd=None`` and stores the (expandable) target
        string. Expand it now, parse it as an integer, and return a shallow
        copy carrying the resolved ``dup_fd`` so every existing dispatch path
        (which reads ``redirect.dup_fd``) works unchanged. The original AST node
        is not mutated, so re-execution (e.g. in a loop) re-resolves each time.

        Non-dup, static (``2>&1``), or close (``>&-``) redirects are returned
        unchanged. Raises OSError for a non-numeric target (bash: "ambiguous
        redirect").
        """
        if redirect.type not in ('>&', '<&'):
            return redirect
        if redirect.dup_fd is not None or not redirect.target or redirect.target == '-':
            return redirect
        expanded = self.shell.expansion_manager.expand_string_variables(
            redirect.target).strip()
        try:
            fd = int(expanded)
        except ValueError:
            raise OSError(f"{expanded}: ambiguous redirect")
        resolved = copy.copy(redirect)
        resolved.dup_fd = fd
        return resolved

    def _redirect_dup_fd(self, redirect):
        """Handle >&/<& fd duplication. Validates source fd."""
        if redirect.fd is not None and redirect.dup_fd is not None:
            if not self._dup_fd_valid(redirect.dup_fd):
                raise OSError(f"{redirect.dup_fd}: Bad file descriptor")
            os.dup2(redirect.dup_fd, redirect.fd)
        elif redirect.fd is not None and redirect.target == '-':
            try:
                os.close(redirect.fd)
            except OSError:
                pass

    def _redirect_readwrite(self, target, redirect):
        """Open file for read-write (<>) and dup2 to target fd."""
        target_fd = redirect.fd if redirect.fd is not None else 0
        fd = os.open(target, os.O_RDWR | os.O_CREAT, 0o644)
        _dup2_preserve_target(fd, target_fd)
        return target_fd

    def _redirect_clobber(self, target, redirect):
        """Force overwrite (>|), ignoring noclobber."""
        target_fd = redirect.fd if redirect.fd is not None else 1
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        _dup2_preserve_target(fd, target_fd)
        return target_fd

    def _redirect_combined(self, target, redirect):
        """Redirect both stdout and stderr to file (&> or &>>)."""
        flags = os.O_WRONLY | os.O_CREAT
        is_append = redirect.type.endswith('>>')
        if is_append:
            flags |= os.O_APPEND
        else:
            if self._noclobber_blocks(target):
                raise OSError(f"cannot overwrite existing file: {target}")
            flags |= os.O_TRUNC
        fd = os.open(target, flags, 0o644)
        _dup2_preserve_target(fd, 1)   # stdout
        os.dup2(1, 2)                  # stderr → stdout

    def _redirect_close_fd(self, redirect):
        """Handle >&-/<&- fd close."""
        if redirect.fd is not None:
            try:
                os.close(redirect.fd)
            except OSError:
                pass

    def _save_fd(self, fd: int):
        """Dup `fd` so it can be restored later.

        Returns the duplicate, or None if `fd` is not currently open (e.g. a
        high fd like `7>file`, where there is no original to restore — the fd
        should simply be closed again on restore).
        """
        try:
            return os.dup(fd)
        except OSError:
            return None

    def apply_redirections(self, redirects: List[Redirect]) -> List[Tuple[int, int]]:
        """Apply redirections and return list of (fd, saved_fd) for restoration.

        Transactional: if any redirect fails part-way through (e.g.
        `cmd >a >/bad/x`), the ones already applied are rolled back before
        the exception propagates, so the shell's fds are never left hijacked.
        """
        saved_fds = []
        try:
            return self._apply_redirections(redirects, saved_fds)
        except Exception:
            self.restore_redirections(saved_fds)
            raise

    def _apply_redirections(self, redirects: List[Redirect],
                            saved_fds: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Apply redirections, appending (fd, saved_fd) pairs to saved_fds."""
        # Save current Python file objects
        self._saved_stdout = self.state.stdout
        self._saved_stderr = self.state.stderr
        self._saved_stdin = self.state.stdin

        for redirect in redirects:
            redirect = self._resolved(redirect)
            target = self._expand_redirect_target(redirect)
            procsub_fd = None
            if target and target.startswith(('<(', '>(')) and target.endswith(')'):
                target, procsub_fd = self._handle_process_sub_redirect(target, redirect)

            if redirect.combined:
                # &> or &>> — redirect both stdout and stderr
                saved_fds.append((1, os.dup(1)))
                saved_fds.append((2, os.dup(2)))
                self._redirect_combined(target, redirect)
            elif redirect.type == '<':
                in_fd = redirect.fd if redirect.fd is not None else 0
                saved_fds.append((in_fd, self._save_fd(in_fd)))
                self._redirect_input_from_file(target, redirect)
            elif redirect.type == '<>':
                target_fd = redirect.fd if redirect.fd is not None else 0
                saved_fds.append((target_fd, self._save_fd(target_fd)))
                self._redirect_readwrite(target, redirect)
            elif redirect.type in ('<<', '<<-'):
                saved_fds.append((0, os.dup(0)))
                self._redirect_heredoc(redirect)
            elif redirect.type == '<<<':
                saved_fds.append((0, os.dup(0)))
                self._redirect_herestring(redirect)
            elif redirect.type == '>|':
                target_fd = redirect.fd if redirect.fd is not None else 1
                saved_fds.append((target_fd, self._save_fd(target_fd)))
                self._redirect_clobber(target, redirect)
            elif redirect.type in ('>', '>>'):
                target_fd = redirect.fd if redirect.fd is not None else 1
                saved_fds.append((target_fd, self._save_fd(target_fd)))
                self._redirect_output_to_file(target, redirect)
            elif redirect.type in ('>&', '<&'):
                # Validate dup_fd BEFORE os.dup(redirect.fd), because os.dup
                # may allocate dup_fd's number as the saved copy, making a
                # closed fd appear valid.
                if (redirect.fd is not None and redirect.dup_fd is not None
                        and not self._dup_fd_valid(redirect.dup_fd)):
                    raise OSError(f"{redirect.dup_fd}: Bad file descriptor")
                if redirect.fd is not None and (redirect.dup_fd is not None or redirect.target == '-'):
                    saved_fds.append((redirect.fd, self._save_fd(redirect.fd)))
                self._redirect_dup_fd(redirect)
            elif redirect.type in ('>&-', '<&-'):
                if redirect.fd is not None:
                    saved_fds.append((redirect.fd, self._save_fd(redirect.fd)))
                self._redirect_close_fd(redirect)

            # The redirect's target fd now references the pipe itself;
            # release the substitution's original parent fd.
            self._close_procsub_parent_fd(procsub_fd, redirect)

        return saved_fds

    def restore_redirections(self, saved_fds: List[Tuple[int, int]]):
        """Restore file descriptors from saved list.

        Restore in REVERSE order: with the same fd redirected twice
        (e.g. `{ cmd; } >a >b`), the first saved backup holds the
        original fd and must win, i.e. be restored last.
        """
        for fd, saved_fd in reversed(saved_fds):
            if saved_fd is None:
                # The fd wasn't open before we redirected it (e.g. 7>file);
                # close what we opened instead of restoring an original.
                try:
                    os.close(fd)
                except OSError:
                    pass
            else:
                os.dup2(saved_fd, fd)
                os.close(saved_fd)

        # Restore Python file objects
        if self._saved_stdout is not None:
            self.state.stdout = self._saved_stdout
            self.state.stderr = self._saved_stderr
            self.state.stdin = self._saved_stdin
            self._saved_stdout = None
            self._saved_stderr = None
            self._saved_stdin = None

    def _stream_sharing_fd(self, target_fd: int):
        """Build a Python text stream that shares target_fd's open file description.

        Used after a *permanent* fd-level redirect (os.open + dup2): builtins
        write through the Python stream (sys.stdout/state.stdout) while
        external children inherit the raw fd, so both views MUST share one
        file offset. A second independent ``open(target, mode)`` would have
        its own offset (and re-truncate in 'w' mode), making the two writers
        overwrite each other. ``os.dup()`` shares the open file description
        (offset and O_APPEND), so dup + fdopen gives both universes a single
        file position. Line-buffered so builtin output reaches the file as
        each line completes, interleaving with external commands like bash's
        unbuffered writes. The dup also means the stream object never owns
        target_fd itself — replacing it later (a second ``exec >file``)
        closes only the dup.
        """
        return os.fdopen(os.dup(target_fd), 'w', buffering=1)

    def _rebind_output_stream(self, target_fd: int):
        """Point the shell's Python-level stdout/stderr at a redirected fd.

        Only fds 1 and 2 have Python stream counterparts; for any other fd
        (``exec 3>file``) the descriptor-level redirect is all there is.
        """
        if target_fd == 1:
            sys.stdout = self._stream_sharing_fd(1)
            self.shell.stdout = sys.stdout
            self.state.stdout = sys.stdout
        elif target_fd == 2:
            sys.stderr = self._stream_sharing_fd(2)
            self.shell.stderr = sys.stderr
            self.state.stderr = sys.stderr

    def apply_permanent_redirections(self, redirects: List[Redirect]):
        """Apply redirections permanently (for exec builtin).

        Output branches do the fd-level redirect first, then rebind the
        Python-level stream onto the SAME open file description via
        _rebind_output_stream() — never a second independent open().
        """
        # Pending buffered output belongs to the OLD destination; flush it
        # before the fd-level dup2 silently re-routes it to the new file.
        for stream in (self.state.stdout, self.state.stderr, sys.stdout, sys.stderr):
            try:
                stream.flush()
            except (OSError, ValueError):
                pass

        for redirect in redirects:
            redirect = self._resolved(redirect)
            target = self._expand_redirect_target(redirect)
            procsub_fd = None
            if target and target.startswith(('<(', '>(')) and target.endswith(')'):
                target, procsub_fd = self._handle_process_sub_redirect(target, redirect)

            if redirect.combined:
                # &> or &>> — redirect both stdout and stderr permanently.
                # After _redirect_combined, fd 2 is a dup of fd 1, so the
                # two rebound streams share one offset with each other and
                # with external children.
                self._redirect_combined(target, redirect)
                self._rebind_output_stream(1)
                self._rebind_output_stream(2)
            elif redirect.type == '<':
                target_fd = self._redirect_input_from_file(target, redirect)
                if target_fd == 0:
                    # Only rebind the shell's stdin when fd 0 changed —
                    # `exec 5<file` opens fd 5 and must leave stdin alone.
                    self.shell.stdin = sys.stdin
                    self.state.stdin = sys.stdin
            elif redirect.type == '<>':
                self._redirect_readwrite(target, redirect)
                self.shell.stdin = sys.stdin
                self.state.stdin = sys.stdin
            elif redirect.type in ('<<', '<<-'):
                self._redirect_heredoc(redirect)
                self.shell.stdin = sys.stdin
                self.state.stdin = sys.stdin
            elif redirect.type == '<<<':
                self._redirect_herestring(redirect)
                self.shell.stdin = sys.stdin
                self.state.stdin = sys.stdin
            elif redirect.type == '>|':
                target_fd = self._redirect_clobber(target, redirect)
                self._rebind_output_stream(target_fd)
            elif redirect.type in ('>', '>>'):
                target_fd = self._redirect_output_to_file(target, redirect)
                self._rebind_output_stream(target_fd)
            elif redirect.type in ('>&', '<&'):
                self._redirect_dup_fd(redirect)
                if redirect.fd is not None and redirect.dup_fd is not None:
                    self._rebind_output_stream(redirect.fd)
            elif redirect.type in ('>&-', '<&-'):
                self._redirect_close_fd(redirect)

            # The redirect's target fd now references the pipe itself;
            # release the substitution's original parent fd (skipped when
            # the parent fd's number became the permanent target, e.g.
            # `exec 3< <(cmd)` where the pipe end happened to be fd 3).
            self._close_procsub_parent_fd(procsub_fd, redirect)

    def _handle_process_sub_redirect(self, target: str,
                                     redirect: Redirect) -> Tuple[str, int]:
        """Handle process substitution used as a redirect target.

        Returns (fd_path, parent_fd). The child pid is registered with the
        ProcessSubstitutionHandler for non-blocking reaping; the parent fd
        is the CALLER's to close once the redirect has been applied (the
        redirect's target fd then holds its own reference to the pipe) —
        see _close_procsub_parent_fd().
        """
        from .process_sub import create_process_substitution

        direction = 'in' if target.startswith('<(') else 'out'
        cmd_str = target[2:-1]
        parent_fd, fd_path, pid = create_process_substitution(cmd_str, direction, self.shell)
        self.shell.io_manager.process_sub_handler.active_pids.append(pid)
        return fd_path, parent_fd

    @staticmethod
    def _close_procsub_parent_fd(procsub_fd: Optional[int], redirect: Redirect):
        """Close a redirect-target process substitution's parent fd.

        Skipped when dup2 repurposed the parent fd's NUMBER as the
        redirect's own target (e.g. `exec 3< <(cmd)` when the pipe end
        happened to be fd 3) — the number now IS the redirect.
        """
        if procsub_fd is None:
            return
        if redirect.combined:
            targets = (1, 2)
        elif redirect.fd is not None:
            targets = (redirect.fd,)
        else:
            targets = (0,) if redirect.type.startswith('<') else (1,)
        if procsub_fd in targets:
            return
        try:
            os.close(procsub_fd)
        except OSError:
            pass
