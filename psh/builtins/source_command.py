"""Source command builtin."""
import os
from typing import TYPE_CHECKING, List, Optional

from ..core import SpecialBuiltinUsageError
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class SourceBuiltin(Builtin):
    """Execute commands from a file in the current shell."""

    @property
    def name(self) -> str:
        return "source"

    @property
    def synopsis(self) -> str:
        return "source FILENAME [ARGS]"

    @property
    def help(self) -> str:
        return """source: source FILENAME [ARGS]
    Execute commands from a file in the current shell.

    Reads and executes commands from FILENAME in the current shell
    environment. If FILENAME does not contain a slash, PATH is
    searched. Any ARGS are set as positional parameters for the
    duration of the sourced script.

    Exit Status:
    Returns the exit status of the last command executed from FILENAME,
    or 1 if the file cannot be found or read."""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the source builtin."""
        if len(args) < 2:
            self.error("filename argument required", shell)
            return 1

        filename = args[1]
        # POSIX/bash: `source file` with no extra args leaves $@/$# unchanged;
        # `source file x y` sets them to x y for the duration of the sourced
        # file (restored afterward unless the file ran `set` — the service
        # owns that rule). Only override when args were given.
        source_args = tuple(args[2:]) if len(args) > 2 else None

        # Find the script file
        script_path = self._find_source_file(filename, shell)
        if script_path is None:
            # Missing file: rc 1, and a POSIX-mode non-interactive shell
            # EXITS (bash 5.2, probe tmp/posixexit — for BOTH the `.` and
            # `source` names, so this raise also fires on the `source`
            # regular-builtin strategy path); `command .`/`command source`
            # strip the exit at the builtin guard.
            self.error(f"{filename}: No such file or directory", shell)
            raise SpecialBuiltinUsageError(1)

        # Pre-flight checks. bash's `source` never content-sniffs the file
        # (its `cannot execute binary file` refusal is the >256-NUL rule,
        # owned by the sourced-program service — campaign F3 probes A6-A13),
        # so the shared validator runs with binary_sniff=False; it returns
        # the script-INVOCATION codes (126) for a directory or unreadable
        # file, remapped here to bash's `source` codes.
        validation_result = shell.script_manager.validate_script_file(
            script_path, binary_sniff=False)
        if validation_result != 0:
            if os.path.isdir(script_path):
                # A directory is a plain rc-1 failure — bash does NOT exit a
                # POSIX-mode shell for it (probe: `. /` survives, rc 1).
                return 1
            # An unreadable file, like a missing one, exits a POSIX-mode
            # non-interactive shell rc 1 (bash probe: Permission denied).
            raise SpecialBuiltinUsageError(1)

        # bash NEVER changes $0 (script_name) when sourcing — the sourced
        # file sees the CALLER's $0. Everything else (source depth, the
        # positional swap with bash's `set`-persistence rule, FunctionReturn,
        # the RETURN trap, restoration on exception exits, the >256-NUL
        # binary refusal) is owned by the ONE sourced-program service — the
        # same service rc loading uses (campaign F3: rc is not a second
        # source dialect).
        from ..scripting.program_source import (
            SourceRequest,
            execute_sourced_file,
        )
        try:
            return execute_sourced_file(
                shell, SourceRequest(path=script_path, args=source_args))
        except OSError as e:
            self.error(f"{script_path}: {e}", shell)
            return 1

    def _find_source_file(self, filename: str, shell: 'Shell') -> Optional[str]:
        """Find a source file, searching PATH if needed."""
        # If filename contains a slash, don't search PATH — use it as given
        # (existence, not isfile, so a directory still reaches the later
        # validate_script_file step, matching bash's `. /somedir`).
        if '/' in filename:
            if os.path.exists(filename):
                return filename
            return None

        # Slash-less: bash (`sourcepath` on) searches $PATH for a READABLE
        # file, then falls back to the cwd. Reuse the ONE resolver PATH walk
        # rather than a third hand-rolled copy — with mode=R_OK because source
        # READS the script (it is not exec'd, so the default X_OK gate is
        # wrong). Delegating also fixes an empty-PATH-component divergence: the
        # old hand walk SKIPPED empty components, but bash (and search_path)
        # maps an empty component to the cwd and searches it IN ORDER — so
        # `PATH=":/dir" source f` picks the cwd copy, not /dir.
        # PATH from the VARIABLE (tri-state), not the child-env projection: a
        # declared-unset `local PATH` shadows the outer export (bash searches an
        # empty PATH and fails), it must not resurrect it (#20 H13 / CV2).
        matches = shell.command_resolver.search_path(
            filename, shell.state.get_variable('PATH', ''), mode=os.R_OK)
        if matches:
            return matches[0]

        # cwd fallback when PATH held no readable match at all.
        if os.path.exists(filename):
            return filename

        return None


@builtin
class DotBuiltin(SourceBuiltin):
    """Dot command (alias for source)."""

    @property
    def name(self) -> str:
        return "."

    @property
    def synopsis(self) -> str:
        return ". FILENAME [ARGS]"

    @property
    def help(self) -> str:
        return """. FILENAME [ARGS]
    Execute commands from FILENAME in the current shell environment.

    This is a synonym for 'source'. See 'help source' for details.

    Exit Status:
    Returns the exit status of the last command executed from FILENAME."""
