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

    def execute(self, cmd_sub: str) -> str:
        """Execute command substitution and return output"""
        # Remove $(...) or `...`
        if cmd_sub.startswith('$(') and cmd_sub.endswith(')'):
            command = cmd_sub[2:-1]
        elif cmd_sub.startswith('`') and cmd_sub.endswith('`'):
            command = cmd_sub[1:-1]
        else:
            return ''

        # Import Shell here to avoid circular import
        from ..shell import Shell

        # Create a pipe for capturing output
        read_fd, write_fd = os.pipe()

        # Reset SIGCHLD to default to prevent job control interference
        import signal
        old_handler = signal.signal(signal.SIGCHLD, signal.SIG_DFL)

        pid = os.fork()
        if pid == 0:
            # Child process
            try:
                from psh.executor import apply_child_signal_policy
                apply_child_signal_policy(
                    self.shell.interactive_manager.signal_manager,
                    self.state,
                    is_shell_process=True,
                )

                # Close read end
                os.close(read_fd)

                # Redirect stdout to write end of pipe
                os.dup2(write_fd, 1)
                os.close(write_fd)

                # Protect stdin in interactive sessions to prevent terminal corruption
                # But preserve stdin for pipelines and scripts where it's needed
                # Use same interactive detection logic as shell initialization
                is_interactive = getattr(self.shell, '_force_interactive', sys.stdin.isatty())
                should_protect_stdin = (
                    not self.state.is_script_mode and
                    is_interactive and
                    not os.environ.get('PYTEST_CURRENT_TEST')  # Don't interfere with tests
                )
                if should_protect_stdin:
                    # Interactive mode: redirect from /dev/null to prevent terminal input consumption
                    null_fd = os.open('/dev/null', os.O_RDONLY)
                    os.dup2(null_fd, 0)
                    os.close(null_fd)

                # Create a temporary shell to execute the command
                temp_shell = Shell(
                    debug_ast=self.state.debug_ast,
                    debug_tokens=self.state.debug_tokens,
                    parent_shell=self.shell,
                    norc=True
                )
                temp_shell.state.in_forked_child = True

                # Execute the command
                try:
                    exit_code = temp_shell.run_command(command, add_to_history=False)
                except SystemExit as e:
                    # Command substitution runs in a subshell, so exit should not affect parent
                    exit_code = e.code if e.code is not None else 0

                # os._exit() does NOT flush Python-level buffers, so output a
                # builtin wrote to the stream (rather than via os.write) would be
                # lost. Flush before exiting so the pipe sees it. Mirrors
                # ProcessLauncher's child-exit flush.
                for stream in (temp_shell.stdout, temp_shell.stderr,
                               sys.stdout, sys.stderr):
                    try:
                        stream.flush()
                    except (OSError, ValueError, AttributeError):
                        pass

                os._exit(exit_code)
            except Exception:
                # Exit with error
                os._exit(1)
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
