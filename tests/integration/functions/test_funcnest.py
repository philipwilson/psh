"""FUNCNEST — maximum function-call nesting depth (reappraisal #14 Tier 2).

bash refuses a function call once the call stack is already FUNCNEST deep,
reporting `NAME: maximum function nesting level exceeded (N)` and aborting the
current top-level command (resuming at the next input line, status 1). psh
ignored FUNCNEST and recursed to Python's limit. FUNCNEST unset or <= 0 means
no limit. Verified against bash 5.2 (error-message prefix differs by design).
"""

import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path


def _psh_c(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def _bash_c(cmd):
    return subprocess.run([BASH, '-c', cmd], capture_output=True, text=True)


def test_limit_caps_recursion_depth():
    # FUNCNEST=3: the body runs at depths 1,2,3 then the 4th call is refused.
    r = _psh_c('FUNCNEST=3; f(){ echo d; f; }; f')
    assert r.stdout == 'd\nd\nd\n'
    assert 'maximum function nesting level exceeded (3)' in r.stderr


def test_limit_one():
    r = _psh_c('FUNCNEST=1; f(){ echo x; f; }; f')
    assert r.stdout == 'x\n'


def test_mutual_recursion():
    r = _psh_c('FUNCNEST=2; a(){ b; }; b(){ a; }; a')
    assert 'maximum function nesting level exceeded (2)' in r.stderr


def test_within_limit_runs_normally():
    r = _psh_c('FUNCNEST=5; a(){ b; }; b(){ echo hi; }; a')
    assert r.stdout == 'hi\n'
    assert r.returncode == 0


def test_abort_unwinds_whole_command():
    # No "after N" prints: the limit unwinds the entire call chain (bash).
    r = _psh_c('FUNCNEST=3; f(){ echo "in $1"; f; echo "after $1"; }; f A; echo TOP')
    assert 'after' not in r.stdout
    assert 'TOP' not in r.stdout  # same line: aborted before TOP


def test_zero_means_no_limit():
    r = _psh_c('FUNCNEST=0; n=0; f(){ n=$((n+1)); [ $n -lt 30 ] && f; }; f; echo "reached $n"')
    assert r.stdout == 'reached 30\n'
    assert r.returncode == 0


def test_unset_means_no_limit():
    r = _psh_c('g(){ echo "$1"; [ "$1" -lt 5 ] && g $(( $1 + 1 )); }; g 1')
    assert r.stdout == '1\n2\n3\n4\n5\n'


def test_resumes_at_next_line():
    # script-mode: the abort resumes at the next top-level command.
    cmd = 'FUNCNEST=2\nf(){ f; }\nf\necho NEXT'
    r = _psh_c(cmd)
    assert 'NEXT' in r.stdout


def test_matches_bash_depth():
    cmd = 'FUNCNEST=4; f(){ echo d; f; }; f'
    psh, bash = _psh_c(cmd), _bash_c(cmd)
    assert psh.stdout == bash.stdout
    assert psh.returncode == bash.returncode
