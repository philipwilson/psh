"""Command builtin for bypassing aliases and functions."""

import os
from typing import TYPE_CHECKING, List, Optional

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..executor.command_resolver import Candidate
    from ..shell import Shell


def _default_path() -> str:
    """bash's ``command -p`` search path: a value guaranteed to find the
    standard utilities. Matches bash, which uses ``confstr(_CS_PATH)``."""
    try:
        return os.confstr("CS_PATH") or "/usr/bin:/bin"
    except (ValueError, OSError):
        return "/usr/bin:/bin"


@builtin
class CommandBuiltin(Builtin):
    """Execute a simple command or display information about commands."""

    @property
    def name(self) -> str:
        return "command"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute command with options or bypass functions/aliases."""
        # -p/-v/-V are boolean flags (clusterable, e.g. -vp); the shared
        # getopt-style helper also matches bash's invalid-option message.
        opts, operands = self.parse_flags(args, shell, flags='pvV')
        if opts is None:
            return 2
        use_default_path = opts['p']
        show_description = opts['v']
        verbose_description = opts['V']

        # bash: bare `command` (or `command -v` with no names) succeeds
        if not operands:
            return 0

        command_name = operands[0]
        command_args = operands

        # Handle description modes (-v and -V)
        if show_description or verbose_description:
            return self._show_command_info(
                operands, verbose_description, shell, use_default_path)

        # `command` bypasses aliases and FUNCTIONS but still selects builtins
        # (bash) — `-p` only changes the PATH used for the EXTERNAL search, it
        # does not force external execution. Any `> file` redirect on the
        # `command ...` word is already applied around this builtin by the
        # executor, so the guarded builtin — and anything it spawns — sees it.
        builtin_obj = shell.builtin_registry.get(command_name)
        if builtin_obj is not None:
            from ..executor.strategies import execute_builtin_guarded
            return execute_builtin_guarded(
                builtin_obj, command_name, command_args[1:], shell)

        # External: with -p search the default path authoritatively (the child
        # still inherits the shell's real PATH); otherwise the normal path with
        # the command hash.
        path_override = _default_path() if use_default_path else None
        return self._execute_external_command(
            command_name, command_args, shell,
            path_override=path_override, use_hash=not use_default_path)

    def _show_command_info(self, names: List[str], verbose: bool, shell: 'Shell',
                           use_default_path: bool = False) -> int:
        """Display information about commands (bash `command -v` / `-V`).

        Renders the shared resolver's result so the lookup order, hash
        consultation, and PATH walk match `type` and the executor exactly —
        and `-V`'s banner text comes from `type_builtin.
        render_candidate_banner`, so the WORDING cannot drift either.
        `command` reports functions here (it only bypasses them for
        execution). Returns 0 if at least one name resolved, else 1.
        """
        from ..executor.command_resolver import ResolveQuery

        resolver = shell.command_resolver
        query = ResolveQuery(path=_default_path() if use_default_path else None)

        any_found = False
        for name in names:
            cand = resolver.resolve(name, query).first
            if cand is None:
                # Not found: -v is silent, -V prints an error (bash)
                if verbose:
                    self.error(f"{name}: not found", shell)
                continue
            any_found = True
            self._render_info(name, cand, verbose, shell)

        return 0 if any_found else 1

    def _render_info(self, name: str, cand: 'Candidate', verbose: bool,
                     shell: 'Shell') -> None:
        """Render one candidate for `command -v` (reusable) or `-V` (verbose)."""
        from ..executor.command_resolver import CandidateKind

        if verbose:
            # -V: the descriptive banner — the SAME renderer `type` uses
            # (bash's wording is identical between the two builtins;
            # probe-pinned), so the two surfaces cannot drift.
            from .type_builtin import render_candidate_banner
            self.write_line(render_candidate_banner(name, cand), shell)
            return

        # -v: a reusable form.
        if cand.kind is CandidateKind.ALIAS:
            escaped = (cand.alias_value or "").replace("'", "'\"'\"'")
            self.write_line(f"alias {name}='{escaped}'", shell)
        elif cand.is_file and cand.path is not None:
            self.write_line(cand.path, shell)
        else:  # keyword / function / builtin
            self.write_line(name, shell)

    def _execute_external_command(self, command_name: str, args: List[str],
                                  shell: 'Shell', *,
                                  path_override: Optional[str] = None,
                                  use_hash: bool = True) -> int:
        """Execute an external command using PSH's external execution strategy."""
        # Use PSH's existing external execution strategy which handles
        # process management, job control, and signal handling correctly
        from ..executor import ExecutionContext, ExternalExecutionStrategy

        return ExternalExecutionStrategy().execute(
            command_name, args[1:], shell, ExecutionContext(),
            redirects=None, background=False,
            path_override=path_override, use_hash=use_hash,
        )

    @property
    def synopsis(self) -> str:
        return "command [-pVv] command [arg ...]"

    @property
    def description(self) -> str:
        return "Execute a simple command or display information about commands"

    @property
    def help(self) -> str:
        return """command: command [-pVv] command [arg ...]
    Execute a simple command or display information about commands.

    Runs COMMAND with ARGS suppressing shell function lookup, or display
    information about the specified COMMANDs.  Can be used to invoke commands
    on disk when a function with the same name exists.

    Options:
      -p    use a default value for PATH that is guaranteed to find all of
            the standard utilities
      -v    print a description of COMMAND similar to the `type' builtin
      -V    print a more verbose description of each COMMAND

    Exit Status:
    Returns exit status of COMMAND, or failure if COMMAND is not found."""


@builtin
class BuiltinBuiltin(Builtin):
    """Run a shell builtin, bypassing function lookup."""

    @property
    def name(self) -> str:
        return "builtin"

    @property
    def synopsis(self) -> str:
        return "builtin [shell-builtin [arg ...]]"

    @property
    def description(self) -> str:
        return "Execute a shell builtin, bypassing functions with the same name"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        if len(args) < 2:
            return 0  # bash: bare `builtin` succeeds

        name = args[1]
        target = shell.builtin_registry.get(name)
        if target is None:
            self.error(f"{name}: not a shell builtin", shell)
            return 1
        # Run through the shared guard (uniform broken-pipe / OSError / defect
        # handling), with the builtin's own name as argv[0]. Any redirect on
        # the `builtin ...` word is already applied around this builtin by the
        # executor.
        from ..executor.strategies import execute_builtin_guarded
        return execute_builtin_guarded(target, name, args[2:], shell)

    @property
    def help(self) -> str:
        return """builtin: builtin [shell-builtin [arg ...]]

    Execute SHELL-BUILTIN with the given arguments, without performing
    function lookup. Lets a function with the same name as a builtin
    call the builtin (e.g. a cd wrapper calling `builtin cd`).

    Exit Status:
    The exit status of SHELL-BUILTIN, or 1 if it is not a shell builtin."""
