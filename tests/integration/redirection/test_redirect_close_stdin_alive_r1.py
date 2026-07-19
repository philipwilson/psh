"""R1 bounce blocker 1: a builtin fd close + stdin redirect must not destroy
the shell's own std fds.

The immediate-close change (H4) freed a low fd DURING the builtin redirect
list; the later stdin redirect's internal stream dup (`dup_sharing_stream` —
bare ``os.dup``) then landed on the freed slot, and the frame restore
(saved fds first, THEN closing the frame's opened streams) closed the
just-restored descriptor.  ``read x 1>&- <infile`` permanently killed the
shell's stdout; the ``2>&-`` twin silently killed stderr; ``3>&-`` variants
killed whatever fd the restore re-targeted.

Two production rules pin this class shut:

* internal stream dups relocate off fds 0-2 (``F_DUPFD >= 3``), so a freed
  std fd is never occupied by an internal stream (a child spawned by the
  builtin must see the closed fd CLOSED, like bash's children do);
* ``restore_builtin_redirections`` closes the frame's opened streams BEFORE
  re-installing saved fds, so even a >=3 collision (``3>&-`` freeing fd 3
  that the stream dup then takes) closes only the frame's own dup, never a
  restored descriptor.

The load-bearing assertions are the FOLLOW-ON commands: stdout/stderr (and
fd 3 in the collision row) must still be alive after the redirected builtin.
All expected values bash-5.2 verified (R1-probes/bounce-probes.txt).
"""
import os
import subprocess
import sys
import tempfile

import pytest

TREE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def run_psh(script, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = TREE
    env["PSH_STRICT_ERRORS"] = "0"
    p = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                       cwd=cwd or TREE, env=env, capture_output=True,
                       text=True, timeout=60)
    return p.stdout, p.stderr, p.returncode


@pytest.fixture()
def infile_dir():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "infile"), "w") as fh:
        fh.write("AAA\nBBB\n")
    return d


# ---- {1>&-} x {<file, <<EOF, <<<, 0<>} : stdout must survive ----

def test_close1_then_file_stdout_alive(infile_dir):
    out, err, rc = run_psh("read x 1>&- <infile; echo after=$x", cwd=infile_dir)
    assert out == "after=AAA\n", (out, err)
    assert "Bad file descriptor" not in (out + err), (out, err)


def test_close1_then_heredoc_stdout_alive(infile_dir):
    out, err, rc = run_psh("read x 1>&- <<EOF\nAAA\nEOF\necho after=$x",
                           cwd=infile_dir)
    assert out == "after=AAA\n", (out, err)


def test_close1_then_herestring_stdout_alive(infile_dir):
    out, err, rc = run_psh("read x 1>&- <<<AAA; echo after=$x", cwd=infile_dir)
    assert out == "after=AAA\n", (out, err)


def test_close1_then_readwrite_stdout_alive(infile_dir):
    out, err, rc = run_psh("read x 1>&- 0<>infile; echo after=$x",
                           cwd=infile_dir)
    assert out == "after=AAA\n", (out, err)


# ---- {2>&-} twins : stderr must survive ----

def test_close2_then_file_stderr_alive(infile_dir):
    out, err, rc = run_psh(
        "read x 2>&- <infile; echo after=$x; echo err=ok >&2", cwd=infile_dir)
    assert out == "after=AAA\n", (out, err)
    assert err == "err=ok\n", (out, err)


def test_close2_then_heredoc_stderr_alive(infile_dir):
    out, err, rc = run_psh(
        "read x 2>&- <<EOF\nAAA\nEOF\necho after=$x; echo err=ok >&2",
        cwd=infile_dir)
    assert out == "after=AAA\n", (out, err)
    assert err == "err=ok\n", (out, err)


def test_close2_then_herestring_stderr_alive(infile_dir):
    out, err, rc = run_psh(
        "read x 2>&- <<<AAA; echo after=$x; echo err=ok >&2", cwd=infile_dir)
    assert out == "after=AAA\n", (out, err)
    assert err == "err=ok\n", (out, err)


def test_close2_then_readwrite_stderr_alive(infile_dir):
    out, err, rc = run_psh(
        "read x 2>&- 0<>infile; echo after=$x; echo err=ok >&2",
        cwd=infile_dir)
    assert out == "after=AAA\n", (out, err)
    assert err == "err=ok\n", (out, err)


# ---- the >=3 collision class: restore-order, not just relocation ----

def test_close3_then_stdin_fd3_still_alive_after(infile_dir):
    # `3>&-` frees fd 3; the stdin stream dup (F_DUPFD >= 3) takes exactly
    # that slot; the per-command restore re-installs the old fd 3. Closing
    # the frame's streams AFTER that restore would close the restored fd 3.
    out, err, rc = run_psh(
        "exec 3>/dev/null; read x 3>&- <infile; echo after=$x; "
        "echo ok3 >&3 && echo fd3=alive", cwd=infile_dir)
    assert out == "after=AAA\nfd3=alive\n", (out, err)
    assert "Bad file descriptor" not in (out + err), (out, err)


# ---- controls ----

def test_reverse_order_still_works(infile_dir):
    # `<infile 1>&-` (open before close) never collided — must stay green.
    out, err, rc = run_psh("read x <infile 1>&-; echo after=$x",
                           cwd=infile_dir)
    assert out == "after=AAA\n", (out, err)


def test_shell_fully_alive_after_close_and_stdin(infile_dir):
    # EVERY subsequent command's streams work — the strongest liveness assert.
    out, err, rc = run_psh(
        "read x 1>&- <infile; echo one; echo two; echo three >&2; echo x=$x",
        cwd=infile_dir)
    assert out == "one\ntwo\nx=AAA\n", (out, err)
    assert err == "three\n", (out, err)


def test_child_sees_closed_fd_and_shell_survives(infile_dir):
    # While the builtin runs with `1>&- <infile`, a child it spawns sees fd 1
    # CLOSED (bash; `cat <&1` fails, never reads infile through fd 1), and the
    # shell's stdout survives the frame restore (`echo rc=$?` prints).
    out, err, rc = run_psh(
        "eval 'read x; /bin/sh -c \"cat <&1\"' 1>&- <infile; echo rc=$?",
        cwd=infile_dir)
    assert out == "rc=1\n", (out, err)
    assert "AAA" not in (out + err) and "BBB" not in (out + err), (
        "infile content leaked to a child through fd 1", out, err)
