"""$0 conformance: inside a function $0 stays the script name (not the
function name) — bash semantics. Fixed v0.338.0 (reappraisal #4 follow-up).

Driven through SCRIPT FILES so psh and bash are directly comparable: when a
script is run by path, both shells report that path for $0 regardless of
function nesting (${FUNCNAME[0]} is the function name). A `-c` snippet would
report each shell's own name ($0 = "psh" vs "bash"), which is correct but not
directly comparable, so these tests use real files.
"""

import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.serial  # spawns subprocesses

BASH = shutil.which("bash")


def _run(shell_argv, script_path):
    return subprocess.run(
        shell_argv + [script_path],
        capture_output=True, text=True, timeout=30,
    ).stdout


def _psh(script_path):
    return _run([sys.executable, "-m", "psh"], script_path)


@pytest.fixture
def script(tmp_path):
    def _make(body):
        p = tmp_path / "s.sh"
        p.write_text(body)
        return str(p)
    return _make


def test_zero_in_function_is_script_path(script):
    s = script('echo "$0"\nf(){ echo "$0"; }\nf\n')
    out = _psh(s).splitlines()
    # Both lines are the script path; the function did not change $0.
    assert out == [s, s]


def test_zero_in_nested_function_is_script_path(script):
    s = script('f(){ echo "$0"; }\ng(){ f; }\ng\n')
    assert _psh(s).strip() == s


def test_funcname_still_reports_function(script):
    s = script('f(){ echo "${FUNCNAME[0]}"; }\nf\n')
    assert _psh(s).strip() == "f"


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_matches_bash(script):
    body = ('echo "top=$0"\n'
            'f(){ echo "fn=$0"; }\n'
            'g(){ f; }\n'
            'g\n')
    s = script(body)
    # Identical output from both shells (the script path in every position).
    assert _psh(s) == _run([BASH], s)
