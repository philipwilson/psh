"""The NON-INTERACTIVE halves of slot 2.5's declared behaviour deltas (R7-B).

WHY THIS FILE EXISTS, stated plainly because it is a correction. Round 1
declared two behaviour changes as INTERACTIVE-ONLY. That was FALSE. Both also
change `-c`, script-file and stdin behaviour — exit status, stdout, and stderr —
and a third, rd-only change rides along with them. The false framing survived
round 1 because the instrument backing it compared psh against BASH at each SHA
and reported "66/66 agree"; agreement with an oracle at two points cannot
establish identity between those points, and here it concealed 18 non-identical
rows (measured by tmp/r2-5-probes/base_tip_identity.py).

ORACLE FOR EVERY ROW BELOW: bash 5.2.26, differential, same host, same bytes.
Every delta moves psh TOWARD bash and stays.

THE THREE DECLARED DELTAS, with their measured base values:

1. `cat <<EOF "abc` / `EOF` / `def"` -- heredoc + unclosed quote on one line.
   base: rc=0, stdout 'MARKER\\n'   (the buffer executed at line 3)
   tip : rc=1, stdout ''            (+ EOF warning)  == bash
   Deriving the heredoc answer from the LEX makes the unclosed-quote outcome
   win, as it does in bash.

2. `cat <<$(x)` / `hi` / `$` -- substitution-bearing delimiter.
   base: stdout 'hi\\n$\\nMARKER\\n'         (delimiter cooked to `$`)
   tip : stdout 'hi\\n$\\necho MARK""ER\\n'  (+ EOF warning)  == bash
   The delimiter is taken literally, so the terminator is `$(x)`; the retired
   regex scanner stopped at `(`.

3. THE rd-ONLY DELTA: at base the recursive-descent parser emitted NO
   unterminated-here-document warning on these shapes while the combinator did.
   At tip BOTH emit it, matching bash. Pinned per-parser below, since a
   per-parser difference is invisible to any test that runs one parser.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

TREE_ROOT = str(Path(__file__).resolve().parents[3])
ORACLE = "/opt/homebrew/bin/bash"

# (label, script bytes)
_SHAPES = [
    ("heredoc_unclosed_dq", b'cat <<EOF "abc\nEOF\ndef"\necho MARK""ER\n'),
    ("subst_delim_dollar", b'cat <<$(x)\nhi\n$\necho MARK""ER\n'),
]
_CHANNELS = ("dash_c", "script", "stdin")
_PARSERS = ("rd", "combinator")


def _normalise(text, script_path=None):
    """Strip the shell's own name/path prefix from diagnostics so psh and bash
    are compared on the MESSAGE, not on which binary emitted it."""
    if script_path:
        text = text.replace(script_path, "<S>")
    return re.sub(r"^[^\s:]*(?:psh|bash)[^\s:]*:", "<SH>:", text,
                  flags=re.MULTILINE)


def _run(argv, raw, channel, cwd, env=None):
    script_path = None
    if channel == "script":
        with tempfile.NamedTemporaryFile("wb", suffix=".sh", dir=cwd,
                                         delete=False) as tf:
            tf.write(raw)
        script_path = tf.name
        argv, stdin_bytes = argv + [script_path], None
    elif channel == "dash_c":
        argv, stdin_bytes = argv + ["-c", raw.decode()], None
    else:
        stdin_bytes = raw
    p = subprocess.run(argv, input=stdin_bytes, capture_output=True,
                       cwd=cwd, env=env, timeout=30)
    return (p.returncode,
            p.stdout.decode(errors="replace"),
            _normalise(p.stderr.decode(errors="replace"), script_path))


@pytest.mark.parametrize("label,raw", _SHAPES, ids=[s[0] for s in _SHAPES])
@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("parser", _PARSERS)
def test_declared_delta_matches_bash_non_interactively(label, raw, channel,
                                                       parser, tmp_path):
    """DIFFERENTIAL against the oracle, per channel AND per parser."""
    if not Path(ORACLE).exists():                            # pragma: no cover
        pytest.skip(f"oracle {ORACLE} not present")
    env = dict(os.environ, PYTHONPATH=TREE_ROOT)
    which = subprocess.run(
        [sys.executable, "-c", "import psh; print(psh.__file__)"],
        capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=30)
    assert which.stdout.startswith(TREE_ROOT), which.stdout

    psh = _run([sys.executable, "-m", "psh", "--norc", "--parser", parser],
               raw, channel, str(tmp_path), env)
    bash = _run([ORACLE, "--norc"], raw, channel, str(tmp_path))
    assert psh == bash, (label, channel, parser, psh, bash)


@pytest.mark.parametrize("label,raw", _SHAPES, ids=[s[0] for s in _SHAPES])
@pytest.mark.parametrize("parser", _PARSERS)
def test_the_eof_warning_is_emitted_by_both_parsers(label, raw, parser,
                                                    tmp_path):
    """The rd-ONLY delta, pinned per-parser.

    At base, `rd` stayed silent on these shapes while `combinator` warned. A
    single-parser test cannot see that, which is why the parser axis is
    explicit here rather than folded into the row above.
    """
    env = dict(os.environ, PYTHONPATH=TREE_ROOT)
    _, _, err = _run([sys.executable, "-m", "psh", "--norc", "--parser",
                      parser], raw, "dash_c", str(tmp_path), env)
    assert "delimited by end-of-file" in err, (label, parser, err)
