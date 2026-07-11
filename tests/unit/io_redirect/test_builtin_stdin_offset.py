"""A builtin ``<`` redirect must point ``sys.stdin`` at a DUP of fd 0 — one open
file description, one offset — not a second independent ``open()``.

The offset bug is LATENT today (psh's input resolver reads a builtin's stdin
through the real fd 0 whenever it has a fileno, so the second open is never
consumed), but the divergence is real: two independent opens have separate
positions, so a builtin that read part of the stream through ``sys.stdin`` and
a child (or a later ``read``) reading fd 0 would restart at 0. These tests pin
the shared-description PROPERTY so it stays fixed (see T5 / io_redirect audit
M2).

fd 0 is manipulated (dup2 onto it, lseek), so this runs psh in a SUBPROCESS —
in-process it would rewrite the test runner's own fd 0 (the xdist worker
channel).
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Set up a builtin `<` redirect through the REAL manager path, then move the
# shared file offset via sys.stdin's fd and observe it through fd 0. If the two
# share one open file description (the fix) fd 0 sees the move; a second
# independent open (the bug) leaves fd 0 at 0.
_OFFSET_PROBE = r'''
import os, sys, tempfile
from psh.shell import Shell
from psh.ast_nodes import Redirect, SimpleCommand

with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as tf:
    tf.write("0123456789\n")
    path = tf.name
try:
    shell = Shell(norc=True)
    cmd = SimpleCommand(
        words=[], redirects=[Redirect(type='<', target=path, fd=None)])
    frame = shell.io_manager.setup_builtin_redirections(cmd)
    sfd = sys.stdin.fileno()
    assert sfd != 0, f"sys.stdin still bound to fd 0 (sfd={sfd})"
    os.lseek(sfd, 3, os.SEEK_SET)         # move the shared description
    pos0 = os.lseek(0, 0, os.SEEK_CUR)    # observe fd 0's offset
    shell.io_manager.restore_builtin_redirections(frame)
    print("SHARED" if pos0 == 3 else f"INDEPENDENT(pos0={pos0})")
finally:
    os.unlink(path)
'''


def _run(script):
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
    )


def test_builtin_stdin_shares_fd0_offset():
    """After `< file`, sys.stdin and fd 0 share one file offset."""
    result = _run(_OFFSET_PROBE)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "SHARED", (
        f"sys.stdin does not share fd 0's offset: {result.stdout!r}\n"
        f"{result.stderr}")


def test_builtin_read_then_read_advances_one_stream():
    """`{ read a; read b; } < f` — the two reads consume consecutive lines
    (the observable consequence of one shared stdin offset)."""
    import os
    import tempfile
    tmp = tempfile.mktemp(suffix=".txt")
    script = (
        'printf "one\\ntwo\\nthree\\n" > "$T"; '
        '{ read a; read b; } < "$T"; echo "$a-$b"; rm -f "$T"')
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
        env={**os.environ, "T": tmp},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "one-two", result.stdout
