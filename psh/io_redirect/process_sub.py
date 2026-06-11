"""Process substitution implementation."""
import fcntl
import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, List, Tuple

from ..ast_nodes import Command

if TYPE_CHECKING:
    from ..shell import Shell


def create_process_substitution(cmd_str: str, direction: str, shell: 'Shell') -> Tuple[int, str, int]:
    """Create a process substitution, returning (parent_fd, fd_path, child_pid).

    Args:
        cmd_str: The command string to execute (without the <()/>()} wrapper).
        direction: 'in' for <(cmd) (parent reads), 'out' for >(cmd) (parent writes).
        shell: The parent shell instance.

    Returns:
        Tuple of (parent_fd, fd_path, child_pid).
    """
    # Create pipe
    if direction == 'in':
        # For <(cmd), parent reads from pipe, child writes to it
        read_fd, write_fd = os.pipe()
        parent_fd = read_fd
        child_fd = write_fd
        child_stdout = child_fd
        child_stdin = 0
    else:
        # For >(cmd), parent writes to pipe, child reads from it
        read_fd, write_fd = os.pipe()
        parent_fd = write_fd
        child_fd = read_fd
        child_stdout = 1
        child_stdin = child_fd

    # Clear close-on-exec flag for parent_fd so it survives exec
    flags = fcntl.fcntl(parent_fd, fcntl.F_GETFD)
    fcntl.fcntl(parent_fd, fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)

    # Fork child for process substitution
    pid = os.fork()
    if pid == 0:  # Child
        from psh.executor import apply_child_signal_policy
        apply_child_signal_policy(
            shell.interactive_manager.signal_manager,
            shell.state,
            is_shell_process=True,
        )

        # Close parent's end of pipe
        os.close(parent_fd)

        # Set up child's stdio
        if direction == 'in':
            os.dup2(child_stdout, 1)
        else:
            os.dup2(child_stdin, 0)

        # Close the pipe fd we duplicated
        os.close(child_fd)

        # Execute the substitution command
        try:
            from ..lexer import tokenize
            from ..parser import parse
            from ..shell import Shell as ShellClass

            tokens = tokenize(cmd_str)
            ast = parse(tokens)
            temp_shell = ShellClass(parent_shell=shell)
            exit_code = temp_shell.execute_command_list(ast)
            os._exit(exit_code)
        except Exception as e:
            print(f"psh: process substitution error: {e}", file=sys.stderr)
            os._exit(1)

    else:  # Parent
        # Close child's end of pipe
        os.close(child_fd)

        # Create path for this fd
        fd_path = f"/dev/fd/{parent_fd}"

        return parent_fd, fd_path, pid


class ProcessSubstitutionHandler:
    """Handles process substitution <(...) and >(...)."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Track process substitution resources for the scope currently
        # being executed (see scope()).
        self.active_fds: List[int] = []
        self.active_pids: List[int] = []
        # Children whose consuming command has finished but which had not
        # exited yet (e.g. `echo >(sleep 3)`). They are re-polled
        # non-blockingly at every scope exit so they are reaped soon after
        # they exit, without ever making the shell wait for them (bash
        # behaves the same: the substitution may outlive its command).
        self.pending_pids: List[int] = []

    def setup_process_substitutions(self, command: Command) -> Tuple[List[int], List[str], List[int]]:
        """
        Set up process substitutions for a command.

        Returns:
            Tuple of (file_descriptors, substituted_paths, child_pids)
        """
        fds_to_keep = []
        substituted_args = []
        child_pids = []

        from ..ast_nodes import LiteralPart
        for i, arg in enumerate(command.args):
            # Detect process substitution via Word AST when available
            is_proc_sub = False
            if command.words and i < len(command.words):
                word = command.words[i]
                if (len(word.parts) == 1 and
                        isinstance(word.parts[0], LiteralPart) and
                        not word.parts[0].quoted):
                    text = word.parts[0].text
                    if text.startswith('<('):
                        is_proc_sub = True
                        arg_type = 'PROCESS_SUB_IN'
                    elif text.startswith('>('):
                        is_proc_sub = True
                        arg_type = 'PROCESS_SUB_OUT'

            if is_proc_sub:
                fd, path, pid = self._create_process_substitution(arg, arg_type)
                fds_to_keep.append(fd)
                substituted_args.append(path)
                child_pids.append(pid)
            else:
                # Not a process substitution, keep as-is
                substituted_args.append(arg)

        # Track for cleanup
        self.active_fds.extend(fds_to_keep)
        self.active_pids.extend(child_pids)

        return fds_to_keep, substituted_args, child_pids

    def _create_process_substitution(self, arg: str, arg_type: str) -> Tuple[int, str, int]:
        """
        Create a single process substitution.

        Returns:
            Tuple of (file_descriptor, fd_path, child_pid)
        """
        # Extract command from <(cmd) or >(cmd)
        if arg.startswith('<('):
            direction = 'in'
            cmd_str = arg[2:-1]  # Remove <( and )
        elif arg.startswith('>('):
            direction = 'out'
            cmd_str = arg[2:-1]  # Remove >( and )
        else:
            raise ValueError(f"Invalid process substitution: {arg}")

        return create_process_substitution(cmd_str, direction, self.shell)

    def handle_redirect_process_sub(self, target: str) -> Tuple[str, int, int]:
        """
        Handle process substitution used as a redirect target.

        Args:
            target: The process substitution string (e.g., "<(cmd)" or ">(cmd)")

        Returns:
            Tuple of (fd_path, fd_to_close, child_pid). The CALLER owns
            fd_to_close (setup_child_redirections closes it after dup2).
        """
        if target.startswith('<('):
            arg_type = 'PROCESS_SUB_IN'
        elif target.startswith('>('):
            arg_type = 'PROCESS_SUB_OUT'
        else:
            raise ValueError(f"Invalid process substitution redirect: {target}")

        fd, path, pid = self._create_process_substitution(target, arg_type)
        self.active_pids.append(pid)
        return path, fd, pid

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
        try:
            yield
        finally:
            self._cleanup_from(fd_mark, pid_mark)

    def _cleanup_from(self, fd_mark: int, pid_mark: int):
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
