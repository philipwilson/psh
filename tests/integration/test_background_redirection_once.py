"""Background builtins/functions evaluate redirections exactly once (F3/F16).

Previously a backgrounded builtin or function installed its redirections
TWICE: once in the parent (in-process / fd-window mode) and again in the
forked child (setup_child_redirections). A command substitution in the
redirect target therefore ran twice — duplicating its side effects.

F16: a backgrounded builtin that runs shell code (e.g. `eval`) now goes
through the shared background-shell-child runner, so a body-set EXIT trap
fires like bash.

Each case runs psh in a subprocess in an isolated temp dir (real background
jobs; a counter file records how many times the redirect target ran).
"""

import os
import subprocess
import sys


def _run(script: str, cwd):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15, cwd=str(cwd),
    )
    return result.stdout, result.stderr, result.returncode


def _count(path) -> int:
    """Number of bytes (== number of target-substitution runs) in the file."""
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return len(f.read())


def test_background_builtin_redirect_target_runs_once(tmp_path):
    # The redirect target substitution appends one 'x' per run to marker.
    script = (
        'echo hi > "$(printf x >> marker; echo out.txt)" & wait; cat out.txt')
    out, _, rc = _run(script, tmp_path)
    assert rc == 0
    assert out == "hi\n"
    assert _count(tmp_path / "marker") == 1


def test_background_colon_redirect_target_runs_once(tmp_path):
    script = ': > "$(printf x >> marker; echo out.txt)" & wait'
    _run(script, tmp_path)
    assert _count(tmp_path / "marker") == 1


def test_background_function_redirect_target_runs_once(tmp_path):
    script = (
        'f() { echo body; }; '
        'f > "$(printf x >> marker; echo out.txt)" & wait; cat out.txt')
    out, _, rc = _run(script, tmp_path)
    assert rc == 0
    assert out == "body\n"
    assert _count(tmp_path / "marker") == 1


def test_background_special_builtin_redirect_target_runs_once(tmp_path):
    # export is a POSIX special builtin (separate background path).
    script = 'export X=y > "$(printf x >> marker; echo out.txt)" & wait'
    _run(script, tmp_path)
    assert _count(tmp_path / "marker") == 1


def test_foreground_builtin_redirect_still_runs_once(tmp_path):
    # Regression guard: the foreground in-process path must not double either.
    script = 'echo hi > "$(printf x >> marker; echo out.txt)"; cat out.txt'
    out, _, _ = _run(script, tmp_path)
    assert out == "hi\n"
    assert _count(tmp_path / "marker") == 1


def test_background_eval_runs_exit_trap(tmp_path):
    # F16: a backgrounded eval that sets an EXIT trap must fire it.
    script = 'eval \'trap "echo bye" EXIT; echo body\' & wait "$!"; echo "rc=$?"'
    out, _, rc = _run(script, tmp_path)
    assert out == "body\nbye\nrc=0\n"
    assert rc == 0


def test_background_eval_exit_code_via_wait(tmp_path):
    script = 'eval "exit 7" & p=$!; wait "$p"; echo "rc=$?"'
    out, _, _ = _run(script, tmp_path)
    assert out == "rc=7\n"


def test_background_builtin_sets_dollar_bang(tmp_path):
    script = 'echo hi > out.txt & p=$!; wait "$p"; [ -n "$p" ] && echo "pid_set"'
    out, _, _ = _run(script, tmp_path)
    assert out == "pid_set\n"
