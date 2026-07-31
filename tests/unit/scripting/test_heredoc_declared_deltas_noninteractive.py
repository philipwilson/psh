"""The NON-INTERACTIVE halves of slot 2.5's declared behaviour deltas (R7-B).

WHY THIS FILE EXISTS, stated plainly because it is a correction. Round 1
declared two behaviour changes as INTERACTIVE-ONLY. That was FALSE. Both also
change `-c`, script-file and stdin behaviour -- exit status, stdout AND stderr
-- and a third, rd-only change rides along.

The false framing survived round 1 because the instrument backing it compared
psh against BASH at each SHA and reported "66/66 agree". Agreement with an
oracle at two points cannot establish IDENTITY between those points: two shells
can agree with bash at both SHAs while psh's own answer changed in ways bash
never sees. The rebuilt instrument (tmp/r2-5-probes/base_tip_identity.py) diffs
psh against ITSELF across the two trees and found 18 non-identical rows.

ORACLE FOR EVERY ROW BELOW: bash, differential, same host, same bytes, through
the typed runner. Every delta moves psh TOWARD bash and stays.

THE THREE DECLARED DELTAS, with their measured base values:

1. `cat <<EOF "abc` / `EOF` / `def"` -- heredoc + unclosed quote on one line.
   base: rc=0, stdout 'MARKER\\n'  (the buffer executed at line 3)
   tip : rc=1, stdout ''           (+ EOF warning)  == bash
   Deriving the heredoc answer from the LEX makes the unclosed-quote outcome
   win, as it does in bash.

2. `cat <<$(x)` / `hi` / `$` -- substitution-bearing delimiter.
   base: stdout 'hi\\n$\\nMARKER\\n'         (delimiter cooked to `$`)
   tip : stdout 'hi\\n$\\necho MARK""ER\\n'  (+ EOF warning)  == bash
   The delimiter is taken literally, so the terminator is `$(x)`; the retired
   regex scanner stopped at `(`.

3. THE rd-ONLY DELTA: at base the recursive-descent parser emitted NO
   unterminated-here-document warning on these shapes while the combinator did.
   At tip BOTH emit it, matching bash. Pinned per-parser, because a per-parser
   difference is invisible to any test that runs one parser.
"""
import pathlib
import re
import tempfile

import pytest
from shell_oracle import Completed, is_comparable, run_bash, run_psh

_SHAPES = [
    ("heredoc_unclosed_dq", 'cat <<EOF "abc\nEOF\ndef"\necho MARK""ER\n'),
    ("subst_delim_dollar", 'cat <<$(x)\nhi\n$\necho MARK""ER\n'),
]

# CLASS-match shapes: psh and bash both report a syntax error and carry on, but
# WORD it differently (they always have -- psh names the construct, bash quotes
# the line). Comparing stderr byte-for-byte here would assert a wording parity
# psh has never had and this slot never claimed, so these rows assert the
# OUTCOME CLASS: an error is reported, and the follow-up command still runs.
#
# Ruling R10-A(6) asked for the degenerate diagnostics to be pinned per
# channel/parser and round 4 dropped that half; R10-B/R11-B is `a[<<]=1`, which
# round 4 framed as INTERACTIVE-ONLY -- the same mis-framing round 2 bounced me
# for. The default assumption is now INVERTED: a delta is ALL-CHANNEL until the
# identity instrument proves otherwise.
_CLASS_SHAPES = [
    ("degenerate_named_heredoc", 'cat {v}<<\necho AFT""ER\n'),
    ("degenerate_named_strip", 'cat {v}<<-\necho AFT""ER\n'),
    ("degenerate_named_herestring", 'cat {v}<<<\necho AFT""ER\n'),
    ("subscript_shift_operator", 'a[<<]=1\necho AFT""ER\n'),
]
_PARSERS = ("rd", "combinator")


def _normalise(text):
    """Compare on the MESSAGE, not on which binary emitted it or which temp
    path the script-file channel happened to use."""
    text = re.sub(r"\S*(?:psh_case|bash_case)\.sh", "<SCRIPT>", text)
    return re.sub(r"^[^\s:]*(?:psh|bash)[^\s:]*:", "<SH>:", text,
                  flags=re.MULTILINE)


@pytest.mark.parametrize("label,script", _SHAPES, ids=[s[0] for s in _SHAPES])
@pytest.mark.parametrize("channel", ["dash_c", "stdin", "script"])
@pytest.mark.parametrize("parser", _PARSERS)
def test_declared_delta_matches_bash_non_interactively(label, script, channel,
                                                       parser, tmp_path):
    """DIFFERENTIAL against the oracle, per channel AND per parser."""
    psh, bash = _run_pair(script, channel, parser, tmp_path)
    assert is_comparable(psh) and is_comparable(bash), (psh, bash)
    assert isinstance(psh, Completed) and isinstance(bash, Completed)
    assert psh.returncode == bash.returncode, (label, channel, parser,
                                               psh.returncode, bash.returncode)
    assert psh.stdout == bash.stdout, (label, channel, parser, psh.stdout,
                                       bash.stdout)
    assert _normalise(psh.stderr) == _normalise(bash.stderr), (
        label, channel, parser, psh.stderr, bash.stderr)


def _run_pair(script, channel, parser, tmp_path):
    """Run the same bytes through psh and bash on one channel."""
    if channel == "dash_c":
        psh = run_psh(["--norc", "--parser", parser, "-c", script])
        bash = run_bash(["--norc", "-c", script])
    elif channel == "stdin":
        psh = run_psh(["--norc", "--parser", parser], stdin_data=script)
        bash = run_bash(["--norc"], stdin_data=script)
    else:
        # SCRIPT-FILE channel (round-3 nit 12: the ledger claimed per-channel
        # coverage while this one was missing). Each shell gets its OWN copy at
        # its own path, and the path is normalised out of diagnostics below, so
        # the comparison is on behaviour rather than on temp-file names.
        with tempfile.TemporaryDirectory() as d:
            pp = pathlib.Path(d) / "psh_case.sh"
            bp = pathlib.Path(d) / "bash_case.sh"
            pp.write_text(script)
            bp.write_text(script)
            psh = run_psh(["--norc", "--parser", parser, str(pp)])
            bash = run_bash(["--norc", str(bp)])
    return psh, bash


@pytest.mark.parametrize("label,script", _SHAPES, ids=[s[0] for s in _SHAPES])
@pytest.mark.parametrize("parser", _PARSERS)
def test_the_eof_warning_is_emitted_by_both_parsers(label, script, parser):
    """The rd-ONLY delta, pinned per-parser.

    At base, `rd` stayed silent on these shapes while `combinator` warned. A
    single-parser test cannot see that, which is why the parser axis is
    explicit here rather than folded into the row above.

    Scoped to _SHAPES: the _CLASS_SHAPES are SYNTAX errors, not unterminated
    here-documents, so no EOF warning is expected or asserted for them.
    """
    psh = run_psh(["--norc", "--parser", parser, "-c", script])
    assert isinstance(psh, Completed), psh
    assert "delimited by end-of-file" in psh.stderr, (label, parser, psh.stderr)


@pytest.mark.parametrize("label,script", _CLASS_SHAPES,
                         ids=[s[0] for s in _CLASS_SHAPES])
@pytest.mark.parametrize("channel", ["dash_c", "stdin", "script"])
@pytest.mark.parametrize("parser", _PARSERS)
def test_class_shapes_report_an_error_and_carry_on_like_bash(label, script,
                                                             channel, parser,
                                                             tmp_path):
    """OUTCOME-CLASS differential, per channel AND per parser.

    What is asserted: both shells report a diagnostic, and both still run the
    follow-up command. What is NOT asserted: identical wording -- psh names the
    construct where bash quotes the line, at both SHAs, and pretending
    otherwise would manufacture a failure that is not a defect.
    """
    psh, bash = _run_pair(script, channel, parser, tmp_path)
    assert psh.stderr.strip(), (label, channel, parser, "psh reported nothing")
    assert bash.stderr.strip(), (label, channel, parser, "bash reported nothing")
    assert ("AFTER" in psh.stdout) == ("AFTER" in bash.stdout), (
        label, channel, parser, psh.stdout, bash.stdout)

