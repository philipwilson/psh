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
                                                       parser):
    """DIFFERENTIAL against the oracle, per channel AND per parser."""
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
    assert is_comparable(psh) and is_comparable(bash), (psh, bash)
    assert isinstance(psh, Completed) and isinstance(bash, Completed)
    assert psh.returncode == bash.returncode, (label, channel, parser,
                                               psh.returncode, bash.returncode)
    assert psh.stdout == bash.stdout, (label, channel, parser, psh.stdout,
                                       bash.stdout)
    assert _normalise(psh.stderr) == _normalise(bash.stderr), (
        label, channel, parser, psh.stderr, bash.stderr)


@pytest.mark.parametrize("label,script", _SHAPES, ids=[s[0] for s in _SHAPES])
@pytest.mark.parametrize("parser", _PARSERS)
def test_the_eof_warning_is_emitted_by_both_parsers(label, script, parser):
    """The rd-ONLY delta, pinned per-parser.

    At base, `rd` stayed silent on these shapes while `combinator` warned. A
    single-parser test cannot see that, which is why the parser axis is
    explicit here rather than folded into the row above.
    """
    psh = run_psh(["--norc", "--parser", parser, "-c", script])
    assert isinstance(psh, Completed), psh
    assert "delimited by end-of-file" in psh.stderr, (label, parser, psh.stderr)
