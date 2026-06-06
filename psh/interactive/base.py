"""Base classes for interactive shell components."""
from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..shell import Shell


class InteractiveComponent(ABC):
    """Base class for interactive shell components."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state
        self.job_manager = shell.job_manager
        self.multi_line_handler = None  # Set by InteractiveManager


class InteractiveManager:
    """Manages all interactive shell components."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Initialize interactive components
        from .history_manager import HistoryManager
        from .prompt_manager import PromptManager
        from .repl_loop import REPLLoop
        from .signal_manager import SignalManager

        self.history_manager = HistoryManager(shell)
        self.prompt_manager = PromptManager(shell)
        self.signal_manager = SignalManager(shell)
        self.repl_loop = REPLLoop(shell)

        # Cross-component dependencies
        self.repl_loop.history_manager = self.history_manager
        self.repl_loop.prompt_manager = self.prompt_manager

        # Skip signal setup when running under pytest to avoid affecting subprocess tests
        # UNLESS we're specifically testing signal handling
        # Also skip if we're in a forked child process (subshell/pipeline)
        import os
        import sys
        skip_signals = (('pytest' in sys.modules and
                        os.environ.get('PSH_TEST_SIGNALS') != '1') or
                       os.environ.get('PSH_IN_FORKED_CHILD') == '1')

        if not skip_signals:
            # Set up signal handlers FIRST to ignore SIGTTOU/SIGTTIN
            # This must happen before ensure_foreground() to avoid being stopped
            self.signal_manager.setup_signal_handlers()

            # Now safe to ensure shell is in its own process group for job control
            self.signal_manager.ensure_foreground()

    def run_interactive_loop(self):
        """Run the interactive shell loop."""
        return self.repl_loop.run()

    def load_history(self):
        """Load command history from file."""
        self.history_manager.load_from_file()

    def save_history(self):
        """Save command history to file."""
        self.history_manager.save_to_file()
