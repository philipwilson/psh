"""The in-process EMBEDDING contract for the substitution abort (slot 2.4, R6-D).

``Shell.run_command`` is psh's public in-process entry point, and it is the one
frame that does NOT contain ``SubstitutionSyntaxAbort``: in script mode the
abort escapes to the CALLER instead of being flattened into a status. That is
deliberate — the fatality belongs to the shell PROCESS in bash, and the only
sanctioned consumer is the whole-shell entry point
``SourceProcessor.execute_as_main``, which ``run_command`` does not route
through (it is also the escape the ``eval`` builtin relies on to abort its
frame). The round-5 verifier found the behaviour undeclared; the integrator
ruled it INTENDED, so it is pinned here rather than repaired.

The interactive-family arm matters just as much: with ``is_script_mode`` False
the consumer never fires, so an embedder there sees an ordinary status. That is
why the whole test suite is unaffected by the escape — the shell fixtures are
interactive-family.
"""

import pytest

from psh.core.exceptions import SubstitutionSyntaxAbort


@pytest.mark.parametrize("command", [
    "echo $(if)",      # unclosed body — found by the reader parse
    "echo $(fi)",      # complete but invalid — found when the body is parsed
    "cat <(if)",       # the procsub spelling rides the same path
])
def test_script_mode_lets_the_abort_escape_run_command(captured_shell, command):
    captured_shell.state.is_script_mode = True
    with pytest.raises(SubstitutionSyntaxAbort):
        captured_shell.run_command(command)


@pytest.mark.parametrize("command", ["echo $(if)", "echo $(fi)"])
def test_interactive_family_gets_a_status_not_an_escape(captured_shell, command):
    """``is_script_mode`` False is the interactive FAMILY, ``-i -c`` included."""
    captured_shell.state.is_script_mode = False
    assert captured_shell.run_command(command) == 2


def test_the_escape_is_not_a_generic_syntax_error_escape(captured_shell):
    """CONTROL: an ordinary syntax error still returns a status in script mode.

    Only the SUBSTITUTION-ORIGIN error is fatal to the process — which is the
    whole point of the typed outcome. If this control ever raises, the abort
    has widened past its origin fact."""
    captured_shell.state.is_script_mode = True
    assert captured_shell.run_command("if") == 2
