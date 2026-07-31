"""The ALIAS route to a non-executable here-document (round-8, ruling R15-A).

THE AXIS, and why eight rounds of verification did not vary it. An alias is
substituted AFTER the line has been lexed. So when an alias expands to
something containing `<<EOF`, the heredoc operator enters the token stream
having never passed through heredoc collection, and the parser builds a plain
`Redirect` carrying a heredoc operator type with no body -- precisely the value
that ruling R9-B called "synthetically constructible only" and that every
offender guard in `tests/unit/io_redirect/test_heredoc_executable_type.py`
hand-builds. The premise was wrong; ordinary user input reaches the arm.

WHAT THIS FAMILY DOES, measured at both SHAs and against the oracle
(tmp/r2-5-probes/alias_heredoc_axis.py, rescued at ceremony -- byte-exact
scripts, discriminator per tree, bash 5.2.26, 7 shapes x 3 channels x 2 parsers
x 2 trees):

* bash COLLECTS the body at alias-expansion time and runs the command with it.
* psh cannot, at either SHA. It reports the limitation and then reads the body
  lines as commands. **This is a DECLARED DIVERGENCE from bash, not a move
  toward it**, and closing it is real feature work (collecting a body at
  expansion time) recorded as a successor row -- not endgame scope.

WHAT CHANGED base -> tip, which is the part that had to be declared:

* PLAIN (`cat <<EOF`), DIGIT (`cat 0<<EOF`) and the BUILTIN-STREAM twin
  (`read x <<EOF`): base behaved the SAME WAY -- error, then body lines as
  commands, rc 0. Only the stderr TEXT changed, as an inherent consequence of
  the sanctioned late-discovery-site replacement. Record-only; asserted here as
  outcome-identity plus the new user-facing wording.
* NAMED-FD (`{v}<<EOF`, `{v}<<-EOF`): base ABORTED the script (rc 2, nothing
  after ran) because it could not lex the spelling at all -- the abort was an
  artifact of the missing feature, not a policy. Tip continues, uniform with
  the rest of the family. RED ON BASE; pinned per channel and parser.

The scripts need `shopt -s expand_aliases`: aliases are off in non-interactive
shells, and that shopt is what makes this axis reachable from a script at all.
"""
import pathlib
import re
import tempfile

import pytest
from shell_oracle import Completed, is_comparable, run_bash, run_psh

_PRE = "shopt -s expand_aliases\n"

# THE USER-VISIBLE CONTRACT is measured with strict-errors OFF, which is the
# CLI default; the suite turns it ON globally (conftest), and under it two of
# the four arms behave differently. Measured, both settings, all four shapes:
#
#   arm                       strict=0            strict=1
#   `cat <<EOF`   (fd)        message, rc 0, on   message, rc 0, on
#   `cat 0<<EOF`  (fd)        message, rc 0, on   message, rc 0, on
#   `true {v}<<`  (var_fd)    message, rc 0, on   TRACEBACK, rc 1, stops
#   `read x <<`   (builtin)   message, rc 0, on   TRACEBACK, rc 1, stops
#
# So the arms are uniform for USERS and asymmetric under the strict-errors
# harness, because `NonExecutableRedirectError` derives from `RuntimeError`
# (the strict-errors-LOUD class) and only two of the four raise sites sit
# inside a catching frame. Now that round 8 has established the shape is
# reachable from ORDINARY INPUT, that classification is arguably wrong for this
# route -- a real design question, DECLARED in the ledger as a successor row
# rather than changed at the endgame of the slot. These rows pin what a user
# gets, per the project's own rule that a test deliberately driving an internal
# exception sets strict-errors off explicitly (psh/core/CLAUDE.md).
_USER_ENV = {"PSH_STRICT_ERRORS": "0"}

# (label, script). Bodies are `hello` + terminator so a body-line-as-command is
# visible as `hello: command not found`, and every script ends with a marker so
# "did the shell carry on?" is observable rather than inferred.
_RECORD_ONLY = [
    ("alias_plain", _PRE + 'alias foo="cat <<EOF"\nfoo\nhello\nEOF\necho AFTER\n'),
    ("alias_digit", _PRE + 'alias foo="cat 0<<EOF"\nfoo\nhello\nEOF\necho AFTER\n'),
    ("alias_builtin_read", _PRE + 'alias r="read x <<EOF"\nr\nhello\nEOF\necho AFTER\n'),
]

_RED_ON_BASE = [
    ("alias_var_fd", _PRE + 'alias foo="true {v}<<EOF"\nfoo\nhello\nEOF\necho AFTER\n'),
    ("alias_var_fd_strip", _PRE + 'alias foo="true {v}<<-EOF"\nfoo\nhello\nEOF\necho AFTER\n'),
]

_CONTROLS = [
    # The same here-document NOT introduced by an alias: collection happens,
    # a HeredocRedirect is built, no arm is reached, psh == bash.
    ("direct_heredoc", _PRE + 'cat <<EOF\nhello\nEOF\necho AFTER\n'),
    # An alias with no here-document: isolates "alias" from "alias introducing
    # a heredoc operator", so a regression in alias handling generally cannot
    # hide inside these rows.
    ("alias_no_heredoc", _PRE + 'alias foo="echo hi"\nfoo\necho AFTER\n'),
]

_ALL = _RECORD_ONLY + _RED_ON_BASE
_PARSERS = ("rd", "combinator")
_CHANNELS = ("dash_c", "stdin", "script")


def _run_pair(script, channel, parser, tmp_path):
    if channel == "dash_c":
        return (run_psh(["--norc", "--parser", parser, "-c", script],
                        env=_USER_ENV),
                run_bash(["--norc", "-c", script]))
    if channel == "stdin":
        return (run_psh(["--norc", "--parser", parser], stdin_data=script,
                        env=_USER_ENV),
                run_bash(["--norc"], stdin_data=script))
    with tempfile.TemporaryDirectory() as d:
        pp = pathlib.Path(d) / "psh_case.sh"
        bp = pathlib.Path(d) / "bash_case.sh"
        pp.write_text(script)
        bp.write_text(script)
        return (run_psh(["--norc", "--parser", parser, str(pp)],
                        env=_USER_ENV),
                run_bash(["--norc", str(bp)]))


@pytest.mark.parametrize("label,script", _ALL, ids=[s[0] for s in _ALL])
@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("parser", _PARSERS)
def test_alias_heredoc_outcome_is_report_and_carry_on(label, script, channel,
                                                      parser, tmp_path):
    """THE OUTCOME half, split from the MESSAGE half on purpose.

    The split makes this file's own base status prove the classification the
    ledger claims, instead of asking a reader to take it on trust:

    * for `alias_plain` / `alias_digit` / `alias_builtin_read` these
      assertions are GREEN ON BASE -- base already reported an error and ran
      on, so the outcome really is base-identical and only the wording moved;
    * for `alias_var_fd` / `alias_var_fd_strip` they are RED ON BASE -- base
      aborted the script with rc 2 and never reached `AFTER`.

    A differential is the wrong instrument for this family either way: psh and
    bash genuinely disagree (see the divergence row below), so agreement cannot
    be asserted. What is worth protecting is psh's own contract -- do not open
    a file named after the delimiter, and carry on to the next command.
    """
    psh, _bash = _run_pair(script, channel, parser, tmp_path)
    assert is_comparable(psh), psh
    assert isinstance(psh, Completed), psh
    assert psh.returncode == 0, (label, channel, parser, psh.returncode)
    assert "AFTER" in psh.stdout, (label, channel, parser, psh.stdout)


@pytest.mark.parametrize("label,script", _ALL, ids=[s[0] for s in _ALL])
@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("parser", _PARSERS)
def test_alias_heredoc_reports_the_limitation(label, script, channel, parser,
                                              tmp_path):
    """THE MESSAGE half -- red on base for EVERY shape, including the
    record-only ones, because the wording is new at tip (round-8 NIT 1)."""
    psh, _bash = _run_pair(script, channel, parser, tmp_path)
    assert isinstance(psh, Completed), psh
    assert "here-document" in psh.stderr, (label, channel, parser, psh.stderr)


@pytest.mark.parametrize("label,script", _ALL, ids=[s[0] for s in _ALL])
@pytest.mark.parametrize("parser", _PARSERS)
def test_the_alias_message_is_written_for_a_user(label, script, parser):
    """Round-8 blocker 2: the message used to end with a false assurance
    ("Every live parse path builds a HeredocRedirect") and to show a Python
    repr. A user who typed an alias must learn WHICH construct is unsupported.

    Asserted: the message names aliases as the cause and says what to do
    instead. Asserted ABSENT: the falsified assurance, and the `Redirect(...)`
    repr that leaked the internal value shape into user-facing stderr.
    """
    psh = run_psh(["--norc", "--parser", parser, "-c", script],
                  env=_USER_ENV)
    assert isinstance(psh, Completed), psh
    assert "ALIAS" in psh.stderr, (label, parser, psh.stderr)
    assert "Write the here-document directly" in psh.stderr, (label, parser,
                                                              psh.stderr)
    assert "Every live parse path" not in psh.stderr, (label, parser,
                                                       psh.stderr)
    assert "Redirect(type=" not in psh.stderr, (label, parser, psh.stderr)


@pytest.mark.parametrize("label,script", _CONTROLS,
                         ids=[s[0] for s in _CONTROLS])
@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("parser", _PARSERS)
def test_controls_are_unaffected_and_match_bash(label, script, channel, parser,
                                                tmp_path):
    """NON-VACUITY. A here-document that is NOT alias-introduced, and an alias
    that introduces no here-document, both agree with bash exactly. Without
    these rows a regression that broke aliases generally, or here-documents
    generally, would still satisfy every row above."""
    psh, bash = _run_pair(script, channel, parser, tmp_path)
    assert is_comparable(psh) and is_comparable(bash), (psh, bash)
    assert isinstance(psh, Completed) and isinstance(bash, Completed)
    assert psh.returncode == bash.returncode, (label, channel, parser)
    assert psh.stdout == bash.stdout, (label, channel, parser, psh.stdout,
                                       bash.stdout)


@pytest.mark.parametrize("label,script", _ALL, ids=[s[0] for s in _ALL])
@pytest.mark.parametrize("parser", _PARSERS)
def test_divergence_alias_heredoc_body_is_not_collected(label, script, parser):
    """DECLARED DIVERGENCE FROM BASH -- the campaign's divergence-pin
    convention, so the successor that fixes it flips a named test.

    bash substitutes the alias and then collects the here-document body, so it
    runs the command with the body attached. psh substitutes after the lex, so
    the body was never gathered: it reports the limitation and reads the body
    lines as commands. Closing this means collecting bodies at alias-expansion
    time -- real feature work, out of remediation 2.5's scope, recorded as a
    successor row.

    This row asserts the DIVERGENCE, not the agreement. When the successor
    lands, this test must go red; that is its purpose.
    """
    psh = run_psh(["--norc", "--parser", parser, "-c", script],
                  env=_USER_ENV)
    bash = run_bash(["--norc", "-c", script])
    assert isinstance(psh, Completed) and isinstance(bash, Completed)
    # bash: silent, body consumed by the command.
    assert not re.search(r"hello: (command )?not found", bash.stderr), bash.stderr
    # psh: body line escapes as a command, and the limitation is reported.
    assert "here-document" in psh.stderr, (label, parser, psh.stderr)
    assert re.search(r"hello.*not found", psh.stderr), (label, parser,
                                                        psh.stderr)
