"""Conformance pins for two io_redirect bash-divergence fixes (reappraisal #6).

Covers:
- L2: a redirect open/dup failure reports bash's `psh: TARGET: STRERROR` shape
      (e.g. `psh: /badpath/nope: No such file or directory`) with exit 1, NOT
      the raw Python OSError repr (`psh: error: [Errno 2] ...`). Verified for
      both the external-command (forked child) path and the builtin path.
- L4: after `exec 1>&-` closes stdout, a subsequent write builtin reports a
      `write error: Bad file descriptor` and the shell exits 1 — not 120 with
      an `Exception ignored while flushing sys.stdout` shutdown leak.

The bash MESSAGE prefix differs (`bash: line 1:` vs `psh:` / the builtin
name) — that is the shell-name prefix, not behavior — so these assert the
target/strerror body and the exit codes rather than byte-identical stderr.

All driven through subprocesses so psh and bash are directly comparable, and
so closing fd 1 happens in a real process (never the test runner's own fds).
"""

import os
import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

pytestmark = pytest.mark.serial  # spawns subprocesses; closes fds

BASH = resolve_bash().path


def _psh(cmd):
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", cmd],
        capture_output=True, text=True, timeout=30,
    )


def _bash(cmd):
    return subprocess.run(
        [BASH, "-c", cmd], capture_output=True, text=True, timeout=30,
    )


# --------------------------------------------------------------------------
# L2: redirect open failures use the `TARGET: STRERROR` shape + exit 1
# --------------------------------------------------------------------------

# (command, expected target token, errno whose strerror bash prints)
_L2_CASES = [
    # external command, write to a nonexistent directory (ENOENT)
    ("cat /etc/hostname > /badpath/nope", "/badpath/nope", "ENOENT", True),
    # builtin write to a nonexistent directory (ENOENT)
    ("echo hi > /badpath/nope", "/badpath/nope", "ENOENT", False),
    # external command, read from a nonexistent file (ENOENT)
    ("cat < /nonexistent-xyz", "/nonexistent-xyz", "ENOENT", True),
    # builtin read from a nonexistent file (ENOENT)
    ("read v < /nonexistent-xyz", "/nonexistent-xyz", "ENOENT", False),
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd,target,errkey,_external", _L2_CASES)
def test_redirect_open_failure_message_and_exit(cmd, target, errkey, _external):
    strerror = os.strerror(getattr(__import__("errno"), errkey))
    p = _psh(cmd)
    b = _bash(cmd)
    # Exit codes identical to bash.
    assert p.returncode == b.returncode == 1, (
        f"exit differs for {cmd!r}: psh={p.returncode} bash={b.returncode}")
    # psh uses the bash `TARGET: STRERROR` shape (not the raw OSError repr).
    expected = f"{target}: {strerror}"
    assert expected in p.stderr, (
        f"psh stderr lacks `{expected}` for {cmd!r}: {p.stderr!r}")
    # And does NOT leak the Python OSError repr.
    assert "[Errno" not in p.stderr, (
        f"psh leaked OSError repr for {cmd!r}: {p.stderr!r}")
    assert "psh: error:" not in p.stderr, (
        f"psh used generic error prefix for {cmd!r}: {p.stderr!r}")


def test_noclobber_message_not_regressed(tmp_path):
    """The pre-existing noclobber message must remain (different from L2)."""
    f = tmp_path / "exists.txt"
    cmd = f'set -C; echo hi > {f}; echo hi > {f}'
    p = _psh(cmd)
    assert p.returncode == 1
    assert "cannot overwrite existing file" in p.stderr
    assert "[Errno" not in p.stderr


# --------------------------------------------------------------------------
# L4: exec 1>&- then write -> write error + exit 1, no shutdown leak
# --------------------------------------------------------------------------

@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("writer", ["echo after", 'printf "after\\n"'])
def test_write_after_closing_stdout(writer):
    cmd = f"echo before; exec 1>&-; {writer}"
    p = _psh(cmd)
    b = _bash(cmd)
    # Same exit code as bash (1), NOT 120 from a finalization failure.
    assert p.returncode == b.returncode == 1, (
        f"exit differs: psh={p.returncode} bash={b.returncode}")
    # The pre-close output reached stdout.
    assert p.stdout == "before\n"
    # bash-shape write-error message.
    assert "write error: Bad file descriptor" in p.stderr, p.stderr
    # No interpreter-shutdown noise.
    assert "Exception ignored" not in p.stderr, p.stderr
    assert "[Errno" not in p.stderr, p.stderr


def test_closing_stdout_does_not_emit_shutdown_noise():
    """Even with no later write, closing fd 1 must not leak shutdown noise."""
    p = _psh("exec 1>&-")
    assert "Exception ignored" not in p.stderr, p.stderr
    assert p.returncode == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
