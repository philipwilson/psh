"""Command substitution implementation."""
import errno
import os
import sys
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..shell import Shell


def _close_quiet(fd: int) -> None:
    """Close ``fd``, ignoring an already-closed / invalid descriptor."""
    try:
        os.close(fd)
    except OSError:
        pass


class CommandSubstitution:
    """Handles command substitution $(...) and `...`."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

    def _reap(self, pid: int) -> int:
        """Wait for the substitution child and map its wait status to a code.

        Normal exit -> its status; killed by a signal -> ``128 + signal``
        (bash); already reaped elsewhere (``ECHILD`` — e.g. a stray
        ``waitpid(-1)`` in a job-control signal handler) -> 1.
        """
        try:
            _, status = os.waitpid(pid, 0)
        except OSError as e:
            if e.errno == errno.ECHILD:
                return 1
            raise
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        if os.WIFSIGNALED(status):
            return 128 + os.WTERMSIG(status)
        return 1

    def _child_io_setup(self, read_fd: int, write_fd: int) -> None:
        """Wire the substitution child's stdio (runs in the child).

        Stdout goes to the capture pipe's write end. In interactive
        sessions stdin is additionally protected with /dev/null to
        prevent the substitution consuming terminal input.
        """
        # Point stdout at the capture pipe's write end collision-safely. When
        # fd 1 began closed (`exec 1>&-`), os.pipe() can return the write end
        # AS fd 1; the naive close(read_fd);dup2(write,1);close(write) would
        # then destroy the very descriptor it just installed. remap_fds
        # promotes and closes the endpoints correctly (D3 in the fd-remap
        # campaign): write end -> fd 1, read end closed, write end kept iff it
        # already is fd 1.
        from ..io_redirect import remap_fds
        remap_fds({write_fd: 1}, owned=[read_fd, write_fd])

        # Protect stdin in interactive sessions to prevent terminal corruption
        # But preserve stdin for pipelines and scripts where it's needed.
        # Capability check, not environment sniffing: only redirect when
        # fd 0 actually IS the terminal — if stdin was redirected to a
        # pipe or file (scripts, tests, `cmd | psh`), the substitution
        # may legitimately need to read it.
        # getattr evaluates its default eagerly, so guard sys.stdin before
        # .isatty(): psh may run with fd 0 closed (`exec 0<&-; psh -c '…$(…)…'`),
        # where CPython sets sys.stdin to None. A closed/absent stdin is not a
        # tty. Matches the guard idiom in shell.py / __main__.py.
        is_interactive = getattr(
            self.shell, '_force_interactive',
            bool(sys.stdin is not None and not sys.stdin.closed
                 and sys.stdin.isatty()))
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

        # Sentinels let the finally tell the failure paths (fork raised, or the
        # read/decode raised) apart from the success path, which has already
        # closed both pipe ends and reaped the child. On any failure the
        # finally still closes the pipe ends, reaps a forked-but-unreaped child
        # (no zombie on a read error), and always restores SIGCHLD — none of
        # which the old code did when fork() or the read loop raised.
        child_pid: Optional[int] = None
        try:
            # Fork with termination signals blocked across the fork window
            # (the v0.300 lost-signal race fix; the child unblocks them in
            # apply_child_signal_policy after resetting handlers to SIG_DFL).
            from psh.executor import fork_with_signal_window, run_child_shell
            pid = fork_with_signal_window()
            if pid == 0:
                # Child: run_child_shell owns the generic child-process work
                # (signal policy, child Shell, exception -> exit-code mapping,
                # stream flush, os._exit). We supply the fd plumbing and body.
                # bash clears set -e in command-substitution children (unlike
                # ( ) subshells and process substitutions, which inherit it)
                # unless POSIX mode or `shopt -s inherit_errexit` asks
                # otherwise: `set -e; x=$(false; echo hi)` sets x=hi.
                opts = self.state.options
                run_child_shell(
                    self.shell,
                    lambda child: child.run_command(command, add_to_history=False),
                    io_setup=lambda: self._child_io_setup(read_fd, write_fd),
                    reset_errexit=not (opts.get('inherit_errexit')
                                       or opts.get('posix')),
                    error_label='command substitution',
                )
            child_pid = pid

            # Parent: consume all of the child's output, then reap it.
            os.close(write_fd)
            write_fd = -1

            chunks = []
            try:
                while True:
                    chunk = os.read(read_fd, 4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
            finally:
                os.close(read_fd)
                read_fd = -1
            output_bytes = b''.join(chunks)

            # Reap on the success path; the finally reaps only if we bail out
            # before reaching here.
            exit_code = self._reap(child_pid)
            child_pid = None

            # Update parent shell's last exit code for command substitution.
            # last_cmdsub_status lets a pure assignment (v=$(cmd)) report
            # the substitution's status as its own (bash: a pure
            # assignment's status is 0 unless a command substitution ran).
            self.shell.state.last_exit_code = exit_code
            self.shell.state.last_cmdsub_status = exit_code
            if self.shell.state.options.get('debug-expansion-detail'):
                print(f"[EXPANSION] Command substitution '{cmd_sub}' exit code: {exit_code}", file=self.shell.state.stderr)

            # Decode under psh's shell byte policy. Bash strips NUL
            # bytes from a substitution — they cannot survive in a C
            # string / argv / environment — and warns once regardless of
            # how many were dropped. Arbitrary non-UTF-8 bytes round-trip
            # via surrogateescape (not the U+FFFD replacement that
            # errors='replace' produced), so `x=$(printf '\xff')`
            # preserves the byte on the way back out through builtin
            # output and external exec, both of which re-encode surrogate
            # escapes to their original bytes. This matches the
            # surrogateescape decode already used for script input
            # (__main__.py, scripting/input_sources.py).
            if b'\x00' in output_bytes:
                output_bytes = output_bytes.replace(b'\x00', b'')
                print("psh: warning: command substitution: "
                      "ignored null byte in input",
                      file=self.shell.state.stderr)
            output = output_bytes.decode('utf-8', errors='surrogateescape')

            # Strip all trailing newlines (POSIX requirement)
            return output.rstrip('\n')
        finally:
            # Failure cleanup (success cleared the sentinels): close any pipe
            # end still open, reap a not-yet-reaped child so a read error or a
            # fork failure cannot leak a zombie, and always restore SIGCHLD.
            if read_fd != -1:
                _close_quiet(read_fd)
            if write_fd != -1:
                _close_quiet(write_fd)
            if child_pid is not None:
                try:
                    os.waitpid(child_pid, 0)
                except OSError:
                    pass
            signal.signal(signal.SIGCHLD, old_handler)
