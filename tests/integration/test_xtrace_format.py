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


# The `for VAR in WORDS` header body is rendered ONCE per loop (P7 item 5),
# not once per iteration, but its output must be UNCHANGED. Two invariants
# would break under a naive hoist and are pinned here against bash (full
# stderr, since a dynamic PS4 emits lines that don't start with `+`):
#   - PS4 is re-expanded EVERY iteration (dynamic PS4 must still vary), so
#     the render-once optimization must not hoist the PS4 expansion.
#   - the `xtrace` option is re-checked EVERY iteration, so a body toggling
#     `set +x`/`set -x` mid-loop still suppresses/emits per iteration.
@pytest.mark.parametrize("cmd", [
    # dynamic PS4: re-expanded per iteration -> <0>,<1>,<2>
    "n=0; PS4='<$n>'; set -x; for i in 1 2 3; do n=$((n+1)); done",
    # PS4 with a command substitution: re-run each trace
    "PS4='$(echo P) '; set -x; for i in 1 2; do :; done",
    # body turns xtrace OFF mid-loop: only the first header appears
    'set -x; for i in 1 2 3; do set +x; done',
    # body turns xtrace ON mid-loop: headers appear from the 2nd iteration
    'for i in 1 2 3; do set -x; done',
    # nested loops (inner header body also rendered once per inner loop)
    'set -x; for i in 1 2; do for j in 3 4; do :; done; done',
])
def test_for_header_render_once_preserves_output(cmd):
    assert _psh(cmd).stderr == _bash(cmd).stderr, cmd


def test_for_header_quoted_words_rendered_once():
    # A quoted header word is single-quoted by psh where bash echoes the
    # source double-quote style (a pre-existing, documented divergence — see
    # the module docstring), so pin psh's OWN output. The point here is that
    # the rendered-once header body still shows the quoted word each
    # iteration, byte-identical.
    trace = [ln for ln in _psh('set -x; for i in "a b" c; do :; done')
             .stderr.splitlines() if ln.startswith('+')]
    assert trace == ["+ for i in 'a b' c", "+ :",
                     "+ for i in 'a b' c", "+ :"]
