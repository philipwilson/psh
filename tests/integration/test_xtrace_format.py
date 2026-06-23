"""`set -x` xtrace formatting (reappraisal #14 Tier 2).

bash single-quotes any traced word that needs it (`echo "a b"` -> `+ echo 'a b'`,
`[ 0 -lt 2 ]` -> `+ '[' 0 -lt 2 ']'`, empty -> `''`), traces `for`/`case`
compound headers, and traces prefix/pure assignments with the VALUE quoted. psh
previously joined trace words unquoted and omitted the compound headers. Verified
against bash 5.2.

Deferred (flat-string AST limitations, documented): the `[[ ... ]]` test command
is not traced, and a QUOTED for/case item is shown single-quoted (`'a b'`) where
bash echoes the source double-quote style (`"a b"`) — both semantically
equivalent.
"""

import subprocess
import sys

import pytest


def _trace(cmd, runner):
    """Return the stderr (xtrace) lines, dropping any non-`+` noise."""
    r = runner(cmd)
    return [ln for ln in r.stderr.splitlines() if ln.startswith('+')]


def _psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def _bash(cmd):
    return subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)


@pytest.mark.parametrize("cmd", [
    # arg quoting
    'set -x; echo "a b" c',
    'set -x; echo "" x',
    'set -x; x="a;b"; echo "$x"',
    'set -x; echo hello world',
    'set -x; echo "a|b" "c&d"',
    'set -x; echo "*" "?"',
    # test-command brackets get quoted
    'set -x; [ 0 -lt 2 ]',
    'set -x; n=0; while [ $n -lt 1 ]; do n=1; done',
    # compound headers (unquoted items match exactly)
    'set -x; for i in 1 2; do :; done',
    'set -x; case x in x) :;; esac',
    'set -x; if true; then :; fi',
    # assignments: value quoted; prefix traced before the command
    'set -x; x="a b"',
    'set -x; x=5 echo hi',
    'set -x; A=1 B=2 echo x',
    # nested compound
    'set -x; if true; then for i in a; do :; done; fi',
])
def test_xtrace_matches_bash(cmd):
    assert _trace(cmd, _psh) == _trace(cmd, _bash), cmd
