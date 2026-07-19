"""Bash-parity: interactive mid-construct syntax errors are IMMEDIATE (I3).

The incremental completeness engine (`parser.session.ParseSession`) must NOT
defer a mid-construct syntax error to structural close — bash reports it on the
offending line (this is the oracle constraint that forces per-feed parsing and
therefore the O(k²) single-open-construct residual; see
`tests/unit/parser/test_session_linearity_i3.py`). These PTY rows LOCK that
behavior as a positive asset: for each row, psh and live bash both emit the
syntax error on the SAME line index, not after the closing keyword.

PTY-driven (both shells over a pseudo-terminal), so this is `serial` and skips
cleanly when pexpect or a suitable bash is unavailable. The deterministic
backbone lives in `test_session_i3.py`
(`test_mid_construct_error_is_invalid_at_the_offending_line`); this test proves
the same classification is what bash actually does interactively.
"""

import os
import sys
from pathlib import Path

import pytest

pexpect = pytest.importorskip("pexpect")

PSH_ROOT = str(Path(__file__).resolve().parents[3])

pytestmark = pytest.mark.serial


def _find_bash():
    for cand in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", "/bin/bash"):
        if os.path.exists(cand):
            return cand
    from shutil import which
    return which("bash")


# (label, lines, offending_index): the line index at which the syntax error
# must appear in BOTH shells (bash PTY-verified during I3 development).
_ROWS = [
    ("then_echo_rparen", ["if true; then echo )"], 0),
    ("top_rparen", ["echo )"], 0),
    ("then_then_rparen", ["if true; then", ")"], 1),
    ("then_done", ["if true; then", "done"], 1),
    ("then_semi_rparen", ["if true; then", "echo a; )"], 1),
]


# Either shell's parse-error diagnostic. bash prints "syntax error near…"; psh
# prints "Parse error (line…): …" (sometimes also "syntax error near…", but the
# `)`-after-`then` case reads "Expected command", so match the "Parse error"
# stem). This test asserts error TIMING parity, not message-wording parity (the
# wording divergence is a separate, documented, campaign-wide psh-vs-bash fact).
_ERROR_RE = r"syntax error|Parse error"


def _error_line_index(child, lines):
    """Send each line; return the index of the first line after which the shell
    printed a parse-error diagnostic, or None if it never did.

    Detection is by the error diagnostic vs a short TIMEOUT rather than by prompt
    matching — the line editors redraw the prompt with cursor-control escapes
    that make prompt matching race-prone, whereas the diagnostic appears in the
    stream only when the shell actually rejects the line (never in a prompt), so
    it is an unambiguous, leftover-immune signal."""
    for i, ln in enumerate(lines):
        child.send(ln + "\r")
        if child.expect([_ERROR_RE, pexpect.TIMEOUT], timeout=3) == 0:
            return i
    return None


def _spawn_psh():
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': '/tmp', 'TERM': 'xterm',
        'PS1': 'PSH1> ', 'PS2': 'PSH2> ',
        'PYTHONUNBUFFERED': '1', 'PYTHONPATH': PSH_ROOT,
    }
    child = pexpect.spawn(
        sys.executable, ['-u', '-m', 'psh', '--norc', '--force-interactive'],
        timeout=10, encoding='utf-8', env=env)
    child.send('\r')
    child.expect('PSH1> ')
    return child


def _spawn_bash(bash):
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': '/tmp', 'TERM': 'xterm',
        'PS1': 'BASH1> ', 'PS2': 'BASH2> ',
    }
    child = pexpect.spawn(
        bash, ['--norc', '-i'], timeout=10, encoding='utf-8', env=env)
    child.expect('BASH1> ')
    return child


@pytest.mark.parametrize("label,lines,offending", _ROWS,
                         ids=[r[0] for r in _ROWS])
def test_mid_construct_error_line_matches_bash(label, lines, offending):
    bash = _find_bash()
    if not bash:
        pytest.skip("no bash available for the parity comparison")

    psh_child = _spawn_psh()
    try:
        psh_idx = _error_line_index(psh_child, lines)
    finally:
        psh_child.close(force=True)

    bash_child = _spawn_bash(bash)
    try:
        bash_idx = _error_line_index(bash_child, lines)
    finally:
        bash_child.close(force=True)

    assert bash_idx == offending, f"bash errored at {bash_idx}, expected {offending}"
    assert psh_idx == bash_idx, (
        f"psh errored at line {psh_idx}, bash at {bash_idx} (must be immediate, "
        f"not deferred to structural close)")
