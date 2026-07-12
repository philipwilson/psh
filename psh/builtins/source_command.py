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
        # file (and restores afterward). Only override when args were given.
        has_source_args = len(args) > 2
        source_args = args[2:] if has_source_args else []

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

        # Validate the script file. The shared validator returns the codes
        # bash uses for the script-INVOCATION path (`psh file`): 126 for a
        # directory, unreadable file, or binary. bash's `source` diverges —
        # it returns 1 for a directory or unreadable file and reserves 126
        # for a binary file (probe-verified vs bash 5.2). The validator has
        # already printed the diagnostic; remap the non-binary failures here.
        validation_result = shell.script_manager.validate_script_file(script_path)
        if validation_result != 0:
            if os.path.isdir(script_path):
                # A directory is a plain rc-1 failure — bash does NOT exit a
                # POSIX-mode shell for it (probe: `. /` survives, rc 1).
                return 1
            if not os.access(script_path, os.R_OK):
                # An unreadable file, like a missing one, exits a POSIX-mode
                # non-interactive shell rc 1 (bash probe: Permission denied).
                raise SpecialBuiltinUsageError(1)
            return validation_result

        # Save current shell state. bash NEVER changes $0 (script_name) when
        # sourcing — the sourced file sees the CALLER's $0 — so we leave it
        # untouched. Positional parameters are saved/restored ONLY when ARGS
        # are passed: a no-args source SHARES the caller's positionals, so a
        # `set --` inside it persists to the caller (bash).
        old_script_mode = shell.state.is_script_mode
        if has_source_args:
            old_positional = shell.state.positional_params.copy()
            shell.state.positional_params = source_args
        # Keep current script mode (sourcing inherits mode)

        shell.state.source_depth += 1
        try:
            from ..scripting.input_sources import FileInput
            from .function_support import FunctionReturn
            try:
                with FileInput(script_path) as input_source:
                    # Execute with no history since it's sourced
                    exit_code = shell.script_manager.execute_from_source(
                        input_source, add_to_history=False)
            except FunctionReturn as ret:
                # `return N` inside the sourced file: stop executing the file
                # and make N the exit status of `source` itself (bash).
                exit_code = ret.exit_code
            # The RETURN trap fires each time a sourced file finishes —
            # whether by end-of-file or an explicit `return` — with $? =
            # the last command's status from before the return (bash).
            # Unlike functions, `source` never hides the trap (it fires
            # without set -T). A `return` in the action overrides the
            # exit status (see TrapManager.execute_return_trap).
            override = shell.trap_manager.execute_return_trap()
            if override is not None:
                exit_code = override
            return exit_code
        except OSError as e:
            self.error(f"{script_path}: {e}", shell)
            return 1
        finally:
            shell.state.source_depth -= 1
            # Restore previous state
            if has_source_args:
                shell.state.positional_params = old_positional
            shell.state.is_script_mode = old_script_mode

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
        matches = shell.command_resolver.search_path(
            filename, shell.env.get('PATH', ''), mode=os.R_OK)
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
