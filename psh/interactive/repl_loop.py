"""Read-Eval-Print Loop implementation."""
import sys
from typing import TYPE_CHECKING, Optional

from .base import InteractiveComponent
from .eof_policy import EOF_IGNORED_MESSAGE, ignoreeof_limit
from .line_editor import LineEditor
from .multiline_handler import MultiLineInputHandler
from .title import idle_title, set_terminal_title

if TYPE_CHECKING:
    from .history_manager import HistoryManager
    from .prompt_manager import PromptManager


class REPLLoop(InteractiveComponent):
    """Implements the interactive shell loop."""

    def __init__(self, shell):
        super().__init__(shell)
        # history_manager/prompt_manager are wired by InteractiveManager;
        # line_editor/multi_line_handler are built by setup() before run().
        self.history_manager: Optional["HistoryManager"] = None
        self.prompt_manager: Optional["PromptManager"] = None
        self.line_editor: Optional[LineEditor] = None
        self.multi_line_handler: Optional[MultiLineInputHandler] = None
        # Consecutive Ctrl-D presses at the prompt, for ignoreeof/
        # IGNOREEOF (reset by a non-blank command; blank lines don't
        # reset it — bash-probed, see interactive/eof_policy.py).
        self._consecutive_eofs = 0

    def setup(self):
        """Set up the REPL environment."""
        # Set up line editor with current edit mode (tab completion is handled
        # by the LineEditor's own CompletionEngine, not readline)
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
        # setup() built the handler; InteractiveManager wired the history manager.
        assert self.multi_line_handler is not None
        assert self.history_manager is not None

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
                    # ignoreeof: swallow up to IGNOREEOF consecutive
                    # EOFs, telling the user how to leave (bash prints
                    # the message to stderr).
                    self._consecutive_eofs += 1
                    limit = ignoreeof_limit(self.state)
                    if limit is not None and self._consecutive_eofs <= limit:
                        print(EOF_IGNORED_MESSAGE, file=sys.stderr)
                        continue
                    # The EOF that exits behaves "as if the user typed
                    # exit" (bash), so the stopped-jobs guard applies —
                    # the first attempt warns and stays.
                    if not self.job_manager.confirm_exit_with_stopped_jobs():
                        continue
                    print()  # New line before exit
                    break

                if command.strip():
                    self._consecutive_eofs = 0
                    warning_was_pending = self.job_manager.exit_warning_pending
                    self.shell.run_command(command)
                    if warning_was_pending:
                        # A command ran after "There are stopped jobs."
                        # without the shell exiting: re-arm the guard
                        # (bash last_shell_builtin semantics — blank
                        # lines don't get here and keep it disarmed).
                        self.job_manager.clear_exit_warning()

            except KeyboardInterrupt:
                # Ctrl-C pressed, cancel multi-line input and continue.
                # The line editor already echoed ^C and moved to a new
                # line (LineRenderer.show_interrupt) — echoing it again
                # here printed a duplicate ^C (reappraisal #17 L1).
                self.multi_line_handler.reset()
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

        # Run the EXIT trap (e.g. on Ctrl-D), then save history on exit.
        if hasattr(self.shell, 'trap_manager'):
            self.shell.trap_manager.execute_exit_trap()
        self.history_manager.save_to_file()
