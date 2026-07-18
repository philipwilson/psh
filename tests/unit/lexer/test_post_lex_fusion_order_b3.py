"""S1 ordering pin: word fusion runs BEFORE keyword normalization in _post_lex.

``psh.lexer._post_lex`` is ``KeywordNormalizer().normalize(fuse_words(tokens))``.
The order is load-bearing: fusion completes each lexical word FIRST (bash's
rule — word boundaries are fixed by metacharacters alone), so a keyword
spelling glued to an adjacent expansion (``then$x``) is ONE plain word and is
never promoted to a keyword. A reserved word is recognized only when the
COMPLETE word is an exact unquoted literal in a grammar position.

HISTORY (campaign S1 re-pin): this file previously pinned the OPPOSITE order
(normalize-then-fuse), under which the normalizer promoted a keyword PREFIX of
a composite word — ``then$x`` became THEN + expansion and ``if true; then$x
echo hi; fi`` printed ``hi``. That was a documented deliberate psh/bash
divergence (reappraisal #20 medium finding 1). It is retired: bash keeps
``then$x`` as one word and reports a syntax error, and so does psh now. The
bash outcomes below were verified against bash 5.2.26 (boundary campaign S1
probe battery, red-on-base at 94d5638b: base psh printed ``hi``/``1 2``/``A``
with rc 0 for the glue rows).

Swapping the two _post_lex stages back (normalize before fuse) resurrects the
keyword-prefix promotion, so every glue case below turns green-for-execution
(rc 0, output) and this pin goes RED — the resurrection guard for the old
order.
"""

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]

# (id, command) — a keyword glued to an adjacent expansion/quote is one WORD,
# not a keyword, so the construct is missing its keyword and the parse fails
# (bash 5.2: rc 2, syntax-error diagnostic on stderr).
_GLUE_IS_ONE_WORD = [
    ("then_var", 'if true; then$x echo hi; fi'),
    ("do_var", 'for i in 1 2; do$x echo $i; done'),
    ("then_braced", 'if true; then${x}echo A; fi'),
    ("then_empty_dq", 'if true; then"" echo hi; fi'),
    ("do_empty_sq", "for i in 1; do'' echo $i; done"),
]

# Control: a space-delimited keyword is a complete word and IS the keyword —
# present so a regression that broke keyword recognition outright (rather than
# the glue rule) is distinguishable from the glue set.
_CONTROL = [
    ("then_spaced", 'if true; then echo hi; fi', 0, "hi\n"),
    ("do_spaced", 'for i in 1; do echo $i; done', 0, "1\n"),
]


def _run(parser, cmd):
    argv = [sys.executable, "-m", "psh"]
    if parser:
        argv += ["--parser", parser]
    p = subprocess.run(argv + ["-c", cmd], capture_output=True, text=True, cwd=_REPO)
    return p.returncode, p.stdout, p.stderr


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd", [c for _, c in _GLUE_IS_ONE_WORD],
                         ids=[i for i, _ in _GLUE_IS_ONE_WORD])
def test_keyword_glued_to_expansion_is_one_word(parser, cmd):
    """Glued keyword prefixes are not keywords: syntax error, nothing runs."""
    rc, out, err = _run(parser, cmd)
    assert rc == 2, f"expected syntax-error rc 2, got {rc} (out={out!r} err={err!r})"
    assert out == ""
    assert err != ""


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd,rc,out",
                         [(c, rc, o) for _, c, rc, o in _CONTROL],
                         ids=[i for i, *_ in _CONTROL])
def test_spaced_keyword_control(parser, cmd, rc, out):
    got_rc, got_out, _ = _run(parser, cmd)
    assert (got_rc, got_out) == (rc, out)


def test_fused_word_not_reclassified_by_normalizer():
    """Token-level shape: ``then$x`` is one WORD with parts and an exact span;
    the normalizer leaves it un-promoted (complete-word eligibility)."""
    from psh.lexer import tokenize
    src = 'if true; then$x echo hi; fi'
    tokens = tokenize(src)
    values = [(t.type.name, t.value) for t in tokens]
    assert ('WORD', 'then$x') in values, values
    fused = next(t for t in tokens if t.value == 'then$x')
    assert fused.parts, "fused word must carry its typed parts"
    assert src[fused.position:fused.end_position] == 'then$x'
    assert not fused.is_keyword
