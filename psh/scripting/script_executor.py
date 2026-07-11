"""Script file execution."""
import sys
from typing import List, Optional

from .base import ScriptComponent
from .input_sources import FileInput


class ScriptExecutor(ScriptComponent):
    """Executes script files."""

    def run_script(self, script_path: str, script_args: Optional[List[str]] = None) -> int:
        """Execute a script file with optional arguments."""
        if script_args is None:
            script_args = []

        # Validate the script file first
        validation_result = self.shell.script_manager.validate_script_file(script_path)
        if validation_result != 0:
            return validation_result

        # NOTE: a `#!...` first line is a COMMENT here, not a dispatch
        # instruction. When a shell is invoked to interpret a file
        # (`psh FILE`), POSIX/bash treat the shebang as an ordinary comment
        # and run the file as shell. The kernel handles `#!` only when a file
        # is exec'd directly as a command — which psh supports via the
        # external-command path (`psh -c './x.sh'`), independent of this code.

        # Save current script state
        old_script_name = self.state.script_name
        old_script_mode = self.state.is_script_mode
        old_stdin_mode = self.state.options.get('stdin_mode')
        old_positional = self.state.positional_params.copy()

        self.state.script_name = script_path
        self.state.is_script_mode = True
        # A script-file shell reads from a file, not stdin: bash's $- has no 's'.
        self.state.options['stdin_mode'] = False
        self.state.positional_params = script_args

        try:
            # A script file ARGUMENT is a bash stream input: a dangling
            # backslash at true EOF is dropped (a sourced file keeps it) —
            # see InputSource.eof_drops_dangling_continuation.
            with FileInput(script_path,
                           eof_drops_dangling_continuation=True) as input_source:
                # execute_as_main fires the EXIT trap exactly once when the
                # script finishes — at end-of-file, on a `set -e` abort, or on
                # an explicit `exit`. (A sourced file does NOT run this path;
                # `source` goes straight through execute_from_source, so its
                # EXIT trap is deferred to the main shell's exit, like bash.)
                return self.shell.script_manager.execute_as_main(
                    input_source, add_to_history=False)
        except OSError as e:
            print(f"psh: {script_path}: {e}", file=sys.stderr)
            return 1
        finally:
            self.state.script_name = old_script_name
            self.state.is_script_mode = old_script_mode
            if old_stdin_mode is not None:
                self.state.options['stdin_mode'] = old_stdin_mode
            self.state.positional_params = old_positional
