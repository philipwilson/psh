"""Trap exit-status precedence, pinned cell by cell against bash 5.3.15.

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

BASH 5.3 WIDENED THE RULE (bash 5.3 NEWS item uu; CHANGES 5.3-beta section 3
item q; POSIX interp 1602): "If `exit' is run in a trap and not supplied an
exit status argument, it uses the value of $? from before the trap only if
it's run at the trap's `top level' and would cause the trap to end (that is,
not in a subshell)."  That now covers SIGNAL traps and ERR, not only EXIT.
Probed on 5.3.15 in all three input modes, "top level" is relative to the
action: the action's own command text, including ``if`` / ``{ }`` / loop
bodies, ``||`` / ``&&`` lists and ``eval``, resolves from the ENTRY status; a
bare ``exit`` inside a FUNCTION BODY or a SOURCED FILE called from the action
still resolves from the CURRENT ``$?``; DEBUG keeps the current ``$?``; the
EXIT trap is unchanged (unconditional, even inside a called function).

psh still implements the EXIT-only rule (``psh/core/trap_manager.py``
records the entry status for EXIT alone).  The cells that moved are pinned
BOTH SIDES in ``DIVERGENCE_CELLS`` as declared divergences: bash 5.3
semantics; psh to follow in slot 2.1, which flips each row into a parity cell
of ``CELLS``.  Every divergence cell asserts bash 5.3.15's output AND psh's
current output, so it goes red the moment EITHER shell moves.  The boundary
shapes where the two shells already agree (function body, sourced file,
DEBUG) are parity cells so the boundary is pinned at the same width as the
rule.  Gate triage node family C242 (Wave 0.3).

Reproduce one cell by hand (oracle = the resolved bash 5.3.15)::

    /opt/homebrew/bin/bash -c "trap 'echo entry=\\$?; false; exit' USR1
    kill -USR1 \\$\\$; sleep 0.2; exit 3"; echo rc=$?      # entry=0 / rc=0
    python -m psh -c "<same>"; echo rc=$?                  # entry=0 / rc=1
"""
import pytest
from shell_oracle import is_comparable, run_bash, run_psh

#: (id, script, discriminating) -- rows where psh and bash AGREE.
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
    # A bare exit inside a FUNCTION called from the EXIT trap is still inside
    # the trap action, so the same rule applies (bash 5.3 keeps EXIT
    # unconditional: the interp-1602 top-level boundary below does NOT apply
    # to the EXIT trap -- probed 5.3.15, rc 3 in both shells).
    ("disc-bare-exit-in-called-function",
     "f() { false; exit; }; trap f EXIT; exit 3", True),
    # errexit: `false` in the body aborts before the bare exit is reached, so
    # both shells report 1. Kept because it looks discriminating and is not.
    ("disc-errexit-aborts-before-bare-exit",
     "set -e; trap 'false; exit' EXIT; exit 3", True),
    # -- bash 5.3 top-level BOUNDARY, parity half: a bare exit that is NOT at
    #    the action's top level resolves from the CURRENT $? in both shells
    #    (bash 5.3 NEWS uu; probed 5.3.15).  These hold today and after the
    #    slot 2.1 flip, so they are parity cells, not divergence cells. ----
    # Function body called from a SIGNAL trap: rc 1 (current $?, from false).
    ("boundary-signal-trap-function-body-uses-current-status",
     "f() { false; exit; }\ntrap f USR1\nkill -USR1 $$\nsleep 0.2\nexit 3",
     True),
    # Sourced file run from a SIGNAL trap: rc 1 (current $?).
    ("boundary-signal-trap-sourced-file-uses-current-status",
     "printf 'false; exit\\n' > s_dot.sh\ntrap '. ./s_dot.sh' USR1\n"
     "kill -USR1 $$\nsleep 0.2\nexit 3",
     True),
    # DEBUG keeps the current $? (rc 1) -- interp 1602 does not cover DEBUG.
    ("boundary-debug-trap-uses-current-status",
     "trap 'false; exit' DEBUG\ntrue", True),
]

#: (id, script, (bash stdout, bash rc), (psh stdout, psh rc)) -- DECLARED
#: DIVERGENCES: bash 5.3 semantics (NEWS uu / CHANGES 5.3-beta 3.q, POSIX
#: interp 1602), psh to follow in slot 2.1.  Both sides are asserted exactly;
#: the flip moves each row into CELLS.  Values are the 5.3.15 probes of
#: 2026-09-06, identical in -c, script-file and stdin modes.
DIVERGENCE_CELLS = [
    # The SIGNAL-trap counterpart of disc-false-then-bare-exit: bash resolves
    # the bare exit from the ENTRY status (0, the kill succeeded); psh from
    # the CURRENT $? (1, from false).  The trap prints its entry status so
    # the cell is self-evidently discriminating.
    ("disc-signal-trap-uses-entry-status",
     "trap 'echo entry=$?; false; exit' USR1\nkill -USR1 $$\nsleep 0.2\nexit 3",
     ("entry=0\n", 0), ("entry=0\n", 1)),
    # The signal arrives while the parent waits for a foreground SUBSHELL, so
    # the action runs after `(...; exit 5)` completes and its ENTRY status is
    # 5; bash's bare exit yields 5, psh's yields the action's current $? (0
    # from true).
    ("disc-signal-trap-entered-after-subshell-uses-entry-status",
     "trap 'true; exit' USR1\n(kill -USR1 $$; exit 5)\nsleep 0.2\nexit 3",
     ("", 5), ("", 0)),
    # An `if` body inside the action IS the action's top level: entry 0.
    ("disc-signal-trap-if-body-is-top-level",
     "trap 'if true; then false; exit; fi' USR1\nkill -USR1 $$\nsleep 0.2\n"
     "exit 3",
     ("", 0), ("", 1)),
    # `eval` inside the action is still the action's top level: entry 0.
    ("disc-signal-trap-eval-is-top-level",
     "trap 'eval \"false; exit\"' USR1\nkill -USR1 $$\nsleep 0.2\nexit 3",
     ("", 0), ("", 1)),
    # ERR is covered too: entry status 1 (from the failing `false`) wins over
    # the brace group's current $? 0 (from true) in bash; psh uses 0.
    ("disc-err-trap-brace-group-is-top-level",
     "trap '{ true; exit; }' ERR\nfalse\necho nr",
     ("", 1), ("", 0)),
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


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("cell_id,script,bash_expect,psh_expect",
                         [pytest.param(*c, id=c[0]) for c in DIVERGENCE_CELLS])
@pytest.mark.oracle_min("5.3")
def test_trap_entry_status_declared_divergence(cell_id, script, bash_expect,
                                               psh_expect, mode, tmp_path):
    """DECLARED DIVERGENCE, both sides pinned: bash 5.3 semantics (NEWS uu,
    POSIX interp 1602); psh to follow in slot 2.1.

    Red the moment EITHER shell moves: if the oracle stops matching
    ``bash_expect`` the oracle drifted (re-baseline, do not edit in place);
    if psh stops matching ``psh_expect`` the 2.1 fix landed and this row must
    move into ``CELLS`` as a parity cell.
    """
    psh = _run(run_psh, "psh", mode, script, tmp_path)
    bash = _run(run_bash, "oracle", mode, script, tmp_path)
    assert is_comparable(psh), psh
    assert is_comparable(bash), bash
    assert (bash.stdout, bash.returncode) == bash_expect, (
        f"{cell_id} [{mode}] ORACLE side moved\n"
        f"  script: {script!r}\n"
        f"  bash: {bash.stdout!r} rc={bash.returncode}, expected {bash_expect}")
    assert (psh.stdout, psh.returncode) == psh_expect, (
        f"{cell_id} [{mode}] PSH side moved (slot 2.1 landed? flip this row)\n"
        f"  script: {script!r}\n"
        f"  psh:  {psh.stdout!r} rc={psh.returncode}, expected {psh_expect}")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.oracle_min("5.3")
def test_bare_exit_in_a_signal_trap_uses_entry_status_declared_divergence(
        mode, tmp_path):
    """MUST-HOLD, rewritten for bash 5.3 (slot 4A.2 ruling R4 is superseded).

    Under bash 5.2 the saved-status rule was EXIT-trap-SPECIFIC and this
    must-hold guarded against generalizing psh's mechanism.  bash 5.3 (NEWS
    item uu, POSIX interp 1602) generalized the rule itself: a bare ``exit``
    at a SIGNAL trap's top level now resolves from the status at trap ENTRY.
    The trap prints its entry status to make the cell self-evidently
    discriminating: entry is 0 (the ``kill`` succeeded) while the current
    status is 1 (from ``false``), so the two rules predict different answers
    -- bash 5.3.15 chooses the entry status (rc 0), psh still chooses the
    current one (rc 1).  Both sides are pinned; slot 2.1 flips the psh side
    to rc 0 and this test to a plain parity must-hold.
    """
    script = ("trap 'echo entry=$?; false; exit' USR1\n"
              "kill -USR1 $$\n"
              "sleep 0.2\n"
              "exit 3\n")
    psh = _run(run_psh, "psh", mode, script, tmp_path)
    bash = _run(run_bash, "oracle", mode, script, tmp_path)
    assert is_comparable(psh) and is_comparable(bash)
    assert bash.stdout == "entry=0\n"
    assert bash.returncode == 0       # bash 5.3: ENTRY status, not current $?
    assert psh.stdout == "entry=0\n"
    assert psh.returncode == 1        # psh today: current $?; slot 2.1 -> 0
