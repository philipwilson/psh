"""Pipelines with standard descriptors initially closed (D1/D2).

`PipelineExecutor._setup_pipeline_redirections` used to dup2 the pipe endpoints
onto fds 0/1 and then close every stored pipe descriptor unconditionally. When
fd 0 or fd 1 began closed (`exec 0<&-`, `exec 1>&-`), os.pipe() hands an
endpoint back AS fd 0 or 1 — dup2(fd, fd) is a no-op and the close loop then
destroys the live endpoint:

- `exec 0<&-; printf x | cat` gave `cat: stdin: Bad file descriptor` instead of
  bash's `x` (the read end landed on fd 0, then got closed).
- `exec 1>&-; printf x | cat` made the upstream `printf` lose its pipe write end
  (`printf: write error: Bad file descriptor`) — bash keeps it; only the last
  member legitimately fails on its closed stdout.

The member now wires its endpoints through the collision-safe remap_fds
utility, so every open/closed combination of fds 0/1/2 matches bash.

The pipeline runs with the selected std fds GENUINELY closed — nothing reopens
them (a cmdsub wrapper or a group redirect would give the pipeline a fresh
stdout and defeat the test). rc + PIPESTATUS are recorded on a HIGH descriptor
(fd 9, opened after the closures, independent of 0/1/2); the pipeline's own
stdout/stderr are observed through the subprocess's captured streams (empty
when that fd was closed, exactly as in bash). psh and bash are compared on all
three: captured stdout, captured stderr, and the fd-9 status.

Subprocess tests: they permanently close the shell's own std fds, so they MUST
NOT run in-process (that would clobber the runner's descriptors, and under
xdist the worker channel). Pinned against the resolve_bash() oracle (5.2),
executed through the shared typed runner (hermetic env, own session,
file-backed capture, bounded output).
"""
import itertools
import os
import sys
import tempfile
from pathlib import Path

import pytest
from shell_oracle import Completed, hermetic_shell_env, resolve_bash, run_shell_case

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV = hermetic_shell_env({'LC_ALL': 'C', 'LANG': 'C',
                          'PYTHONPATH': str(REPO_ROOT)})
BASH = resolve_bash().path


def _closures(c0, c1, c2):
    parts = []
    if c0:
        parts.append("0<&-")
    if c1:
        parts.append("1>&-")
    if c2:
        parts.append("2>&-")
    return ("exec " + " ".join(parts) + "; ") if parts else ""


def _normalize_status(status):
    """Collapse SIGPIPE (141) in PIPESTATUS to 0.

    When a pipeline member's downstream exits early (here the final member
    fails on its legitimately closed stdout), the upstream members may or may
    not receive SIGPIPE before their write completes — a scheduling race that
    exists in bash too and shows up only under parallel test load. That makes a
    non-final stage's status 0 OR 141 depending on timing. Collapsing 141 -> 0
    keeps the deterministic, fd-remap-relevant parts (final status; a genuine
    `Bad file descriptor` would be 1, not 141, and is preserved) while removing
    the race. Applied identically to psh and bash.
    """
    if " ps=" in status:
        head, ps = status.split(" ps=", 1)
        elems = ["0" if e == "141" else e for e in ps.split()]
        return head + " ps=" + " ".join(elems)
    return status


def _observe(argv, closures, pipeline_expr):
    """Return (stdout, stderr, normalized fd9-status) for the pipeline."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False) as tf:
        path = tf.name
    try:
        script = (closures +
                  f'exec 9>{path}; {pipeline_expr}; '
                  f'printf "rc=%s ps=%s" "$?" "${{PIPESTATUS[*]}}" >&9')
        r = run_shell_case(argv + ["-c", script], stdin_data="",
                           env=ENV, timeout=20)
        assert isinstance(r, Completed), f"harness failure: {r!r}"
        with open(path) as f:
            status = _normalize_status(f.read())
        return r.stdout, r.stderr, status
    finally:
        os.unlink(path)


PIPELINES = ["printf x | cat", "printf x | cat | cat",
             "printf ab | cat | tr a-z A-Z"]
COMBOS = list(itertools.product([0, 1], repeat=3))


@pytest.mark.parametrize("pipeline_expr", PIPELINES)
@pytest.mark.parametrize("c0,c1,c2", COMBOS)
def test_pipeline_closed_fd_matches_bash(pipeline_expr, c0, c1, c2):
    """Every open/closed combo of fds 0/1/2 matches bash (stdout+stderr+PS)."""
    closures = _closures(c0, c1, c2)
    psh = _observe([sys.executable, "-m", "psh"], closures, pipeline_expr)
    bash = _observe([BASH], closures, pipeline_expr)
    assert psh == bash, (
        f"combo (0={c0},1={c1},2={c2}) {pipeline_expr!r}: "
        f"psh={psh!r} bash={bash!r}")


def test_d1_closed_stdin_pipeline():
    """exec 0<&-; printf x | cat prints x, PIPESTATUS 0 0 (was 'Bad fd')."""
    out, err, status = _observe([sys.executable, "-m", "psh"], "exec 0<&-; ",
                                "printf x | cat")
    assert out == "x"
    assert err == ""
    assert status == "rc=0 ps=0 0"


def test_d2_closed_stdout_upstream_keeps_write_end():
    """exec 1>&-: upstream printf no longer errors; only the last member fails.

    bash emits just `cat: stdout: Bad file descriptor` (cat's own closed
    stdout), never a `printf: write error`.
    """
    out, err, status = _observe([sys.executable, "-m", "psh"], "exec 1>&-; ",
                                "printf x | cat")
    assert "printf" not in err  # upstream keeps its pipe write end
    assert err == "cat: stdout: Bad file descriptor\n"
    assert status == "rc=1 ps=0 1"


def test_ordinary_pipeline_unchanged():
    """The all-open pipeline is unchanged: x on stdout, PIPESTATUS 0 0."""
    out, err, status = _observe([sys.executable, "-m", "psh"], "",
                                "printf x | cat")
    assert out == "x"
    assert status == "rc=0 ps=0 0"
