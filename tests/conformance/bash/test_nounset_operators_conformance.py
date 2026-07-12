"""`set -u` (nounset) with parameter-expansion operators (R14.B).

bash errors ("unbound variable", exit 127) when a VALUE-substituting operator
is applied to an unset variable — ${#x}, ${x#p}, ${x%p}, ${x/a/b}, ${x^^},
${x:off:len}, ${x@Q}, etc. The set-testing operators (${x-d}, ${x:-d}, ${x=d},
${x:=d}, ${x+d}, ${x:+d}) are exempt (they handle unset themselves), and an
unset ARRAY ELEMENT (${#arr[5]}) is bash's deliberate exception (no error).
psh previously enforced nounset only on the plain ${x} form, so every operator
form silently treated unset as empty — this pins the fix.
"""

import subprocess
import sys

import pytest
from conformance_framework import ConformanceTest


def _exit(cmd):
    """(psh_rc, bash_rc) for `cmd` under a non-interactive shell."""
    psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                         capture_output=True, text=True)
    bash = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)
    return psh.returncode, bash.returncode


# Operators that MUST raise "unbound variable" (exit 127) on an unset scalar.
ERRORING = [
    'set -u; echo ${#x}',          # length
    'set -u; echo ${x#p}',         # prefix removal
    'set -u; echo ${x##*/}',
    'set -u; echo ${x%p}',         # suffix removal
    'set -u; echo ${x%%*}',
    'set -u; echo ${x/a/b}',       # substitution
    'set -u; echo ${x//a/b}',
    'set -u; echo ${x^^}',         # case mod
    'set -u; echo ${x,,}',
    'set -u; echo ${x:0:1}',       # substring
    'set -u; echo ${x@Q}',         # transform
]

# Forms that MUST NOT error (exit 0).
EXEMPT = [
    'set -u; echo ${x-d}',
    'set -u; echo ${x:-d}',
    'set -u; echo ${x=d}',
    'set -u; echo ${x:=d}',
    'set -u; echo ${x+d}',
    'set -u; echo ${x:+d}',
    'set -u; x=; echo ${#x}',      # set-but-empty: not unset
    'set -u; x=hi; echo ${x#h}',   # set: fine
    'set -u; arr=(1); echo ${#arr[5]}',  # unset array element: bash exception
]


@pytest.mark.parametrize('cmd', ERRORING)
def test_nounset_operator_errors(cmd):
    psh_rc, bash_rc = _exit(cmd)
    assert psh_rc == bash_rc == 127, f"{cmd}: psh={psh_rc} bash={bash_rc}"


@pytest.mark.parametrize('cmd', EXEMPT)
def test_nounset_operator_exempt(cmd):
    psh_rc, bash_rc = _exit(cmd)
    assert psh_rc == bash_rc == 0, f"{cmd}: psh={psh_rc} bash={bash_rc}"


class TestNounsetExemptOutput(ConformanceTest):
    """The exempt forms also produce identical OUTPUT (not just exit code)."""

    def test_default_value(self):
        self.assert_identical_behavior('set -u; echo ${x:-fallback}')

    def test_alternative_unset(self):
        self.assert_identical_behavior('set -u; echo "[${x+set}]"')
