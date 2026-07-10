"""N2 semantic pin: word fusion is SUPPRESSED inside ``(( ... ))``.

``word_fusion.fuse_words`` tracks ``DOUBLE_LPAREN`` / ``DOUBLE_RPAREN`` depth and
does NOT fuse word-like tokens while inside an arithmetic ``(( ))`` (or a C-style
``for (( ; ; ))`` header): that interior is consumed raw by
``collect_arithmetic_expression`` and re-serialized, so fusing there would
corrupt the reconstructed arithmetic expression. The most visible corruption is
a QUOTED array subscript: ``a["foo"]`` inside ``(( ))`` must reach the arithmetic
evaluator with its subscript intact. If the gate were dropped, the lexer would
fuse ``a`` ``[`` ``"foo"`` ``]`` into one WORD whose parts drop the quote, and the
reconstructed expression would no longer index the associative array correctly.

These are SEMANTIC (not corpus-shape) pins: each evaluates a quoted subscript in
``(( ))`` and asserts the bash 5.2 result. Each is RED when the arith gate is
dropped (demonstrated during fix-forward verification: the ``(( a["foo"] ... ))``
cases fail once ``fuse_words`` fuses inside ``(( ))``).
"""

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]

# (id, command, stdout) — bash 5.2 verified; RED under a dropped arith gate.
_CASES = [
    ("assoc_quoted_eq",
     'declare -A a; a[foo]=7; (( a["foo"] == 7 )) && echo match', "match\n"),
    ("assoc_quoted_truth",
     'declare -A a; a[foo]=7; (( a["foo"] )) && echo nonzero', "nonzero\n"),
    ("assoc_quoted_compound",
     'declare -A a; a[foo]=3; a[bar]=4; (( a["foo"] + a["bar"] == 7 )) && echo sum',
     "sum\n"),
]


def _run(parser, cmd):
    argv = [sys.executable, "-m", "psh"]
    if parser:
        argv += ["--parser", parser]
    p = subprocess.run(argv + ["-c", cmd], capture_output=True, text=True, cwd=_REPO)
    return p.returncode, p.stdout


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd,out",
                         [(c, o) for _, c, o in _CASES],
                         ids=[i for i, *_ in _CASES])
def test_quoted_subscript_in_arith_gate(parser, cmd, out):
    assert _run(parser, cmd) == (0, out)
