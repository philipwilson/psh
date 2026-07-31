"""Named-fd here-documents `{v}<<EOF` (round-2 blocker R7-A).

THE REGRESSION THIS PINS. Slot 2.5 made the LEXER the only decider of
heredoc-ness. The retired text-level regex scanner knew the `{v}<<` spelling;
the lexer did not — its named-fd recognizer's operator table had `>>` but no
`<<`, so `{v}<<EOF` lexed as `{v}<` plus a separate `<`, no here-document was
registered, and the session called the line COMPLETE. Interactively that meant
the BODY LINES EXECUTED AS COMMANDS (`body: command not found`) where base and
bash both hold the line open.

The lesson, recorded because it generalises: the corpora varied what the FIX
changed (heredoc spellings, quoting, context, options) but not what the DELETED
DECIDER used to decide. The regex's input space included `{v}<<`; the fd-kind
axis had only ever been varied by DIGIT. When a decider is removed, ITS input
space is the claim's universe.

WHAT IS PINNED HERE, and the honest status of each:

* the REGRESSION FIX — a named-fd heredoc is detected, its body is not
  executed. Base parity restored.
* an IMPROVEMENT BEYOND BASE, declared: base could not RUN these at all (parse
  error, "Expected file name"); psh now matches bash end to end — the body
  lands on a shell-allocated fd >= 10, the number is stored in the variable,
  and `exec {v}<<EOF` followed by `cat <&$v` reads the body. Measured against
  bash 5.2.26, which allocates fd 10 for the same scripts.

Non-interactive half of the pin; the terminal half is the `named_fd_*` rows of
tests/system/interactive/test_heredoc_detection_interactive_pty.py.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

TREE_ROOT = str(Path(__file__).resolve().parents[3])
ORACLE = "/opt/homebrew/bin/bash"


def _run_psh(script_bytes, tmp_path, parser):
    script = tmp_path / "probe.sh"
    script.write_bytes(script_bytes)
    env = dict(os.environ, PYTHONPATH=TREE_ROOT)
    which = subprocess.run(
        [sys.executable, "-c", "import psh; print(psh.__file__)"],
        capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=30)
    assert which.stdout.startswith(TREE_ROOT), \
        f"imported the wrong psh: {which.stdout!r}"
    return subprocess.run(
        [sys.executable, "-m", "psh", "--norc", "--parser", parser,
         str(script)],
        capture_output=True, text=True, cwd=str(tmp_path), env=env,
        stdin=subprocess.DEVNULL, timeout=30)


# (label, script, expected stdout)
# `true`/`cat <&$v` rather than a bare `cat`: with the body on fd {v}, a bare
# `cat` still reads STDIN and would block — a hang is a probe fault, not a
# shell answer.
_ROWS = [
    ("plain", b"true {v}<<EOF\nbody\nEOF\necho RC=$?\n", "RC=0\n"),
    ("strip", b"true {v}<<-EOF\n\tbody\n\tEOF\necho RC=$?\n", "RC=0\n"),
    ("quoted", b"true {v}<<'EOF'\nbody $NOPE\nEOF\necho RC=$?\n", "RC=0\n"),
    ("exec_then_read", b"exec {v}<<EOF\nhello\nEOF\ncat <&$v\necho RC=$?\n",
     "hello\nRC=0\n"),
    ("fd_number_allocated", b"true {v}<<EOF\nbody\nEOF\necho FD=$v\n",
     "FD=10\n"),
    ("inline_read", b"{v}<<EOF cat <&$v\nhello\nEOF\n", "hello\n"),
]


@pytest.mark.parametrize("label,script,expected", _ROWS,
                         ids=[r[0] for r in _ROWS])
@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_named_fd_heredoc_matches_bash(label, script, expected, parser,
                                       tmp_path):
    result = _run_psh(script, tmp_path, parser)
    assert result.returncode == 0, (label, result.stderr[:400])
    assert result.stdout == expected, (label, result.stdout, result.stderr[:300])
    # The body must NEVER surface as a command — that was the regression.
    assert "command not found" not in result.stderr, (label, result.stderr[:300])


@pytest.mark.parametrize("label,script,expected", _ROWS,
                         ids=[r[0] for r in _ROWS])
def test_the_expectations_are_bash_s_own_answers(label, script, expected,
                                                 tmp_path):
    """The expected values above are not hand-reasoned: they are what the
    blessed oracle prints for the same bytes. Skipped rather than silently
    weakened if the oracle is unavailable."""
    if not Path(ORACLE).exists():                            # pragma: no cover
        pytest.skip(f"oracle {ORACLE} not present")
    script_path = tmp_path / "oracle.sh"
    script_path.write_bytes(script)
    result = subprocess.run([ORACLE, "--norc", str(script_path)],
                            capture_output=True, text=True, cwd=str(tmp_path),
                            stdin=subprocess.DEVNULL, timeout=30)
    assert result.stdout == expected, (label, result.stdout)


def test_a_named_fd_with_one_less_than_is_still_a_plain_redirect(tmp_path):
    """The control: `{v}<file` must NOT become a here-document. A fix that
    over-matched would break ordinary named-fd input redirection."""
    result = _run_psh(b"exec {v}</dev/null\necho FD=$v\n", tmp_path, "rd")
    assert result.returncode == 0, result.stderr[:400]
    assert result.stdout == "FD=10\n", (result.stdout, result.stderr[:300])
