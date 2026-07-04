"""Core shell builtins (exit, :, true, false, exec)."""

import sys
from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class ExitBuiltin(Builtin):
    """Exit the shell."""

    @property
    def name(self) -> str:
        return "exit"

    @property
    def synopsis(self) -> str:
        return "exit [n]"

    @property
    def description(self) -> str:
        return "Exit the shell"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Exit the shell with optional exit code (bash semantics)."""
        if len(args) > 2:
            # bash: "too many arguments" is an error that does NOT exit the
            # shell — it reports and returns 1, the shell keeps running.
            self.error("too many arguments", shell)
            return 1

        # Bare `exit` uses the status of the last command ($?), not 0.
        exit_code = shell.state.last_exit_code
        if len(args) == 2:
            try:
                # bash wraps the code modulo 256 (so `exit 257` -> 1,
                # `exit -1` -> 255); & 0xFF matches for negatives too.
                exit_code = int(args[1]) & 0xFF
            except ValueError:
                self.error(f"{args[1]}: numeric argument required", shell)
                exit_code = 2

        # bash: the FIRST interactive exit attempt with stopped jobs is
        # blocked with "There are stopped jobs."; a second consecutive
        # attempt proceeds. One chokepoint, shared with the REPL's
        # Ctrl-D path (JobManager owns the two-strikes state; the REPL
        # re-arms it when another command runs in between). A blocked
        # exit returns 1 (bash sets $? to EXECUTION_FAILURE).
        if not shell.job_manager.confirm_exit_with_stopped_jobs():
            return 1

        # Set the exit code in shell state for EXIT trap
        shell.state.last_exit_code = exit_code

        # Execute EXIT trap if set
        if hasattr(shell, 'trap_manager'):
            shell.trap_manager.execute_exit_trap()

        # Save history before exiting
        if hasattr(shell, 'interactive_manager'):
            shell.interactive_manager.history_manager.save_to_file()

        sys.exit(exit_code)

    @property
    def help(self) -> str:
        return """exit: exit [n]
    Exit the shell.

    Exits the shell with a status of N. If N is omitted, the exit status
    is that of the last command executed.

    Exit Status:
    Returns N, or failure if an invalid argument is given."""


@builtin
class ColonBuiltin(Builtin):
    """Null command - does nothing and returns success."""

    @property
    def name(self) -> str:
        return ":"

    @property
    def synopsis(self) -> str:
        return ": [arguments]"

    @property
    def description(self) -> str:
        return "Null command that returns success"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Do nothing and return success."""
        return 0

    @property
    def help(self) -> str:
        return """: : [arguments]
    Null command.

    This command does nothing and always returns success (0).
    Any arguments are ignored. Useful as a placeholder or for parameter expansion
    side effects.

    Exit Status:
    Always returns success."""


@builtin
class TrueBuiltin(Builtin):
    """Always return success."""

    @property
    def name(self) -> str:
        return "true"

    @property
    def synopsis(self) -> str:
        return "true"

    @property
    def description(self) -> str:
        return "Always return success"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Always return success (0)."""
        return 0

    @property
    def help(self) -> str:
        return """true: true
    Always return success.

    Always returns success (exit code 0). Useful in conditional expressions.

    Exit Status:
    Always returns success."""


@builtin
class FalseBuiltin(Builtin):
    """Always return failure."""

    @property
    def name(self) -> str:
        return "false"

    @property
    def synopsis(self) -> str:
        return "false"

    @property
    def description(self) -> str:
        return "Always return failure"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Always return failure (1)."""
        return 1

    @property
    def help(self) -> str:
        return """false: false
    Always return failure.

    Always returns failure (exit code 1). Useful in conditional expressions.

    Exit Status:
    Always returns failure."""


@builtin
class ExecBuiltin(Builtin):
    """Execute commands and manipulate file descriptors."""

    @property
    def name(self) -> str:
        return "exec"

    @property
    def synopsis(self) -> str:
        return "exec [-cl] [-a name] [command [argument ...]]"

    @property
    def description(self) -> str:
        return "Execute commands and manipulate file descriptors"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute command or apply redirections."""
        # -a NAME overrides argv[0]; -c runs with an empty environment;
        # -l prepends '-' to argv[0] (login-shell convention).
        opts, command = self.parse_flags(args, shell, flags='cl', value_flags='a')
        if opts is None:
            return 2

        if not command:
            # exec with no command (with or without flags) - just succeed.
            # Any redirections were already applied by the executor/io_manager.
            return 0

        import errno
        import os

        # bash locates the program with the shell's PATH, then hands the
        # child the requested environment — so `-c` (empty env) still finds
        # a command that lives on PATH.
        env = {} if opts['c'] else shell.env
        exec_file = command[0]
        if opts['c'] and '/' not in exec_file:
            from .type_builtin import TypeBuiltin
            found = TypeBuiltin._find_in_path(exec_file, shell.env.get('PATH', ''))
            if found:
                exec_file = found[0]

        argv0 = opts['a'] if opts['a'] is not None else command[0]
        if opts['l']:
            argv0 = '-' + argv0
        argv = [argv0] + command[1:]

        if not exec_file:
            # bash: `exec ""` → "exec: : not found", status 127 (os.execvpe
            # would raise a ValueError about argv instead).
            self.error(f"{command[0]}: not found", shell)
            return self._exec_failed(shell, 127)

        # Reconcile signal dispositions for the new process image: keep
        # SIG_IGN for `trap '' SIG` (POSIX: exec preserves ignored
        # signals — psh's managed traps are Python handlers the kernel
        # would reset to SIG_DFL), default everything else psh/CPython
        # holds a handler or ignore for (SIGTTOU in script mode, CPython's
        # SIGXFSZ). Same policy as forked children (reset_child_signals);
        # restore on the exec-failed path so a surviving shell keeps
        # working.
        restore_signals = (
            shell.interactive_manager.signal_manager.prepare_signals_for_exec())

        try:
            os.execvpe(exec_file, argv, env)
        except FileNotFoundError as e:
            restore_signals()
            from ..executor.strategies import format_exec_failure
            if '/' in exec_file:
                # A pathname (or a PATH-resolved file that vanished): bash
                # reports "No such file or directory", no "exec:" prefix —
                # so write_error_line (unprefixed), not error().
                resolved = exec_file if exec_file != command[0] else None
                message, status = format_exec_failure(command[0], e, resolved)
                self.write_error_line(message, shell)
            else:
                # A bare name PATH couldn't resolve: bash's exec builtin
                # says "not found" (unlike plain-command "command not
                # found").
                self.error(f"{command[0]}: not found", shell)
                status = 127
            return self._exec_failed(shell, status)
        except OSError as e:
            restore_signals()
            # bash prints TWO lines here: the shell-level execve failure
            # ("/etc: Is a directory", unprefixed) followed by the exec
            # builtin's own diagnostic ("exec: /etc: cannot execute: Is a
            # directory"). format_exec_failure owns the first line's
            # wording (shared with the forked exec paths).
            from ..executor.strategies import format_exec_failure
            resolved = exec_file if exec_file != command[0] else None
            message, status = format_exec_failure(command[0], e, resolved)
            self.write_error_line(message, shell)
            if os.path.isdir(exec_file):
                detail = os.strerror(errno.EISDIR)
            else:
                detail = e.strerror or str(e)
            self.error(f"{command[0]}: cannot execute: {detail}", shell)
            return self._exec_failed(shell, status)

    def _exec_failed(self, shell: 'Shell', code: int) -> int:
        """Handle a failed exec.

        POSIX: a non-interactive shell exits when `exec command` fails
        (127 not found, 126 not executable); an interactive shell survives
        and reports the status.
        """
        if shell.state.is_script_mode:
            sys.exit(code)
        return code

    @property
    def help(self) -> str:
        return """exec: exec [command [argument ...]]

    Execute commands and manipulate file descriptors.

    If command is specified, it replaces the shell without creating a new process.
    If no command is specified, any redirections take effect in the current shell.

    Examples:
        exec echo hello world    # Replace shell with echo command
        exec 3< file             # Open file descriptor 3 for reading
        exec 4> file             # Open file descriptor 4 for writing
        exec 5<&0                # Duplicate fd 0 to fd 5
        exec 3<&-                # Close file descriptor 3

    Exit Status:
        If command is specified: doesn't return (process replaced)
        Command not found: 127
        Command not executable: 126
        Redirection error: 1-125
        Success (no command): 0"""
