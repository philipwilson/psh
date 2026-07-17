"""Long pipelines stay within the descriptor limit (D4).

PipelineExecutor used to open all N-1 pipes before forking the first child, so
the parent held ~2*(N-1) pipe descriptors at once and a long pipeline hit
EMFILE under an ordinary RLIMIT_NOFILE (the appraisal measured failure at 130
commands under `ulimit -n 256`). Rolling construction keeps only O(1) pipe
descriptors in the parent, so the same pipeline now runs.

These tests lower RLIMIT_NOFILE in a bash wrapper and then exec the target
shell (a modest pipeline under a lowered limit — never a 200-process storm at
the default limit). They compare psh against bash at the same length and limit,
executed through the shared typed runner (hermetic env, own session,
file-backed capture, bounded output) — the ulimit wrapper is ordinary script
text, so run_shell_case runs it unchanged.

Marked serial: they fork many short-lived processes and must not contend with
other tests under xdist.
"""
import sys
from pathlib import Path

import pytest
from shell_oracle import Completed, hermetic_shell_env, resolve_bash, run_shell_case

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV = hermetic_shell_env({'LC_ALL': 'C', 'LANG': 'C',
                          'PYTHONPATH': str(REPO_ROOT)})
BASH = resolve_bash().path

pytestmark = pytest.mark.serial


def _pipeline(nstages):
    # printf x | cat | cat | ... (nstages-1 cats); output is always "x".
    return "printf x" + " | cat" * (nstages - 1)


def _run_under_limit(shell_cmd, nofile, nstages):
    """Lower RLIMIT_NOFILE to nofile in bash, then exec shell_cmd -c pipeline."""
    pipeline = _pipeline(nstages)
    quoted = "'" + pipeline.replace("'", "'\\''") + "'"
    inner = f"ulimit -n {nofile}; exec {shell_cmd} -c {quoted}"
    r = run_shell_case([BASH, "-c", inner], stdin_data="", env=ENV, timeout=60)
    assert isinstance(r, Completed), f"harness failure: {r!r}"
    return r


PSH = f"{sys.executable} -m psh"


def test_long_pipeline_no_emfile_under_lowered_limit():
    """A 100-stage pipeline runs under `ulimit -n 128` (old design: EMFILE).

    Old psh pre-opened 2*99 = 198 descriptors > 128 and failed at ~80 stages;
    rolling keeps O(1), so 100 succeeds — matching bash at the same limit.
    """
    r = _run_under_limit(PSH, 128, 100)
    assert r.returncode == 0, f"psh failed: {r.stderr!r}"
    assert r.stdout == "x"
    assert "Too many open files" not in r.stderr


def test_bash_parity_at_same_length_and_limit():
    """bash runs the same 100-stage pipeline under the same limit."""
    r = _run_under_limit(BASH, 128, 100)
    assert r.returncode == 0
    assert r.stdout == "x"


def test_old_failing_length_now_succeeds():
    """The length that failed before (80 stages under ulimit 128) now works."""
    r = _run_under_limit(PSH, 128, 80)
    assert r.returncode == 0, f"psh failed: {r.stderr!r}"
    assert r.stdout == "x"
    assert "Too many open files" not in r.stderr
