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

* DETECTION — restored to base behaviour: the line is held open and the body
  is never executed as commands. Base did this too (via the regex scanner), so
  "restored" is the honest word for this half and only this half.
* EXECUTION — an IMPROVEMENT BEYOND BASE, never a restoration. Base could not
  RUN any of these: it failed at parse time with `Expected file name`. psh now
  matches bash end to end — the body lands on a shell-allocated descriptor,
  the number is stored in the variable, and `exec {v}<<EOF` followed by
  `cat <&$v` reads the body back.

Non-interactive half of the pin; the terminal half is the `named_fd_*` rows of
tests/system/interactive/test_heredoc_detection_interactive_pty.py.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

TREE_ROOT = str(Path(__file__).resolve().parents[3])
# The blessed oracle through the ONE resolver -- never a hardcoded path
# (tests/harness/shell_oracle.py#resolve_bash; the static ratchet
# test_bash_oracle_resolution.py enforces this and caught the first
# version of both these files).
from shell_oracle import resolve_bash  # noqa: E402

_ORACLE = resolve_bash()


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
    ("inline_read", b"{v}<<EOF cat <&$v\nhello\nEOF\n", "hello\n"),
]

# NOTE what is deliberately NOT in the table above: an exact `FD=10` row. bash
# allocates the LOWEST FREE fd >= 10, which depends on what descriptors the
# shell happens to be holding, so a literal `FD=10` could red on the Linux
# nightly and would be a false alarm of my own making (ruling R8-A). The fd is
# pinned by SEMANTICS below (>= 10, and readable), plus a same-host
# differential against bash's own number.
_FD_SCRIPT = b"true {v}<<EOF\nbody\nEOF\necho FD=$v\n"


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
    blessed oracle prints for the same bytes. The oracle is resolved at import
    and raises there if absent -- loud, never a silent skip."""
    script_path = tmp_path / "oracle.sh"
    script_path.write_bytes(script)
    result = subprocess.run([_ORACLE.path, "--norc", str(script_path)],
                            capture_output=True, text=True, cwd=str(tmp_path),
                            stdin=subprocess.DEVNULL, timeout=30)
    assert result.stdout == expected, (label, result.stdout)


def test_a_named_fd_with_one_less_than_is_still_a_plain_redirect(tmp_path):
    """The control: `{v}<file` must NOT become a here-document. A fix that
    over-matched would break ordinary named-fd input redirection."""
    result = _run_psh(b"exec {v}</dev/null\necho FD=$v\n", tmp_path, "rd")
    assert result.returncode == 0, result.stderr[:400]
    # Semantics, not a literal — same Linux-nightly reasoning as above.
    assert result.stdout.startswith("FD="), result.stdout
    assert int(result.stdout.split("=", 1)[1].strip()) >= 10, result.stdout


@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_the_allocated_fd_obeys_bash_s_semantics(parser, tmp_path):
    """SEMANTICS, not a magic number: the variable holds a descriptor >= 10.

    Portable by construction — nothing here depends on which descriptors the
    host shell happens to hold.
    """
    result = _run_psh(_FD_SCRIPT, tmp_path, parser)
    assert result.returncode == 0, result.stderr[:400]
    assert result.stdout.startswith("FD="), result.stdout
    assert int(result.stdout.split("=", 1)[1].strip()) >= 10, result.stdout


@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_the_allocated_fd_matches_the_oracle_on_this_host(parser, tmp_path):
    """DIFFERENTIAL: psh's number equals BASH's number for the same script,
    measured on the SAME host in the same run.

    This is how the exact allocation is pinned without hard-coding it: if a
    platform allocates 11, both shells report 11 and the comparison still
    holds. A literal expectation would have made the Linux nightly red for a
    difference that is not a psh defect.
    """
    script = tmp_path / "fd.sh"
    script.write_bytes(_FD_SCRIPT)
    oracle = subprocess.run([_ORACLE.path, "--norc", str(script)],
                            capture_output=True, text=True, cwd=str(tmp_path),
                            stdin=subprocess.DEVNULL, timeout=30)
    result = _run_psh(_FD_SCRIPT, tmp_path, parser)
    assert result.stdout == oracle.stdout, (result.stdout, oracle.stdout)
