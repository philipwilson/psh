"""Unit tests for the Word-stage brace expander (WordBraceExpander).

WordBraceExpander turns one parsed Word into the list of Words it expands to,
operating on the word's literal SKELETON (unquoted literal text is structural;
quoted literals and expansion parts are opaque). These tests exercise the
Word-level mechanics directly — the fast path, opaque handling, empty/range
edges, and bare-$name fusion — complementing the behavioral coverage in
test_braceexpand_option.py and test_brace_expansion.py.
"""
import pytest

from psh.ast_nodes import (
    ExpansionPart,
    LiteralPart,
    VariableExpansion,
    Word,
)
from psh.expansion.brace_expansion_words import WordBraceExpander


def _lit(text, quoted=False, qc=None):
    return LiteralPart(text, quoted=quoted, quote_char=qc)


def _words_texts(words):
    """display_text of each result Word (pre-expansion source-shaped text)."""
    return [w.display_text() for w in words]


@pytest.fixture
def bx():
    return WordBraceExpander()


class TestFastPath:
    def test_no_brace_returns_same_object(self, bx):
        w = Word(parts=[_lit('hello')])
        out = bx.expand(w)
        assert out == [w]
        assert out[0] is w  # identity preserved: no work done

    def test_quoted_brace_is_not_structural(self, bx):
        # "{a,b}" — the single quoted literal has a '{' but it is opaque.
        w = Word(parts=[_lit('{a,b}', quoted=True, qc='"')])
        out = bx.expand(w)
        assert out == [w]
        assert out[0] is w

    def test_nonexpandable_brace_returns_single(self, bx):
        # {a} has no comma/range -> not a brace expression.
        w = Word(parts=[_lit('{a}')])
        out = bx.expand(w)
        assert _words_texts(out) == ['{a}']


class TestListAndRange:
    def test_simple_list(self, bx):
        out = bx.expand(Word(parts=[_lit('{a,b,c}')]))
        assert _words_texts(out) == ['a', 'b', 'c']

    def test_prefix_suffix(self, bx):
        out = bx.expand(Word(parts=[_lit('pre{1,2}post')]))
        assert _words_texts(out) == ['pre1post', 'pre2post']

    def test_numeric_range(self, bx):
        out = bx.expand(Word(parts=[_lit('{1..4}')]))
        assert _words_texts(out) == ['1', '2', '3', '4']

    def test_cartesian(self, bx):
        out = bx.expand(Word(parts=[_lit('{a,b}{1,2}')]))
        assert _words_texts(out) == ['a1', 'a2', 'b1', 'b2']

    def test_empty_list_item_dropped(self, bx):
        # {a,,b} -> a b (the empty middle item is dropped, matching bash).
        out = bx.expand(Word(parts=[_lit('{a,,b}')]))
        assert _words_texts(out) == ['a', 'b']

    def test_empty_item_fused_survives(self, bx):
        # a{,b} -> a ab (empty item fused with prefix is non-empty).
        out = bx.expand(Word(parts=[_lit('a{,b}')]))
        assert _words_texts(out) == ['a', 'ab']

    def test_cross_case_range_keeps_empty_word(self, bx):
        # {Z..a} spans the backslash (ASCII 92), which becomes a KEPT empty
        # word — so the result count includes one empty string.
        out = bx.expand(Word(parts=[_lit('{Z..a}')]))
        texts = _words_texts(out)
        assert texts == ['Z', '[', '', ']', '^', '_', '`', 'a']


class TestOpaqueParts:
    def test_expansion_part_is_opaque(self, bx):
        # x$v{1,2} -> the $v is carried opaque; the {1,2} is structural.
        w = Word(parts=[
            _lit('x'),
            ExpansionPart(VariableExpansion('v'), quoted=False),
            _lit('{1,2}'),
        ])
        out = bx.expand(w)
        # Two Words, each starting 'x' + $v(fused) ...
        assert len(out) == 2
        assert _words_texts(out) == ['x$v1', 'x$v2']

    def test_quoted_expansion_not_fused(self, bx):
        # "$v"{1,2} -> the quoted $v stays a separate part; '1'/'2' do NOT fuse
        # into the variable name.
        w = Word(parts=[
            ExpansionPart(VariableExpansion('v'), quoted=True, quote_char='"'),
            _lit('{1,2}'),
        ])
        out = bx.expand(w)
        assert len(out) == 2
        # Each result: quoted ExpansionPart($v) + LiteralPart('1'/'2')
        for word, digit in zip(out, ('1', '2'), strict=True):
            assert isinstance(word.parts[0], ExpansionPart)
            assert word.parts[0].expansion.name == 'v'
            assert isinstance(word.parts[1], LiteralPart)
            assert word.parts[1].text == digit


class TestBareNameFusion:
    def test_bare_var_fuses_trailing_name_chars(self, bx):
        # $v{1,2} -> variable names v1/v2 (fusion), because brace expansion
        # precedes parameter expansion.
        w = Word(parts=[
            ExpansionPart(VariableExpansion('v', braced=False), quoted=False),
            _lit('{1,2}'),
        ])
        out = bx.expand(w)
        names = [p.expansion.name for word in out for p in word.parts
                 if isinstance(p, ExpansionPart)]
        assert names == ['v1', 'v2']

    def test_braced_var_does_not_fuse(self, bx):
        # ${v}{1,2} -> variable v, then literal 1/2 (NO fusion).
        w = Word(parts=[
            ExpansionPart(VariableExpansion('v', braced=True), quoted=False),
            _lit('{1,2}'),
        ])
        out = bx.expand(w)
        assert len(out) == 2
        for word, digit in zip(out, ('1', '2'), strict=True):
            assert word.parts[0].expansion.name == 'v'  # not fused
            assert word.parts[1].text == digit

    def test_fusion_does_not_mutate_shared_original(self, bx):
        # The original VariableExpansion node must be untouched (result Words
        # get fresh nodes) so sibling result Words don't corrupt each other.
        orig = VariableExpansion('v', braced=False)
        w = Word(parts=[ExpansionPart(orig, quoted=False), _lit('{1,2}')])
        bx.expand(w)
        assert orig.name == 'v'

    def test_partial_name_char_run_fuses_leading_only(self, bx):
        # $v{1,2}-x -> $v1-x / $v2-x: only the leading name-char run ('1'/'2')
        # fuses; the '-x' stays literal.
        w = Word(parts=[
            ExpansionPart(VariableExpansion('v'), quoted=False),
            _lit('{1,2}-x'),
        ])
        out = bx.expand(w)
        assert _words_texts(out) == ['$v1-x', '$v2-x']
        for word in out:
            assert word.parts[0].expansion.name in ('v1', 'v2')


class TestTypeGuard:
    def test_non_word_raises_loudly(self, bx):
        with pytest.raises(TypeError, match='expects a Word'):
            bx.expand('not a word')
