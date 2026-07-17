"""Explicit-fd heredoc/here-string must not self-close on an fd collision.

``_content_to_fd`` delivered a heredoc/here-string body via an anonymous temp
file, then dup2'd it onto the target fd. When the temp file happened to land ON
the target fd (the lowest free fd — e.g. ``cat 3<<EOF <&3`` when fd 3 is free),
the old "skip the dup2 when the fds already match, then ``tmp.close()``" closed
the very fd holding the body, yielding ``Bad file descriptor`` and losing the
data (appraisal 2026-06-21, M6). The existing conformance test used fds 5 and 10,
too high to collide, so it never caught this.

The fix routes delivery through the shared fd-preserving primitive (``os.dup``
first, so closing the temp object can never reclaim the target fd).

Heredocs need real OS fds, so these run psh in a subprocess.
"""

import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path


def run(script):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                          capture_output=True, text=True)


def run_bash(script):
    return subprocess.run([BASH, '-c', script], capture_output=True, text=True)


def test_fd3_heredoc_body_delivered():
    # fd 3 is the lowest free fd, exactly where tempfile lands.
    r = run('cat 3<<EOF <&3\nfd3body\nEOF')
    assert r.returncode == 0
    assert r.stdout == "fd3body\n"
    assert "Bad file descriptor" not in r.stderr


def test_fd4_heredoc_after_exec3():
    # With fd 3 busy, the collision moves to fd 4.
    r = run('exec 3>/dev/null; cat 4<<EOF <&4\nfd4body\nEOF')
    assert r.returncode == 0
    assert r.stdout == "fd4body\n"


def test_fd5_here_string():
    r = run('cat 5<<<"hello fd5" <&5')
    assert r.returncode == 0
    assert r.stdout == "hello fd5\n"


def test_plain_stdin_heredoc_regression():
    r = run('cat <<EOF\nplain\nEOF')
    assert r.returncode == 0
    assert r.stdout == "plain\n"


def test_matches_bash_fd3():
    script = 'cat 3<<EOF <&3\nfd3body\nEOF'
    assert run(script).stdout == run_bash(script).stdout


def test_large_heredoc_regression():
    # The temp-file (not pipe) path must still handle bodies > pipe buffer.
    body = "\n".join(str(i) for i in range(5000))
    r = run(f'cat <<EOF | wc -l\n{body}\nEOF')
    assert r.returncode == 0
    assert r.stdout.strip() == "5000"
