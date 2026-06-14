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
        validation_result = self.shell.script_manager.script_validator.validate_script_file(script_path)
        if validation_result != 0:
            return validation_result

        # Check for shebang and execute with appropriate interpreter
        if self.shell.script_manager.shebang_handler.should_execute_with_shebang(script_path):
            return self.shell.script_manager.shebang_handler.execute_with_shebang(
                script_path, script_args)

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
            with FileInput(script_path) as input_source:
                exit_code = self.shell.script_manager.source_processor.execute_from_source(
                    input_source, add_to_history=False)

                # Execute EXIT trap if set (only for the main script, not sourced files)
                if hasattr(self.shell, 'trap_manager') and old_script_mode != True:
                    self.shell.trap_manager.execute_exit_trap()

                return exit_code
        except OSError as e:
            print(f"psh: {script_path}: {e}", file=sys.stderr)
            return 1
        finally:
            self.state.script_name = old_script_name
            self.state.is_script_mode = old_script_mode
            if old_stdin_mode is not None:
                self.state.options['stdin_mode'] = old_stdin_mode
            self.state.positional_params = old_positional
