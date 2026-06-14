"""Source command builtin."""
import os
from typing import TYPE_CHECKING, List

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
            self.error(f"{filename}: No such file or directory", shell)
            return 1

        # Validate the script file
        validation_result = shell.script_manager.script_validator.validate_script_file(script_path)
        if validation_result != 0:
            return validation_result

        # Save current shell state
        old_positional = shell.state.positional_params.copy()
        old_script_name = shell.state.script_name
        old_script_mode = shell.state.is_script_mode

        # Set new state for sourced script
        if has_source_args:
            shell.state.positional_params = source_args
        shell.state.script_name = script_path
        # Keep current script mode (sourcing inherits mode)

        shell.state.source_depth += 1
        try:
            from ..scripting.input_sources import FileInput
            from .function_support import FunctionReturn
            try:
                with FileInput(script_path) as input_source:
                    # Execute with no history since it's sourced
                    return shell.script_manager.source_processor.execute_from_source(input_source, add_to_history=False)
            except FunctionReturn as ret:
                # `return N` inside the sourced file: stop executing the file
                # and make N the exit status of `source` itself (bash).
                return ret.exit_code
        except OSError as e:
            self.error(f"{script_path}: {e}", shell)
            return 1
        finally:
            shell.state.source_depth -= 1
            # Restore previous state
            shell.state.positional_params = old_positional
            shell.state.script_name = old_script_name
            shell.state.is_script_mode = old_script_mode

    def _find_source_file(self, filename: str, shell: 'Shell') -> str:
        """Find a source file, searching PATH if needed."""
        # If filename contains a slash, don't search PATH
        if '/' in filename:
            if os.path.exists(filename):
                return filename
            return None

        # First check current directory
        if os.path.exists(filename):
            return filename

        # Search in PATH
        path_dirs = shell.env.get('PATH', '').split(':')
        for path_dir in path_dirs:
            if path_dir:  # Skip empty path components
                full_path = os.path.join(path_dir, filename)
                if os.path.exists(full_path):
                    return full_path

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
