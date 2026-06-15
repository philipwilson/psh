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

    def run_interactive_loop(self):
        """Run the interactive shell loop.

        Process-global signal handlers are installed HERE, not at manager
        construction: every Shell builds an InteractiveManager, but only a
        shell actually entering the interactive loop may take over the
        process's signal dispositions (an in-process test shell or a
        library embedder must not). This replaces the old "pytest in
        sys.modules" gate with a structural guarantee.
        """
        # Set up signal handlers FIRST to ignore SIGTTOU/SIGTTIN
        # This must happen before ensure_foreground() to avoid being stopped
        self.signal_manager.setup_signal_handlers()

        # Now safe to ensure shell is in its own process group for job control
        self.signal_manager.ensure_foreground()

        try:
            return self.repl_loop.run()
        finally:
            # Restore the handlers saved by setup_signal_handlers() on EVERY
            # exit path (EOF, `exit` builtin via SystemExit, exceptions).
            # When this process IS psh the handlers die with the process
            # anyway, but an embedder (Shell object inside another Python
            # process, e.g. the test suite) must get its own signal
            # dispositions back when the loop ends.
            self.signal_manager.restore_default_handlers()

    def load_history(self):
        """Load command history from file."""
        self.history_manager.load_from_file()

    def save_history(self):
        """Save command history to file."""
        self.history_manager.save_to_file()
