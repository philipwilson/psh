"""Process substitution implementation."""
import fcntl
import os
import signal
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from ..ast_nodes import Redirect
    from ..shell import Shell


def create_process_substitution(
        cmd_str: str, direction: str,
        shell: 'Shell') -> Tuple[Optional[int], str, int, Optional[str]]:
    """Create a process substitution, returning (parent_fd, fd_path, child_pid).

    Args:
        cmd_str: The command string to execute (without the <()/>()} wrapper).
        direction: 'in' for <(cmd) (parent reads), 'out' for >(cmd) (parent writes).
        shell: The parent shell instance.

    Returns:
        Tuple of (parent_fd, path, child_pid, cleanup_path). parent_fd is
        None for FIFO-backed write-side substitutions.
    """
    if direction == 'out':
        return _create_write_process_substitution(cmd_str, shell)

    # Create pipe
    # For <(cmd), parent reads from pipe, child writes to it
    read_fd, write_fd = os.pipe()
    parent_fd = read_fd
    child_fd = write_fd
    child_stdout = child_fd

    # Clear close-on-exec flag for parent_fd so it survives exec
    flags = fcntl.fcntl(parent_fd, fcntl.F_GETFD)
    fcntl.fcntl(parent_fd, fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)

    # Fork child for process substitution, with termination signals
    # blocked across the fork window (the v0.300 lost-signal race fix;
    # the child unblocks them in apply_child_signal_policy after
    # resetting handlers to SIG_DFL).
    from psh.executor import fork_with_signal_window, run_child_shell
    pid = fork_with_signal_window()
    if pid == 0:  # Child
        # run_child_shell owns the generic child-process work (signal
        # policy, child Shell, exception -> exit-code mapping, stream
        # flush, os._exit). We supply the fd plumbing and the body.
        def _io_setup() -> None:
            # Close parent's end of pipe, wire ours onto stdio.
            os.close(parent_fd)
            os.dup2(child_stdout, 1)
            # Close the pipe fd we duplicated
            os.close(child_fd)

        def _body(child_shell: 'Shell') -> int:
            from ..lexer import tokenize
            from ..parser import parse
            tokens = tokenize(cmd_str)
            ast = parse(tokens)
            return child_shell.execute_command_list(ast)

        run_child_shell(
            shell, _body,
            norc=False,
            io_setup=_io_setup,
            error_label='process substitution',
        )

    else:  # Parent
        # Close child's end of pipe
        os.close(child_fd)

        # Create path for this fd
        fd_path = f"/dev/fd/{parent_fd}"

        return parent_fd, fd_path, pid, None


def _execute_process_substitution_body(cmd_str: str, child_shell: 'Shell') -> int:
    from ..lexer import tokenize
    from ..parser import parse
    tokens = tokenize(cmd_str)
    ast = parse(tokens)
    return child_shell.execute_command_list(ast)


def _create_write_process_substitution(cmd_str: str, shell: 'Shell') -> Tuple[None, str, int, str]:
    """Create a FIFO-backed ``>(cmd)`` substitution.

    On macOS, reopening a write-only pipe through ``/dev/fd/N`` can fail
    with EPERM for external consumers such as ``tee``. A named FIFO gives
    those consumers a normal path to open while the substitution command
    reads from the FIFO on stdin.
    """
    fifo_dir = tempfile.mkdtemp(prefix='psh-psub-')
    fifo_path = os.path.join(fifo_dir, 'pipe')
    os.mkfifo(fifo_path, 0o600)

    from psh.executor import fork_with_signal_window, run_child_shell
    pid = fork_with_signal_window()
    if pid == 0:
        def _io_setup() -> None:
            class OpenTimeout(Exception):
                pass

            def timeout_handler(_signum, _frame):
                raise OpenTimeout()

            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            fd = None
            try:
                # If nobody ever opens the generated path, do not leave the
                # substitution child blocked forever in open(2). Consuming
                # commands open the FIFO immediately, so this does not affect
                # normal `tee >(cmd)` style use.
                signal.alarm(5)
                try:
                    fd = os.open(fifo_path, os.O_RDONLY)
                except OpenTimeout:
                    fd = os.open(os.devnull, os.O_RDONLY)
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
                os.dup2(fd, 0)
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

        def _body(child_shell: 'Shell') -> int:
            return _execute_process_substitution_body(cmd_str, child_shell)

        run_child_shell(
            shell, _body,
            norc=False,
            io_setup=_io_setup,
            error_label='process substitution',
        )

    return None, fifo_path, pid, fifo_path


@dataclass
class ProcessSubstitutionResource:
    """One process substitution created for a redirect target."""
    path: str
    parent_fd: Optional[int]
    pid: int
    cleanup_path: Optional[str] = None

    def register_with(self, handler: 'ProcessSubstitutionHandler') -> None:
        handler.active_pids.append(self.pid)
        if self.cleanup_path is not None:
            handler.active_paths.append(self.cleanup_path)

    def close_parent_fd_for_redirect(
            self, redirect: 'Redirect', *, applied: bool) -> None:
        """Close the parent fd unless successful dup2 made it the target fd."""
        if self.parent_fd is None:
            return
        if applied and self.parent_fd in self._target_fds(redirect):
            return
        try:
            os.close(self.parent_fd)
        except OSError:
            pass
        self.parent_fd = None

    @staticmethod
    def _target_fds(redirect: 'Redirect') -> Tuple[int, ...]:
        if redirect.combined:
            return (1, 2)
        if redirect.fd is not None:
            return (redirect.fd,)
        return (0,) if redirect.type.startswith('<') else (1,)


class ProcessSubstitutionHandler:
    """Handles process substitution <(...) and >(...)."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Track process substitution resources for the scope currently
        # being executed (see scope()).
        self.active_fds: List[int] = []
        self.active_pids: List[int] = []
        self.active_paths: List[str] = []
        # Children whose consuming command has finished but which had not
        # exited yet (e.g. `echo >(sleep 3)`). They are re-polled
        # non-blockingly at every scope exit so they are reaped soon after
        # they exit, without ever making the shell wait for them (bash
        # behaves the same: the substitution may outlive its command).
        self.pending_pids: List[int] = []

    def create_for_expansion(self, direction: str, command: str) -> str:
        """Create one process substitution during word expansion.

        Used by the expansion manager for ProcessSubstitution word parts —
        both whole-word (``<(cmd)``) and embedded (``pre<(cmd)post``) forms.
        The parent fd and child pid are registered with the handler so the
        enclosing scope() closes the fd and reaps the child when the
        consuming command finishes.

        Args:
            direction: 'in' for <(cmd), 'out' for >(cmd).
            command: The command text (without the <()/>()} wrapper).

        Returns:
            The /dev/fd/N path to splice into the word.
        """
        fd, path, pid, cleanup_path = create_process_substitution(
            command, direction, self.shell)
        resource = ProcessSubstitutionResource(path, fd, pid, cleanup_path)
        if resource.parent_fd is not None:
            self.active_fds.append(resource.parent_fd)
        resource.register_with(self)
        return path

    def resolve_procsub_resource(
            self, target: Optional[str]
            ) -> Tuple[Optional[str], Optional[ProcessSubstitutionResource]]:
        """Resolve a redirect-target process substitution to a resource."""
        if not (target and target.startswith(('<(', '>('))
                and target.endswith(')')):
            return target, None
        direction = 'in' if target.startswith('<(') else 'out'
        parent_fd, fd_path, pid, cleanup_path = create_process_substitution(
            target[2:-1], direction, self.shell)
        resource = ProcessSubstitutionResource(
            fd_path, parent_fd, pid, cleanup_path)
        resource.register_with(self)
        return fd_path, resource

    @contextmanager
    def scope(self):
        """Own the substitutions created while the scope is active.

        On exit, the parent-side fds registered inside the scope are
        closed and their children reaped non-blockingly; children that
        are still running are parked in pending_pids for later polling.
        Scopes nest (a command inside a redirected loop body only cleans
        up its own substitutions, not the loop's `< <(cmd)`).
        """
        fd_mark = len(self.active_fds)
        pid_mark = len(self.active_pids)
        path_mark = len(self.active_paths)
        try:
            yield
        finally:
            self._cleanup_from(fd_mark, pid_mark, path_mark)

    def _cleanup_from(self, fd_mark: int, pid_mark: int, path_mark: int):
        """Release substitutions registered at or after the given marks."""
        # Close the parent-side fds. Consumers hold their own references
        # (a forked child inherited the fd; a redirect dup2'd it), so this
        # only releases the shell's copy.
        for fd in self.active_fds[fd_mark:]:
            try:
                os.close(fd)
            except OSError:
                pass
        del self.active_fds[fd_mark:]

        for path in self.active_paths[path_mark:]:
            try:
                os.unlink(path)
            except OSError:
                pass
            try:
                os.rmdir(os.path.dirname(path))
            except OSError:
                pass
        del self.active_paths[path_mark:]

        # Never block on substitution children: a >(cmd) child may outlive
        # the command that spawned it (bash returns immediately too).
        self.pending_pids.extend(self.active_pids[pid_mark:])
        del self.active_pids[pid_mark:]
        self.reap_pending()

    def reap_pending(self):
        """Reap any finished substitution children without blocking.

        Only the recorded substitution pids are waited on (never -1), so
        this can never steal an exit status from the job manager.
        """
        still_running = []
        for pid in self.pending_pids:
            try:
                wpid, _status = os.waitpid(pid, os.WNOHANG)
            except OSError:
                # Already reaped (e.g. by a waitpid(-1) elsewhere) — drop it.
                continue
            if wpid == 0:
                still_running.append(pid)
        self.pending_pids[:] = still_running
