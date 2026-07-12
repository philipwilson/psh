"""
Execution strategies for different command types.

This module implements the Strategy pattern for command execution,
providing different strategies for builtins, functions, and external commands.
"""

import errno
import os
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..ast_nodes import SimpleCommand
from ..builtins.base import EMPTY_BUILTIN_CONTEXT
from ..core import (
    ExpansionError,
    FunctionReturn,
    LoopBreak,
    LoopContinue,
    NamerefCycleError,
    SpecialBuiltinUsageError,
    UnboundVariableError,
    arith_assignment_discard,
    fatal_expansion_status,
    report_internal_defect,
    special_builtin_usage_exit,
)
from ..core.job_state import JobState
from ..expansion.arithmetic import ShellArithmeticError
from .child_policy import run_background_shell_child
from .function import FunctionOperationExecutor
from .process_launcher import ProcessConfig, ProcessRole

if TYPE_CHECKING:
    from ..ast_nodes import Redirect
    from ..builtins.base import BuiltinContext
    from ..core.state import ShellState
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
    if not full_args or not full_args[0]:
        # A quoted empty command word (`''`, `"$empty"`) is an attempted
        # invocation of a command whose name is the empty string (F1).
        # Python's execve rejects an empty argv[0] with ValueError, but bash
        # reports it as an ordinary lookup failure ("command not found", 127).
        # Raise FileNotFoundError so the shared report path
        # (report_exec_failure -> format_exec_failure) produces that.
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                full_args[0] if full_args else '')
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


def format_exec_failure(cmd_name: str, exc: OSError,
                        resolved_path: Optional[str] = None
                        ) -> Tuple[str, int]:
    """Format a failed exec as bash's diagnostic; return ``(message, status)``.

    The single source of truth for exec-failure WORDING, shared by the
    forked execution paths (via :func:`report_exec_failure`) and the
    ``exec`` builtin, so every exec failure produces the same bash-style
    diagnostics: "command not found" with status 127 for a missing
    command, the OS error's strerror with status 126 otherwise (e.g.
    permission denied) — never the raw Python OSError repr. The returned
    message is BARE (no ``psh:``/location prefix): each caller prepends
    bash's ``<$0>: [line N: ]`` prefix via ``state.error_location_prefix()``
    (report_exec_failure does; the exec builtin uses ``report_error``).

    When the exec used a pre-resolved path (hash table) and the file is
    gone, bash names the stale PATH: "bash: /path/cmd: No such file or
    directory", still 127 (probe-verified: bash 5.2 does NOT re-search
    PATH unless `shopt -s checkhash` — the re-verify happens parent-side
    in ExternalExecutionStrategy, before the fork). A missing command
    given as a *pathname* (one containing a slash) is likewise reported
    as "No such file or directory", not "command not found" — bash reserves
    "command not found" for a bare name that PATH couldn't resolve.
    """
    if isinstance(exc, FileNotFoundError):
        if resolved_path is not None:
            return f"{resolved_path}: No such file or directory", 127
        if '/' in cmd_name:
            return f"{cmd_name}: No such file or directory", 127
        return f"{cmd_name}: command not found", 127
    # Report bash's strerror ("Permission denied", "Is a directory"), not
    # Python's OSError repr ("[Errno 13] Permission denied: './x'"). exec of a
    # directory returns EACCES on macOS, but bash reports "Is a directory" — so
    # special-case a directory target to match.
    target = resolved_path or cmd_name
    if os.path.isdir(target):
        detail = os.strerror(errno.EISDIR)
    else:
        detail = exc.strerror or str(exc)
    return f"{cmd_name}: {detail}", 126


def report_exec_failure(cmd_name: str, exc: OSError,
                        resolved_path: Optional[str] = None,
                        *, state: 'ShellState') -> int:
    """Report a failed exec on fd 2 and return the exit status.

    Shared by the in-pipeline (inline exec) and fork execution paths so
    both produce the same bash-style diagnostics (see
    :func:`format_exec_failure`, which owns the wording). Writes at the
    fd level — both callers run in a forked child. ``state`` supplies the
    ``<$0>: [line N: ]`` location prefix bash prepends (matching a builtin
    runtime error); the child inherits the parent's script_name/line/options
    at fork, so the prefix is correct.
    """
    message, status = format_exec_failure(cmd_name, exc, resolved_path)
    # surrogateescape on the diagnostics: a command name carrying non-UTF-8
    # bytes (from a non-UTF-8 script, read with surrogateescape) must not make
    # the error message itself raise UnicodeEncodeError — the byte round-trips
    # back out unchanged, and the command is still reported as not found.
    text = f"{state.error_location_prefix()}{message}\n"
    os.write(2, text.encode('utf-8', errors='surrogateescape'))
    return status


def report_unbound_variable(state: 'ShellState', exc: Exception) -> int:
    """Report a ``set -u`` violation (UnboundVariableError) the bash way.

    Prints once, then applies the shell-exit family of the fatal
    expansion-error model (``fatal_expansion_status``): a non-interactive
    shell EXITS — 127 for ``-c``, 1 for a script file / piped stdin — and
    an interactive (or embedded) shell discards the current line with
    status 1. Shared by the simple-command path and the arithmetic command
    / C-style-for paths so every set -u violation behaves identically (a
    bare ``$undef``, ``$(( undef ))``, ``(( undef ))`` and ``for ((i=undef;``
    all abort the same way). Never returns normally — raises ``SystemExit``
    or ``TopLevelAbort`` (typed ``-> int`` for its ``return
    report_unbound_variable(...)`` callers).
    """
    print(f"{state.error_location_prefix()}{exc}", file=state.stderr)
    return fatal_expansion_status(state, exc)


def report_assignment_error(state: 'ShellState', exc: Exception) -> int:
    """Report a readonly / cyclic-nameref assignment failure the bash way
    and fail the command (status 1) WITHOUT aborting the shell.

    Shared by every handler that evaluates arithmetic as a command —
    ``(( ))``, the three C-style ``for`` expressions, ``[[ ]]`` — and by
    the ``for`` loop-variable binding, so ``readonly r; (( r=9 ))`` behaves
    identically everywhere: print ``psh: r: readonly variable`` (bash's
    message and flow — error, status 1, execution continues) instead of
    leaking a PshError to the buffered-command guard as an "unexpected
    error" that aborts a ``-c`` list. A cyclic nameref prints bash's
    warning form instead of the error form.
    """
    if isinstance(exc, NamerefCycleError):
        state.scope_manager.warn_nameref_cycle(exc.name)
    else:
        print(f"{state.error_location_prefix()}{exc}", file=state.stderr)
    return 1


def setup_child_redirections_for(shell: 'Shell', redirects) -> None:
    """Apply a redirect list in a forked child via setup_child_redirections.

    The four fork-child strategy sites (backgrounded builtin, backgrounded
    function, pipeline exec, external command) each wrapped a bare redirect
    list in a throwaway ``SimpleCommand`` solely to reach
    ``io_manager.setup_child_redirections``; this is that one wrapper. A
    falsy/empty list is a no-op.
    """
    if not redirects:
        return
    shell.io_manager.setup_child_redirections(
        SimpleCommand(redirects=redirects))


def execute_builtin_guarded(builtin, cmd_name: str, args: List[str],
                            shell: 'Shell',
                            invocation: Optional['BuiltinContext'] = None,
                            special_exit: bool = False) -> int:
    """Run a builtin, converting unexpected exceptions to exit status 1.

    Shared by the special-builtin and regular-builtin strategies:

    - SystemExit (e.g. the ``exit`` builtin) propagates unchanged.
    - Control-flow exceptions (return / break / continue — e.g. raised
      inside ``eval``) and ``set -u`` violations propagate to their
      handlers rather than being converted to exit status 1.
    - ``SpecialBuiltinUsageError`` (a special builtin's typed usage/syntax
      outcome) resolves here: with ``special_exit`` (a DIRECT invocation —
      both strategy paths pass it) the one POSIX exit policy applies
      (``special_builtin_usage_exit``: POSIX + non-interactive → the shell
      exits with the carried status); without it (``command``/``builtin``,
      which strip the special property) the builtin simply fails with that
      status.
    - Anything else is a builtin defect: print "psh: NAME: error" and
      return 1, surfacing the traceback under --debug-exec so the bug
      isn't hidden behind the generic message.
    """
    if invocation is None:
        invocation = EMPTY_BUILTIN_CONTEXT
    try:
        # Builtins expect the command name as the first argument. Invoke
        # through execute_in_context so declaration builtins receive their
        # structured array initializers (BuiltinContext) explicitly.
        return builtin.execute_in_context([cmd_name] + args, shell, invocation)
    except SystemExit:
        # Some builtins like 'exit' raise SystemExit
        raise
    except SpecialBuiltinUsageError as e:
        if special_exit:
            return special_builtin_usage_exit(shell, e.status,
                                              suppressible=e.suppressible)
        return e.status
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
        # A declaration value that fails to evaluate arithmetically
        # (`declare -i v='1/0'`, `local -i w='1//'`): bash prints
        # "declare: 1/0: division by 0" and DISCARDS the rest of the
        # line (rest of the whole -c string under -c) — the
        # assignment/subscript arithmetic-error family.
        if isinstance(e, ShellArithmeticError):
            print(f"psh: {cmd_name}: {e}", file=shell.stderr)
            arith_assignment_discard(shell.state)
        # ExpansionError propagates to _handle_execution_error, which knows
        # a fatal expansion (message already printed at the raise site, e.g.
        # `unset "a[08]"`) aborts a non-interactive shell like bash.
        # RecursionError propagates so runaway recursion THROUGH a builtin
        # (e.g. `f(){ eval f; }`) still reaches the function-call boundary,
        # which converts it to the FUNCNEST diagnostic.
        if isinstance(e, (FunctionReturn, LoopBreak, LoopContinue,
                          UnboundVariableError, ExpansionError,
                          RecursionError)):
            raise
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
                visitor=None,
                invocation: Optional['BuiltinContext'] = None) -> int:
        """Execute the command and return exit status."""
        pass


# The complete POSIX special-builtin registry (policy data). Two mode-aware
# consequences, both decided in CommandExecutor._resolve_command (F9):
#
#   - Prefix-assignment persistence: `VAR=v <special>` leaves VAR set ONLY in
#     POSIX mode. In default (bash) mode the prefix is temporary, exactly like
#     any other builtin (`X=new :; echo ${X-unset}` -> unset).
#   - Lookup precedence: in default mode functions shadow special builtins
#     (`exit(){ ...; }; exit` runs the function); in POSIX mode special
#     builtins take precedence over functions.
#
# Must be COMPLETE, including `.` and `times` (they are special too — so a
# POSIX-mode `X=v . file` persists X). `source` is a bash extension, NOT a
# POSIX special builtin, so it is deliberately absent.
POSIX_SPECIAL_BUILTINS = {
    '.', ':', 'break', 'continue', 'eval', 'exec', 'exit', 'export',
    'readonly', 'return', 'set', 'shift', 'times', 'trap', 'unset'
}


class SpecialBuiltinExecutionStrategy(ExecutionStrategy):
    """Strategy for executing POSIX special builtin commands."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if command is a POSIX special builtin."""
        return (cmd_name in POSIX_SPECIAL_BUILTINS and
                shell.builtin_registry.has(cmd_name))

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None,
                invocation: Optional['BuiltinContext'] = None) -> int:
        """Execute a special builtin command."""
        if background:
            # Special builtins can run in background with subshell
            return self._execute_in_background(
                cmd_name, args, shell, context, redirects, invocation)

        builtin = shell.builtin_registry.get(cmd_name)
        if not builtin:
            return 127  # Command not found

        # Direct special-builtin invocation: the POSIX usage-error exit
        # policy applies (special_exit; see execute_builtin_guarded).
        return execute_builtin_guarded(builtin, cmd_name, args, shell,
                                       invocation, special_exit=True)

    def _execute_in_background(self, cmd_name: str, args: List[str],
                              shell: 'Shell', context: 'ExecutionContext',
                              redirects: Optional[List['Redirect']],
                              invocation: Optional['BuiltinContext'] = None) -> int:
        """Execute special builtin in background (subshell)."""
        # Use same background execution logic as regular builtins
        return BuiltinExecutionStrategy()._execute_builtin_in_background(
            cmd_name, args, shell, context, redirects, invocation
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
                visitor=None,
                invocation: Optional['BuiltinContext'] = None) -> int:
        """Execute a builtin command."""
        if background:
            # Run builtin in background by forking a subshell (bash compatibility)
            return self._execute_builtin_in_background(
                cmd_name, args, shell, context, redirects, invocation)

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
        # output method. special_exit: this is a direct invocation, and the
        # POSIX usage-error exit policy also covers `source` (a regular
        # builtin here, but bash exits for its missing-file/syntax errors in
        # POSIX mode exactly like `.` — probe-verified, tmp/posixexit).
        return execute_builtin_guarded(builtin, cmd_name, args, shell,
                                       invocation, special_exit=True)

    def _execute_builtin_in_background(self, cmd_name: str, args: List[str],
                                     shell: 'Shell', context: 'ExecutionContext',
                                     redirects: Optional[List['Redirect']] = None,
                                     invocation: Optional['BuiltinContext'] = None) -> int:
        """Execute a builtin command in the background as a forked shell child.

        A backgrounded builtin can itself run shell code (``eval``, ``.``,
        ``source``), so it goes through ``run_background_shell_child`` — the
        SAME shared bg-child runner as ``( ... ) &`` / ``{ ...; } &`` / a
        backgrounded function (F16). That runner gives it the async-list
        signal defaults, resets inherited parent traps, and — crucially — runs
        a body-set EXIT trap on completion, so ``eval 'trap "..." EXIT; ...' &``
        fires the trap like bash. It also goes through
        ``execute_builtin_guarded`` (defect-to-status, EBADF/EPIPE handling)
        and preserves the ``BuiltinContext`` (array initializers for a
        backgrounded declaration builtin).

        Redirections are installed exactly ONCE, here in the child
        (``setup_child_redirections``); the parent defers them (F3).
        """
        # The launcher applies the unified child signal policy on fork.
        launcher = shell.process_launcher

        def execute_fn():

            def body() -> int:
                # Apply redirections once in the child.
                setup_child_redirections_for(shell, redirects)

                builtin = shell.builtin_registry.get(cmd_name)
                if builtin is None:
                    return 127
                return execute_builtin_guarded(
                    builtin, cmd_name, args, shell, invocation)

            return run_background_shell_child(shell, body)

        # The child keeps running shell code (eval/source can start pipelines
        # or set traps), so mark it a shell process.
        # Join cleanly so an argument-less command (`false &`) has no trailing
        # space in the job table — bash lists `false`, not `false ` (visible
        # once `jobs` lists a completed job in script/stdin mode).
        return launcher.launch_background_job(
            execute_fn, " ".join([cmd_name, *args]), cmd_name,
            is_shell_process=True)


class FunctionExecutionStrategy(ExecutionStrategy):
    """Strategy for executing shell functions."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """Check if command is a defined function."""
        return shell.function_manager.get_function(cmd_name) is not None

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None,
                invocation: Optional['BuiltinContext'] = None) -> int:
        """Execute a shell function."""
        if background:
            # bash runs `f &` in a forked subshell
            return self._execute_function_in_background(
                cmd_name, args, shell, context, redirects, visitor)


        # Create a function executor to handle the call
        function_executor = FunctionOperationExecutor(shell)

        # Reuse the caller's visitor to preserve accumulated state;
        # fall back to creating a new one if not provided.
        if visitor is None:
            # cycle-break: executor.core -> executor.command -> executor.strategies
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

            # A backgrounded function call runs in a forked subshell
            # environment (bash). The shared bg-child runner gives it the same
            # trap discipline as ( ... ) & / { ...; } &: inherited PARENT traps
            # reset, a body-set managed-signal trap fires, and the EXIT trap
            # runs on completion / fatal signal.
            def body() -> int:
                setup_child_redirections_for(shell, redirects)

                function_executor = FunctionOperationExecutor(shell)
                v = visitor
                if v is None:
                    # cycle-break: executor.core -> executor.command -> executor.strategies
                    from .core import ExecutorVisitor
                    v = ExecutorVisitor(shell)
                    v.context = context
                return function_executor.execute_function_call(
                    cmd_name, args, context, v, None)

            return run_background_shell_child(shell, body)

        # The child keeps running shell code (the function body may start
        # pipelines or manage terminal control), so mark it a shell process.
        # Join cleanly so an argument-less command (`false &`) has no trailing
        # space in the job table — bash lists `false`, not `false ` (visible
        # once `jobs` lists a completed job in script/stdin mode).
        return launcher.launch_background_job(
            execute_fn, " ".join([cmd_name, *args]), cmd_name,
            is_shell_process=True)


class ExternalExecutionStrategy(ExecutionStrategy):
    """Strategy for executing external commands."""

    def can_execute(self, cmd_name: str, shell: 'Shell') -> bool:
        """External commands are the fallback - always return True."""
        return True

    def execute(self, cmd_name: str, args: List[str],
                shell: 'Shell', context: 'ExecutionContext',
                redirects: Optional[List['Redirect']] = None,
                background: bool = False,
                visitor=None,
                invocation: Optional['BuiltinContext'] = None,
                *, path_override: Optional[str] = None,
                use_hash: bool = True) -> int:
        """Execute an external command.

        Resolution goes through the shared :class:`CommandResolver` BEFORE
        forking, so a remembered location and its hit count land on the
        parent's state (pipeline members run in the forked child, whose
        table is a fork-copy — matching bash, where ``ls | cat`` leaves the
        parent table untouched).

        Two overrides serve the wrappers that build their own environment:

        - ``path_override`` (``command -p``): search that PATH authoritatively
          — no shell-hash consult, remember the find, and if the name is not
          in that PATH report "command not found" rather than letting
          ``execvpe`` fall back to the live PATH. The child still inherits the
          shell's real PATH (bash does not export the default path).
        - ``use_hash=False`` (``env`` with a PATH override): skip the command
          hash entirely so ``execvpe`` re-searches the (overridden) environment
          PATH, matching bash — the D3 fix (a stale shell hash must not run the
          old path when ``env PATH=... cmd`` changes the search).
        """
        full_args = [cmd_name] + args
        force_not_found = False
        if path_override is not None:
            # command -p: authoritative search in the given PATH; the shell
            # hash is neither consulted nor a fallback, but a find IS
            # remembered (bash overwrites any prior entry).
            if '/' in cmd_name:
                resolved_path = None
            else:
                matches = shell.command_resolver.search_path(cmd_name, path_override)
                resolved_path = matches[0] if matches else None
                if resolved_path is not None:
                    shell.state.command_hash.insert(cmd_name, resolved_path, hits=1)
                else:
                    force_not_found = True
        elif use_hash:
            resolved_path = shell.command_resolver.resolve_for_exec(cmd_name)
        else:
            # env override: no shell hash; execvpe walks the (overridden) env.
            resolved_path = None

        if context.in_pipeline:
            # In pipeline, use exec to replace current process
            try:
                # Set up redirections if any
                setup_child_redirections_for(shell, redirects)

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

                if force_not_found:
                    raise FileNotFoundError(errno.ENOENT,
                                            os.strerror(errno.ENOENT), cmd_name)
                exec_external(full_args, shell.env, resolved_path)
            except OSError as e:
                os._exit(report_exec_failure(full_args[0], e, resolved_path, state=shell.state))

        # Set terminal title to show running command
        if not background and not context.in_pipeline and shell.state.options.get('interactive'):
            # cycle-break: interactive.title -> interactive.signal_manager -> executor.job_control
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
            setup_child_redirections_for(shell, redirects)

            # Execute the command with proper environment
            if shell.state.options.get('debug-exec'):
                print(f"DEBUG ExternalStrategy: execvpe {full_args[0]} with "
                      f"PATH={shell.env.get('PATH', 'NOT_SET')[:50]}...",
                      file=sys.stderr)

            try:
                if force_not_found:
                    raise FileNotFoundError(errno.ENOENT,
                                            os.strerror(errno.ENOENT), cmd_name)
                exec_external(full_args, shell.env, resolved_path)
            except OSError as e:
                return report_exec_failure(full_args[0], e, resolved_path, state=shell.state)

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

            # Announce abnormal termination (Terminated / Segmentation fault /
            # ...) the way bash does for a signal-killed foreground command.
            shell.job_manager.report_abnormal_termination(job)

            # Reclaim the terminal (if we handed it over) and clear
            # foreground-job bookkeeping (a stopped job stays as %+).
            shell.job_manager.finish_foreground_job(original_pgid is not None, job)

            # Clean up
            if job.state == JobState.DONE:
                shell.job_manager.remove_job(job.job_id)

            return exit_status
