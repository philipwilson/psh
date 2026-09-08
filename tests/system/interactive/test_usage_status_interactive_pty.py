"""INTERACTIVE (real PTY) disposition of the usage-error status family (2.3).

Two of the family's cells behave DIFFERENTLY at a terminal from the way they
behave in a script, and neither difference is visible from the non-interactive
matrix -- so they are pinned here, against a real ``bash -i``:

* the bad-count cell (``break abc`` / ``continue abc``) does NOT exit an
  interactive shell.  It drops the REST OF THE LINE and the next prompt sees
  ``$?`` = 2.  Checking only ``$?`` is not enough and was the round-1 miss:
  psh reported 2 for the status while still RUNNING the loop body, which the
  dropped-line assertion below catches.
* the operand cell (``exit 99999999999999999999``) must leave the REPL ALIVE.
  Before ``psh/builtins/numeric.py#legal_number`` existed, Python's ``int()``
  accepted the operand and the interactive shell EXITED on it -- a REPL that
  dies on a typo.  That is the guard rail this module exists for.

Every row is a PARITY row: bash and psh must produce the SAME answer, so the
pin goes red if either side moves.  Values probed against bash 5.3.15 on
2026-09-07 (empirical: the family's statuses have no CHANGES/NEWS item).

Ledger rows: W0-N10 (bad count), W0-N30 (rejected operands).
"""

import os
import re
import sys
from pathlib import Path

import pytest

pexpect = pytest.importorskip("pexpect")

# The blessed bash oracle is resolved through the ONE resolver
# (tests/harness/shell_oracle.py#resolve_bash), never a hardcoded path.
from shell_oracle import resolve_bash  # noqa: E402

# Module scope on purpose: a missing oracle must be LOUD at import, not a
# silent per-test skip that reports green while the comparison never runs.
_ORACLE = resolve_bash()

PSH_ROOT = str(Path(__file__).resolve().parents[3])

# Drives real terminals and reaps real children; never run under xdist.
pytestmark = pytest.mark.serial

_SENTINEL = "ALIVE_SENTINEL"

# (label, line, expected MARK value, expected $? on the NEXT line)
# MARK is None when the shell must DROP the rest of the line before reaching
# the echo that would print it -- the assertion that separates "dropped the
# line" from "kept running with the right status".
#
# EVERY marker is written so that only EXECUTION can produce a digit: the
# terminal echoes the typed line verbatim, so a literal `MARK=body` would
# appear in the transcript whether or not the shell ran it. `$((10+1))` and
# `$?` are echoed unexpanded and match nothing.
_ROWS = [
    ("break_bad_count",
     'for i in 1; do break abc; echo MARK=$((10+1)); done; echo MARK=$((20+2))',
     None, "2"),
    ("continue_bad_count",
     'for i in 1; do continue abc; echo MARK=$((10+1)); done; echo MARK=$((20+2))',
     None, "2"),
    # Control: the discard cell already behaved this way interactively, and
    # the bad-count cell now routes into it.
    ("too_many_arguments_discard",
     'exit 1 2; echo MARK=$((30+3))', None, "2"),
    # The operand cell CONTINUES on the same line, so its MARK does print.
    ("operand_rejected_by_legal_number",
     'exit 99999999999999999999; echo MARK=$?', "2", "0"),
    ("operand_non_numeric",
     'exit abc; echo MARK=$?', "2", "0"),
]

_DIAGNOSTIC = r"numeric argument required|too many arguments"


def _env():
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp", "TERM": "xterm",
        "PS1": "P1> ", "PS2": "P2> ",
        "PYTHONUNBUFFERED": "1", "PYTHONPATH": PSH_ROOT,
    }


def _spawn_psh():
    child = pexpect.spawn(
        sys.executable,
        ["-u", "-m", "psh", "--norc", "--force-interactive"],
        timeout=15, encoding="utf-8", env=_env())
    child.send("\r")
    child.expect("P1> ")
    return child


def _spawn_bash():
    child = pexpect.spawn(_ORACLE.path, ["--norc", "-i"], timeout=15,
                          encoding="utf-8", env=_env())
    child.expect("P1> ")
    return child


def _drive(child, line):
    """Send the row's line, then `echo AFTER=$?`, then a sentinel.

    Detection is by the SENTINEL rather than by prompt matching: line editors
    redraw the prompt with cursor-control escapes, which makes prompt matching
    race-prone, while the sentinel appears only when the shell actually ran
    the follow-up.  Its SECOND appearance proves execution (the first is the
    terminal echoing the typed line).
    """
    child.send(line + "\r")
    child.send("echo AFTER=$?\r")
    child.send(f"echo {_SENTINEL}\r")
    try:
        child.expect(_SENTINEL, timeout=10)
        transcript = child.before
        alive = child.expect([_SENTINEL, pexpect.TIMEOUT], timeout=10) == 0
    except pexpect.TIMEOUT:
        return ("<TIMEOUT>" + (child.before or ""), False)
    except pexpect.EOF:
        # The shell DIED on the line -- the W0-N30 failure mode.
        return ("<EOF>" + (child.before or ""), False)
    return (transcript, alive)


def _mark(transcript):
    # Only a DIGIT run counts: the terminal's echo of the typed line carries
    # the unexpanded `$((10+1))` / `$?`, so a hit here means the echo actually
    # ran.
    hits = re.findall(r"MARK=(\d+)", transcript)
    return hits[-1] if hits else None


def _after(transcript):
    hits = re.findall(r"AFTER=(\d+)", transcript)
    return hits[-1] if hits else None


@pytest.mark.parametrize("label,line,mark,after", _ROWS,
                         ids=[r[0] for r in _ROWS])
def test_interactive_usage_status_matches_bash(label, line, mark, after):
    bash_child = _spawn_bash()
    try:
        b_transcript, b_alive = _drive(bash_child, line)
    finally:
        bash_child.close(force=True)

    psh_child = _spawn_psh()
    try:
        p_transcript, p_alive = _drive(psh_child, line)
    finally:
        psh_child.close(force=True)

    # THE GUARD RAIL, asserted first and for both shells: the REPL survives.
    # `exit 99999999999999999999` used to kill psh's REPL outright.
    assert b_alive, (label, b_transcript[-400:])
    assert p_alive, (label, p_transcript[-400:])
    assert "Traceback (most recent call last)" not in p_transcript, \
        p_transcript[-400:]

    # Every row's error IS reported -- silence would be its own divergence.
    assert re.search(_DIAGNOSTIC, b_transcript), (label, b_transcript[-400:])
    assert re.search(_DIAGNOSTIC, p_transcript), (label, p_transcript[-400:])

    # Did the rest of the LINE run? (mark is None when it must be dropped.)
    assert _mark(b_transcript) == mark, (label, b_transcript[-400:])
    assert _mark(p_transcript) == mark, (label, p_transcript[-400:])

    # ... and what does the NEXT line see?
    assert _after(b_transcript) == after, (label, b_transcript[-400:])
    assert _after(p_transcript) == after, (label, p_transcript[-400:])
