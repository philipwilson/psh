"""INTERACTIVE (real PTY): a shell at a prompt ignores `set -n` (slot 1.10, C040).

The complement of the per-statement noexec gate. bash REFUSES to turn noexec on
in an interactive shell — `set -n`, `set -o noexec` and `shopt -so noexec` all
succeed silently and leave the option OFF — so the following commands still run,
`$-` never grows an `n`, and `set -o` still reports `noexec off`.

This is a PTY fact and cannot be measured any other way: `-i -c` and a piped
stdin are different `interactive` worlds from a shell reading a terminal, and
psh's REPL is exactly where the old per-input-unit check did its worst damage —
`set -n` at a psh prompt wedged the session permanently, because the `set +n`
that would undo it was skipped too.

Both shells are asserted on every row, so an improvement on the bash side fails
this pin rather than passing unnoticed. The command-line `-n` FLAG is the
control: bash honours it even for `bash -i` (invocation flags are parsed before
bash decides the shell is interactive), and so does psh.

The harness drives real terminals through pexpect and reads until a sentinel,
so nothing here depends on a bare sleep against a filling pty buffer (COMMON.md
N-8). No row sends a signal, so the SIGINT-disposition trap of N-7 does not
apply; the assertions are about option state and command execution only.
"""
import os
import re
import sys
from pathlib import Path

import pytest

pexpect = pytest.importorskip("pexpect")

# The blessed bash oracle is resolved through the ONE resolver, never a path.
from shell_oracle import resolve_bash  # noqa: E402

# Module scope on purpose: a missing oracle must be LOUD at import, not a
# silent per-test skip that reports green while the comparison never runs.
_ORACLE = resolve_bash()

PSH_ROOT = str(Path(__file__).resolve().parents[3])

pytestmark = pytest.mark.serial

_SENTINEL = "NOEXEC_SENTINEL"


def _env():
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp", "TERM": "dumb",
        "PS1": "P1> ", "PS2": "P2> ",
        "HISTFILE": "/dev/null",
        "PYTHONUNBUFFERED": "1", "PYTHONPATH": PSH_ROOT,
    }


def _spawn(argv, cwd, extra=()):
    child = pexpect.spawn(argv[0], [*argv[1:], *extra], timeout=20,
                          encoding="utf-8", env=_env(), cwd=str(cwd))
    child.send("\r")
    child.expect("P1> ")
    return child


def _spawn_shell(shell, cwd):
    """One spawn for both columns: the resolved oracle, or psh from this tree."""
    if shell == "oracle":
        return _spawn([_ORACLE.path, "--norc", "-i"], cwd)
    return _spawn([sys.executable, "-u", "-m", "psh", "--norc",
                   "--force-interactive"], cwd)


def _drive(child, lines):
    """Send each line, then a per-line sentinel echo; return the transcript.

    Reading to the sentinel after EVERY line keeps the pty drained: a bare
    sleep would let the shell block on a full buffer and every column of the
    matrix would become meaningless (COMMON.md N-8). The sentinel appears
    twice — once as the terminal's echo of the command, once when the shell
    actually runs it — and BOTH `before` segments are kept, because the
    command's own output lands between them.
    """
    transcript = []
    for index, line in enumerate(lines):
        marker = f"{_SENTINEL}{index}"
        child.send(line + "\r")
        child.send(f"echo {marker}\r")
        try:
            for _ in range(2):
                child.expect(marker, timeout=15)
                transcript.append(child.before or "")
        except pexpect.TIMEOUT:
            transcript.append("<TIMEOUT>" + (child.before or ""))
            break
    return "".join(transcript)


_LINES = [
    "set -n",
    "touch marker",
    "echo RAN_AFTER_SET_N",
    "set -o noexec",
    "shopt -so noexec",
    "echo dash=$-",
    "set -o | grep noexec",
    "echo TAIL",
]


@pytest.mark.parametrize("shell", ["oracle", "psh"])
def test_interactive_shell_ignores_noexec(shell, tmp_path):
    cwd = tmp_path / shell
    cwd.mkdir()
    child = _spawn_shell(shell, cwd)
    try:
        transcript = _drive(child, _LINES)
    finally:
        child.close(force=True)

    assert "<TIMEOUT>" not in transcript, transcript[-600:]
    # The commands after `set -n` RAN: the marker exists and the echo printed.
    assert (cwd / "marker").exists(), (
        f"{shell}: an interactive shell honoured noexec\n{transcript[-600:]}")
    assert "RAN_AFTER_SET_N" in transcript, transcript[-600:]
    assert "TAIL" in transcript, transcript[-600:]
    # The option never turned on, so both readouts stay honest.
    assert "noexec" in transcript and "off" in transcript, transcript[-600:]
    for line in transcript.splitlines():
        if line.strip().startswith("noexec"):
            assert "off" in line, f"{shell}: {line!r}"
    for line in transcript.splitlines():
        if "dash=" in line and "echo" not in line:
            flags = line.split("dash=", 1)[1].strip()
            assert "n" not in flags, f"{shell}: $- grew an n: {flags!r}"
    assert "Traceback (most recent call last)" not in transcript


# (id, line, what the row must show) — the SCOPE of the refusal, measured at a
# real prompt in both shells. It reaches every SYNCHRONOUS child of the session
# and is dropped by an asynchronous COMPOUND one; a backgrounded SIMPLE command
# keeps it, because bash forks those on a path that never leaves the session.
# Each line prints `R=[…]`; `expected` is that payload.
_SCOPE_ROWS = [
    # --- refused: the child is still in the session -----------------------
    ("cmdsub", 'x=$(set -n; echo hi); printf "R=[%s]\\n" "$x"', "hi"),
    ("backticks", 'x=`set -n; echo hi`; printf "R=[%s]\\n" "$x"', "hi"),
    ("cmdsub_in_subshell",
     '( x=$(set -n; echo deep); printf "R=[%s]\\n" "$x" )', "deep"),
    ("cmdsub_reports_option_off",
     'x=$(set -n; set -o | grep -c "noexec.*off"); printf "R=[%s]\\n" "$x"',
     "1"),
    ("sync_subshell",
     '( set -n; printf "R=[%s]\\n" SYNC )', "SYNC"),
    ("brace_group", '{ set -n; printf "R=[%s]\\n" BRACE; }', "BRACE"),
    ("pipeline_member",
     'echo x | { set -n; printf "R=[%s]\\n" MEMBER; }', "MEMBER"),
    ("process_substitution",
     'cat <(set -n; printf "R=[%s]\\n" PROCSUB)', "PROCSUB"),
    # A backgrounded SIMPLE command is NOT an async compound: bash keeps the
    # session for it, so the refusal still applies.
    ("async_function",
     'f() { set -n; printf "R=[%s]\\n" FN; }; f & wait', "FN"),
    ("async_eval",
     'eval "set -n; printf \'R=[%s]\\n\' EV" & wait', "EV"),
    # --- honoured: the child left the session ------------------------------
    ("async_subshell",
     '( set -n; printf "R=[%s]\\n" ASYNC ) & wait', None),
    ("async_brace_group",
     '{ set -n; printf "R=[%s]\\n" ASYNCBRACE; } & wait', None),
    ("async_pipeline",
     '{ set -n; printf "R=[%s]\\n" ASYNCPIPE; } | cat & wait', None),
    ("async_and_or",
     'true && { set -n; printf "R=[%s]\\n" ASYNCAO; } & wait', None),
    ("async_for_loop",
     'for i in 1; do set -n; printf "R=[%s]\\n" ASYNCFOR; done & wait', None),
    # The drop is INHERITED: the substitution inside an async subshell honours
    # noexec too, so `inner` never runs and the payload is empty. (The outer
    # printf is a statement of the SUBSHELL, whose own noexec was never set,
    # so it still prints — which is what makes the empty payload visible.)
    ("cmdsub_inside_async_subshell",
     '( x=$(set -n; echo inner); printf "R=[%s]\\n" "$x" ) & wait', ""),
]


@pytest.mark.parametrize("case_id,line,expected", _SCOPE_ROWS,
                         ids=[r[0] for r in _SCOPE_ROWS])
@pytest.mark.parametrize("shell", ["oracle", "psh"])
def test_where_the_refusal_reaches(shell, case_id, line, expected, tmp_path):
    """Both directions of the refusal's SCOPE, both shells asserted.

    `expected is None` means the row must print nothing at all: noexec was
    honoured, so the printf never ran. Keying on the payload rather than on a
    return code is what makes "nothing ran" distinguishable from "ran and said
    nothing" (D3).

    Round 1 shipped a refusal keyed on the per-child `interactive` flag, and
    the cmdsub rows here were the silent regression that found: `$(set -n; echo
    hi)` yielded the empty string.
    """
    cwd = tmp_path / f"{shell}-{case_id}"
    cwd.mkdir()
    child = _spawn_shell(shell, cwd)
    try:
        transcript = _drive(child, [line])
    finally:
        child.close(force=True)

    assert "<TIMEOUT>" not in transcript, transcript[-600:]
    assert "Traceback (most recent call last)" not in transcript
    payloads = [m for m in re.findall(r"R=\[([^\]]*)\]", transcript)]
    # The terminal echoes the typed line too, so a literal `R=[%s]` in the echo
    # is not an answer; only a substituted payload is.
    payloads = [p for p in payloads if p != "%s"]
    if expected is None:
        assert not payloads, (
            f"{shell}/{case_id}: noexec was NOT honoured — got {payloads}\n"
            f"{transcript[-600:]}")
    else:
        assert payloads == [expected], (
            f"{shell}/{case_id}: expected [{expected!r}], got {payloads}\n"
            f"{transcript[-600:]}")


@pytest.mark.parametrize("shell", ["oracle", "psh"])
def test_the_command_line_flag_is_still_honoured(shell, tmp_path):
    """The control: `-i -n` executes nothing in BOTH shells. bash parses
    invocation flags before it decides the shell is interactive."""
    cwd = tmp_path / f"flag-{shell}"
    cwd.mkdir()
    if shell == "oracle":
        argv = [_ORACLE.path, "--norc", "-i", "-n"]
    else:
        argv = [sys.executable, "-u", "-m", "psh", "--norc",
                "--force-interactive", "-n"]
    child = pexpect.spawn(argv[0], argv[1:], timeout=20, encoding="utf-8",
                          env=_env(), cwd=str(cwd))
    try:
        child.send("touch marker\r")
        child.send("echo SHOULD_NOT_PRINT\r")
        child.expect([pexpect.TIMEOUT, pexpect.EOF], timeout=3)
        transcript = child.before or ""
    finally:
        child.close(force=True)

    assert not (cwd / "marker").exists(), (
        f"{shell}: the -n flag did not suppress execution\n{transcript[-400:]}")
