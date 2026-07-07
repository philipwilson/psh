"""The ``env`` builtin (display environment, run command with overrides).

bash-faithful model (v0.656): standard ``env`` is an EXTERNAL command. With a
command it builds the exact child environment and execs the argv through the
shell's normal external launcher — it does NOT resolve shell builtins,
functions, or aliases (``/usr/bin/env`` is external, so ``env cd`` /
``env export`` / ``env somefunc`` are "No such file or directory", exactly as
in bash). This is what makes ``env`` isolate process state: ``env exit 7`` can
no longer terminate psh, ``env exec`` cannot replace it, and ``env cd`` /
``env umask`` / ``env ulimit`` cannot mutate the parent's cwd / umask / limits,
because the command runs in a forked child, never in the shell process.

Running the command in an in-process child ``Shell`` (the pre-v0.656 design)
could isolate only Python-owned state; process-level cwd/umask/limits/signal
dispositions and process replacement/termination always leaked. That approach —
and its ``builtins-through-env`` extension — was dropped (see the ledger note
in the core-state Phase 1 campaign).
"""

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class EnvBuiltin(Builtin):
    """Display environment variables or run a command with a modified one."""

    @property
    def name(self) -> str:
        return "env"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Display environment variables or run a command externally."""
        # Keep shell.env in sync with exported scope variables first.
        shell.state.scope_manager.sync_exports_to_environment(shell.env)

        if len(args) == 1:
            self._print_environment(shell.env, shell)
            return 0

        parsed = self._parse_invocation(args[1:], shell)
        if parsed is None:
            return 1
        clear_env, unset_names, assignments, command_args = parsed

        env_map = {} if clear_env else shell.env.copy()
        for name in unset_names:
            env_map.pop(name, None)
        env_map.update(assignments)

        # No command: print the (temporarily overridden) environment.
        if not command_args:
            self._print_environment(env_map, shell)
            return 0

        # Command mode: run the argv EXTERNALLY with env_map. env does not
        # resolve shell builtins/functions (bash-faithful). Redirections on the
        # env invocation itself were already applied at the fd level by the
        # builtin-redirection setup, so the forked child inherits them.
        return self._exec_external(command_args, env_map, shell)

    def _exec_external(self, command_args: List[str], env_map: Dict[str, str],
                       shell: 'Shell') -> int:
        """Run *command_args* through the shell's external launcher with the
        constructed environment.

        Delegates to ``ExternalExecutionStrategy`` (the single fork + job
        control + execvp-search + 126/127-diagnostics path — the same one the
        ``command`` builtin uses), temporarily installing *env_map* as the
        live environment so the forked child execs with exactly it. The swap is
        confined to the (blocking) foreground run and restored afterwards; the
        parent never observes env_map. The argv is passed as a list — never
        quoted into source text and reparsed.

        KNOWN EDGE (verifier finding, v0.656; fix belongs to the shared
        CommandResolver work): the direct ``shell.state.env`` swap bypasses the
        PATH observer, so ``command_hash`` is NOT cleared — after a command has
        been auto-hashed, ``env PATH=/override <same-cmd>`` execs the HASHED
        path where bash re-searches the overridden PATH. Non-corrupting
        (wrong lookup, not state damage); resolver campaign should bypass or
        clear the hash when env overrides PATH.
        """
        from ..executor import ExecutionContext, ExternalExecutionStrategy

        saved_env = shell.state.env
        shell.state.env = env_map
        try:
            return ExternalExecutionStrategy().execute(
                command_args[0], command_args[1:], shell, ExecutionContext(),
                redirects=None, background=False)
        finally:
            shell.state.env = saved_env

    def _parse_invocation(
        self, argv: List[str], shell: 'Shell'
    ) -> Optional[Tuple[bool, List[str], Dict[str, str], List[str]]]:
        """Parse env options, assignments, and command arguments."""
        clear_env = False
        unset_names: List[str] = []
        assignments: Dict[str, str] = {}
        idx = 0

        # Parse leading options.
        while idx < len(argv):
            arg = argv[idx]
            if arg == '--':
                idx += 1
                break
            if arg in ('-', '-i'):
                clear_env = True
                idx += 1
                continue
            if arg == '-u':
                if idx + 1 >= len(argv):
                    self.error("option requires an argument -- 'u'", shell)
                    return None
                unset_names.append(argv[idx + 1])
                idx += 2
                continue
            if arg.startswith('-u') and len(arg) > 2:
                unset_names.append(arg[2:])
                idx += 1
                continue
            if arg.startswith('-'):
                self.error(f"invalid option: {arg}", shell)
                return None
            break

        # Parse leading NAME=VALUE assignments after options.
        while idx < len(argv) and self._is_env_assignment(argv[idx]):
            key, value = argv[idx].split('=', 1)
            assignments[key] = value
            idx += 1

        return clear_env, unset_names, assignments, argv[idx:]

    def _is_env_assignment(self, arg: str) -> bool:
        """Check whether an argument is an env assignment token."""
        if '=' not in arg:
            return False
        name, _ = arg.split('=', 1)
        return bool(name)

    def _print_environment(self, env_map: Dict[str, str], shell: 'Shell') -> None:
        """Print environment mapping (forked-child aware via Builtin.write)."""
        for key, value in sorted(env_map.items()):
            self.write_line(f"{key}={value}", shell)

    @property
    def help(self) -> str:
        return """env: env [OPTION]... [-] [name=value ...] [command [args ...]]

    Display environment variables or run a command with a modified environment.
    With no arguments, print all environment variables.
    With -i (or -), start with an empty environment.
    With -u NAME, remove NAME from the environment for this invocation.
    With name=value pairs and no command, print the modified environment.
    With a command, run it EXTERNALLY with the modified environment (env does
    not run shell builtins or functions, matching /usr/bin/env)."""
