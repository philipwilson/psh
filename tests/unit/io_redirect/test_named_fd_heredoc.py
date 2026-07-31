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
  matches bash for the COMMAND-BEARING spellings, allocating a descriptor and
  storing its number in the variable. That covers `{v}<<`, `{v}<<-` AND
  `{v}<<<` — the here-string spelling was missed in round 2 and closed in
  round 3; the structural guard against another sibling-table gap is
  tests/unit/lexer/test_fd_prefix_table_parity.py.
* THE NULL-COMMAND SPELLING IS A DECLARED DIVERGENCE (round-8 nit 7). The
  wording above used to say "end to end", which every row in this file
  satisfies only because every row HAS a command word — the axis was never
  varied. With no command, bash performs the redirection and then undoes it,
  leaving the variable unset (`v=[]`); psh keeps the descriptor (`v=[10]`).
  PRE-EXISTING psh semantics rather than a regression: the untouched
  `{v}</dev/null` form behaves identically at BOTH SHAs. What this slot changed
  is that the heredoc spellings reach it at all (base parse-errored). Pinned as
  a divergence below, with that control.

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
    # DEGENERATE rows -- operator present, OPERAND ABSENT (ruling R10-A(3)
    # asked for these in the BATTERY as well as the PTY module; round 5 caught
    # that I had landed only the PTY half).
    ("degenerate_heredoc", "cat {v}<<\necho AFTER\n"),
    ("degenerate_strip", "cat {v}<<-\necho AFTER\n"),
    ("degenerate_herestring", "cat {v}<<<\necho AFTER\n"),
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


# === THE NULL-COMMAND SPELLING: a declared divergence (round-8 nit 7) ========
#
# The axis every row above leaves unvaried: whether the redirection has a
# COMMAND to attach to. bash treats a redirection with no command as performed
# and then undone, so the variable is left unset; psh keeps the allocated
# descriptor. Measured, script channel, stdin </dev/null, bash 5.2.26:
#
#   shape             bash    psh tip   psh base
#   {v}<<EOF ...      v=[]    v=[10]    parse error   <- newly reachable
#   {v}<<<hs          v=[]    v=[10]    parse error   <- newly reachable
#   {v}</dev/null     v=[]    v=[10]    v=[10]        <- CONTROL: pre-existing
#   true {v}<<EOF     v=[10]  v=[10]    parse error   <- command-bearing, agrees
_NULL_COMMAND_ROWS = [
    ("null_cmd_heredoc", '{v}<<EOF\nbody\nEOF\necho "v=[$v]"\n'),
    ("null_cmd_herestring", '{v}<<<hs\necho "v=[$v]"\n'),
]


@pytest.mark.parametrize("label,script", _NULL_COMMAND_ROWS,
                         ids=[r[0] for r in _NULL_COMMAND_ROWS])
@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_divergence_null_command_named_fd_keeps_the_descriptor(label, script,
                                                               parser):
    """DECLARED DIVERGENCE, campaign convention: asserts the DISAGREEMENT so a
    successor that fixes it flips a named test rather than surprising anyone.

    Not a regression introduced here — see the control below — but newly
    REACHABLE through the heredoc spellings this slot added, which is why it is
    declared by this slot rather than left silent.
    """
    psh, bash = _both(script, parser)
    assert bash.stdout.strip() == "v=[]", (label, bash.stdout)
    assert psh.stdout.strip().startswith("v=["), (label, psh.stdout)
    assert psh.stdout.strip() != "v=[]", (label, psh.stdout)


@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_the_null_command_divergence_is_pre_existing(parser):
    """THE CONTROL that makes the row above a DECLARATION rather than an
    accusation: `{v}</dev/null` is a surface this branch never touched, and it
    diverges from bash in exactly the same way. So the semantics are psh's,
    not this slot's; only the reachability is new."""
    psh, bash = _both('{v}</dev/null\necho "v=[$v]"\n', parser)
    assert bash.stdout.strip() == "v=[]", bash.stdout
    assert psh.stdout.strip() != "v=[]", psh.stdout
