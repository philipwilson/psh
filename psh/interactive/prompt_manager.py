"""Prompt formatting and management."""
from .base import InteractiveComponent
from .prompt import PromptExpander


class PromptManager(InteractiveComponent):
    """Manages shell prompts (PS1, PS2)."""

    def __init__(self, shell):
        super().__init__(shell)
        self.prompt_expander = PromptExpander(shell)

    def get_primary_prompt(self) -> str:
        """Get the primary prompt (PS1)."""
        ps1 = self.state.get_variable('PS1', r'\u@\h:\w\$ ')
        return self.expand_prompt(ps1)

    def get_continuation_prompt(self) -> str:
        """Get the continuation prompt (PS2)."""
        ps2 = self.state.get_variable('PS2', '> ')
        return self.expand_prompt(ps2)

    def expand_prompt(self, prompt_string: str) -> str:
        """Expand a prompt: backslash escapes, then parameter / command /
        arithmetic expansion (bash's default ``promptvars``).

        Delegates to ``PromptExpander.expand_full`` so PS1/PS2 and the
        ``${var@P}`` operator share one implementation.
        """
        return self.prompt_expander.expand_full(prompt_string)

    def set_prompt(self, prompt_type: str, value: str) -> None:
        """Set a prompt value."""
        if prompt_type in ("PS1", "PS2"):
            self.state.set_variable(prompt_type, value)
