"""EXIT-trap exit-status precedence, pinned cell by cell against bash 5.2.

Slot 4A.2's charter clause is "specify exit-status precedence".  The spec is
this table: it lives in the tree so it survives the merge and ratchets, rather
than in a probe transcript that dies with the worktree.

THE RULE.  An EXIT trap's body cannot change the shell's exit status except
through an explicit ``exit N``.  A BARE ``exit`` inside the trap means "leave
the status alone" and resolves to the status in effect when the trap was
ENTERED -- NOT to the body's current ``$?``.

WHY EVERY CELL IS COMPOSED.  The slot's first battery pinned bare ``exit``
with two cells (``trap 'exit' EXIT; exit 3`` and ``trap 'exit' EXIT; false``)
in which NOTHING inside the trap changed ``$?`` before the bare exit.  Those
cells are VACUOUS for this rule: "pre-trap status" and "current ``$?``"
predict the same answer, so they could not have failed for the reason they
were written, and they certified agreement while psh diverged (D-3.4 lesson
8).  Every row below is therefore labelled: ``DISC`` rows change ``$?`` in the
body before the bare exit and so can tell the two rules apart; ``control``
rows cannot, and are kept precisely so the distinction stays visible to the
next reader.

Cells marked DISC were RED before the fix (psh resolved a bare ``exit`` from
the current ``$?``); the controls and the explicit-operand guard were green
throughout and are must-holds.
"""
import pytest
from shell_oracle import is_comparable, run_bash, run_psh

#: (id, script, discriminating)
CELLS = [
    # -- controls: cannot discriminate; kept labelled so they are not re-read
    #    as evidence for the bare-exit rule ---------------------------------
    ("control-bare-exit-after-exit3", "trap 'exit' EXIT; exit 3", False),
    ("control-bare-exit-after-false", "trap 'exit' EXIT; false", False),
    # The trap body's status alone never leaked: psh already had this right.
    ("control-body-status-not-leaked", "trap 'false' EXIT; exit 3", False),
    # An explicit operand overrides, and must keep overriding (must-hold).
    ("guard-explicit-operand-wins", "trap 'false; exit 7' EXIT; exit 3", False),
    # -- discriminating: the body changes $? before the bare exit ----------
    ("disc-false-then-bare-exit", "trap 'false; exit' EXIT; exit 3", True),
    ("disc-true-then-bare-exit", "trap 'true; exit' EXIT; exit 3", True),
    ("disc-normal-end-body-false", "trap 'false; exit' EXIT", True),
    ("disc-outer-false-body-true", "trap 'true; exit' EXIT; false", True),
    ("disc-subshell-exit9-then-bare",
     "trap '(exit 9); exit' EXIT; exit 3", True),
    # Localizing cell: `$?` READ inside the trap is the CURRENT value in both
    # shells (q=1), while the bare exit resolves to the ENTRY status. Pins
    # that the fix changed the resolution ONLY, and did not disturb `$?`.
    ("disc-localizing-read-vs-resolve",
     "trap 'false; echo q=$?; exit' EXIT; exit 3", True),
    # A bare exit inside a FUNCTION called from the trap is still inside the
    # trap action, so the same rule applies.
    ("disc-bare-exit-in-called-function",
     "f() { false; exit; }; trap f EXIT; exit 3", True),
    # errexit: `false` in the body aborts before the bare exit is reached, so
    # both shells report 1. Kept because it looks discriminating and is not.
    ("disc-errexit-aborts-before-bare-exit",
     "set -e; trap 'false; exit' EXIT; exit 3", True),
    # The SIGNAL-trap counterpart, carried across all three modes so the
    # EXIT-only boundary is pinned at the same width as the rule itself. Its
    # dedicated must-hold (below) additionally asserts the exact values.
    ("disc-signal-trap-uses-current-status",
     "trap 'echo entry=$?; false; exit' USR1\nkill -USR1 $$\nsleep 0.2\nexit 3",
     True),
]

MODES = ["command", "script", "stdin"]


def _run(runner, tag, mode, script, tmp_path):
    """One cell in one input mode, through the shell-oracle runner.

    The runner is passed as a CALLABLE (``run_psh`` / ``run_bash``) rather
    than selected from a shell-name string: a literal ``"bash"`` argument here
    trips the oracle-resolution guard, which cannot tell a mode selector from
    a hard-coded oracle binary. ``tag`` only names the temp script file.
    """
    if mode == "command":
        return runner(["-c", script])
    if mode == "script":
        path = tmp_path / f"case_{tag}.sh"
        path.write_text(script + "\n")
        return runner([str(path)])
    return runner([], stdin_data=script + "\n", stdin_mode="pipe")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("cell_id,script,discriminating",
                         [pytest.param(*c, id=c[0]) for c in CELLS])
def test_exit_trap_status_matches_bash(cell_id, script, discriminating, mode,
                                       tmp_path):
    """psh and bash agree on stdout AND exit status for every cell x mode."""
    psh = _run(run_psh, "psh", mode, script, tmp_path)
    bash = _run(run_bash, "oracle", mode, script, tmp_path)
    assert is_comparable(psh), psh
    assert is_comparable(bash), bash
    assert (psh.stdout, psh.returncode) == (bash.stdout, bash.returncode), (
        f"{cell_id} [{mode}] {'DISCRIMINATING' if discriminating else 'control'}\n"
        f"  script: {script!r}\n"
        f"  bash: {bash.stdout!r} rc={bash.returncode}\n"
        f"  psh:  {psh.stdout!r} rc={psh.returncode}")


def test_bare_exit_in_a_signal_trap_still_uses_current_status():
    """MUST-HOLD against generalizing the mechanism (slot 4A.2 ruling R4).

    The saved-status rule is EXIT-trap-SPECIFIC.  In a SIGNAL trap bash
    resolves a bare ``exit`` from the CURRENT ``$?``, so a fix that saved the
    entry status for every trap would introduce a NEW divergence in the act of
    closing this one.  The trap prints its entry status to make the cell
    self-evidently discriminating: entry is 0 (the ``kill`` succeeded) while
    the status is 1 (from ``false``), so the two rules predict different
    answers and both shells choose the current one.
    """
    script = ("trap 'echo entry=$?; false; exit' USR1\n"
              "kill -USR1 $$\n"
              "sleep 0.2\n"
              "exit 3\n")
    psh = run_psh(["-c", script])
    bash = run_bash(["-c", script])
    assert is_comparable(psh) and is_comparable(bash)
    assert (psh.stdout, psh.returncode) == (bash.stdout, bash.returncode)
    assert psh.stdout == "entry=0\n"
    assert psh.returncode == 1        # current $?, NOT the entry status 0
