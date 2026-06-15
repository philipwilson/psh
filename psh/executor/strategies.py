"""
Execution strategies for different command types.

This module implements the Strategy pattern for command execution,
providing different strategies for builtins, functions, and external commands.
"""

import errno
import os
import shlex
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

from .process_launcher import ProcessConfig, ProcessRole

if TYPE_CHECKING:
    from ..ast_nodes import Redirect
    from ..shell import Shell
    from .context import ExecutionContext


def exec_external(full_args: List[str], env: dict,
                  resolved_path: Optional[str] = None) -> None:
    """exec with the POSIX ENOEXEC fallback.

    With *resolved_path* (a hash-table/parent-side resolution) the file
    is exec'd directly; otherwise execvpe walks PATH. An executable text
    file without a shebang fails execve with "Exec format error"; POSIX
    requires the shell to run it as a shell script instead (bash
    re-executes it with itself). We re-exec the file through psh. Only
    returns by raising OSError.
    """
    try:
        if resolved_path is not None:
            os.execve(resolved_path, full_args, env)
        else:
            os.execvpe(full_args[0], full_args, env)
    except OSError as e:
        if e.errno != errno.ENOEXEC:
            raise
        # Resolve through PATH the way execvpe did, so a script found
        # on PATH is opened from the right location.
        if resolved_path is None:
            import shutil
            resolved_path = shutil.which(
                full_args[0], path=env.get('PATH', os.defpath)) or full_args[0]
        os.execve(sys.executable,
                  [sys.executable, '-m', 'psh', resolved_path] + list(full_args[1:]),
                  env)


def report_exec_failure(cmd_name: str, exc: OSError,
                        resolved_path: Optional[str] = None) -> int:
    """Report a failed exec on fd 2 and return the exit status.

    Shared by the in-pipeline (inline exec) and fork execution paths so
    both produce the same bash-style diagnostics: "command not found"
    with status 127 for a missing command, the OS error with status 126
    otherwise (e.g. permission denied). Writes at the fd level — both
    callers run in a forked child.

    When the exec used a pre-resolved path (hash table) and the file is
    gone, bash names the stale PATH: "bash: /path/cmd: No such file or
    directory", still 127 (probe-verified: bash 5.2 does NOT re-search
    PATH unless `shopt -s checkhash` — the re-verify happens parent-side
    in ExternalExecutionStrategy, before the fork).
    """
    if isinstance(exc, FileNotFoundError):
        if resolved_path is not None:
            os.write(2, f"psh: {resolved_path}: No such file or directory\n"
                     .encode('utf-8'))
        else:
            os.write(2, f"psh: {cmd_name}: command not found\n".encode('utf-8'))
        return 127
    os.write(2, f"psh: {cmd_name}: {exc}\n".encode('utf-8'))
    return 126


def execute_builtin_guarded(builtin, cmd_name: str, args: List[str],
                            shell: 'Shell') -> int:
    """Run a builtin, converting unexpected exceptions to exit status 1.

    Shared by the special-builtin and regular-builtin strategies:

    - SystemExit (e.g. the ``exit`` builtin) propagates unchanged.
    - Control-flow exceptions (return / break / continue — e.g. raised
      inside ``eval``) and ``set -u`` violations propagate to their
      handlers rather than being converted to exit status 1.
    - Anything else is a builtin defect: print "psh: NAME: error" and
      return 1, surfacing the traceback under --debug-exec so the bug
      isn't hidden behind the generic message.
    """
    try:
        # Builtins expect the command name as the first argument
        return builtin.execute([cmd_name] + args, shell)
    except SystemExit:
        # Some builtins like 'exit' raise SystemExit
        raise
    except OSError as e:
        # The builtin's output fd was closed/broken (`pwd 1>&-`, a builtin
        # writing into a closed pipe), so its write through the Python stream
        # raised EBADF/EPIPE. bash reports `NAME: write error: <strerror>`
        # and returns 1 — emit that here so EVERY builtin behaves like bash
        # without each one needing its own try/except (echo/printf still
        # catch internally to also cover their own buffering paths). Any other
        # OSError is a genuine error and falls through to the defect handler.
        if e.errno in (errno.EBADF, errno.EPIPE):
            strerror = os.strerror(e.errno)
            try:
                print(f"{cmd_name}: write error: {strerror}",
                      file=shell.stderr)
            except OSError:
                # stderr itself was the closed fd (e.g. `cmd 2>&-`); nothing
                # more we can do — bash is silent here too.
                pass
            return 1
        raise
    except Exception as e:
        # Imports here to avoid circular imports
        from ..core import LoopBreak, LoopContinue, UnboundVariableError
        from ..core.exceptions import FunctionReturn
        if isinstance(e, (FunctionReturn, LoopBreak, LoopContinue,
                          UnboundVariableError)):
            raise
        from ..core import report_internal_defect
        return report_internal_defect(shell.state, e, prefix=f"{cmd_name}: ",
                                      stream=shell.stderr)


class ExecutionStrategy(ABC):
    """Abstract base class for command execution strategies."""

    @abstractmethod
    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if this strategy can execute the given command."""
        pass

    @abstractmethod
    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute the command and return exit status."""
        pass


# POSIX special builtins that take precedence over functions
POSIX_SPECIAL_BUILTINS = {
    ':', 'break', 'continue', 'eval', 'exec', 'exit', 'export',
    'readonly', 'return', 'set', 'shift', 'trap', 'unset'
}


class SpecialBuiltinExecutionStrategy(ExecutionStrategy):
    """Strategy for executing POSIX special builtin commands that take precedence over functions."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if command is a POSIX special builtin."""
        return (cmd_name in POSIX_SPECIAL_BUILTINS and
                shell.builtin_registry.has(cmd_name))

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute a special builtin command."""
        if background:
            # Special builtins can run in background with subshell
            return self._execute_in_background(cmd_name, args, shell, context, redirects)

        builtin = shell.builtin_registry.get(cmd_name)
        if not builtin:
            return 127  # Command not found

        return execute_builtin_guarded(builtin, cmd_name, args, shell)

    def _execute_in_background(self, cmd_name: str, args: List[str],
                              shell: 'Shell', context: 'ExecutionContext',
                              redirects: Optional[List['Redirect']]) -> int:
        """Execute special builtin in background (subshell)."""
        # Use same background execution logic as regular builtins
        return BuiltinExecutionStrategy()._execute_builtin_in_background(
            cmd_name, args, shell, context, redirects
        )


class BuiltinExecutionStrategy(ExecutionStrategy):
    """Strategy for executing regular builtin commands."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if command is a regular builtin (not a special builtin)."""
        return (shell.builtin_registry.has(cmd_name) and
                cmd_name not in POSIX_SPECIAL_BUILTINS)

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute a builtin command."""
        if background:
            # Run builtin in background by forking a subshell (bash compatibility)
            return self._execute_builtin_in_background(cmd_name, args, shell, context, redirects)

        builtin = shell.builtin_registry.get(cmd_name)
        if not builtin:
            return 127  # Command not found

        # DEBUG: Log builtin execution
        if shell.state.options.get('debug-exec'):
            print(f"DEBUG BuiltinStrategy: executing builtin '{cmd_name}' with args {args}",
                  file=sys.stderr)
            print(f"DEBUG BuiltinStrategy: in_pipeline={context.in_pipeline}, "
                  f"in_forked_child={shell.state.in_forked_child}", file=sys.stderr)

        # The builtin will check shell.state.in_forked_child to determine its
        # output method.
        return execute_builtin_guarded(builtin, cmd_name, args, shell)

    def _execute_builtin_in_background(self, cmd_name: str, args: List[str],
                                     shell: 'Shell', context: 'ExecutionContext',
                                     redirects: Optional[List['Redirect']] = None) -> int:
        """Execute a builtin command in background by forking a subshell."""
        # The launcher applies the unified child signal policy on fork
        launcher = shell.process_launcher

        # Create execution function
        def execute_fn():
            # Apply redirections if any
            if redirects:
                from ..ast_nodes import SimpleCommand
                temp_command = SimpleCommand(redirects=redirects)
                shell.io_manager.setup_child_redirections(temp_command)

            # Execute the builtin
            builtin = shell.builtin_registry.get(cmd_name)
            if builtin:
                return builtin.execute([cmd_name] + args, shell)
            else:
                return 127

        # Configure as background job
        config = ProcessConfig(
            role=ProcessRole.SINGLE,
            foreground=False
        )

        pid, pgid = launcher.launch(execute_fn, config)

        # Register the job and print the interactive "[N] PID" notice
        shell.job_manager.launch_background(
            pgid, f"{cmd_name} {' '.join(args)}", [(pid, cmd_name)])

        return 0


class FunctionExecutionStrategy(ExecutionStrategy):
    """Strategy for executing shell functions."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if command is a defined function."""
        return shell.function_manager.get_function(cmd_name) is not None

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute a shell function."""
        if background:
            # bash runs `f &` in a forked subshell
            return self._execute_function_in_background(
                cmd_name, args, shell, context, redirects, visitor)

        # Import here to avoid circular imports
        from .function import FunctionOperationExecutor

        # Create a function executor to handle the call
        function_executor = FunctionOperationExecutor(shell)

        # Reuse the caller's visitor to preserve accumulated state;
        # fall back to creating a new one if not provided.
        if visitor is None:
            from .core import ExecutorVisitor
            visitor = ExecutorVisitor(shell)
            visitor.context = context

        return function_executor.execute_function_call(
            cmd_name, args, context, visitor, redirects
        )

    def _execute_function_in_background(self, cmd_name: str, args: List[str],
                                        shell: 'Shell', context: 'ExecutionContext',
                                        redirects: Optional[List['Redirect']] = None,
                                        visitor=None) -> int:
        """Execute a shell function in the background (forked subshell, bash)."""
        launcher = shell.process_launcher

        def execute_fn():
            if redirects:
                from ..ast_nodes import SimpleCommand
                temp_command = SimpleCommand(redirects=redirects)
                shell.io_manager.setup_child_redirections(temp_command)

            from .function import FunctionOperationExecutor
            function_executor = FunctionOperationExecutor(shell)
            v = visitor
            if v is None:
                from .core import ExecutorVisitor
                v = ExecutorVisitor(shell)
                v.context = context
            return function_executor.execute_function_call(
                cmd_name, args, context, v, None)

        # The child keeps running shell code (the function body may start
        # pipelines or manage terminal control), so mark it a shell process.
        config = ProcessConfig(
            role=ProcessRole.SINGLE,
            foreground=False,
            is_shell_process=True
        )

        pid, pgid = launcher.launch(execute_fn, config)

        # Register the job and print the interactive "[N] PID" notice
        shell.job_manager.launch_background(
            pgid, f"{cmd_name} {' '.join(args)}", [(pid, cmd_name)])

        return 0


class AliasExecutionStrategy(ExecutionStrategy):
    """Strategy for executing shell aliases."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if command is an alias."""
        # Check for bypass mechanisms first
        if cmd_name.startswith('\\'):
            return False  # Backslash escapes bypass aliases
        result = shell.alias_manager.has_alias(cmd_name)
        return result

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute an alias by expanding and re-executing."""
        alias_definition = shell.alias_manager.get_alias(cmd_name)
        if not alias_definition:
            return 127  # Should not happen if can_execute returned True

        # Prevent infinite recursion
        if cmd_name in shell.alias_manager.expanding:
            # Already expanding this alias, treat as external command
            return self._execute_as_external(cmd_name, args, shell, context, redirects, background)

        # Mark this alias as being expanded
        shell.alias_manager.expanding.add(cmd_name)

        try:
            # Create new command string by expanding the alias.
            #
            # The alias VALUE (`alias_definition`) is kept RAW: an alias is
            # meant to be parsed as shell source (`alias ll='ls -l'` must
            # parse `ls -l` as two words, `alias x='a; b'` as two commands).
            #
            # The appended `args`, however, are already-expanded DATA — they
            # have already gone through variable/command/glob expansion and
            # quote removal. Re-joining them raw and re-lexing would
            # reinterpret any metacharacters they contain as SYNTAX (a
            # command-injection-class bug: `e 'a; echo PWNED'` would run a
            # second command). Shell-quote each arg with shlex.quote so the
            # re-lexer treats it as a single literal word. (shlex.quote
            # returns simple/safe words like `x` unquoted, so correct cases
            # are unchanged.)
            quoted_args = ' '.join(shlex.quote(a) for a in args)
            # If alias has trailing space, next word can also be expanded
            if alias_definition.endswith(' '):
                # Handle trailing space for chained alias expansion
                expanded_command = alias_definition + quoted_args
            else:
                expanded_command = alias_definition + ((' ' + quoted_args) if args else '')

            # Re-tokenize and parse the expanded command
            from ..lexer import tokenize
            from ..parser import Parser

            tokens = tokenize(expanded_command)
            parser = Parser(tokens, source_text=expanded_command)
            ast = parser.parse()

            # Reuse the caller's visitor to preserve accumulated state;
            # fall back to creating a new one if not provided.
            if visitor is None:
                from .core import ExecutorVisitor
                visitor = ExecutorVisitor(shell)
                visitor.context = context

            return visitor.visit(ast)

        finally:
            # Remove from expanding set
            shell.alias_manager.expanding.discard(cmd_name)

    def _execute_as_external(self, cmd_name: str, args: List[str],
                            shell: 'Shell', context: 'ExecutionContext',
                            redirects: Optional[List['Redirect']] = None,
                            background: bool = False) -> int:
        """Execute as external command when alias recursion is detected."""
        external_strategy = ExternalExecutionStrategy()
        return external_strategy.execute(cmd_name, args, shell, context, redirects, background)


class ExternalExecutionStrategy(ExecutionStrategy):
    """Strategy for executing external commands."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """External commands are the fallback - always return True."""
        return True

    @staticmethod
    def resolve_via_hash_table(cmd_name: str, shell: 'Shell') -> Optional[str]:
        """Consult and populate the command hash table (bash hashing).

        Runs parent-side, before the fork, so the table on shell.state
        records both new resolutions and hit counts (bash: running an
        external command remembers its path with 1 hit; each later run
        increments). Returns the path to exec directly, or None to fall
        back to execvpe's own PATH walk (slash names, hashing disabled
        via ``set +h``, or a PATH miss — the forked child then produces
        the usual "command not found").

        Re-verify semantics are bash 5.2's, probe-verified: by default a
        remembered path is exec'd blindly even if the file is gone (the
        exec fails with "No such file or directory", 127, and the hit
        still counts); under ``shopt -s checkhash`` the stale entry is
        dropped here and PATH is searched afresh.
        """
        if '/' in cmd_name or not shell.state.options.get('hashcmds', True):
            return None
        table = shell.state.command_hash
        cached = table.lookup(cmd_name)  # counts the hit (bash)
        if cached is not None:
            if shell.state.options.get('checkhash') and not (
                    os.path.isfile(cached) and os.access(cached, os.X_OK)):
                table.remove(cmd_name)  # stale: fall through to re-search
            else:
                return cached
        from ..builtins.type_builtin import TypeBuiltin
        paths = TypeBuiltin._find_in_path(cmd_name, shell.env.get('PATH', ''))
        if paths:
            table.insert(cmd_name, paths[0], hits=1)
            return paths[0]
        return None

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None) -> int:
        """Execute an external command."""
        full_args = [cmd_name] + args
        # Resolve through the command hash table BEFORE forking, so the
        # remembered location and hit count land on the parent's state.
        # (Pipeline members run this in the forked child — their table is
        # a fork-copy, matching bash, where `ls | cat` leaves the parent
        # table untouched.)
        resolved_path = self.resolve_via_hash_table(cmd_name, shell)

        if context.in_pipeline:
            # In pipeline, use exec to replace current process
            try:
                # Set up redirections if any
                if redirects:
                    # Create a dummy command object for the io_manager
                    from ..ast_nodes import SimpleCommand
                    temp_command = SimpleCommand(redirects=redirects)
                    shell.io_manager.setup_child_redirections(temp_command)

                # Ensure we're in the correct process group before exec
                # This is important for commands that might fork after exec
                current_pgid = os.getpgrp()
                current_pid = os.getpid()

                if shell.state.options.get('debug-exec'):
                    print(f"DEBUG ExternalStrategy: Before exec - PID={current_pid}, PGID={current_pgid}",
                          file=sys.stderr)

                # Always explicitly set the process group to ensure it's inherited
                # This helps when execvpe creates a new process
                os.setpgid(0, current_pgid)

                exec_external(full_args, shell.env, resolved_path)
            except OSError as e:
                os._exit(report_exec_failure(full_args[0], e, resolved_path))

        # Set terminal title to show running command
        if not background and not context.in_pipeline and shell.state.options.get('interactive'):
            from ..interactive.title import command_title, set_terminal_title
            set_terminal_title(command_title(cmd_name, shell))

        # Manage terminal control only for foreground commands when this
        # shell actually owns the terminal (real capability check — no
        # test-runner sniffing).
        original_pgid = None
        if not background:
            original_pgid = shell.job_manager.terminal_pgid_if_owned()

        # The launcher applies the unified child signal policy on fork
        launcher = shell.process_launcher

        # Create execution function
        def execute_fn():
            # Set up redirections if any
            if redirects:
                # Create a dummy command object for the io_manager
                from ..ast_nodes import SimpleCommand
                temp_command = SimpleCommand(redirects=redirects)
                shell.io_manager.setup_child_redirections(temp_command)

            # Execute the command with proper environment
            if shell.state.options.get('debug-exec'):
                print(f"DEBUG ExternalStrategy: execvpe {full_args[0]} with "
                      f"PATH={shell.env.get('PATH', 'NOT_SET')[:50]}...",
                      file=sys.stderr)

            try:
                exec_external(full_args, shell.env, resolved_path)
            except OSError as e:
                return report_exec_failure(full_args[0], e, resolved_path)

            # Not reached if exec succeeds
            return 127

        # Configure launch
        config = ProcessConfig(
            role=ProcessRole.SINGLE,
            foreground=not background
        )

        pid, pgid = launcher.launch(execute_fn, config)

        command_string = " ".join(str(arg) for arg in full_args)

        if background:
            # Register the job (sets current_job and $!) and print the
            # interactive "[N] PID" notice
            shell.job_manager.launch_background(
                pgid, command_string, [(pid, str(full_args[0]))])
            return 0
        else:
            # Foreground job - create it for tracking and give it terminal control
            job = shell.job_manager.create_job(pgid, command_string)
            job.add_process(pid, str(full_args[0]))
            job.foreground = True
            shell.job_manager.set_foreground_job(job)

            # Hand the terminal to the new foreground process group
            if original_pgid is not None:
                if shell.job_manager.transfer_terminal_control(pgid, "ExternalStrategy"):
                    shell.state.foreground_pgid = pgid

            # Use job manager to wait (it handles SIGCHLD)
            exit_status = shell.job_manager.wait_for_job(job)

            # Reclaim the terminal (if we handed it over) and clear
            # foreground-job bookkeeping
            shell.job_manager.finish_foreground_job(original_pgid is not None)

            # Clean up
            from .job_control import JobState
            if job.state == JobState.DONE:
                shell.job_manager.remove_job(job.job_id)

            return exit_status
