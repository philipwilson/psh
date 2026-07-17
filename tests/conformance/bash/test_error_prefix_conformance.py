"""Conformance: the systemic runtime-error location prefix vs live bash.

bash prefixes runtime errors with ``<$0>: line N: <msg>`` (non-interactive).
psh's ``$0`` analogue is ``"psh"``; bash normally reports its own argv0 path,
so a naive stderr diff would differ only in ``$0``. bash's ``-c`` form takes a
``$0`` operand — ``bash -c CMD psh`` sets ``$0="psh"`` — which lets us compare
psh's stderr to bash's **byte for byte**, proving the ``line N:`` tracking, the
message wording, AND the exit status all match (task #21 [#35]).

Message-BODY divergences (kill signal wording, arithmetic error phrasing) are a
SEPARATE concern tracked by task #40 and are deliberately excluded here.
"""

import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path


def _run(argv, cmd, dollar0=None):
    full = list(argv) + ["-c", cmd] + ([dollar0] if dollar0 else [])
    return subprocess.run(full, capture_output=True, text=True, timeout=15)


def _psh(cmd):
    return _run([sys.executable, "-m", "psh"], cmd)


def _bash(cmd):
    # Pass $0="psh" so bash's error prefix names "psh" exactly like our shell.
    return _run([BASH], cmd, dollar0="psh")


# Representative cell per error class — each is prefix-only (body already
# matches bash), so exact stderr equality is the right assertion.
PREFIX_CELLS = [
    "trap -x",                               # builtin bad option (+ usage line)
    "cd /nonexistent_zz_99",                 # builtin bad operand
    "local x",                               # builtin runtime error
    "return abc",                            # return double-error outside fn
    "nosuchcmd_zz_123",                      # external command not found
    "set -u; echo $undef_zz_123",            # set -u unbound variable
    "unset x; echo ${x:?custom message}",    # ${x:?} expansion error
    "readonly r=1; r=2",                     # plain assignment readonly
    "readonly r=1; (( r=2 ))",               # arithmetic-command readonly
    "readonly r=1; export r=2",              # readonly via builtin (no name)
    "echo ${!x*bad}",                        # bad substitution
    'trap "echo hi" NOPE',                   # trap SET-path invalid signal (F1)
    "trap -p NOPE",                          # trap -p-path invalid signal (sibling)
    'declare -n a=b; declare -n b=a; echo $a',   # nameref-cycle warning (F2)
    'x=$(printf "a\\0b"); echo done',        # cmd-sub null-byte warning (re-sweep)
]


@pytest.mark.parametrize("cmd", PREFIX_CELLS)
def test_prefix_matches_bash_exactly(cmd):
    p, b = _psh(cmd), _bash(cmd)
    assert p.stderr == b.stderr, f"{cmd!r}\n psh={p.stderr!r}\nbash={b.stderr!r}"
    assert p.returncode == b.returncode, cmd


def test_multiline_line_number_matches_bash():
    # The `line N:` counter must track the failing command across lines.
    cmd = "echo a\necho b\ntrap -x\ncd /nonexistent_zz_99"
    p, b = _psh(cmd), _bash(cmd)
    assert p.stderr == b.stderr, f"psh={p.stderr!r}\nbash={b.stderr!r}"


def test_usage_line_stays_unprefixed_like_bash():
    # The dual-line shape: prefixed runtime error, then the bare usage line.
    p, b = _psh("trap -x"), _bash("trap -x")
    plines, blines = p.stderr.splitlines(), b.stderr.splitlines()
    assert plines[0] == blines[0] == "psh: line 1: trap: -x: invalid option"
    assert plines[1] == blines[1]  # `trap: usage: ...`, no location prefix
    assert not plines[1].startswith("psh: line")
