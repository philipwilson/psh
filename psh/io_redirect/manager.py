"""I/O redirection manager for handling all types of redirections."""
import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, List, Tuple

from ..ast_nodes import Command, Redirect
from .file_redirect import FileRedirector
from .heredoc import HeredocHandler
from .process_sub import ProcessSubstitutionHandler

if TYPE_CHECKING:
    from ..shell import Shell


class IOManager:
    """Manages all I/O redirections including files, heredocs, and process substitutions."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Initialize sub-handlers
        self.file_redirector = FileRedirector(shell)
        self.heredoc_handler = HeredocHandler(shell)
        self.process_sub_handler = ProcessSubstitutionHandler(shell)

        # Track saved file descriptors for restoration
        self._saved_fds = []
        self._saved_fds_list = []


    @contextmanager
    def with_redirections(self, redirects: List[Redirect]):
        """Context manager for applying redirections temporarily."""
        if not redirects:
            yield
            return
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
        """Set up redirections for built-in commands. Returns tuple of backup objects."""
        import io

        # DEBUG: Log builtin redirection setup
        if self.state.options.get('debug-exec'):
            print(f"DEBUG IOManager: setup_builtin_redirections called", file=sys.stderr)
            print(f"DEBUG IOManager: Redirects: {[(r.type, r.target, r.fd) for r in command.redirects]}", file=sys.stderr)

        stdout_backup = None
        stderr_backup = None
        stdin_backup = None
        stdin_fd_backup = None

        for redirect in command.redirects:
            target = self.file_redirector._expand_redirect_target(redirect)

            # Handle process substitution as redirect target
            if target and target.startswith(('<(', '>(')) and target.endswith(')'):
                from .process_sub import create_process_substitution

                direction = 'in' if target.startswith('<(') else 'out'
                cmd_str = target[2:-1]
                parent_fd, fd_path, pid = create_process_substitution(cmd_str, direction, self.shell)
                self.process_sub_handler.active_fds.append(parent_fd)
                self.process_sub_handler.active_pids.append(pid)
                target = fd_path

            if redirect.combined:
                # &> or &>> — redirect both stdout and stderr
                stdout_backup = sys.stdout
                stderr_backup = sys.stderr
                is_append = redirect.type.endswith('>>')
                mode = 'a' if is_append else 'w'
                if not is_append and self.state.options.get('noclobber', False) and os.path.exists(target):
                    raise OSError(f"cannot overwrite existing file: {target}")
                f = open(target, mode)
                sys.stdout = f
                sys.stderr = f
            elif redirect.type == '<':
                stdin_backup = sys.stdin
                stdin_fd_backup = os.dup(0)
                self.file_redirector._redirect_input_from_file(target)
                sys.stdin = open(target, 'r')
            elif redirect.type == '<>':
                stdin_backup = sys.stdin
                stdin_fd_backup = os.dup(0)
                self.file_redirector._redirect_readwrite(target, redirect)
                sys.stdin = open(target, 'r+')
            elif redirect.type in ('<<', '<<-'):
                stdin_backup = sys.stdin
                stdin_fd_backup = os.dup(0)
                content = self.file_redirector._redirect_heredoc(redirect)
                sys.stdin = io.StringIO(content)
            elif redirect.type == '<<<':
                stdin_backup = sys.stdin
                stdin_fd_backup = os.dup(0)
                content = self.file_redirector._redirect_herestring(redirect)
                sys.stdin = io.StringIO(content)
            elif redirect.type == '>|':
                target_fd = redirect.fd if redirect.fd is not None else 1
                if target_fd == 1:
                    stdout_backup = sys.stdout
                    sys.stdout = open(target, 'w')
                elif target_fd == 2:
                    stderr_backup = sys.stderr
                    sys.stderr = open(target, 'w')
                else:
                    # fd >= 3: operate on the real descriptor, not sys.stdout.
                    saved_fds = self.file_redirector.apply_redirections([redirect])
                    self._saved_fds_list.extend(saved_fds)
            elif redirect.type in ('>', '>>'):
                target_fd = redirect.fd if redirect.fd is not None else 1
                mode = 'w' if redirect.type == '>' else 'a'
                if redirect.type == '>':
                    self.file_redirector._check_noclobber(target)
                if target_fd == 1:
                    stdout_backup = sys.stdout
                    sys.stdout = open(target, mode)
                    if self.state.options.get('debug-exec'):
                        action = "Redirected stdout" if redirect.type == '>' else "Redirected stdout (append)"
                        print(f"DEBUG IOManager: {action} to file '{target}'", file=sys.stderr)
                        print(f"DEBUG IOManager: sys.stdout is now {sys.stdout}", file=sys.stderr)
                elif target_fd == 2:
                    stderr_backup = sys.stderr
                    sys.stderr = open(target, mode)
                else:
                    # fd >= 3: operate on the real descriptor, not sys.stdout.
                    saved_fds = self.file_redirector.apply_redirections([redirect])
                    self._saved_fds_list.extend(saved_fds)
            elif redirect.type == '>&':
                # Handle fd duplication like 2>&1, >&2, etc.
                if redirect.fd == 2 and redirect.dup_fd == 1:
                    stderr_backup = sys.stderr
                    sys.stderr = sys.stdout
                elif redirect.fd == 1 and redirect.dup_fd == 2:
                    stdout_backup = sys.stdout
                    sys.stdout = sys.stderr
                else:
                    saved_fds = self.file_redirector.apply_redirections([redirect])
                    self._saved_fds_list.extend(saved_fds)
            elif redirect.type in ('<&', '>&-', '<&-'):
                saved_fds = self.file_redirector.apply_redirections([redirect])
                self._saved_fds_list.extend(saved_fds)

        return stdin_backup, stdout_backup, stderr_backup, stdin_fd_backup

    def restore_builtin_redirections(self, stdin_backup, stdout_backup, stderr_backup, stdin_fd_backup=None):
        """Restore original stdin/stdout/stderr after built-in execution"""
        import io

        # Restore any file descriptors saved by file_redirector
        if self._saved_fds_list:
            self.file_redirector.restore_redirections(self._saved_fds_list)
            self._saved_fds_list = []

        # Restore in reverse order
        if stderr_backup is not None:
            if hasattr(sys.stderr, 'close') and sys.stderr != stderr_backup:
                # Don't close StringIO objects as they might be reused
                if not isinstance(sys.stderr, io.StringIO):
                    sys.stderr.close()
            sys.stderr = stderr_backup

        if stdout_backup is not None:
            if hasattr(sys.stdout, 'close') and sys.stdout != stdout_backup:
                # Don't close StringIO objects as they might be reused
                if not isinstance(sys.stdout, io.StringIO):
                    sys.stdout.close()
            sys.stdout = stdout_backup

        if stdin_backup is not None:
            if hasattr(sys.stdin, 'close') and sys.stdin != stdin_backup:
                # Don't close StringIO objects as they might be reused
                if not isinstance(sys.stdin, io.StringIO):
                    sys.stdin.close()
            sys.stdin = stdin_backup

        # Restore stdin file descriptor if it was saved
        if stdin_fd_backup is not None:
            os.dup2(stdin_fd_backup, 0)
            os.close(stdin_fd_backup)

        # Clean up process substitution resources if any
        self.process_sub_handler.cleanup()

    def setup_child_redirections(self, command: Command):
        """Set up redirections in child process (after fork) using dup2."""
        for redirect in command.redirects:
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
                    if not redirect.type.endswith('>>') and self.state.options.get('noclobber', False) and os.path.exists(target):
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
                    if redirect.type == '>' and self.state.options.get('noclobber', False) and os.path.exists(target):
                        os.write(2, f"psh: cannot overwrite existing file: {target}\n".encode('utf-8'))
                        os._exit(1)
                    self.file_redirector._redirect_output_to_file(target, redirect, check_noclobber=False)
                elif redirect.type == '>&':
                    # Child-process fd dup: must exit on error, not raise
                    if redirect.fd is not None and redirect.dup_fd is not None:
                        try:
                            import fcntl
                            fcntl.fcntl(redirect.dup_fd, fcntl.F_GETFD)
                        except OSError:
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
                        try:
                            import fcntl
                            fcntl.fcntl(redirect.dup_fd, fcntl.F_GETFD)
                        except OSError:
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

    def setup_process_substitutions(self, command: Command) -> Tuple[List[int], List[str], List[int]]:
        """Set up process substitutions for a command."""
        return self.process_sub_handler.setup_process_substitutions(command)

    def cleanup_process_substitutions(self):
        """Clean up process substitution resources."""
        self.process_sub_handler.cleanup()

