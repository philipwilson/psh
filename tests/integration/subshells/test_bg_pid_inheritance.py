"""`$!` (last background PID) is inherited by subshell-style children.

Regression for reappraisal #10 R12.A: `ShellState.adopt()` didn't copy
`last_bg_pid`, so `$!` read empty inside `( … )`, `$( … )`, and the env
builtin's child. bash inherits it (`sleep 1 & ( echo $! )` prints the pid).
"""

import subprocess
import sys


def run_psh(script):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '--norc', '-c', script],
        capture_output=True, text=True, timeout=10)


def test_bg_pid_visible_in_paren_subshell():
    # The pid printed inside ( ) must equal $! in the parent.
    r = run_psh('sleep 1 & p=$!; ( echo "$!" ); echo "parent=$p"; wait')
    lines = r.stdout.split()
    assert lines, f"no output: {r.stdout!r} / {r.stderr!r}"
    sub_pid = lines[0]
    assert sub_pid.isdigit() and int(sub_pid) > 0, \
        f"$! empty/invalid in subshell: {r.stdout!r}"
    assert f"parent={sub_pid}" in r.stdout


def test_bg_pid_visible_in_command_substitution():
    r = run_psh('sleep 1 & x=$(echo "$!"); echo "[$x]"; wait')
    assert r.returncode == 0
    inner = r.stdout.strip()
    assert inner.startswith('[') and inner[1:-1].isdigit(), \
        f"$! empty in command substitution: {r.stdout!r}"
