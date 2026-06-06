"""File redirection implementation."""
import copy
import fcntl
import os
from typing import TYPE_CHECKING, List, Tuple

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
        """True when noclobber is set and the target already exists.

        Shared predicate for every redirect path; the response differs (raise in
        the parent, os._exit in a forked child), but the condition is one place.
        """
        return self.state.options.get('noclobber', False) and os.path.exists(target)

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

    def _redirect_input_from_file(self, target):
        """Open file for input and dup2 to stdin."""
        fd = os.open(target, os.O_RDONLY)
        _dup2_preserve_target(fd, 0)

    def _redirect_heredoc(self, redirect):
        """Create pipe with heredoc content, dup2 to stdin. Returns content."""
        r, w = os.pipe()
        content = redirect.heredoc_content or ''
        if content and not getattr(redirect, 'heredoc_quoted', False):
            content = self.shell.expansion_manager.expand_string_variables(content)
        os.write(w, content.encode())
        os.close(w)
        _dup2_preserve_target(r, 0)
        return content

    def _redirect_herestring(self, redirect):
        """Create pipe with here-string content, dup2 to stdin. Returns content."""
        r, w = os.pipe()
        if hasattr(redirect, 'quote_type') and redirect.quote_type == "'":
            expanded = redirect.target
        else:
            expanded = self.shell.expansion_manager.expand_string_variables(redirect.target)
        content = expanded + '\n'
        os.write(w, content.encode())
        os.close(w)
        _dup2_preserve_target(r, 0)
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
        """Apply redirections and return list of (fd, saved_fd) for restoration."""
        saved_fds = []

        # Save current Python file objects
        self._saved_stdout = self.state.stdout
        self._saved_stderr = self.state.stderr
        self._saved_stdin = self.state.stdin

        for redirect in redirects:
            redirect = self._resolved(redirect)
            target = self._expand_redirect_target(redirect)
            if target and target.startswith(('<(', '>(')) and target.endswith(')'):
                target = self._handle_process_sub_redirect(target, redirect)

            if redirect.combined:
                # &> or &>> — redirect both stdout and stderr
                saved_fds.append((1, os.dup(1)))
                saved_fds.append((2, os.dup(2)))
                self._redirect_combined(target, redirect)
            elif redirect.type == '<':
                saved_fds.append((0, os.dup(0)))
                self._redirect_input_from_file(target)
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

        return saved_fds

    def restore_redirections(self, saved_fds: List[Tuple[int, int]]):
        """Restore file descriptors from saved list."""
        for fd, saved_fd in saved_fds:
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

    def apply_permanent_redirections(self, redirects: List[Redirect]):
        """Apply redirections permanently (for exec builtin)."""
        import sys

        for redirect in redirects:
            redirect = self._resolved(redirect)
            target = self._expand_redirect_target(redirect)
            if target and target.startswith(('<(', '>(')) and target.endswith(')'):
                target = self._handle_process_sub_redirect(target, redirect)

            if redirect.combined:
                # &> or &>> — redirect both stdout and stderr permanently
                self._redirect_combined(target, redirect)
                mode = 'a' if redirect.type.endswith('>>') else 'w'
                sys.stdout = open(target, mode)
                self.shell.stdout = sys.stdout
                self.state.stdout = sys.stdout
                sys.stderr = open(target, mode)
                self.shell.stderr = sys.stderr
                self.state.stderr = sys.stderr
            elif redirect.type == '<':
                self._redirect_input_from_file(target)
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
                if target_fd == 1:
                    sys.stdout = open(target, 'w')
                    self.shell.stdout = sys.stdout
                    self.state.stdout = sys.stdout
                elif target_fd == 2:
                    sys.stderr = open(target, 'w')
                    self.shell.stderr = sys.stderr
                    self.state.stderr = sys.stderr
            elif redirect.type in ('>', '>>'):
                target_fd = self._redirect_output_to_file(target, redirect)
                mode = 'w' if redirect.type == '>' else 'a'
                if target_fd == 1:
                    sys.stdout = open(target, mode)
                    self.shell.stdout = sys.stdout
                    self.state.stdout = sys.stdout
                elif target_fd == 2:
                    sys.stderr = open(target, mode)
                    self.shell.stderr = sys.stderr
                    self.state.stderr = sys.stderr
            elif redirect.type in ('>&', '<&'):
                self._redirect_dup_fd(redirect)
                if redirect.fd is not None and redirect.dup_fd is not None:
                    if redirect.fd == 1:
                        self.shell.stdout = os.fdopen(1, 'w')
                        self.state.stdout = self.shell.stdout
                    elif redirect.fd == 2:
                        self.shell.stderr = os.fdopen(2, 'w')
                        self.state.stderr = self.shell.stderr
            elif redirect.type in ('>&-', '<&-'):
                self._redirect_close_fd(redirect)

    def _handle_process_sub_redirect(self, target: str, redirect: Redirect) -> str:
        """Handle process substitution used as a redirect target."""
        from .process_sub import create_process_substitution

        direction = 'in' if target.startswith('<(') else 'out'
        cmd_str = target[2:-1]
        parent_fd, fd_path, pid = create_process_substitution(cmd_str, direction, self.shell)
        # Track through ProcessSubstitutionHandler for unified cleanup
        self.shell.io_manager.process_sub_handler.active_fds.append(parent_fd)
        self.shell.io_manager.process_sub_handler.active_pids.append(pid)
        return fd_path
