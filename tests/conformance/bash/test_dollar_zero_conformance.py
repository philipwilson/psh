"""$0 conformance: inside a function $0 stays the script name (not the
function name) — bash semantics. Fixed v0.338.0 (reappraisal #4 follow-up).

Driven through SCRIPT FILES so psh and bash are directly comparable: when a
script is run by path, both shells report that path for $0 regardless of
function nesting (${FUNCNAME[0]} is the function name). A `-c` snippet would
report each shell's own name ($0 = "psh" vs "bash"), which is correct but not
directly comparable, so these tests use real files.
"""

import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

pytestmark = pytest.mark.serial  # spawns subprocesses

BASH = resolve_bash().path


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


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_dash_c_name_is_dollar_zero():
    """R14.B: `sh -c CMD name a b` sets $0=name, $1=a, $#=2 (POSIX) — psh used
    to make name $1. Comparable across shells because $0 is the operand here."""
    cmd = 'echo "0=$0 1=$1 2=$2 #=$#"'
    psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd, 'myname', 'a', 'b'],
                         capture_output=True, text=True).stdout
    bash = subprocess.run([BASH, '-c', cmd, 'myname', 'a', 'b'],
                          capture_output=True, text=True).stdout
    assert psh == bash == '0=myname 1=a 2=b #=2\n'


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_non_utf8_script_does_not_crash(tmp_path):
    """R14.B: a stray non-UTF-8 byte in a script must not crash psh with an
    uncaught traceback — bash treats it as a (not-found) command and continues.
    Both shells run the surrounding commands and exit 0."""
    s = tmp_path / "badenc.sh"
    s.write_bytes(b'echo before\n\xe9\necho after\n')
    # errors='replace' on the capture: the diagnostic legitimately contains the
    # raw non-UTF-8 byte (round-tripped), which a strict text decode can't read.
    psh = subprocess.run([sys.executable, '-m', 'psh', str(s)],
                         capture_output=True, text=True, errors='replace')
    bash = subprocess.run([BASH, str(s)], capture_output=True, text=True,
                          errors='replace')
    assert psh.stdout == bash.stdout == 'before\nafter\n'
    assert psh.returncode == bash.returncode == 0
    assert 'Traceback' not in psh.stderr
    assert 'command not found' in psh.stderr
