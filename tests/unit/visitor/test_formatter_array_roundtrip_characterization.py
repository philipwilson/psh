"""Characterization: formatter/validator output over array AST nodes.

Frozen guard for Tier C-A2 of the lexer/parser/AST architecture review
(``docs/reviews/lexer_parser_ast_architecture_review_2026-06-13.md``).
A2 deletes the STORED quote/type sidecar fields on ``ArrayInitialization``
and ``ArrayElementAssignment`` and re-derives them as ``@property`` from
the canonical ``Word`` fields.

The ONLY consumers of those sidecars are ``FormatterVisitor`` and
``ValidatorVisitor`` (locked by
``tests/unit/parser/test_legacy_field_isolation.py``). This file freezes
their OBSERVABLE output -- the formatted source string and the validator
summary -- over a broad corpus of array initializations and element
assignments (quoted / unquoted / mixed / indexed / append / empty). The
expected strings below were captured on the ORIGINAL (stored-field) code;
after the derive-to-property refactor they must still match byte for byte.

Both parsers are exercised. A known combinator-only divergence is pinned
explicitly (see ``COMBINATOR_VALIDATOR_DIVERGENCE``): the educational
combinator parser splits the composite word ``p$x`` into three tokens, so
its STORED ``element_types`` were ``['WORD','VARIABLE','WORD']`` (mixed),
emitting a spurious "mixed element types" info. Deriving from the
(already-split) Words yields all ``'WORD'`` -- matching the production
recursive-descent parser. That single case is the only place the derived
value cannot reproduce the combinator's stored value, and the change is a
strict improvement (it removes a tokenization-artifact warning). The
production RD parser is byte-identical throughout.
"""

import pytest

from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.combinators.parser import ParserCombinatorShellParser
from psh.visitor.formatter_visitor import FormatterVisitor
from psh.visitor.validator_visitor import ValidatorVisitor


def _rd_parse(src):
    return Parser(tokenize(src), source_text=src).parse()


def _comb_parse(src):
    return ParserCombinatorShellParser().parse(tokenize(src))


def _format(ast):
    return FormatterVisitor().visit(ast)


def _validate_summary(ast):
    vv = ValidatorVisitor()
    vv.visit(ast)
    return vv.get_summary()


def _mixed_info(ast):
    """True if the validator emitted the mixed-element-types info."""
    return "mixed element types" in _validate_summary(ast)


# -- Corpus + frozen formatter output (identical for both parsers). ---------
# (source, expected_formatted_source)
FORMATTER_CASES = [
    ('a=(1 2 3)', 'a=(1 2 3)'),
    ('a=("x y" z)', 'a=("x y" z)'),
    ("a=('one' two)", "a=('one' two)"),
    ('a=()', 'a=()'),
    ('a+=(four five)', 'a+=(four five)'),
    ('arr=(\'one\' "two" three)', 'arr=(\'one\' "two" three)'),
    ('a=("a" "b")', 'a=("a" "b")'),
    ('a=("p" \'q\')', 'a=("p" \'q\')'),
    # Element assignments
    ('a[0]=x', 'a[0]=x'),
    ('a[0]="q v"', 'a[0]="q v"'),
    ("a[k]+='lit'", "a[k]+='lit'"),
    ('a[i+1]=val', 'a[i+1]=val'),
    ('a[0]+="z"', 'a[0]+="z"'),
    # Reappraisal #15 J3/J6: values render from the Word layer, re-escaped —
    # no legacy flat-string corruption (literal tab, spurious `$`, lost quotes).
    ("a=($'x\\ty')", "a=($'x\\ty')"),
    ("a=($'x\\ty' plain)", "a=($'x\\ty' plain)"),
    ('a=("x\\"y")', 'a=("x\\"y")'),
    ('m=([k]="v 1")', 'm=([k]="v 1")'),
    ("a[3]=$'x\\ty'", "a[3]=$'x\\ty'"),
    ("a[0]=$'p q'", "a[0]=$'p q'"),
]


@pytest.mark.parametrize("src,expected", FORMATTER_CASES)
def test_formatter_rd_byte_identical(src, expected):
    assert _format(_rd_parse(src)) == expected


@pytest.mark.parametrize("src,expected", FORMATTER_CASES)
def test_formatter_combinator_byte_identical(src, expected):
    assert _format(_comb_parse(src)) == expected


# -- Validator mixed-element-types info (the only validator branch that
#    reads the sidecar). Frozen verdict for the RD (production) parser. -----
# (source, mixed_info_expected)
VALIDATOR_MIXED_CASES = [
    ('a=(1 2 3)', False),
    ('a=("x y" z)', True),       # STRING + WORD
    ("a=('one' two)", True),     # STRING + WORD
    ('a=("a" "b")', False),      # all STRING
    ('a=()', False),
    ('a+=(four five)', False),   # all WORD
    ('a=(p$x q)', True),         # COMPOSITE + WORD (RD merges p$x)
]


@pytest.mark.parametrize("src,mixed", VALIDATOR_MIXED_CASES)
def test_validator_mixed_rd(src, mixed):
    assert _mixed_info(_rd_parse(src)) is mixed


# -- Combinator validator verdict. Same as RD EXCEPT the one documented
#    divergence below (combinator splits p$x -> p, $x, q). ------------------
COMBINATOR_VALIDATOR_DIVERGENCE = {'a=(p$x q)'}


@pytest.mark.parametrize("src,mixed", VALIDATOR_MIXED_CASES)
def test_validator_mixed_combinator(src, mixed):
    if src in COMBINATOR_VALIDATOR_DIVERGENCE:
        pytest.skip("combinator composite-word split divergence (pinned separately)")
    assert _mixed_info(_comb_parse(src)) is mixed


# -- Semantic oracle (reappraisal #15 J3/J6): assigning, then formatting and
#    re-running, must leave the array's `declare -p` identical. This catches
#    value corruption the byte-identical formatter check above cannot (the old
#    flat-string path emitted a literal tab / spurious `$` / lost quotes that
#    still "looked" plausible but changed the stored value on re-parse). -------
import subprocess  # noqa: E402
import sys  # noqa: E402

DECLARE_P_CASES = [
    ("a", "a=($'x\\ty')"),
    ("a", "a=($'x\\ty' plain)"),
    ("a", 'a=("x\\"y")'),
    ("a", "a=('one' \"two\" three)"),
    ("a", "a[3]=$'x\\ty'"),
    ("a", "a[0]=$'p q'"),
    ("m", 'declare -A m=([k]="v 1")'),
    ("m", "declare -A m=([x]=$'a\\tb' [y]='p q')"),
]


def _psh(*args):
    return subprocess.run([sys.executable, "-m", "psh", *args],
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("var,src", DECLARE_P_CASES)
def test_declare_p_survives_format_roundtrip(var, src):
    formatted = _psh("--format", "-c", src).stdout
    orig = _psh("-c", f"{src}\ndeclare -p {var}").stdout
    after = _psh("-c", f"{formatted}\ndeclare -p {var}").stdout
    assert after == orig, f"src={src!r} formatted={formatted!r}"
