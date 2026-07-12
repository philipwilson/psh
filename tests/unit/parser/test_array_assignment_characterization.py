"""Characterization corpus for array/assignment parsing (Tier C-B2, Ugly 5).

This freezes the EXACT parse result (full AST ``repr`` for successes, the
exception type + first message line for failures) of a broad corpus of
array-assignment source strings, parsed through the SAME entry the shell
uses: ``Parser(tokenize(src), source_text=src).parse()``.

It is the primary oracle for the zero-behavior-change refactor of
``psh/parser/recursive_descent/parsers/arrays.py``. The frozen values live
in the sidecar ``array_assignment_characterization_frozen.json``; a refactor
must keep every entry byte-identical.

The ``ArrayElementAssignment.index`` entries were re-frozen in reappraisal
#19 (B2, H4): ``index`` was retyped from ``Union[str, List[Token]]`` to plain
``str`` — both parsers already stored a one-token ``[Token(WORD, subscript)]``
list that the executor unwrapped, so the change is a pure AST-shape cleanup
(``index=[Token(...WORD..., value='0'...)]`` → ``index='0'``) with no change to
the parsed subscript text or any observable shell behaviour.

Notes on the corpus (ground truth from the CURRENT ModularLexer):

- ``a[i]=v`` / ``a[i]+=v`` / ``a[i]="x y"`` etc. arrive as a SINGLE WORD
  token whose value contains ``[...]=`` (plus adjacent expansion/quoted
  continuation tokens). This is the only LIVE element-assignment shape.
- ``a=(...)`` arrives as WORD ``a=`` + ``LPAREN`` (single-token name).
- ``a+=(...)`` arrives as WORD ``a`` + WORD ``+=`` + ``LPAREN`` and the
  spaced forms ``a = (...)`` likewise (separate ``=``/``+=`` token).
- The four ``a [ i ] = v`` (space BEFORE the bracket) forms are NOT array
  assignments: bash parses them as a simple command (``a`` plus the words
  ``[ i ] = v``) and reports "command not found". psh used to special-case
  them into a bespoke parse error; that separate-bracket machinery was
  removed (reappraisal #5), so they now parse as ordinary simple commands
  and the corpus freezes the resulting AST.
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


def test_corpus_is_nonempty():
    kinds = {e[1] for e in FROZEN}
    assert len(FROZEN) >= 35
    # Both parse successes and failures appear: the spaced array-initializer
    # forms ``a= (1 2)`` / ``a = (1 2)`` are now syntax errors (a non-adjacent
    # ``(`` after an assignment head is not an array init, matching bash;
    # appraisal finding 5b). The rest parse successfully.
    assert kinds == {"OK", "ERR"}
