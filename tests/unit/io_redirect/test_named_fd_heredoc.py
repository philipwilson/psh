"""Named-fd here-documents `{v}<<EOF` (round-2 blocker R7-A).

THE REGRESSION THIS PINS. Slot 2.5 made the LEXER the only decider of
heredoc-ness. The retired text-level regex scanner knew the `{v}<<` spelling;
the lexer did not — its named-fd recognizer's operator table had `>>` but no
`<<`, so `{v}<<EOF` lexed as `{v}<` plus a separate `<`, no here-document was
registered, and the session called the line COMPLETE. Interactively that meant
the BODY LINES EXECUTED AS COMMANDS where base and bash both hold the line open.

The lesson, recorded because it generalises: the corpora varied what the FIX
changed (heredoc spellings, quoting, context, options) but not what the DELETED
DECIDER used to decide. The regex's input space included `{v}<<`; the fd-kind
axis had only ever been varied by DIGIT. When a decider is removed, ITS input
space is the claim's universe.

WHAT IS PINNED, and the honest status of each half:

* DETECTION — restored to base behaviour: the line is held open and the body is
  never executed as commands. Base did this too (via the regex), so "restored"
  is the honest word for this half and only this half.
* EXECUTION — an IMPROVEMENT BEYOND BASE, never a restoration. Base could not
  RUN any of these: it failed at parse time with `Expected file name`. psh now
  matches bash end to end, allocating a descriptor and storing its number in
  the variable. That covers `{v}<<`, `{v}<<-` AND `{v}<<<` — the here-string
  spelling was missed in round 2 and closed in round 3; the structural guard
  against another sibling-table gap is
  tests/unit/lexer/test_fd_prefix_table_parity.py.

ORACLE: bash, differential, same host, same bytes, via the typed runner.
Non-interactive half; the terminal half is the `named_fd_*` rows of
tests/system/interactive/test_heredoc_detection_interactive_pty.py.
"""
import pytest
from shell_oracle import Completed, is_comparable, resolve_bash, run_bash, run_psh

_ORACLE = resolve_bash()

# `true`/`cat <&$v` rather than a bare `cat`: with the body on fd {v}, a bare
# `cat` still reads STDIN and would block — a hang is a probe fault, not a
# shell answer.
_ROWS = [
    ("plain", "true {v}<<EOF\nbody\nEOF\necho RC=$?\n"),
    ("strip", "true {v}<<-EOF\n\tbody\n\tEOF\necho RC=$?\n"),
    ("quoted", "true {v}<<'EOF'\nbody $NOPE\nEOF\necho RC=$?\n"),
    ("exec_then_read", "exec {v}<<EOF\nhello\nEOF\ncat <&$v\necho RC=$?\n"),
    ("inline_read", "{v}<<EOF cat <&$v\nhello\nEOF\n"),
    # HERE-STRING on the named fd (round-3 blocker R9-A). The digit-fd table
    # has had `<<<` all along; the named-fd table did not, so `{v}<<<w`
    # parse-errored while `0<<<w` worked. Same improvement-beyond-base status
    # as the heredoc forms: base could not run it at all.
    ("herestring", "true {v}<<<hello\necho RC=$?\n"),
    ("herestring_exec", "exec {v}<<<hello\ncat <&$v\necho RC=$?\n"),
    ("herestring_fd", "true {v}<<<hello\necho FD=$v\n"),
    # The fd NUMBER is compared against bash's own rather than pinned to a
    # literal: bash allocates the LOWEST FREE fd >= 10, which depends on what
    # descriptors the shell holds, so a hard-coded 10 could red on the Linux
    # nightly for something that is not a psh defect (ruling R8-A).
    ("fd_number", "true {v}<<EOF\nbody\nEOF\necho FD=$v\n"),
    # Control: a named fd with ONE `<` must stay an ordinary redirect, so a fix
    # that over-matched would fail here.
    ("plain_redirect_control", "exec {v}</dev/null\necho FD=$v\n"),
]


def _both(script, parser):
    psh = run_psh(["--norc", "--parser", parser, "-c", script])
    bash = run_bash(["--norc", "-c", script])
    assert is_comparable(psh) and is_comparable(bash), (psh, bash)
    assert isinstance(psh, Completed) and isinstance(bash, Completed)
    return psh, bash


@pytest.mark.parametrize("label,script", _ROWS, ids=[r[0] for r in _ROWS])
@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_named_fd_heredoc_matches_bash(label, script, parser):
    psh, bash = _both(script, parser)
    assert psh.stdout == bash.stdout, (label, psh.stdout, bash.stdout)
    assert psh.returncode == bash.returncode, (label, psh.returncode,
                                               bash.returncode)
    # The body must NEVER surface as a command — that was the regression.
    assert "command not found" not in psh.stderr, (label, psh.stderr[:300])


@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_the_allocated_fd_obeys_bash_s_semantics(parser):
    """SEMANTICS, not a magic number: the variable holds a descriptor >= 10.
    Portable by construction — independent of what the host shell holds open."""
    psh, _ = _both("true {v}<<EOF\nbody\nEOF\necho FD=$v\n", parser)
    assert psh.stdout.startswith("FD="), psh.stdout
    assert int(psh.stdout.split("=", 1)[1].strip()) >= 10, psh.stdout
