"""`${...}` extent with a literal `{` in the body (reappraisal #14 Tier 2).

A bare `{` inside a `${...}` body is ordinary literal text; bash ends the
expansion at the first unescaped `}`. The lexer used to count the bare `{`
toward nesting depth, so `${x:-/path/{a,b}/c}` over-consumed and
`"[${u:-a{b}]"` ran off the end into a spurious "Unclosed quote" parse error.
Nested `${...}`/`$(...)`/`$((...))` are still skipped (their `}` doesn't end
the outer one). Verified against bash 5.2.
"""

import subprocess
import sys

import pytest


def _out(cmd, runner):
    r = runner(cmd)
    return (r.stdout, r.returncode)


def _psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def _bash(cmd):
    return subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)


@pytest.mark.parametrize("cmd", [
    'echo "${x:-/path/{a,b}/c}"',          # over-consumed before
    'echo "[${u:-a{b}]"',                  # unclosed-quote parse error before
    'x=Y; echo "${x:-/path/{a,b}/c}"',     # set value: default not taken
    'echo "${x:-{a,b}}"',                  # literal brace pair in default
    'a=A; echo "${x:-${a}}"',              # nested ${...} still skipped
    'unset a b; echo "${a:-${b:-deep}}"',  # deep nesting
    'unset a b c; echo "${a:-${b:-${c:-x}}}"',
    'echo "${x:-$(echo hi)}"',             # nested command substitution
    'echo "${x:-$((1+2))}"',               # nested arithmetic
    'v=a.b.c; echo "${v//./_}"',           # ordinary pattern op (regression)
    'v=hello; echo "${#v}"',               # length op (regression)
])
def test_brace_extent_matches_bash(cmd):
    assert _out(cmd, _psh) == _out(cmd, _bash), cmd
