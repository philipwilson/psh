"""B3 ordering pin: word fusion runs AFTER keyword normalization in _post_lex.

``psh.lexer._post_lex`` is ``fuse_words(KeywordNormalizer().normalize(tokens))``.
The order is load-bearing: normalization retypes reserved words FIRST and
removes them from the word-like set, so a keyword glued to a following
expansion (``then$x``) is NOT fused and stays a keyword. If fusion ran first,
``then`` and ``$x`` (both word-like) would merge into one WORD ``then$x`` that
normalization no longer recognizes as ``then`` -> the compound command would
fail to parse.

psh recognizes a keyword even when an expansion is lexically adjacent
(``then$x``); this is a deliberate, PRE-EXISTING psh/bash divergence (bash keeps
``then$x`` as one word and syntax-errors) that predates word fusion and is
unchanged by it — these outputs match base (pre-fusion) psh exactly, which is
what these pins lock. This is an internal-invariant guard, not a bash claim.

Swapping the two _post_lex stages turns every glue case below into a parse
error, so the pin is RED under that mutation (demonstrated during fix-forward
verification).
"""

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]

# (id, command, rc, stdout) — a keyword glued to an adjacent expansion is still
# the keyword because normalization runs before fusion (x/y unset).
_GLUE_KEEPS_KEYWORD = [
    ("then_var", 'if true; then$x echo hi; fi', 0, "hi\n"),
    ("do_var", 'for i in 1 2; do$x echo $i; done', 0, "1\n2\n"),
    ("then_braced", 'if true; then${x}echo A; fi', 0, "A\n"),
]

# Control: a space-delimited keyword is unaffected either way (fusion never
# fires) — present so a swap that somehow spared these still fails the glue set.
_CONTROL = [
    ("then_spaced", 'if true; then echo hi; fi', 0, "hi\n"),
    ("do_spaced", 'for i in 1; do echo $i; done', 0, "1\n"),
]


def _run(parser, cmd):
    argv = [sys.executable, "-m", "psh"]
    if parser:
        argv += ["--parser", parser]
    p = subprocess.run(argv + ["-c", cmd], capture_output=True, text=True, cwd=_REPO)
    return p.returncode, p.stdout


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd,rc,out",
                         [(c, rc, o) for _, c, rc, o in _GLUE_KEEPS_KEYWORD],
                         ids=[i for i, *_ in _GLUE_KEEPS_KEYWORD])
def test_keyword_glued_to_expansion_stays_keyword(parser, cmd, rc, out):
    assert _run(parser, cmd) == (rc, out)


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd,rc,out",
                         [(c, rc, o) for _, c, rc, o in _CONTROL],
                         ids=[i for i, *_ in _CONTROL])
def test_spaced_keyword_control(parser, cmd, rc, out):
    assert _run(parser, cmd) == (rc, out)
