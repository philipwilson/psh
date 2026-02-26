"""Read-Eval-Print Loop implementation."""
import sys

from ..line_editor import LineEditor
from ..multiline_handler import MultiLineInputHandler
from .base import InteractiveComponent
from .title import idle_title, set_terminal_title


class REPLLoop(InteractiveComponent):
    """Implements the interactive shell loop."""

    def __init__(self, shell):
        super().__init__(shell)
        self.history_manager = None
        self.prompt_manager = None
        self.completion_manager = None
        self.line_editor = None
        self.multi_line_handler = None

    def setup(self):
        """Set up the REPL environment."""
        # Set up readline and tab completion
        self.completion_manager.setup_readline()

        # Set up line editor with current edit mode
        self.line_editor = LineEditor(
            self.state.history,
            edit_mode=self.state.edit_mode
        )

        # Set up multi-line input handler
        self.multi_line_handler = MultiLineInputHandler(
            self.line_editor,
            self.shell
        )

    def run(self):
        """Run the main interactive loop."""
        self.setup()

        while True:
            try:
                # Process any pending SIGCHLD notifications
                # This is the self-pipe pattern: signal handler writes to pipe,
                # main loop processes notifications outside signal context
                if hasattr(self.shell, 'interactive_manager'):
                    self.shell.interactive_manager.signal_manager.process_sigchld_notifications()

                # Check for completed background jobs (only if notify option is disabled)
                # When notify is enabled, jobs are notified immediately when they complete
                if not self.state.options.get('notify', False):
                    self.job_manager.notify_completed_jobs()

                # Check for stopped jobs (from Ctrl-Z)
                self.job_manager.notify_stopped_jobs()

                # Set terminal title to idle state before each prompt
                set_terminal_title(idle_title(self.shell))

                # Read command (possibly multi-line)
                on_resize = lambda: set_terminal_title(idle_title(self.shell))
                command = self.multi_line_handler.read_command(on_resize=on_resize)

                if command is None:  # EOF (Ctrl-D)
                    print()  # New line before exit
                    break

                if command.strip():
                    self.shell.run_command(command)

            except KeyboardInterrupt:
                # Ctrl-C pressed, cancel multi-line input and continue
                self.multi_line_handler.reset()
                print("^C")
                self.state.last_exit_code = 130  # 128 + SIGINT(2)
                continue
            except EOFError:
                # Ctrl-D pressed
                print()
                break
            except OSError as e:
                # Handle I/O errors specially
                if e.errno == 5:  # EIO - Input/output error
                    print(f"psh: fatal: {e}", file=sys.stderr)
                    break  # Exit the loop instead of continuing
                else:
                    print(f"psh: {e}", file=sys.stderr)
                    self.state.last_exit_code = 1
            except Exception as e:
                print(f"psh: {e}", file=sys.stderr)
                self.state.last_exit_code = 1

        # Save history on exit
        self.history_manager.save_to_file()
