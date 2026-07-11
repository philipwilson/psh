"""Base classes for script handling components."""
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ..shell import Shell


class ScriptComponent:
    """Shared base for script-handling components.

    Provides only the common ``shell``/``state`` wiring. Each concrete
    component (ScriptExecutor, ScriptValidator, SourceProcessor) exposes its
    own domain method; there is no shared polymorphic entry point, so this is
    a plain base, not an ABC.
    """

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state


class ScriptManager:
    """Facade over the script-handling components.

    Callers of the routed operations (execute_as_main, validate_script_file)
    should go through this facade rather than
    reaching into ``.source_processor``/``.script_validator`` directly — it
    exposes the full public API (``run_script``, ``execute_from_source``,
    ``execute_as_main``, ``validate_script_file``).
    """

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Initialize script components
        from .script_executor import ScriptExecutor
        from .script_validator import ScriptValidator
        from .source_processor import SourceProcessor

        self.script_executor = ScriptExecutor(shell)
        self.script_validator = ScriptValidator(shell)
        self.source_processor = SourceProcessor(shell)

    def run_script(self, script_path: str, script_args: Optional[List[str]] = None) -> int:
        """Execute a script file with optional arguments."""
        return self.script_executor.run_script(script_path, script_args)

    def execute_from_source(self, input_source, add_to_history: bool = True,
                            base_line: int = 1) -> int:
        """Execute commands from an input source.

        ``base_line`` offsets the source onto absolute $LINENO lines (default
        1); >1 only for eval/trap nested executions — see Shell.run_command.
        """
        return self.source_processor.execute_from_source(
            input_source, add_to_history, base_line=base_line)

    def execute_as_main(self, input_source, add_to_history: bool = True) -> int:
        """Execute an input source as the main script/``-c``/stdin program.

        Fires the EXIT trap exactly once when the program finishes (EOF, a
        ``set -e`` abort, or an explicit ``exit``); see
        ``SourceProcessor.execute_as_main``.
        """
        return self.source_processor.execute_as_main(input_source, add_to_history)

    def validate_script_file(self, script_path: str) -> int:
        """Pre-flight file checks + syntax validation for a script file
        (see ``ScriptValidator.validate_script_file``)."""
        return self.script_validator.validate_script_file(script_path)
