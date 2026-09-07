"""Trap exit-status precedence, pinned cell by cell against bash 5.3.15.

Slot 4A.2's charter clause is "specify exit-status precedence".  The spec is
this table: it lives in the tree so it survives the merge and ratchets, rather
than in a probe transcript that dies with the worktree.

THE RULE (bash 5.3; CHANGES 5.3-beta section 3 item q, line 277; NEWS item uu,
line 141; POSIX interp 1602): "If `exit' is run in a trap and not supplied an
exit status argument, it uses the value of $? from before the trap only if
it's run at the trap's `top level' and would cause the trap to end (that is,
not in a subshell)."  A trap action's body therefore cannot change the shell's
exit status except through an explicit ``exit N``.

WHAT "TOP LEVEL" MEANS, probed on 5.3.15 in all three input modes: the
action's OWN command text, including its ``if`` / ``{ }`` / loop / ``case``
bodies, ``&&``/``||`` lists and ``eval``.  A bare ``exit`` inside a FUNCTION
BODY or a SOURCED FILE called from the action is NOT at top level and keeps
the CURRENT ``$?``.  The comparison is against the depths at trap ENTRY, so a
trap entered while already inside a function has a top level of its own.  Trap
kinds: EXIT, signal, ERR and RETURN all record an entry status; DEBUG does not.
The EXIT trap is the one exception to the top-level restriction -- its bare
``exit`` resolves to the entry status even inside a called function or a
sourced file.

"NOT IN A SUBSHELL" is the item's other half, and it turns on the forked unit's
SHAPE, not on the fork.  Probed on 5.3.15: a forked COMPOUND -- a pipeline
member ``{ }``/``if``/loop/``case``, a backgrounded ``{ } &`` -- keeps the
CURRENT ``$?``, while a forked SIMPLE command keeps the ENTRY status
(``exit &``, ``false | exit``, ``eval "true; exit" &``).  Both halves are
pinned below, so a fix for one cannot silently over-correct the other.

BARE ``return`` FOLLOWS THE SAME RULE (bash 5.3 CHANGES 5.3-alpha section item
y, line 370: "Change for POSIX interpretation 1602 about the default return
status for `return' in a trap command").  ``ReturnBuiltin`` asks the same owner
query as ``ExitBuiltin``; the ``ret-`` cells below pin it.

WHY EVERY CELL IS COMPOSED.  The slot's first battery pinned bare ``exit``
with two cells (``trap 'exit' EXIT; exit 3`` and ``trap 'exit' EXIT; false``)
in which NOTHING inside the trap changed ``$?`` before the bare exit.  Those
cells are VACUOUS for this rule: "pre-trap status" and "current ``$?``"
predict the same answer, so they could not have failed for the reason they
were written, and they certified agreement while psh diverged (D-3.4 lesson
8).  Every row below is therefore labelled: ``disc-`` rows change ``$?`` in
the body before the bare exit and so can tell the two rules apart;
``control-`` rows cannot, and are kept precisely so the distinction stays
visible to the next reader; ``boundary-`` rows sit just outside "top level"
and pin the rule's width; ``guard-`` rows are must-holds.

HISTORY.  Under the 5.2 series the saved-status rule was EXIT-trap-SPECIFIC,
and psh implemented exactly that.  bash 5.3 widened it, and Wave 0.3 pinned the
widened cells BOTH SIDES as declared divergences.  Slot 2.1 made psh follow --
one stacked owner,
``psh/core/trap_manager.py#TrapManager.bare_status_entry_value`` -- and flipped
every one of those rows into an equality cell of ``ENTRY_STATUS_CELLS`` below.
Gate-triage rows G32-G35 (FLIP-PINS slot 2.1).

Reproduce one cell by hand (oracle = the resolved bash 5.3.15)::

    /opt/homebrew/bin/bash -c "trap 'echo entry=\\$?; false; exit' USR1
    kill -USR1 \\$\\$; sleep 0.2; exit 3"; echo rc=$?      # entry=0 / rc=0
    python -m psh -c "<same>"; echo rc=$?                  # entry=0 / rc=0
"""
import pytest
from shell_oracle import is_comparable, run_bash, run_psh

#: Tail that makes the trap ENTRY status 5 while the action's own
#: ``$?`` is 0 -- the two rules then predict different answers.
K5 = "(kill -USR1 $$; exit 5)\nsleep 0.2\nexit 3"

#: (id, script, discriminating) -- rows that hold on any supported bash: the
#: EXIT-trap rule, the boundaries where a bare exit keeps the current ``$?``
#: (untouched by bash 5.3), and the explicit-operand guards.
CELLS = [
    # -- controls: cannot discriminate; kept labelled so they are not re-read
    #    as evidence for the bare-exit rule ---------------------------------
    ("control-bare-exit-after-exit3", "trap 'exit' EXIT; exit 3", False),
    ("control-bare-exit-after-false", "trap 'exit' EXIT; false", False),
    # The trap body's status alone never leaked: psh already had this right.
    ("control-body-status-not-leaked", "trap 'false' EXIT; exit 3", False),
    # An explicit operand overrides, and must keep overriding (must-hold).
    ("guard-explicit-operand-wins", "trap 'false; exit 7' EXIT; exit 3", False),
    ("guard-signal-trap-explicit-operand-wins",
     "trap 'true; exit 7' USR1\nkill -USR1 $$\nsleep 0.2\nexit 3", False),
    ("guard-err-trap-explicit-operand-wins",
     "trap 'true; exit 7' ERR\n(exit 9)\necho nr", False),
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
    # the trap action, so the same rule applies: bash 5.3 keeps EXIT
    # unconditional, so the interp-1602 top-level boundary does NOT apply to
    # the EXIT trap -- probed 5.3.15, rc 3 in both shells.
    ("disc-bare-exit-in-called-function",
     "f() { false; exit; }; trap f EXIT; exit 3", True),
    # ... and the same inside a file SOURCED from the EXIT action: rc 3.
    ("disc-bare-exit-in-sourced-file-from-exit-trap",
     "printf 'false; exit\\n' > s_exit.sh\ntrap '. ./s_exit.sh' EXIT\nexit 3",
     True),
    # errexit: `false` in the body aborts before the bare exit is reached, so
    # both shells report 1. Kept because it looks discriminating and is not.
    ("disc-errexit-aborts-before-bare-exit",
     "set -e; trap 'false; exit' EXIT; exit 3", True),
    # -- BOUNDARY, parity half: a bare exit that is NOT at the action's top
    #    level resolves from the CURRENT $? -- the half bash 5.3 did NOT
    #    move, so these held before the slot 2.1 flip and after it ----------
    # Function body called from a SIGNAL trap: rc 1 (current $?, from false).
    ("boundary-signal-trap-function-body-uses-current-status",
     "f() { false; exit; }\ntrap f USR1\nkill -USR1 $$\nsleep 0.2\nexit 3",
     True),
    # `eval` INSIDE that function body is still inside the function: rc 1.
    ("boundary-signal-trap-eval-in-function-body-uses-current-status",
     "f() { eval \"false; exit\"; }\ntrap f USR1\nkill -USR1 $$\nsleep 0.2\n"
     "exit 3",
     True),
    # Sourced file run from a SIGNAL trap: rc 1 (current $?).
    ("boundary-signal-trap-sourced-file-uses-current-status",
     "printf 'false; exit\\n' > s_dot.sh\ntrap '. ./s_dot.sh' USR1\n"
     "kill -USR1 $$\nsleep 0.2\nexit 3",
     True),
    # Function body called from an ERR trap: rc 0 (current $?, from true),
    # not the entry status 9.
    ("boundary-err-trap-function-body-uses-current-status",
     "f() { true; exit; }\ntrap f ERR\n(exit 9)\necho nr", True),
    # Sourced file run from an ERR trap: rc 0, not the entry status 9.
    ("boundary-err-trap-sourced-file-uses-current-status",
     "printf 'true; exit\\n' > s_err.sh\ntrap '. ./s_err.sh' ERR\n(exit 9)\n"
     "echo nr",
     True),
    # A SUBSHELL inside the action is the "not in a subshell" half of interp
    # 1602: its bare exit ends the subshell with the current $? (b=1), and
    # the action carries on to its own top-level bare exit.
    ("boundary-signal-trap-subshell-inside-action-uses-current-status",
     "trap 'echo a; (false; exit); echo b=$?; exit' USR1\nkill -USR1 $$\n"
     "sleep 0.2\nexit 3",
     True),
    ("boundary-exit-trap-subshell-inside-action-uses-current-status",
     "trap 'echo a; (false; exit); echo b=$?; exit' EXIT\nexit 3", True),
    # DEBUG keeps the current $? -- interp 1602 does not cover DEBUG.
    ("boundary-debug-trap-uses-current-status",
     "trap 'false; exit' DEBUG\ntrue", True),
    # ... and the entry status is VISIBLE there (d=4) yet still loses to the
    # current $? (0 from true), so the cell discriminates the two rules.
    ("boundary-debug-trap-entry-status-is-visible-but-loses",
     "trap 'echo d=$?; true; exit' DEBUG\n(exit 4)\ntrue", True),
    # -- BOUNDARY, "not in a subshell": a forked COMPOUND child of the action
    #    keeps the CURRENT $?.  The EXIT-trap spellings held before the slot
    #    2.1 flip and after it, so they need no 5.3 oracle. -----------------
    ("boundary-exit-trap-bg-brace-group-uses-current-status",
     "trap '{ true; exit; } & wait $!; echo c=$?; exit' EXIT\nexit 3", True),
    ("boundary-exit-trap-pipeline-brace-member-uses-current-status",
     "trap 'false | { true; exit; }; echo after=$?; exit' EXIT\nexit 3", True),
    # -- CONTROL against over-correcting that boundary: a forked SIMPLE
    #    command KEEPS the entry status in bash, so a fix that drops the
    #    frames on every fork fails here. ----------------------------------
    ("control-exit-trap-bg-simple-command-keeps-entry-status",
     "trap 'true; exit & wait $!; echo c=$?; exit' EXIT\nexit 3", True),
    ("control-exit-trap-pipeline-simple-member-keeps-entry-status",
     "trap 'true; false | exit; echo after=$?; exit' EXIT\nexit 3", True),
]

#: (id, script, discriminating) -- rows that need bash 5.3's WIDENED rule
#: (NEWS uu / CHANGES 5.3-beta 3.q, POSIX interp 1602).  Wave 0.3 pinned the
#: first five BOTH SIDES as declared divergences; slot 2.1 flipped them here.
ENTRY_STATUS_CELLS = [
    # -- the five flipped Wave 0.3 divergence rows, cell ids unchanged -----
    # The SIGNAL-trap counterpart of disc-false-then-bare-exit: the bare exit
    # resolves from the ENTRY status (0, the kill succeeded), not the current
    # $? (1, from false). The trap prints its entry status so the cell is
    # self-evidently discriminating.
    ("disc-signal-trap-uses-entry-status",
     "trap 'echo entry=$?; false; exit' USR1\nkill -USR1 $$\nsleep 0.2\n"
     "exit 3",
     True),
    # The signal arrives while the parent waits for a foreground SUBSHELL, so
    # the action runs after `(...; exit 5)` completes and its ENTRY status is
    # 5; the bare exit yields 5, not the action's current $? (0 from true).
    ("disc-signal-trap-entered-after-subshell-uses-entry-status",
     "trap 'true; exit' USR1\n(kill -USR1 $$; exit 5)\nsleep 0.2\nexit 3",
     True),
    # An `if` body inside the action IS the action's top level: entry 0.
    ("disc-signal-trap-if-body-is-top-level",
     "trap 'if true; then false; exit; fi' USR1\nkill -USR1 $$\nsleep 0.2\n"
     "exit 3",
     True),
    # `eval` inside the action is still the action's top level: entry 0.
    ("disc-signal-trap-eval-is-top-level",
     "trap 'eval \"false; exit\"' USR1\nkill -USR1 $$\nsleep 0.2\nexit 3",
     True),
    # ERR is covered too: entry status 1 (from the failing `false`) wins over
    # the brace group's current $? 0 (from true).
    ("disc-err-trap-brace-group-is-top-level",
     "trap '{ true; exit; }' ERR\nfalse\necho nr", True),
    # -- the rest of the widened rule --------------------------------------
    # Loop and `case` bodies are the action's top level too: entry 0.
    ("disc-signal-trap-loop-body-is-top-level",
     "trap 'for i in 1; do false; exit; done' USR1\nkill -USR1 $$\n"
     "sleep 0.2\nexit 3",
     True),
    ("disc-signal-trap-case-body-is-top-level",
     "trap 'case a in a) false; exit;; esac' USR1\nkill -USR1 $$\nsleep 0.2\n"
     "exit 3",
     True),
    # An `||` list is one command list, not a nested scope: entry 0.
    ("disc-signal-trap-and-or-list-is-top-level",
     "trap 'false || exit' USR1\nkill -USR1 $$\nsleep 0.2\nexit 3", True),
    # Back AT the top level after a called function returns: entry 0, even
    # though the function left $? at 1. The boundary is the frame the bare
    # exit sits in, not "the action called a function at some point".
    ("disc-signal-trap-top-level-after-a-function-returns",
     "f() { false; }\ntrap 'f; exit' USR1\nkill -USR1 $$\nsleep 0.2\nexit 3",
     True),
    # Same for a sourced file that has finished: entry 0.
    ("disc-signal-trap-top-level-after-a-source-returns",
     "printf 'false\\n' > s_ret.sh\ntrap '. ./s_ret.sh; exit' USR1\n"
     "kill -USR1 $$\nsleep 0.2\nexit 3",
     True),
    # The trap is ENTERED inside a function, so its top level is that same
    # function depth -- the comparison is relative to entry, never to zero.
    ("disc-signal-trap-entered-inside-a-function-has-its-own-top-level",
     "g() { kill -USR1 $$; sleep 0.2; }\ntrap 'false; exit' USR1\ng\nexit 3",
     True),
    # NESTED actions: a signal trap firing DURING the EXIT action takes the
    # SIGNAL rule (its own entry status 0), not the EXIT action's 3.
    ("disc-signal-trap-nested-in-exit-action-takes-the-signal-entry-status",
     "trap 'echo E-entry=$?; kill -USR1 $$; sleep 0.2; echo E-after=$?; "
     "exit' EXIT\ntrap 'echo S-entry=$?; false; exit' USR1\nexit 3",
     True),
    # ERR at the action's plain top level, with a non-zero entry status.
    ("disc-err-trap-uses-entry-status",
     "trap 'true; exit' ERR\n(exit 9)\necho nr", True),
    ("disc-err-trap-eval-is-top-level",
     "trap 'eval \"true; exit\"' ERR\n(exit 9)\necho nr", True),
    # RETURN is covered as well (probed 5.3.15). It needs `set -T`, which is
    # how bash exposes a RETURN trap inside a function at all.
    ("disc-return-trap-uses-entry-status",
     "set -T\nf() { (exit 6); }\ntrap 'echo e=$?; true; exit' RETURN\nf\n"
     "echo nr",
     True),
    ("disc-return-trap-false-then-bare-exit",
     "set -T\nf() { return 4; }\ntrap 'false; exit' RETURN\nf\necho nr",
     True),
    # -- "not in a subshell", signal/ERR/RETURN half.  Entry status is 5 and
    #    the forked child's own $? is 0, so the two rules disagree. --------
    ("boundary-signal-trap-bg-brace-group-uses-current-status",
     "trap '{ true; exit; } & wait $!; echo c=$?; exit' USR1\n" + K5, True),
    ("boundary-signal-trap-pipeline-brace-member-uses-current-status",
     "trap 'false | { true; exit; }; echo after=$?; exit' USR1\n" + K5, True),
    ("boundary-signal-trap-pipeline-if-member-uses-current-status",
     "trap 'false | if true; then exit; fi; echo after=$?; exit' USR1\n" + K5,
     True),
    ("boundary-signal-trap-pipeline-loop-member-uses-current-status",
     "trap 'false | for i in 1; do true; exit; done; echo after=$?; exit'"
     " USR1\n" + K5, True),
    ("boundary-signal-trap-pipeline-brace-in-eval-uses-current-status",
     "trap 'eval \"false | { true; exit; }\"; echo after=$?; exit' USR1\n"
     + K5, True),
    ("boundary-signal-trap-pipefail-brace-first-member-uses-current-status",
     "set -o pipefail\ntrap '{ true; exit; } | cat; echo after=$?; exit'"
     " USR1\n" + K5, True),
    ("boundary-err-trap-pipeline-brace-member-uses-current-status",
     "trap 'true | { true; exit; }; echo after=$?; exit' ERR\n(exit 9)\n"
     "echo nr", True),
    ("boundary-return-trap-pipeline-brace-member-uses-current-status",
     "set -T\nf() { (exit 6); }\ntrap 'true | { true; exit; }; "
     "echo after=$?; exit' RETURN\nf\necho nr", True),
    # -- CONTROLS against over-correcting: a forked SIMPLE command keeps the
    #    ENTRY status (5), and so does a backgrounded `eval`. --------------
    ("control-signal-trap-bg-simple-command-keeps-entry-status",
     "trap 'true; exit & wait $!; echo c=$?; exit' USR1\n" + K5, True),
    ("control-signal-trap-pipeline-simple-member-keeps-entry-status",
     "trap 'true; false | exit; echo after=$?; exit' USR1\n" + K5, True),
    ("control-signal-trap-bg-eval-builtin-keeps-entry-status",
     "trap 'eval \"true; exit\" & wait $!; echo c=$?; exit' USR1\n" + K5,
     True),
    # -- BARE `return` takes the entry status too (CHANGES 5.3-alpha item y).
    ("disc-return-builtin-uses-entry-status",
     "f() { kill -USR1 $$; sleep 0.2; echo in-f; }\n"
     "trap 'false; return' USR1\nf\necho after=$?\nexit 3", True),
    ("disc-return-builtin-entry-status-from-subshell",
     "f() { (kill -USR1 $$; exit 5); sleep 0.2; echo in-f; }\n"
     "trap 'true; return' USR1\nf\necho after=$?\nexit 3", True),
    ("disc-return-builtin-in-err-action-inside-function",
     "set -E\nf() { (exit 9); echo f-after; }\ntrap 'true; return' ERR\nf\n"
     "echo after=$?\nexit 3", True),
    ("boundary-return-builtin-in-called-function-uses-current-status",
     "f() { kill -USR1 $$; sleep 0.2; echo in-f; }\ng() { false; return; }\n"
     "trap 'g; echo g=$?; false; return' USR1\nf\necho after=$?\nexit 3",
     True),
    ("boundary-return-builtin-in-sourced-file-uses-current-status",
     "printf 'false; return\\n' > r_dot.sh\n"
     "f() { kill -USR1 $$; sleep 0.2; echo in-f; }\n"
     "trap '. ./r_dot.sh; echo s=$?; false; return' USR1\nf\n"
     "echo after=$?\nexit 3", True),
    ("guard-return-builtin-explicit-operand-wins",
     "f() { kill -USR1 $$; sleep 0.2; echo in-f; }\n"
     "trap 'true; return 7' USR1\nf\necho after=$?\nexit 3", True),
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


def _assert_parity(cell_id, script, discriminating, mode, tmp_path):
    """Both shells agree on stdout AND exit status for one cell x mode."""
    psh = _run(run_psh, "psh", mode, script, tmp_path)
    bash = _run(run_bash, "oracle", mode, script, tmp_path)
    assert is_comparable(psh), psh
    assert is_comparable(bash), bash
    assert (psh.stdout, psh.returncode) == (bash.stdout, bash.returncode), (
        f"{cell_id} [{mode}] "
        f"{'DISCRIMINATING' if discriminating else 'control'}\n"
        f"  script: {script!r}\n"
        f"  bash: {bash.stdout!r} rc={bash.returncode}\n"
        f"  psh:  {psh.stdout!r} rc={psh.returncode}")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("cell_id,script,discriminating",
                         [pytest.param(*c, id=c[0]) for c in CELLS])
def test_exit_trap_status_matches_bash(cell_id, script, discriminating, mode,
                                       tmp_path):
    """psh and bash agree on stdout AND exit status for every cell x mode."""
    _assert_parity(cell_id, script, discriminating, mode, tmp_path)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("cell_id,script,discriminating",
                         [pytest.param(*c, id=c[0])
                          for c in ENTRY_STATUS_CELLS])
@pytest.mark.oracle_min("5.3")
def test_trap_entry_status_matches_bash(cell_id, script, discriminating, mode,
                                        tmp_path):
    """The bash 5.3 WIDENED rule, cell by cell (gate rows G32-G35, slot 2.1).

    A bare ``exit`` at the top level of a signal, ERR or RETURN action -- not
    only an EXIT action -- resolves to the status at trap ENTRY (CHANGES
    5.3-beta section 3 item q line 277; NEWS item uu line 141; POSIX interp
    1602).  Needs the 5.3 oracle: the 5.2 series answers with the current ``$?``
    for every one of these cells, which is what Wave 0.3 pinned as psh's
    declared divergence before this slot flipped it.
    """
    _assert_parity(cell_id, script, discriminating, mode, tmp_path)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.oracle_min("5.3")
def test_bare_exit_in_a_signal_trap_uses_entry_status(mode, tmp_path):
    """MUST-HOLD, rewritten for bash 5.3 (slot 4A.2 ruling R4 is superseded).

    Under the 5.2 series the saved-status rule was EXIT-trap-SPECIFIC and this
    must-hold guarded against generalizing psh's mechanism.  bash 5.3 (NEWS
    item uu, POSIX interp 1602) generalized the rule itself, and slot 2.1 made
    psh follow.  The trap prints its entry status to make the cell
    self-evidently discriminating: entry is 0 (the ``kill`` succeeded) while
    the current status is 1 (from ``false``), so the two rules predict
    different answers -- both shells now choose the entry status, rc 0.
    Closes gate-triage rows G32-G35 (FLIP-PINS slot 2.1).
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
    assert psh.stdout == bash.stdout
    assert psh.returncode == bash.returncode
