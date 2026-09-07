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


@pytest.mark.parametrize("shell", ["bash", "psh"])
def test_interactive_shell_ignores_noexec(shell, tmp_path):
    cwd = tmp_path / shell
    cwd.mkdir()
    if shell == "bash":
        child = _spawn([_ORACLE.path, "--norc", "-i"], cwd)
    else:
        child = _spawn([sys.executable, "-u", "-m", "psh", "--norc",
                        "--force-interactive"], cwd)
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


@pytest.mark.parametrize("shell", ["bash", "psh"])
def test_the_command_line_flag_is_still_honoured(shell, tmp_path):
    """The control: `-i -n` executes nothing in BOTH shells. bash parses
    invocation flags before it decides the shell is interactive."""
    cwd = tmp_path / f"flag-{shell}"
    cwd.mkdir()
    if shell == "bash":
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
