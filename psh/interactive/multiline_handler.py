"""Multi-line input handler for interactive mode.

This module provides multi-line command support for the interactive shell,
allowing users to naturally type control structures across multiple lines.

The completeness decision — "has the user finished this command?" — is NOT
made here. Every line is fed to the shared `CommandAccumulator`
(`psh/scripting/command_accumulator.py`), the same parser-driven oracle the
script/`-c` path uses, so interactive and script line-gathering can never
disagree. What lives here is the interactive glue: the read_line loop, the
PS1/PS2 prompts, and the rendering of the accumulator's continuation hint
as a contextual prompt ("if> ", "for then> ") when the parser reports which
constructs are still open.
"""

from typing import Callable, Optional

from ..scripting.command_accumulator import CommandAccumulator, Complete, Hint
from .line_editor import LineEditor


class MultiLineInputHandler:
    """Handles multi-line command input for interactive mode."""

    def __init__(self, line_editor: LineEditor, shell):
        self.line_editor = line_editor
        self.shell = shell
        self.accumulator = CommandAccumulator(shell)
        # last NeedMore hint, drives the continuation prompt
        self._hint: Optional[Hint] = None

    def read_command(self, on_resize: Optional[Callable[[], None]] = None) -> Optional[str]:
        """Read a complete command, possibly spanning multiple lines."""
        self.reset()

        # Honor `set -o vi` / `set -o emacs` issued since the last read
        self.line_editor.set_edit_mode(self.shell.state.edit_mode)

        # Get SIGWINCH notification fd from signal manager if available
        # (the line editor's KeyDecoder multiplexes it with stdin and
        # drains it itself; resize redraws surface as Resize events)
        sigwinch_fd = -1
        if hasattr(self.shell, 'interactive_manager') and self.shell.interactive_manager:
            sigwinch_fd = self.shell.interactive_manager.signal_manager.get_sigwinch_fd()

        while True:
            # Determine prompt
            prompt = self._get_prompt()

            # Read one line
            line = self.line_editor.read_line(prompt, sigwinch_fd,
                                              on_resize=on_resize)
            if line is None:  # EOF
                if not self.accumulator.is_empty:
                    print("\npsh: syntax error: unexpected end of file")
                    self.reset()
                return None

            result = self.accumulator.feed(line)
            if isinstance(result, Complete):
                # The whole logical command, continuations joined. Execution
                # goes through shell.run_command -> the source processor,
                # which re-applies the oracle and reports any syntax error
                # carried in result.error.
                self.reset()
                from ..scripting.input_preprocessing import process_line_continuations
                return process_line_continuations(result.text)

            self._hint = result.hint

    def reset(self):
        """Reset multi-line state (also the Ctrl-C handler's entry point)."""
        self.accumulator.reset()
        self._hint = None

    def _get_prompt(self) -> str:
        """Get the appropriate prompt based on current state.

        Rendering goes through the shared ``PromptManager`` (the one the
        interactive manager wires up), so PS1/PS2 get bash's full ``promptvars``
        expansion — backslash escapes THEN parameter / command / arithmetic
        expansion — not the escape-only pass.
        """
        prompt_manager = self.shell.interactive_manager.prompt_manager
        if self.accumulator.is_empty:
            # Primary prompt
            ps1 = self.shell.state.variables.get('PS1', '\\u@\\h:\\w\\$ ')
            return prompt_manager.expand_prompt(ps1)

        # Continuation prompt. When the parser told us which constructs are
        # still open, show them ("if> ", "for then> "); otherwise (heredoc
        # bodies, unclosed quotes/expansions, line continuations) use PS2.
        if self._hint is not None and self._hint.constructs:
            return ' '.join(self._hint.constructs) + '> '
        ps2 = self.shell.state.variables.get('PS2', '> ')
        return prompt_manager.expand_prompt(ps2)
