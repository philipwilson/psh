"""INTERACTIVE (real PTY) heredoc-vs-not detection (slot 2.5, #22 MEDIUM-3).

WHY THIS IS A PTY MODULE AND NOT A `-c` TEST. The defect is LATENT everywhere
except a terminal. Fed `echo \\<<EOF`, the session's completeness oracle used a
second, REGEX heredoc grammar that read the escaped `<` as opening a heredoc on
`EOF`; the real lexer sees an escaped `<` plus an ordinary input redirection,
and so does bash. Non-interactively the flush path re-lexes and the wrong answer
never surfaces -- measured at base e36116c3 across `-c`, script-file and stdin,
both parsers: 66/66 rows identical to bash. So a `-c` pin would have been GREEN
ON BASE and would have proven nothing. Only at a terminal does the session's
answer become observable: psh dropped to PS2 and swallowed the following line as
a phantom here-document body.

THE OBSERVABLE, and why line 2 is spelled oddly: each case sends its shape line
then `echo MARK""ER`. A terminal ECHOES the typed bytes, so a literal
`echo MARKER` would put "MARKER" in the transcript even when nothing ran.
Quote-splitting the word makes the typed echo (`MARK""ER`) and the executed
output (`MARKER`) textually distinct, so `marker_ran` means the shell really
executed the follow-up -- i.e. it considered the shape line COMPLETE.

AXES (ruling R1-E). The corpus varies: SPELLING (escaped `\\<<`, escaped second
`<\\<`, escaped-escape `\\\\<<`), QUOTING (`'<<EOF'`, `"<<EOF"`, `<<'EOF'`),
OPERATOR ADJACENCY (`<<<`, `<<-`, digit-prefixed `0<<`, arithmetic `$((1<<2))`),
NESTING (`<<` inside an unclosed `$(`, and the defect's own spelling inside a
closed `$( )`), and OPTION STATE (`set -o posix` on the divergent spelling plus
two true-heredoc controls). Every row asserts BOTH shells, so an improvement on
either side fails this pin instead of passing unnoticed.

FOR A NIGHTLY READER (Linux): the bash-side expectations were measured against
bash 5.2.26 on macOS. Nothing here is platform-specific (no signals, no
/dev/fd, no locale collation), but a failure showing a DIFFERENT bash answer is
a bash-VERSION difference, not a psh regression -- check the oracle's version
first. This module resolves its oracle AT IMPORT and raises if bash is absent;
that loudness is deliberate and must not be converted into a skip to make a
nightly green.
"""

import os
import sys
from pathlib import Path

import pytest

pexpect = pytest.importorskip("pexpect")

# The blessed bash oracle, through the ONE resolver — never a hardcoded path.
from shell_oracle import resolve_bash  # noqa: E402

# Module scope on purpose: a missing oracle must be LOUD at import, not a
# silent per-test skip that reports green while the comparison never runs.
_ORACLE = resolve_bash()

PSH_ROOT = str(Path(__file__).resolve().parents[3])

pytestmark = pytest.mark.serial

# (id, lines to send before `echo MARK""ER`, line-1-is-COMPLETE)
# `complete=True`  -> the shell runs the follow-up: marker_ran, no PS2.
# `complete=False` -> the shell waits for a here-document body: PS2, no marker.
_ROWS = [
    # THE DEFECT: `\<` is an escaped literal '<'; what is left is `<EOF`, an
    # ordinary input redirection, so the line is COMPLETE.
    ("escaped_lt", [r"echo \<<EOF"], True),
    # The escaped SECOND '<': `<` redirect whose target word unquotes to `<EOF`.
    ("escaped_second_lt", [r"echo <\<EOF"], True),
    # An escaped BACKSLASH followed by a REAL heredoc — must stay incomplete.
    ("double_backslash", ["echo \\\\<<EOF"], False),
    # QUOTING: text, not an operator.
    ("single_quoted", ["echo '<<EOF'"], True),
    ("double_quoted", ['echo "<<EOF"'], True),
    # OPERATOR ADJACENCY.
    ("here_string", ["cat <<<EOF"], True),
    ("arith_shift", ["echo $((1<<2))"], True),
    # TRUE heredoc controls: these must REMAIN incomplete-detected. Without
    # them a fix that simply stopped detecting heredocs would pass.
    ("true_heredoc", ["cat <<EOF"], False),
    ("true_heredoc_strip", ["cat <<-EOF"], False),
    ("true_heredoc_fd", ["cat 0<<EOF"], False),
    ("true_heredoc_quoted", ["cat <<'EOF'"], False),
    # NESTING: a heredoc inside an unclosed substitution stays incomplete...
    ("nested_cmdsub_heredoc", ["echo $(cat <<EOF"], False),
    # ... and the defect's spelling one level down is complete.
    ("nested_cmdsub_escaped", [r"echo $(echo \<<EOF)"], True),
    # OPTION STATE: the divergent spelling and two controls under POSIX mode.
    ("posix_escaped_lt", ["set -o posix", r"echo \<<EOF"], True),
    ("posix_true_heredoc", ["set -o posix", "cat <<EOF"], False),
    ("posix_true_heredoc_strip", ["set -o posix", "cat <<-EOF"], False),
]


def _env():
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp", "TERM": "dumb",
        "PS1": "P1> ", "PS2": "P2> ",
        "PYTHONUNBUFFERED": "1", "PYTHONPATH": PSH_ROOT,
    }


def _spawn_psh(parser, cwd):
    child = pexpect.spawn(
        sys.executable,
        ["-u", "-m", "psh", "--norc", "--force-interactive",
         "--parser", parser],
        timeout=20, encoding="utf-8", env=_env(), cwd=cwd)
    child.send("\r")
    child.expect("P1> ")
    return child


def _spawn_bash(cwd):
    child = pexpect.spawn(_ORACLE.path, ["--norc", "-i"], timeout=20,
                          encoding="utf-8", env=_env(), cwd=cwd)
    child.expect("P1> ")
    return child


def _drive(child, lines):
    """Send the shape line(s) then the marker; report (outcome, transcript).

    RACES the two mutually exclusive observables rather than waiting out a
    timeout: a shell that considered the shape line COMPLETE runs the follow-up
    and MARKER appears; one that wants a here-document body prints PS2 and
    MARKER never comes. Whichever reaches the stream first decides, so an
    incomplete row costs a prompt round-trip instead of a full timeout — which
    is what keeps this module fast enough to run by default (a timeout-based
    version cost ~16s per incomplete row).
    """
    try:
        for line in lines:
            child.send(line + "\r")
        child.send('echo MARK""ER\r')
        index = child.expect(["MARKER", r"P2> ", pexpect.TIMEOUT], timeout=15)
        transcript = (child.before or "") + (child.after or ""
                                             if index < 2 else "")
    except pexpect.TIMEOUT:                                  # pragma: no cover
        return "timeout", "<TIMEOUT>" + (child.before or "")
    return {0: "complete", 1: "incomplete", 2: "timeout"}[index], transcript


@pytest.mark.parametrize("label,lines,complete", _ROWS,
                         ids=[r[0] for r in _ROWS])
@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_interactive_heredoc_detection_matches_bash(label, lines, complete,
                                                    parser, tmp_path):
    cwd = str(tmp_path)
    expected = "complete" if complete else "incomplete"

    bash_child = _spawn_bash(cwd)
    try:
        b_outcome, b_transcript = _drive(bash_child, lines)
    finally:
        bash_child.close(force=True)

    psh_child = _spawn_psh(parser, cwd)
    try:
        p_outcome, p_transcript = _drive(psh_child, lines)
    finally:
        psh_child.close(force=True)

    assert "Traceback (most recent call last)" not in p_transcript, \
        p_transcript[-400:]

    # BOTH shells are asserted against the declared expectation, so a bash
    # change is as loud as a psh change. `timeout` is a third, always-failing
    # outcome, so a hung shell can never read as agreement.
    # (The failure labels deliberately avoid a bare "bash" as the first tuple
    # element: the oracle-resolution ratchet reads `("bash", ...)` as an argv
    # head. Renaming the label is the honest fix; an allowlist entry for an
    # assertion message would have blunted a guard that is doing its job.)
    assert b_outcome == expected, ("bash-side", label, b_transcript[-400:])
    assert p_outcome == expected, ("psh-side", label, parser,
                                   p_transcript[-400:])
