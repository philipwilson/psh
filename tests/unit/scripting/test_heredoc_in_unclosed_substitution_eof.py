"""DECLARED delta: heredoc inside an UNCLOSED `$(` at end of input (slot 2.5).

A pathological, EOF-truncated shape:

    echo $(cat <<E
    body
    <EOF>

Deriving the session's heredoc answer from the LEXER (slot 2.5, #22 MEDIUM-3)
changed one thing here, and only here. Before, the text-level regex scanner saw
`<<E`, so the session pushed a pending heredoc and `ParseSession.flush` took
its heredoc branch, which keeps the buffer VERBATIM (a here-document delimited
by end-of-file owns its trailing newline). Now the lex FAILS on the unclosed
`$(` before any heredoc can be registered, so no heredoc is pending and flush
takes the ordinary branch, which strips trailing separators. The buffered text
echoed back in the parse-error diagnostic therefore loses one trailing newline.

WHAT DOES NOT CHANGE: the exit status (2) and stdout (empty) are identical, and
so is the error CLASS -- an unclosed-command-substitution parse error. Only the
quoted source fragment inside the message differs by that newline.

WHY THIS IS DECLARED RATHER THAN QUIETLY ACCEPTED: brief §7 requires any
behavior delta beyond the chartered fix to be declared and pinned, improvement
or not. This one is neither an improvement nor a regression relative to bash --
bash answers this shape completely differently at BOTH SHAs (it warns about the
EOF-delimited here-document, then reports an unexpected EOF looking for `)`),
so there is no "moves toward the oracle" claim to make. It is pinned so the
shape has an owner and a future change to it is deliberate.

BOUNDED, measured base-vs-tip: plain unclosed `$(`, a plain unterminated
heredoc, and an unclosed quote are all byte-identical across the change. The
delta needs the heredoc to be INSIDE the unclosed substitution.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

TREE_ROOT = str(Path(__file__).resolve().parents[3])


def _run(script_bytes, tmp_path):
    script = tmp_path / "probe.sh"
    script.write_bytes(script_bytes)
    env = dict(os.environ, PYTHONPATH=TREE_ROOT)
    which = subprocess.run(
        [sys.executable, "-c", "import psh; print(psh.__file__)"],
        capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=30)
    assert which.stdout.startswith(TREE_ROOT), \
        f"imported the wrong psh: {which.stdout!r}"
    return subprocess.run(
        [sys.executable, "-m", "psh", "--norc", str(script)],
        capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=30)


def test_heredoc_inside_unclosed_substitution_reports_without_trailing_newline(
        tmp_path):
    """THE declared delta. The quoted fragment ends at the body's last
    character; before slot 2.5 it carried one more newline."""
    result = _run(b"echo $(cat <<E\nbody\n", tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "unclosed command substitution" in result.stderr
    assert "body'" in result.stderr, result.stderr
    assert "body\n'" not in result.stderr, result.stderr


@pytest.mark.parametrize("script,expect_rc", [
    (b"echo $(echo x\n", 2),        # unclosed $( with NO heredoc
    (b"cat <<E\nbody\n", 0),        # unterminated heredoc, no substitution
    (b'echo "unclosed\n', 2),       # unclosed quote
])
def test_the_neighbouring_shapes_are_untouched(script, expect_rc, tmp_path):
    """The bound on the delta: it needs the heredoc to be INSIDE the unclosed
    substitution. These three were byte-identical across base and tip when
    measured, so a future change that widens the blast radius fails here."""
    result = _run(script, tmp_path)
    assert result.returncode == expect_rc, (script, result.stderr[:300])
