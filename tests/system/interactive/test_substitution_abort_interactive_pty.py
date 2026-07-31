"""INTERACTIVE (real PTY) disposition of the substitution abort (slot 2.4, R6-C).

Slot 2.4 closed the substitution-origin fatality for SCRIPT-MODE frames (`-c`,
a script file, stdin, and the `eval`/`source` frames inside them). Interactive
shells were deliberately left alone: bash's own REPL does not abort the session
on these errors, so psh gates the consumer on `state.is_script_mode`
(`psh/scripting/source_processor.py#SourceProcessor._substitution_syntax_abort`).

What that gate leaves behind is pinned here, at a REAL PTY, because these are
PTY facts: a shell reading from a terminal is a different `is_script_mode`
world from `-i -c`, and the round-5 claim that PTY coverage "falls out of" the
non-interactive matrix was FALSE — the interactive fork rows answer differently
from both bash and psh's own non-interactive answer.

THE INVARIANT THAT MATTERS MOST is the guard rail: whatever the status, the
REPL SURVIVES every row and never shows a traceback. A REPL that dies on
`echo $(if)` is the failure this whole area is fenced against.

THE DECLARED DIVERGENCE, and why it is not a bug in the gate: the gate is
PER-SHELL, and a forked child of an interactive shell inherits
`is_script_mode` False (`psh/shell.py#Shell.for_subshell`), so the consumer
does not fire in the CHILD either and the child keeps psh's legacy status 2
where bash's child reports 1. Closing that means giving the child of an
interactive shell a script-mode-like disposition, which is an interactive
semantics change — out of HIGH-9's charter (successor row).

Measured identically at base 1b271d77 and at the slot tip, both parsers
(`tmp/r24-probes/r6c_pty.py` -> `r6c-pty-*.txt`): the slot moved NOTHING here,
which is exactly what the charter required.
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

pytestmark = pytest.mark.serial

# (label, line, bash answer, psh answer) — the answer is the value of the
# SENTINEL variable the line echoes, or None when the shell discards the whole
# line and never reaches the echo. Both shells' values are asserted, so an
# improvement on either side fails this pin instead of passing unnoticed.
_ROWS = [
    # The fork FAMILY: an abort inside a forked child of an INTERACTIVE shell.
    # bash reports the child's contained status; psh's child, being interactive
    # -family too, keeps the legacy 2.
    ("fork_errexit_suppressed",
     "( set -e; eval 'echo $(if)' ) || echo SUPPRC=$?", "1", "2"),
    ("fork_no_errexit",
     "( eval 'echo $(if)' ) || echo SUPPRC=$?", "1", "2"),
    # EQUALITY: with errexit ACTIVE and unsuppressed, both give 2.
    ("fork_errexit_unsuppressed",
     "( set -e; eval 'echo $(if)' ); echo AFTERRC=$?", "2", "2"),
    # The eval frame in the interactive shell ITSELF (no fork): bash leaves 1,
    # psh leaves its ordinary syntax-error 2.
    ("eval_frame", "eval 'echo $(fi)'; echo AFTERRC=$?", "1", "2"),
    # EQUALITY guard rail: the direct shape discards the whole line in BOTH
    # shells — the trailing echo never runs — and both stay alive.
    ("direct_complete_but_invalid", "echo $(fi); echo AFTERRC=$?", None, None),
]

_SENTINEL = "ALIVE_SENTINEL"
_DIAGNOSTIC = r"syntax error|Parse error"


def _env():
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp", "TERM": "xterm",
        "PS1": "P1> ", "PS2": "P2> ",
        "PYTHONUNBUFFERED": "1", "PYTHONPATH": PSH_ROOT,
    }


def _spawn_psh(parser):
    child = pexpect.spawn(
        sys.executable,
        ["-u", "-m", "psh", "--norc", "--force-interactive",
         "--parser", parser],
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
    """Send one line, then a sentinel echo; return (transcript, alive).

    Detection is by the SENTINEL rather than by prompt matching — the line
    editors redraw the prompt with cursor-control escapes, which makes prompt
    matching race-prone, whereas the sentinel appears in the stream only when
    the shell actually executed the follow-up command. Its SECOND appearance is
    the one that proves execution (the first is the terminal echoing the line).
    """
    child.send(line + "\r")
    child.send(f"echo {_SENTINEL}\r")
    try:
        child.expect(_SENTINEL, timeout=10)
        transcript = child.before
        alive = child.expect([_SENTINEL, pexpect.TIMEOUT], timeout=10) == 0
    except pexpect.TIMEOUT:
        return ("<TIMEOUT>" + (child.before or ""), False)
    return (transcript, alive)


def _answer(transcript):
    m = re.search(r"(?:SUPPRC|AFTERRC)=(\d+)", transcript)
    return m.group(1) if m else None


@pytest.mark.parametrize("label,line,bash_answer,psh_answer", _ROWS,
                         ids=[r[0] for r in _ROWS])
@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_interactive_substitution_abort_disposition(label, line, bash_answer,
                                                    psh_answer, parser):
    bash_child = _spawn_bash()
    try:
        b_transcript, b_alive = _drive(bash_child, line)
    finally:
        bash_child.close(force=True)

    psh_child = _spawn_psh(parser)
    try:
        p_transcript, p_alive = _drive(psh_child, line)
    finally:
        psh_child.close(force=True)

    # THE GUARD RAIL, asserted first and for both shells: the REPL survives.
    assert b_alive, (label, b_transcript[-400:])
    assert p_alive, (label, parser, p_transcript[-400:])
    assert "Traceback (most recent call last)" not in p_transcript, \
        p_transcript[-400:]

    # Every row's error IS reported — silence would be its own divergence.
    assert re.search(_DIAGNOSTIC, b_transcript), (label, b_transcript[-400:])
    assert re.search(_DIAGNOSTIC, p_transcript), (label, parser,
                                                  p_transcript[-400:])

    assert _answer(b_transcript) == bash_answer, (label, b_transcript[-400:])
    assert _answer(p_transcript) == psh_answer, (label, parser,
                                                 p_transcript[-400:])
