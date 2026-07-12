"""Pins for the R19 T7 diagnostic-stream rider: executor diagnostics honor
the ``state.stderr`` override.

The ``select`` PS3 prompt + menu (control_flow.py), the ``[[ ]]``
ValueError/TypeError/OSError diagnostic (core.py, the sibling of the
ShellArithmeticError arm five lines up), and the ROOT-sequence out-of-loop
break/continue announce (core.py) used to write to raw ``sys.stderr``,
escaping an embedder's ``state.stderr`` override — the captured-shell /
embedder pattern — while every neighboring diagnostic honored the override.

These tests DISCRIMINATE the routing: they install ONLY a ``state.stderr``
override (a private buffer) while ``sys.stderr`` points at a DIFFERENT decoy
buffer. On the pre-fix tree the text lands in the decoy and the override
stays empty; post-fix the override receives it and the decoy stays empty.
(The ``captured_shell`` fixture routes sys.stderr and the override to the
SAME buffer, so it cannot see this distinction — hence the dedicated shape.)
Demonstrated red-on-base at c59d11d5; see the T7 ledger.
"""
import io
import sys

import pytest

from psh.core import LoopBreak, LoopContinue
from psh.executor.core import ROOT_SEQUENCE, ExecutorVisitor


@pytest.fixture
def routed_shell(shell, monkeypatch):
    """A shell whose state.stderr/stdout are private buffers while
    sys.stderr is a separate DECOY buffer (the leak detector)."""
    override = io.StringIO()
    stdout = io.StringIO()
    decoy = io.StringIO()
    shell.state.stderr = override
    shell.state.stdout = stdout
    monkeypatch.setattr(sys, 'stderr', decoy)
    return shell, override, decoy, stdout


class TestSelectMenuRouting:
    """select writes its menu and PS3 prompt to the shell's stderr sink
    (bash writes both to stderr; probed under 2>file in the T7 battery)."""

    def test_menu_and_ps3_land_in_state_stderr(self, routed_shell):
        shell, override, decoy, _stdout = routed_shell
        shell.state.stdin = io.StringIO("1\n")
        # (The body's stdout routing is not this pin's subject — the executor
        # re-derives stdout per command; only the stderr sink is asserted.)
        rc = shell.run_command(
            'select x in alpha beta; do echo picked:$x; break; done')
        assert rc == 0
        err = override.getvalue()
        assert "1) alpha" in err
        assert "2) beta" in err
        assert "#? " in err                       # the default PS3 prompt
        assert decoy.getvalue() == ""             # nothing leaked to sys.stderr


class TestDoubleBracketDiagnosticRouting:
    """The [[ ]] ValueError diagnostic (`psh: [[: ...`, status 2) uses
    state.stderr like its ShellArithmeticError sibling in the same method."""

    def test_invalid_regex_diagnostic_lands_in_state_stderr(self, routed_shell):
        shell, override, decoy, _stdout = routed_shell
        # An unquoted variable RHS is live regex source; "(" fails to compile
        # -> ValueError -> the except arm at issue (status 2, like bash).
        rc = shell.run_command('re="("; [[ a =~ $re ]]')
        assert rc == 2
        assert "psh: [[:" in override.getvalue()
        assert decoy.getvalue() == ""             # nothing leaked to sys.stderr


class TestOutOfLoopAnnounceRouting:
    """The ROOT-sequence 'only meaningful in a loop' announce uses
    state.stderr. Driven directly through _execute_sequence, the same shape
    as test_execute_sequence.py (the announce arm needs a context that reset
    loop_depth after the raise — e.g. a trap action)."""

    class _Stmt:
        """Stand-in statement; ExecutorVisitor.visit is stubbed below."""
        line = None

    @pytest.mark.parametrize("exc, keyword", [
        (LoopBreak(), "break"),
        (LoopContinue(), "continue"),
    ])
    def test_announce_lands_in_state_stderr(self, routed_shell, exc, keyword):
        shell, override, decoy, _stdout = routed_shell
        ev = ExecutorVisitor(shell)
        ev.context.loop_depth = 0

        def raise_it(_node):
            raise exc
        ev.visit = raise_it  # type: ignore[method-assign]

        ev._execute_sequence([self._Stmt()], context=ROOT_SEQUENCE)
        assert f"{keyword}: only meaningful" in override.getvalue()
        assert decoy.getvalue() == ""             # nothing leaked to sys.stderr
