"""Eval builtin implementation."""
from .base import Builtin
from .registry import builtin


@builtin
class EvalBuiltin(Builtin):
    """Execute arguments as shell commands."""

    name = "eval"

    @property
    def synopsis(self) -> str:
        return "eval [ARG ...]"

    @property
    def help(self) -> str:
        return """eval: eval [ARG ...]
    Execute arguments as shell commands.

    Concatenates all ARGs into a single string, then parses and
    executes the result as a shell command. This allows constructing
    commands dynamically.

    Exit Status:
    Returns the exit status of the executed command, or 0 if no
    arguments are given."""

    def execute(self, args, shell):
        """Execute the eval builtin."""
        # Skip args[0] which is 'eval' itself
        if len(args) <= 1:
            # Empty eval returns 0
            return 0

        # Concatenate all arguments after 'eval' with spaces
        command_string = ' '.join(args[1:])

        # Execute using shell's run_command method
        # This ensures full processing: tokenization, parsing, execution
        # add_to_history=False prevents eval commands from polluting history.
        # Anchor $LINENO at the eval command's own line (bash behavior): the
        # eval string's line 1 reports the line eval was invoked on, not 1.
        # line_oriented=True processes the (possibly multi-line) string
        # PHYSICAL-line-by-line like a script, so a word-arithmetic / readonly
        # discard-line error inside it discards only the offending line and
        # resumes at the next — matching bash (`eval 'echo a\necho $((1/0))\n
        # echo c'` prints a and c, not just a).
        base_line = shell.state.scope_manager.get_current_line_number()
        return shell.run_command(command_string, add_to_history=False,
                                 base_line=base_line, line_oriented=True)
