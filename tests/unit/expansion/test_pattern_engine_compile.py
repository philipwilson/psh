"""Unit tests for the pattern-engine compiler (AST, parse-once).

Covers the node shapes, the tricky bracket/extglob edge syntax the campaign
called out (``[!``, ``[]]``, ``[a-]``, unterminated ``(``, ``@()`` empty,
``!()`` empty), the extglob-off mode, and an idempotent structural round-trip
through :func:`unparse`.
"""
import pytest

from psh.expansion.pattern_engine import (
    AnyChar,
    Bracket,
    Extglob,
    Literal,
    Sequence,
    Star,
    compile_pattern,
    structure,
    unparse,
)


def S(pattern, **kw):
    return structure(compile_pattern(pattern, **kw))


def test_plain_literals_and_wildcards():
    assert S("abc") == ('Seq', (('Lit', 'a'), ('Lit', 'b'), ('Lit', 'c')))
    assert S("a*b?c") == ('Seq', (('Lit', 'a'), ('Star',), ('Lit', 'b'),
                                  ('Any',), ('Lit', 'c')))


def test_backslash_escape_is_literal():
    assert S(r"a\*b") == ('Seq', (('Lit', 'a'), ('Lit', '*'), ('Lit', 'b')))
    assert S(r"\?") == ('Seq', (('Lit', '?'),))
    # A trailing lone backslash has no following char: it stays a literal '\'.
    assert S("a\\") == ('Seq', (('Lit', 'a'), ('Lit', '\\')))


def test_bracket_expressions():
    assert S("[abc]") == ('Seq', (('Brk', 'abc'),))
    assert S("[a-z]") == ('Seq', (('Brk', 'a-z'),))
    # Negation markers are kept in the raw content (matcher interprets them).
    assert S("[!a-z]") == ('Seq', (('Brk', '!a-z'),))
    assert S("[^a-z]") == ('Seq', (('Brk', '^a-z'),))


def test_bracket_edge_syntax():
    # A ']' immediately after '[' (or '[!') is a literal member, not the close.
    assert S("[]]") == ('Seq', (('Brk', ']'),))
    assert S("[!]]") == ('Seq', (('Brk', '!]'),))
    assert S("[]abc]") == ('Seq', (('Brk', ']abc'),))
    # Trailing '-' is a literal member.
    assert S("[a-]") == ('Seq', (('Brk', 'a-'),))
    # POSIX class name is preserved verbatim inside the content.
    assert S("[[:alpha:]]") == ('Seq', (('Brk', '[:alpha:]'),))
    assert S("[![:digit:]]") == ('Seq', (('Brk', '![:digit:]'),))
    # Escaped ']' member.
    assert S(r"[a\]b]") == ('Seq', (('Brk', 'a\\]b'),))


def test_unterminated_bracket_is_literal():
    assert S("[abc") == ('Seq', (('Lit', '['), ('Lit', 'a'), ('Lit', 'b'),
                                 ('Lit', 'c')))
    assert S("[") == ('Seq', (('Lit', '['),))


@pytest.mark.parametrize("op", list("?*+@!"))
def test_extglob_operators(op):
    assert S(f"{op}(a|b)") == (
        'Seq', (('Ext', op, (('Seq', (('Lit', 'a'),)),
                             ('Seq', (('Lit', 'b'),)))),))


def test_extglob_empty_group():
    # @() / !() have a single EMPTY-sequence alternative (bash-compatible).
    assert S("@()") == ('Seq', (('Ext', '@', (('Seq', ()),)),))
    assert S("!()") == ('Seq', (('Ext', '!', (('Seq', ()),)),))


def test_nested_extglob():
    assert S("*(a@(b)c)") == (
        'Seq', (('Ext', '*', (
            ('Seq', (('Lit', 'a'),
                     ('Ext', '@', (('Seq', (('Lit', 'b'),)),)),
                     ('Lit', 'c'))),)),))


def test_extglob_alternatives_split_respects_nested_parens():
    # The '|' inside the inner group must NOT split the outer alternatives.
    node = compile_pattern("@(a|@(b|c))")
    assert structure(node) == (
        'Seq', (('Ext', '@', (
            ('Seq', (('Lit', 'a'),)),
            ('Seq', (('Ext', '@', (('Seq', (('Lit', 'b'),)),
                                   ('Seq', (('Lit', 'c'),)))),)))),))


def test_unbalanced_extglob_paren_is_literal_prefix():
    # '@(' with no matching ')': '@' is literal, '(' reprocessed as literal.
    assert S("a@(b") == ('Seq', (('Lit', 'a'), ('Lit', '@'), ('Lit', '('),
                                 ('Lit', 'b')))


def test_extglob_disabled_mode():
    # With extglob off, ?/*, keep glob meaning; +@! and ( are literals.
    assert S("+(a)", extglob=False) == (
        'Seq', (('Lit', '+'), ('Lit', '('), ('Lit', 'a'), ('Lit', ')')))
    assert S("?(a)", extglob=False) == (
        'Seq', (('Any',), ('Lit', '('), ('Lit', 'a'), ('Lit', ')')))
    assert S("*", extglob=False) == ('Seq', (('Star',),))


def test_node_types_are_produced():
    node = compile_pattern("a*?[x]@(y)")
    kinds = [type(e) for e in node.elements]
    assert kinds == [Literal, Star, AnyChar, Bracket, Extglob]
    assert isinstance(node, Sequence)


# --- round-trip ------------------------------------------------------------

_ROUNDTRIP = [
    "abc", "a*b", "a?c", "a*b?c", r"a\*b", r"\?", "a\\",
    "[abc]", "[a-z]", "[!a-z]", "[^a-z]", "[]]", "[!]]", "[]abc]", "[a-]",
    "[[:alpha:]]", "[![:digit:]]", r"[a\]b]", "[abc", "[",
    "?(a|b)", "*(a|b)", "+(a|b)", "@(a|b)", "!(a|b)", "@()", "!()",
    "*(a@(b)c)", "@(a|@(b|c))", "a@(b", "a!(x)c", "foo!(*.txt)bar",
    "*(a|aa)c", "[*?]", "[-a]", "[a^]",
]


@pytest.mark.parametrize("pattern", _ROUNDTRIP)
def test_unparse_roundtrip_is_idempotent(pattern):
    """compile → unparse → compile yields the same structure."""
    first = compile_pattern(pattern)
    second = compile_pattern(unparse(first))
    assert structure(second) == structure(first), (
        f"round-trip changed structure for {pattern!r}: "
        f"unparse={unparse(first)!r}")
