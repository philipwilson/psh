"""Characterization corpus for array/assignment parsing (Tier C-B2, Ugly 5).

This freezes the EXACT parse result (full AST ``repr`` for successes, the
exception type + first message line for failures) of a broad corpus of
array-assignment source strings, parsed through the SAME entry the shell
uses: ``Parser(tokenize(src), source_text=src).parse()``.

It is the primary oracle for the zero-behavior-change refactor of
``psh/parser/recursive_descent/parsers/arrays.py``. The frozen values live
in the sidecar ``array_assignment_characterization_frozen.json`` and were
captured on the ORIGINAL (pre-refactor) code; the refactor must keep every
entry byte-identical.

Notes on the corpus (ground truth from the CURRENT ModularLexer):

- ``a[i]=v`` / ``a[i]+=v`` / ``a[i]="x y"`` etc. arrive as a SINGLE WORD
  token whose value contains ``[...]=`` (plus adjacent expansion/quoted
  continuation tokens). This is the only LIVE element-assignment shape.
- ``a=(...)`` arrives as WORD ``a=`` + ``LPAREN`` (single-token name).
- ``a+=(...)`` arrives as WORD ``a`` + WORD ``+=`` + ``LPAREN`` and the
  spaced forms ``a = (...)`` likewise (separate ``=``/``+=`` token).
- The four ``a [ i ] = v`` (space BEFORE the bracket) forms are PINNED
  LATENT BUGS: psh raises a parse error where bash reports
  "command not found". They exercise the separate-bracket detection +
  parse path and are frozen as errors so the refactor preserves them.
"""

import json
from pathlib import Path

import pytest

from psh.lexer import tokenize
from psh.parser import Parser

FROZEN_PATH = Path(__file__).parent / "array_assignment_characterization_frozen.json"
FROZEN = json.loads(FROZEN_PATH.read_text())


def _actual(src: str) -> tuple:
    """Parse ``src`` and return ('OK', repr) or ('ERR', 'Type: first-line')."""
    try:
        ast = Parser(tokenize(src), source_text=src).parse()
        return ("OK", repr(ast))
    except Exception as e:  # noqa: BLE001 - characterizing exact failures
        return ("ERR", f"{type(e).__name__}: {str(e).splitlines()[0]}")


@pytest.mark.parametrize("src,kind,frozen", FROZEN, ids=[e[0] for e in FROZEN])
def test_array_assignment_characterization(src, kind, frozen):
    actual_kind, actual = _actual(src)
    assert actual_kind == kind, (
        f"{src!r}: kind changed {kind!r} -> {actual_kind!r} (value: {actual!r})"
    )
    assert actual == frozen, f"{src!r}: parse result changed"


def test_corpus_is_nonempty_and_covers_both_outcomes():
    kinds = {e[1] for e in FROZEN}
    assert len(FROZEN) >= 35
    assert kinds == {"OK", "ERR"}
