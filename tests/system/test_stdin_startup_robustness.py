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
    closed/absent stdin is now simply non-interactive, exactly like bash
    (exit 0).

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

PSH = [sys.executable, "-m", "psh"]
BASH = ["bash"]
TRACEBACK = b"Traceback (most recent call last)"


def _run(argv, *, stdin_bytes=None, stdin=None, close_fd0=False, timeout=10):
    """Run *argv* as a subprocess and capture bytes.

    ``close_fd0`` closes fd 0 in the child before exec (portable stand-in for
    ``exec 0<&-``); ``stdin_bytes`` pipes raw bytes; ``stdin`` passes an open
    file object (for a real ``< file`` redirect).
    """
    preexec = (lambda: os.close(0)) if close_fd0 else None
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

class TestClosedFd0Startup:
    def test_dash_c_with_closed_fd0(self):
        """`exec 0<&-; psh -c 'echo hi'` prints hi and exits 0."""
        r = _run(PSH + ["-c", "echo hi"], close_fd0=True)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 0
        assert r.stdout == b"hi\n"
        b = _run(BASH + ["-c", "echo hi"], close_fd0=True)
        assert (r.returncode, r.stdout) == (b.returncode, b.stdout)

    def test_plain_with_closed_fd0(self):
        """`exec 0<&-; psh` (no -c): non-interactive, nothing to read, exit 0."""
        r = _run(PSH, close_fd0=True)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 0
        b = _run(BASH, close_fd0=True)
        assert r.returncode == b.returncode

    def test_dash_s_with_closed_fd0(self):
        """`exec 0<&-; psh -s`: no stdin to read, exit 0, no crash."""
        r = _run(PSH + ["-s"], close_fd0=True)
        assert TRACEBACK not in r.stderr, r.stderr
        assert r.returncode == 0

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
