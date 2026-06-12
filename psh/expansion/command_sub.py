"""Command substitution implementation."""
import errno
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..shell import Shell


class CommandSubstitution:
    """Handles command substitution $(...) and `...`."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

    def _child_io_setup(self, read_fd: int, write_fd: int) -> None:
        """Wire the substitution child's stdio (runs in the child).

        Stdout goes to the capture pipe's write end. In interactive
        sessions stdin is additionally protected with /dev/null to
        prevent the substitution consuming terminal input.
        """
        # Close read end
        os.close(read_fd)

        # Redirect stdout to write end of pipe
        os.dup2(write_fd, 1)
        os.close(write_fd)

        # Protect stdin in interactive sessions to prevent terminal corruption
        # But preserve stdin for pipelines and scripts where it's needed.
        # Capability check, not environment sniffing: only redirect when
        # fd 0 actually IS the terminal — if stdin was redirected to a
        # pipe or file (scripts, tests, `cmd | psh`), the substitution
        # may legitimately need to read it.
        is_interactive = getattr(self.shell, '_force_interactive', sys.stdin.isatty())
        should_protect_stdin = (
            not self.state.is_script_mode and
            is_interactive and
            os.isatty(0)
        )
        if should_protect_stdin:
            # Interactive mode: redirect from /dev/null to prevent
            # terminal input consumption
            null_fd = os.open('/dev/null', os.O_RDONLY)
            os.dup2(null_fd, 0)
            os.close(null_fd)

    def execute(self, cmd_sub: str) -> str:
        """Execute command substitution and return output"""
        # Remove $(...) or `...`
        if cmd_sub.startswith('$(') and cmd_sub.endswith(')'):
            command = cmd_sub[2:-1]
        elif cmd_sub.startswith('`') and cmd_sub.endswith('`'):
            command = cmd_sub[1:-1]
        else:
            return ''

        # Create a pipe for capturing output
        read_fd, write_fd = os.pipe()

        # Reset SIGCHLD to default to prevent job control interference.
        # In interactive mode the shell installs a SIGCHLD handler that
        # notifies the REPL loop, whose processing reaps with
        # waitpid(-1, WNOHANG); a background job exiting while we sit in
        # the blocking waitpid(pid) below could let that path steal this
        # child's exit status (the ECHILD fallback would then report 1).
        # SIG_DFL for the duration makes the substitution's status
        # capture race-free; the handler is restored in the finally
        # below, and the job manager already tolerates reaped-elsewhere
        # children. (In script mode SIGCHLD is SIG_DFL already, so this
        # is a no-op there.)
        import signal
        old_handler = signal.signal(signal.SIGCHLD, signal.SIG_DFL)

        # Fork with termination signals blocked across the fork window
        # (the v0.300 lost-signal race fix; the child unblocks them in
        # apply_child_signal_policy after resetting handlers to SIG_DFL).
        from psh.executor import fork_with_signal_window, run_child_shell
        pid = fork_with_signal_window()
        if pid == 0:
            # Child: run_child_shell owns the generic child-process work
            # (signal policy, child Shell, exception -> exit-code mapping,
            # stream flush, os._exit). We supply the fd plumbing and body.
            run_child_shell(
                self.shell,
                lambda child: child.run_command(command, add_to_history=False),
                io_setup=lambda: self._child_io_setup(read_fd, write_fd),
                error_label='command substitution',
            )
        else:
            # Parent process
            try:
                # Close write end
                os.close(write_fd)

                # Read all output from child
                chunks = []
                while True:
                    chunk = os.read(read_fd, 4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                output_bytes = b''.join(chunks)

                os.close(read_fd)

                # Wait for child to finish
                try:
                    _, status = os.waitpid(pid, 0)
                    # Get exit code from status
                    if os.WIFEXITED(status):
                        exit_code = os.WEXITSTATUS(status)
                    else:
                        exit_code = 1
                except OSError as e:
                    # In some environments (like pytest), the child might have already been reaped
                    # by a signal handler. This happens particularly with the job control system
                    if e.errno == errno.ECHILD:
                        exit_code = 1
                    else:
                        raise

                # Update parent shell's last exit code for command substitution.
                # last_cmdsub_status lets a pure assignment (v=$(cmd)) report
                # the substitution's status as its own (bash: a pure
                # assignment's status is 0 unless a command substitution ran).
                self.shell.state.last_exit_code = exit_code
                self.shell.state.last_cmdsub_status = exit_code
                if self.shell.state.options.get('debug-expansion-detail'):
                    print(f"[EXPANSION] Command substitution '{cmd_sub}' exit code: {exit_code}", file=self.shell.state.stderr)

                # Decode output
                output = output_bytes.decode('utf-8', errors='replace')

                # Strip all trailing newlines (POSIX requirement)
                output = output.rstrip('\n')

                return output
            finally:
                # Restore SIGCHLD handler even if an exception occurred
                signal.signal(signal.SIGCHLD, old_handler)
