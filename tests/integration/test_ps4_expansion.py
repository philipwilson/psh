"""PS4 (the `set -x` trace prefix) is expanded like bash.

R18 T2-E (M-s1): psh emitted PS4 verbatim at every xtrace site, so the
user-guide example `PS4='+ line ${LINENO}: '` printed the literal `${LINENO}`.
bash performs parameter, command, and arithmetic expansion on PS4 on each use
(and suppresses tracing DURING that expansion, or `PS4='$(cmd) '` would recurse
forever). All five xtrace emission sites now route through
`ExpansionManager.expand_ps4()`. Pinned against bash 5.2.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, 'PYTHONPATH': str(REPO_ROOT)}

# The campaign oracle is real bash 5.2; fall back to PATH `bash` otherwise.
BASH = '/opt/homebrew/bin/bash' if os.path.exists('/opt/homebrew/bin/bash') \
    else shutil.which('bash')


def _psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=10, env=ENV)


def _bash(cmd):
    return subprocess.run([BASH, '-c', cmd],
                          capture_output=True, text=True, timeout=10)


def test_ps4_expands_lineno():
    cmd = "PS4='+ ${LINENO}: '\nset -x\necho a\necho b"
    r = _psh(cmd)
    assert '+ 3: echo a' in r.stderr
    assert '+ 4: echo b' in r.stderr


def test_ps4_command_substitution_no_recursion():
    # A command substitution in PS4 must expand once (untraced), not recurse.
    r = _psh("PS4='[$(echo TAG)] '\nset -x\necho a")
    assert r.returncode == 0
    assert '[TAG] echo a' in r.stderr
    assert 'recursion' not in r.stderr.lower()


def test_ps4_arithmetic_expansion():
    r = _psh("PS4='$((1+1))> '\nset -x\n:")
    assert '2> :' in r.stderr


def test_ps4_default_unchanged():
    r = _psh("set -x\necho a")
    assert '+ echo a' in r.stderr


def test_ps4_static_value_unchanged():
    r = _psh("PS4='DEBUG: '\nset -x\necho a")
    assert 'DEBUG: echo a' in r.stderr


@pytest.mark.skipif(not BASH, reason="no bash available")
@pytest.mark.parametrize("cmd", [
    "PS4='+ ${LINENO}: '\nset -x\necho a\necho b",
    "PS4='[$(echo TAG)] '\nset -x\necho a",
    "PS4='$((1+1))> '\nset -x\n:",
    "set -x\necho a",
])
def test_ps4_stderr_matches_bash(cmd):
    assert _psh(cmd).stderr == _bash(cmd).stderr, cmd
