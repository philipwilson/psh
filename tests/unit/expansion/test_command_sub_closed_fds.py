"""Command substitution with standard descriptors initially closed (D3).

`CommandSubstitution._child_io_setup` used to do

    close(read_fd); dup2(write_fd, 1); close(write_fd)

which, when fd 1 began closed (`exec 1>&-`), let os.pipe() hand back the write
end AS fd 1 — dup2(1,1) is a no-op and the close then destroyed the
substitution's own stdout, so `x=$(printf x)` produced `<> rc=1` instead of
bash's `<x> rc=0`. The child now wires its stdout through the collision-safe
remap_fds utility, so every open/closed combination of fds 0/1/2 matches bash.

These are subprocess tests: they permanently close the shell's own std fds, so
they MUST NOT run in-process (that would clobber the test runner's descriptors,
and under xdist the worker channel). Each result is written to a fresh file
descriptor (a temp file), which is unaffected by the std-fd closures, so it can
be read back whatever was closed. All expectations pinned against bash 5.2.
"""
import itertools
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV = {**os.environ, 'PYTHONPATH': str(REPO_ROOT)}


def _closures(c0, c1, c2):
    parts = []
    if c0:
        parts.append("0<&-")
    if c1:
        parts.append("1>&-")
    if c2:
        parts.append("2>&-")
    return ("exec " + " ".join(parts) + "; ") if parts else ""


def _run(command):
    subprocess.run([sys.executable, '-m', 'psh', '-c', command],
                   input=b'', capture_output=True, timeout=20,
                   cwd=str(REPO_ROOT), env=ENV)


@pytest.mark.parametrize("c0,c1,c2", list(itertools.product([0, 1], repeat=3)))
def test_cmdsub_all_closed_fd_combinations(c0, c1, c2):
    """x=$(printf x) yields <x> rc=0 for every open/closed combo of 0/1/2."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False) as tf:
        path = tf.name
    try:
        script = (_closures(c0, c1, c2) +
                  f'x=$(printf x); printf "<%s> rc=%s" "$x" "$?" > {path}')
        _run(script)
        with open(path) as f:
            result = f.read()
    finally:
        os.unlink(path)
    assert result == "<x> rc=0", f"combo (0={c0},1={c1},2={c2}) gave {result!r}"


def test_cmdsub_output_captured_with_stdout_closed():
    """`exec 1>&-; y=$(echo captured)` still captures the output."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False) as tf:
        path = tf.name
    try:
        _run(f'exec 1>&-; y=$(echo captured); printf "%s" "$y" > {path}')
        with open(path) as f:
            assert f.read() == "captured"
    finally:
        os.unlink(path)


def test_many_closed_fd_cmdsubs_do_not_leak():
    """Repeated closed-fd cmdsubs in one process leave no fd/zombie leak.

    Runs 40 command substitutions after closing stdin, counting open
    descriptors before and after; the count must not grow (a leaked pipe end
    or unreaped child would show up here).
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False) as tf:
        path = tf.name
    try:
        # Count fds with a glob (no pipeline): a pipeline would need stdin,
        # which is closed here, and that is a separate defect (D1) fixed in a
        # later commit; the leak check must not depend on it.
        script = (
            "exec 0<&-; "
            "count() { set -- /dev/fd/*; echo $#; }; "
            "start=$(count); "
            "i=0; while [ $i -lt 40 ]; do z=$(printf y); i=$((i+1)); done; "
            "end=$(count); "
            f'printf "%s %s" "$start" "$end" > {path}')
        _run(script)
        with open(path) as f:
            start, end = (int(n) for n in f.read().split())
    finally:
        os.unlink(path)
    assert end <= start, f"fd growth: start={start} end={end}"
