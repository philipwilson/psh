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

                # Report completed background jobs before the next prompt.
                # bash with `set -b`/`set -o notify` prints these the instant
                # the child is reaped — even while the shell sits idle at the
                # prompt. psh cannot match that immediacy while blocked in the
                # line editor's select() (it multiplexes only stdin and the
                # SIGWINCH pipe, not the SIGCHLD pipe), so it emits at the next
                # reaping opportunity — here — for BOTH notify states. Skipping
                # this under `notify` used to drop the notice entirely AND leak
                # the job as a stale DONE (notify_completed_jobs is the only
                # reaper of finished background jobs); the synchronous wait path
                # still emits immediately for jobs reaped by an in-progress
                # `wait`, and marks them notified so this call won't double-report.
                self.job_manager.notify_completed_jobs()

                # Check for stopped jobs (from Ctrl-Z)
                self.job_manager.notify_stopped_jobs()

                # bash runs PROMPT_COMMAND after job notices and before PS1
                # (never before a PS2 continuation — hence here, once per
                # logical command, not inside read_command).
                self._run_prompt_command()

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
                    # exit" (bash synthesizes one), so shift it into the
                    # command register — after `jobs`, a Ctrl-D exits
                    # without a warning, exactly like `exit` — and apply
                    # the stopped-jobs guard: the first attempt warns
                    # and stays.
                    self.job_manager.note_simple_command('exit')
                    if not self.job_manager.confirm_exit_with_stopped_jobs():
                        continue
                    # bash echoes "exit" (to stderr) on the EOF that actually
                    # leaves the shell; the newline also moves the cursor off
                    # the prompt line the Ctrl-D left it on.
                    print('exit', file=sys.stderr)
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

    def _run_prompt_command(self):
        """Run $PROMPT_COMMAND before the primary prompt, bash-style.

        bash executes PROMPT_COMMAND before each PS1: as a command string,
        or — in bash 5.x — each element of an array in order. The user's
        ``$?`` is preserved across it (a PROMPT_COMMAND that runs ``true``
        must not clobber the exit status the next prompt/command sees), and
        it is never recorded in history. A failing PROMPT_COMMAND reports
        its error but does not escape (the REPL loop's own handler is the
        final backstop). Behavior pinned to bash 5.2 —
        tmp/probes-r18t2-interactive/probe_mi2_*.
        """
        from ..core.variables import AssociativeArray, IndexedArray

        var = self.state.scope_manager.get_variable_object('PROMPT_COMMAND')
        if var is None:
            return
        if isinstance(var.value, (IndexedArray, AssociativeArray)):
            commands = var.value.all_elements()
        else:
            commands = [var.as_string()]

        saved_exit_code = self.state.last_exit_code
        try:
            for command in commands:
                if command.strip():
                    self.shell.run_command(command, add_to_history=False)
        finally:
            self.state.last_exit_code = saved_exit_code
