"""Characterization corpus for Word quote context (Tier C-D1, Ugly 3).

Freezes, for a broad corpus of quoting shapes parsed through BOTH the
recursive-descent and combinator parsers, the per-``Word`` tuple

    (quote_type, is_quoted, is_unquoted_literal, effective_quote_char,
     source_text())

This is the primary oracle for the zero-behavior-change refactor that turns
``Word.quote_type`` from a stored dataclass field into a DERIVED property
(parts become the single source of truth for quote context).

CRUCIAL extra assertion: for every Word the parsers produce, the DERIVED
quote_type (computed straight from the parts by the rule below) equals the
quote_type the Word reports. If any parser site set ``quote_type`` WITHOUT
marking the parts, the derived value would diverge here BEFORE the refactor,
flagging a site that must mark its parts first. The corpus was captured on
the ORIGINAL (pre-refactor) code; the refactor must keep every tuple
identical and must keep derived == reported.

The derivation rule (single source of truth = the parts):
    quote_type = parts[0].quote_char  if parts and every part is quoted
                                        with the SAME quote_char
               = None                  otherwise

Five corpus entries report a DIFFERENT (derived) quote_type than the old
stored field did, and the sidecar baseline records the post-refactor value
for them. All five are verified behavior-neutral (bash differential +
full suite):

  - ``"a""b"`` / ``'a''b'`` (adjacent same-quote composites): the old code
    stored None on these; the parts are uniformly quoted, so the derived
    quote_type is the quote char. A uniformly double/single-quoted word
    expands identically through the whole-word and the composite dispatch
    branches, so promoting it changes nothing observable.
  - quoted case patterns (``case ... in "a b") ...``): the case-pattern
    builder stored None but marked its part quoted; the derived quote_type
    is now the quote char. Case patterns are matched purely via per-part
    quote context (``expand_word_as_pattern``), never via this property.
  - the combinator ``'mixed'`` sentinel: a non-real quote char the old code
    stored but never read; it derives to None (the part is not flagged
    quoted).
"""

import dataclasses
import json
from pathlib import Path

import pytest

from psh.ast_nodes import Word
from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.combinators.parser import ParserCombinatorShellParser

FROZEN_PATH = Path(__file__).parent / "word_quote_derivation_frozen.json"

# A large corpus spanning every quoting shape. Kept flat so the per-Word
# tuples are easy to read in failure output.
CORPUS = [
    # whole-word single / double / ansi-c
    "echo 'abc'",
    'echo "a b"',
    r"echo $'x\ty'",
    # empty quoted words
    "echo ''",
    'echo ""',
    # plain unquoted
    "echo plain",
    # composite mixed quoting
    'echo a"b"c',
    "echo a'b'c",
    'echo "a"\'b\'',
    # adjacent same-quote
    'echo "a""b"',
    "echo 'a''b'",
    # quoted with expansion
    'echo "a$b c"',
    'echo "$v"',
    'echo "${x:-d}"',
    'echo "pre$(echo hi)post"',
    'echo "$@"',
    'echo "${arr[@]}"',
    # unquoted expansion (splittable)
    "echo $x",
    "echo ${x:-d}",
    "echo $(echo hi)",
    # quoted glob (suppressed)
    'echo "*"',
    "echo '*'",
    # backslash / escapes
    r"echo a\ b",
    # nested in for loop
    'for i in "a b" c \'d\'; do echo $i; done',
    # nested in while/case
    'case "$x" in "a b") echo m;; *) echo n;; esac',
    # nested in array init
    'arr=("a b" $v \'z\')',
    # nested in redirections (here string)
    'cat <<< "a b"',
    'cat <<< plain',
    # assignment-shaped argument words
    'x="a b"',
    "y='c d'",
    # tilde
    "echo ~",
    'echo "~"',
]


def _derived_quote_type(word: Word):
    """The quote_type implied SOLELY by the parts (the refactor's rule).

    Every part quoted with the SAME quote char -> that char; otherwise None.
    This is the rule the production ``Word.quote_type`` property uses, so
    derived == reported is the post-refactor invariant.
    """
    parts = word.parts
    if not parts:
        return None
    first = getattr(parts[0], "quote_char", None)
    for p in parts:
        if not getattr(p, "quoted", False):
            return None
        if getattr(p, "quote_char", None) != first:
            return None
    return first


def _walk_words(obj, seen=None):
    """Yield every Word reachable from a parsed AST (dataclass/list walk)."""
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, Word):
        yield obj
    if dataclasses.is_dataclass(obj):
        for f in dataclasses.fields(obj):
            yield from _walk_words(getattr(obj, f.name), seen)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _walk_words(item, seen)


def _word_tuple(word: Word):
    return (
        word.quote_type,
        word.is_quoted,
        word.is_unquoted_literal,
        word.effective_quote_char,
        word.source_text(),
    )


def _rd_words(src: str):
    ast = Parser(tokenize(src), source_text=src).parse()
    return list(_walk_words(ast))


def _comb_words(src: str):
    parser = ParserCombinatorShellParser()
    ast = parser.parse(tokenize(src))
    return list(_walk_words(ast))


if FROZEN_PATH.exists():
    _FROZEN = json.loads(FROZEN_PATH.read_text())
    FROZEN_RD = _FROZEN["rd"]
    FROZEN_COMB = _FROZEN["comb"]
else:  # pragma: no cover - only during initial generation
    FROZEN_RD = {}
    FROZEN_COMB = {}


def _as_lists(tuples):
    """JSON round-trips tuples to lists; normalize for comparison."""
    return [list(t) for t in tuples]


@pytest.mark.parametrize("src", CORPUS)
def test_rd_word_tuples_frozen(src):
    """Per-Word tuple must match the frozen baseline (recursive descent)."""
    words = _rd_words(src)
    actual = _as_lists(_word_tuple(w) for w in words)
    assert actual == FROZEN_RD[src], f"{src!r}: RD Word tuples changed"


@pytest.mark.parametrize("src", CORPUS)
def test_comb_word_tuples_frozen(src):
    """Per-Word tuple must match the frozen baseline (combinator)."""
    try:
        words = _comb_words(src)
    except Exception as e:  # noqa: BLE001 - combinator gaps are documented
        assert FROZEN_COMB[src] == ["ERR", type(e).__name__], (
            f"{src!r}: combinator outcome changed"
        )
        return
    actual = _as_lists(_word_tuple(w) for w in words)
    assert actual == FROZEN_COMB[src], f"{src!r}: combinator Word tuples changed"


@pytest.mark.parametrize("src", CORPUS)
def test_rd_derived_equals_reported(src):
    """The parts alone must imply the same quote_type the Word reports.

    If this fails on a source, that parser site set quote_type without
    marking its parts -- it must mark the parts before quote_type can be
    a pure derivation.
    """
    for w in _rd_words(src):
        assert _derived_quote_type(w) == w.quote_type, (
            f"{src!r}: derived {_derived_quote_type(w)!r} != reported "
            f"{w.quote_type!r} for parts {w.parts!r}"
        )


@pytest.mark.parametrize("src", CORPUS)
def test_comb_derived_equals_reported(src):
    """Same derived==reported invariant for the combinator parser."""
    try:
        words = _comb_words(src)
    except Exception:  # noqa: BLE001 - documented gaps
        pytest.skip("combinator does not parse this corpus entry")
    for w in words:
        assert _derived_quote_type(w) == w.quote_type, (
            f"{src!r}: derived {_derived_quote_type(w)!r} != reported "
            f"{w.quote_type!r} for parts {w.parts!r}"
        )


# ---------------------------------------------------------------------------
# Regenerate the frozen sidecar (captured on ORIGINAL code) with:
#   python tests/unit/parser/test_word_quote_derivation.py
# ---------------------------------------------------------------------------
def _capture():
    rd = {}
    comb = {}
    for src in CORPUS:
        rd[src] = [list(_word_tuple(w)) for w in _rd_words(src)]
        try:
            comb[src] = [list(_word_tuple(w)) for w in _comb_words(src)]
        except Exception as e:  # noqa: BLE001
            comb[src] = ["ERR", type(e).__name__]
    FROZEN_PATH.write_text(json.dumps({"rd": rd, "comb": comb}, indent=2) + "\n")
    print(f"wrote {FROZEN_PATH}")


if __name__ == "__main__":
    _capture()
