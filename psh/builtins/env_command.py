"""The ``env`` builtin (display/modify environment, run command with overrides).

Split out of ``environment.py`` because ``env`` is unusual among the
environment builtins: it runs a command in a nested in-process child Shell
and carries its own process-fd binding helpers (really an I/O concern) to
make redirections reach forked grandchildren correctly.
"""

import io
import os
import shlex
import sys
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class EnvBuiltin(Builtin):
    """Display or modify environment variables."""

    @property
    def name(self) -> str:
        return "env"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Display environment variables or run command with modified environment."""
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

        # No command: print environment with temporary overrides.
        if not command_args:
            self._print_environment(env_map, shell)
            return 0

        # Command mode: env deliberately does its own "executor" work here.
        # The command runs in an isolated in-process child Shell (not a fork)
        # so builtin side effects (export/unset/cd) cannot leak into the
        # parent, while env's environment overrides apply only to the child.
        # See _bind_process_fds_to_streams() for why fds are juggled around
        # the child run.
        command_text = " ".join(shlex.quote(arg) for arg in command_args)

        from ..core import VarAttributes
        from ..shell import Shell

        child_shell = Shell.for_subshell(shell, norc=False)
        child_shell.state.options.update(shell.state.options)
        child_shell.stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
        child_shell.stderr = shell.stderr if hasattr(shell, 'stderr') else sys.stderr
        child_shell.stdin = shell.stdin if hasattr(shell, 'stdin') else sys.stdin

        self._configure_child_export_attributes(child_shell, clear_env, unset_names)
        child_shell.env.clear()
        child_shell.env.update(env_map)

        # Apply env overrides to child's exported environment only.
        for key, value in assignments.items():
            child_shell.state.scope_manager.set_variable(
                key, value, attributes=VarAttributes.EXPORT, local=False
            )
            child_shell.env[key] = value

        fd_backups = self._bind_process_fds_to_streams(child_shell)
        try:
            return child_shell.run_command(command_text, add_to_history=False)
        finally:
            self._restore_process_fds(fd_backups)

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

    def _configure_child_export_attributes(
        self, shell: 'Shell', clear_env: bool, unset_names: List[str]
    ) -> None:
        """Prevent child export sync from reintroducing env entries removed by env options."""
        from ..core import VarAttributes

        scope_manager = shell.state.scope_manager
        if clear_env:
            for var in scope_manager.all_variables_with_attributes():
                if var.is_exported:
                    scope_manager.remove_attribute(var.name, VarAttributes.EXPORT)

        for name in unset_names:
            scope_manager.remove_attribute(name, VarAttributes.EXPORT)

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

    def _bind_process_fds_to_streams(self, shell: 'Shell') -> List[Tuple[int, int]]:
        """Align process fds 0/1/2 with the shell's stream objects.

        Why env needs this: unlike most builtins, `env CMD` runs CMD in a
        nested in-process Shell (see execute()). External commands launched
        by that child shell fork+exec and inherit the *process-level* fds,
        not the parent shell's stream objects — so when env itself was
        redirected at the shell level (e.g. `env cmd > file` captured into
        shell.stdout), the grandchild would write to the wrong place.
        Temporarily dup2() each stream's fd over 0/1/2 so forked commands
        see the same redirections. Returns (target_fd, backup_fd) pairs for
        _restore_process_fds().
        """
        backups: List[Tuple[int, int]] = []
        stream_to_fd = (
            (shell.stdin if hasattr(shell, 'stdin') else sys.stdin, 0),
            (shell.stdout if hasattr(shell, 'stdout') else sys.stdout, 1),
            (shell.stderr if hasattr(shell, 'stderr') else sys.stderr, 2),
        )

        for stream, target_fd in stream_to_fd:
            try:
                stream_fd = stream.fileno()
            except (AttributeError, io.UnsupportedOperation, ValueError):
                continue

            if stream_fd == target_fd:
                continue

            backup_fd = os.dup(target_fd)
            os.dup2(stream_fd, target_fd)
            backups.append((target_fd, backup_fd))

        return backups

    def _restore_process_fds(self, backups: List[Tuple[int, int]]) -> None:
        """Restore fds previously redirected by _bind_process_fds_to_streams."""
        for target_fd, backup_fd in reversed(backups):
            os.dup2(backup_fd, target_fd)
            os.close(backup_fd)

    @property
    def help(self) -> str:
        return """env: env [OPTION]... [-] [name=value ...] [command [args ...]]

    Display environment variables or run a command with modified environment.
    With no arguments, print all environment variables.
    With -i (or -), start with an empty environment.
    With -u NAME, remove NAME from the environment for this invocation.
    With name=value pairs and no command, print the modified environment.
    With a command, run it with temporary environment overrides."""
