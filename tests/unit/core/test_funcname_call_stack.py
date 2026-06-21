"""FUNCNAME is the full call stack, not just the current function (Tier 3).

bash's ``FUNCNAME`` is an ARRAY: ``[0]`` is the running function, ``[1]`` its
caller, and so on. psh returned only a scalar (the current function), so
``${FUNCNAME[1]}`` and ``${#FUNCNAME[@]}`` beyond index 0 were empty (appraisal
2026-06-21). It is now built from ``function_stack`` reversed (innermost first).

Every expectation was probe-verified against bash 5.2.
"""

import subprocess
import sys

import pytest


def run(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def run_bash(cmd):
    return subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)


CASES = [
    ('outer(){ inner; }; inner(){ echo "${FUNCNAME[1]}"; }; outer', 'outer\n'),
    ('f(){ echo "${FUNCNAME[0]}"; }; f', 'f\n'),
    ('f(){ echo "$FUNCNAME"; }; f', 'f\n'),                       # bare = [0]
    ('a(){ b; }; b(){ c; }; c(){ echo "${#FUNCNAME[@]}"; }; a', '3\n'),
    ('a(){ b; }; b(){ c; }; c(){ echo "${FUNCNAME[@]}"; }; a', 'c b a\n'),
    ('echo "[${FUNCNAME[0]}]"', '[]\n'),                          # outside a fn
]


@pytest.mark.parametrize('cmd,expected',
                         [pytest.param(c, e, id=c[:40]) for c, e in CASES])
def test_funcname_stack(cmd, expected):
    assert run(cmd).stdout == expected


@pytest.mark.parametrize('cmd', [c for c, _ in CASES])
def test_matches_bash(cmd):
    assert run(cmd).stdout == run_bash(cmd).stdout
