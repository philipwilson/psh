"""Startup robustness: binary/undecodable stdin and a closed fd 0 must not crash.

Reappraisal #18 T1-1. Two crash-class regressions where a raw Python traceback
reached the user:

  * Binary or otherwise non-UTF-8 bytes on stdin raised an uncaught
    ``UnicodeDecodeError`` from the unguarded ``sys.stdin.read()`` in
    ``psh/__main__.py``.  psh now reads stdin with ``surrogateescape`` (matching
    the ``FileInput`` script treatment), so garbage bytes are handled leniently
    like bash — a stray byte simply becomes a "command not found".

  * Starting psh with fd 0 already closed (``exec 0<&-; psh``) left
    ``sys.stdin`` as ``None``, so ``sys.stdin.isatty()`` (in ``shell.py`` and,
    once that was guarded, in ``__main__.py``) raised ``AttributeError``.  A
    closed fd 0 is now simply non-interactive with no stream to read commands
    from: bash 5.3 exits 126 with ``error creating buffered stream: Bad file
    descriptor`` (empirical, 5.3.15 — earlier bash releases exited 0; retuned
    in Wave 0.3 of the 2026-09 improvement program, C242 gate triage), and psh
    prints the same message under its ``psh:`` prefix.  Only the plain and
    ``-s`` (read-commands-from-fd-0) invocations are affected: ``-c`` and a
    script file never read fd 0 for commands and still run, an OPEN but empty
    fd 0 (``< /dev/null``) still exits 0, and ``-i`` stays an
    interactive-family shell that sees immediate EOF (exit 0).

These drive the real CLI in a subprocess.  ``PSH_STRICT_ERRORS=1`` is on
suite-wide (conftest.py), so any surviving internal defect would surface as a
traceback and fail these tests loudly — which is exactly the regression pin.

NOTE (deliberate scope): a *valid command's argument or an assignment value*
containing a raw non-UTF-8 byte still hits a later ``UnicodeEncodeError`` when
psh tries to write the surrogate byte back to its UTF-8 stdout.  That is a
PRE-EXISTING output-layer byte-model limitation that already affects script
FILES read via ``FileInput`` identically — this fix makes stdin *consistent*
with that, and does not attempt to change it.  These tests therefore pin only
the crash that was fixed (garbage bytes that never round-trip to output: an
unknown command name), not that deeper divergence.
"""

import os
import subprocess
import sys

import pytest
from shell_oracle import is_comparable, resolve_bash, run_bash, run_psh

PSH = [sys.executable, "-m", "psh"]
BASH = [resolve_bash().path]
TRACEBACK = b"Traceback (most recent call last)"


def _run(argv, *, stdin_bytes=None, stdin=None, close_fd0=False,
         close_fd2=False, timeout=10):
    """Run *argv* and capture bytes.

    ``close_fd0`` closes fd 0 in the child before exec (portable stand-in for
    ``exec 0<&-``); ``close_fd2`` additionally closes fd 2 (``2>&-``: the
    child has no stderr at all, so ``r.stderr`` reads back empty); ``stdin_bytes``
    supplies raw bytes on stdin; ``stdin`` passes an open file object (for a
    real ``< file`` redirect).

    TWO ENVIRONMENT REGIMES LIVE IN THIS HELPER — know which branch a new row
    lands on: the runner branch gets the HERMETIC env (every inherited
    ``LC_*``/``LANG`` and ``DISPLAY`` stripped), while the direct-spawn branch
    below inherits the ambient ``os.environ`` unchanged.  A locale- or
    env-sensitive row added to the direct branch would be host-sensitive in a
    way its runner-routed siblings are not (exactly the failure mode
    continuation-finding H records).  Put such rows on the runner branch, or
    build the child env explicitly.

    Raw-byte-stdin runs route through the typed oracle runner
    (``run_psh``/``run_bash``) so a non-comparable outcome fails loudly. A run
    that must close fd 0 (needs a ``preexec_fn``) or hand psh a live file object
    is not expressible through the runner and stays a direct spawn.
    """
    if close_fd0 or stdin is not None:
        def _close_fds():
            if close_fd0:
                os.close(0)
            if close_fd2:
                os.close(2)
        preexec = _close_fds if (close_fd0 or close_fd2) else None
        kwargs = {}
        if stdin is not None:
            kwargs["stdin"] = stdin
        return subprocess.run(
            argv,
            input=stdin_bytes,
            capture_output=True,
            timeout=timeout,
            preexec_fn=preexec,
            **kwargs,
        )
    if argv[0] == sys.executable:
        r = run_psh(argv[3:], stdin_data=stdin_bytes, stdin_mode="pipe",
                    timeout=timeout)
    else:
        r = run_bash(argv[1:], stdin_data=stdin_bytes, stdin_mode="pipe",
                     timeout=timeout)
    assert is_comparable(r), r
    return subprocess.CompletedProcess(
        argv, r.returncode,
        stdout=r.stdout.encode("utf-8", "surrogateescape"),
        stderr=r.stderr.encode("utf-8", "surrogateescape"))


# ---------------------------------------------------------------------------
# Bug A: binary / undecodable stdin must not traceback.
# ---------------------------------------------------------------------------

class TestBinaryStdinNoTraceback:
    def test_pipe_binary_bytes(self):
        """Undecodable bytes piped in: no traceback, command-not-found (127)."""
        r = _run(PSH, stdin_bytes=b"\xff\xfe")
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 127
        assert b"command not found" in r.stderr
        # bash agrees on the exit status (byte-exact error text differs — the
        # documented byte-model divergence).
        b = _run(BASH, stdin_bytes=b"\xff\xfe")
        assert r.returncode == b.returncode

    def test_dash_s_binary_bytes(self):
        """`-s` (read stdin, operands are positionals) with garbage bytes."""
        r = _run(PSH + ["-s"], stdin_bytes=b"\xff")
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 127
        b = _run(BASH + ["-s"], stdin_bytes=b"\xff")
        assert r.returncode == b.returncode

    def test_redirect_binary_file(self, tmp_path):
        """`psh < binaryfile`: the `< file` channel must not traceback either."""
        binfile = tmp_path / "bin.dat"
        binfile.write_bytes(b"\xff\xfe\n")
        with open(binfile, "rb") as fh:
            r = _run(PSH, stdin=fh)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 127

    def test_validate_visitor_mode_binary(self):
        """Visitor mode (`--validate`) reads ALL of stdin — must not traceback."""
        r = _run(PSH + ["--validate"], stdin_bytes=b"\xff\xfe")
        assert TRACEBACK not in r.stderr, r.stderr
        # Analysis modes never execute; empty-of-real-commands validates cleanly.
        assert r.returncode == 0

    def test_mixed_valid_and_invalid_bytes(self):
        """Valid lines around a garbage line still run; overall no crash."""
        script = b"echo hello\n\xff\xfe\necho world\n"
        r = _run(PSH, stdin_bytes=script)
        assert TRACEBACK not in r.stderr, r.stderr
        assert b"hello\n" in r.stdout
        assert b"world\n" in r.stdout
        b = _run(BASH, stdin_bytes=script)
        # Both run the good lines and finish on echo's success.
        assert r.returncode == b.returncode == 0
        assert r.stdout == b.stdout

    def test_valid_utf8_stdin_unaffected(self):
        """A well-formed UTF-8 (multibyte) script is unchanged by the fix."""
        script = "echo café\n".encode("utf-8")
        r = _run(PSH, stdin_bytes=script)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 0
        assert r.stdout == "café\n".encode("utf-8")
        b = _run(BASH, stdin_bytes=script)
        assert r.stdout == b.stdout

    def test_empty_stdin(self):
        """Empty stdin: clean exit 0, no crash."""
        r = _run(PSH, stdin_bytes=b"")
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 0
        assert r.stdout == b""


# ---------------------------------------------------------------------------
# Bug B: psh started with fd 0 already closed must not crash.
# ---------------------------------------------------------------------------

BUFFERED_STREAM_ERROR = b"error creating buffered stream: Bad file descriptor"


@pytest.mark.oracle_min("5.3")
class TestClosedFd0Startup:
    """The four command channels with fd 0 CLOSED at startup (D6: the
    failure shape differs by input mode): plain stdin and ``-s`` read commands
    from fd 0 and cannot (126 + bash's diagnostic); ``-c`` and a script file
    do not read fd 0 and run normally. The open-but-empty ``< /dev/null`` row
    pins the discriminator (a CLOSED descriptor, not an EMPTY one)."""

    def test_dash_c_with_closed_fd0(self):
        """`exec 0<&-; psh -c 'echo hi'` prints hi and exits 0."""
        r = _run(PSH + ["-c", "echo hi"], close_fd0=True)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 0
        assert r.stdout == b"hi\n"
        b = _run(BASH + ["-c", "echo hi"], close_fd0=True)
        assert (r.returncode, r.stdout) == (b.returncode, b.stdout)

    def test_plain_with_closed_fd0(self):
        """`exec 0<&-; psh` (no -c): no stream to read commands from -> bash
        5.3's `error creating buffered stream: Bad file descriptor`, exit 126
        (empirical, 5.3.15). RED ON BASE (788ffe41): psh exited 0 silently."""
        r = _run(PSH, close_fd0=True)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 126
        assert r.stdout == b""
        assert r.stderr == b"psh: " + BUFFERED_STREAM_ERROR + b"\n"
        b = _run(BASH, close_fd0=True)
        assert (r.returncode, r.stdout) == (b.returncode, b.stdout)
        assert BUFFERED_STREAM_ERROR in b.stderr

    def test_dash_s_with_closed_fd0(self):
        """`exec 0<&-; psh -s`: the same no-stream failure, exit 126 (bash 5.3
        `-s <&-` is also 126; empirical, 5.3.15). RED ON BASE (788ffe41)."""
        r = _run(PSH + ["-s"], close_fd0=True)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 126
        assert r.stderr == b"psh: " + BUFFERED_STREAM_ERROR + b"\n"
        b = _run(BASH + ["-s"], close_fd0=True)
        assert (r.returncode, r.stdout) == (b.returncode, b.stdout)
        assert BUFFERED_STREAM_ERROR in b.stderr

    def test_open_empty_fd0_still_exits_zero(self):
        """`psh < /dev/null` (fd 0 OPEN, empty): no commands, exit 0 — only a
        CLOSED descriptor triggers the 126 (bash 5.3 agrees; empirical,
        5.3.15)."""
        with open(os.devnull, "rb") as fh:
            r = _run(PSH, stdin=fh)
        assert TRACEBACK not in r.stderr, r.stderr
        assert (r.returncode, r.stdout, r.stderr) == (0, b"", b"")
        with open(os.devnull, "rb") as fh:
            b = _run(BASH, stdin=fh)
        assert (r.returncode, r.stdout) == (b.returncode, b.stdout)

    def test_dash_i_with_closed_fd0_is_interactive_eof(self):
        """`psh -i <&-`: an interactive-family shell that sees immediate EOF
        exits 0 (bash 5.3 `-i <&-` prints its no-job-control notices, then
        `exit`, status 0; empirical, 5.3.15). The 126 path is non-`-i` only.
        Status-only row: the stderr SHAPES differ (bash's notices vs psh's
        silence) and are not pinned here."""
        r = _run(PSH + ["-i"], close_fd0=True)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 0
        assert BUFFERED_STREAM_ERROR not in r.stderr
        b = _run(BASH + ["--norc", "-i"], close_fd0=True)
        assert r.returncode == b.returncode

    def test_plain_with_closed_fd0_and_fd2(self):
        """`psh <&- 2>&-`: fd 2 closed too (sys.stderr is None). bash 5.3 still
        exits 126, silently (empirical, 5.3.15); psh must exit 126 with EMPTY
        stdout — the diagnostic goes only to a live stderr, never to stdout
        and never as a traceback. RED ON BASE (6c31871f): AttributeError on
        `sys.stderr.write`, rc 1."""
        r = _run(PSH, close_fd0=True, close_fd2=True)
        assert (r.returncode, r.stdout, r.stderr) == (126, b"", b"")
        b = _run(BASH, close_fd0=True, close_fd2=True)
        assert (r.returncode, r.stdout, r.stderr) == (b.returncode, b.stdout, b.stderr)

    def test_dash_s_with_closed_fd0_and_fd2(self):
        """`psh -s <&- 2>&-`: same silent 126 (empirical, 5.3.15)."""
        r = _run(PSH + ["-s"], close_fd0=True, close_fd2=True)
        assert (r.returncode, r.stdout, r.stderr) == (126, b"", b"")
        b = _run(BASH + ["-s"], close_fd0=True, close_fd2=True)
        assert (r.returncode, r.stdout, r.stderr) == (b.returncode, b.stdout, b.stderr)

    def test_dash_c_with_closed_fd0_and_fd2(self):
        """`psh -c 'echo hi' <&- 2>&-` still runs: `-c` never reads fd 0."""
        r = _run(PSH + ["-c", "echo hi"], close_fd0=True, close_fd2=True)
        assert (r.returncode, r.stdout) == (0, b"hi\n")
        b = _run(BASH + ["-c", "echo hi"], close_fd0=True, close_fd2=True)
        assert (r.returncode, r.stdout) == (b.returncode, b.stdout)

    def test_script_file_with_closed_fd0_and_fd2(self, tmp_path):
        """A script FILE still runs with fd 0 and fd 2 both closed."""
        script = tmp_path / "s.sh"
        script.write_text("echo fromscript\n")
        r = _run(PSH + [str(script)], close_fd0=True, close_fd2=True)
        assert (r.returncode, r.stdout) == (0, b"fromscript\n")
        b = _run(BASH + [str(script)], close_fd0=True, close_fd2=True)
        assert (r.returncode, r.stdout) == (b.returncode, b.stdout)

    def test_script_file_with_closed_fd0(self, tmp_path):
        """A script FILE still runs when fd 0 was closed at startup."""
        script = tmp_path / "s.sh"
        script.write_text("echo fromscript\n")
        r = _run(PSH + [str(script)], close_fd0=True)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 0
        assert r.stdout == b"fromscript\n"

    def test_command_substitution_with_closed_fd0(self):
        """Command substitution in a forked child must not choke on closed fd0.

        The child's stdin-protection check (command_sub.py) reads
        ``sys.stdin.isatty()`` via a getattr DEFAULT (eagerly evaluated), so
        with fd 0 closed it saw ``None.isatty()`` and emitted an empty
        substitution + a "command substitution error" on stderr instead of the
        real output. Guarded now — matches bash's ``hi``.
        """
        r = _run(PSH + ["-c", "echo $(echo hi)"], close_fd0=True)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 0
        assert r.stdout == b"hi\n"
        assert r.stderr == b""
        b = _run(BASH + ["-c", "echo $(echo hi)"], close_fd0=True)
        assert (r.returncode, r.stdout, r.stderr) == (b.returncode, b.stdout, b.stderr)
