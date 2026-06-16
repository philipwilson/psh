"""The formatter must preserve quoting on `[[ ]]` binary-test operands.

Previously it emitted the derived (unquoted) operand strings, which changed
the meaning — `[[ $x == "*.txt" ]]` (literal compare) became `[[ $x == *.txt ]]`
(glob), and `[[ $x == "a b" ]]` no longer re-parsed (reappraisal #13 MED).
"""

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor.formatter_visitor import FormatterVisitor


def _fmt(src):
    return FormatterVisitor().visit(parse(tokenize(src)))


def test_quoted_glob_operand_preserved():
    # The quotes make it a literal compare; dropping them would make it a glob.
    assert _fmt('[[ $x == "*.txt" ]]') == '[[ $x == "*.txt" ]]'


def test_operand_with_space_preserved_and_reparses():
    out = _fmt('[[ $x == "a b" ]]')
    assert out == '[[ $x == "a b" ]]'
    parse(tokenize(out))  # must not raise


def test_unquoted_glob_operand_unchanged():
    assert _fmt('[[ $x == *.txt ]]') == '[[ $x == *.txt ]]'


def test_unquoted_var_operands_unchanged():
    assert _fmt('[[ $a != $b ]]') == '[[ $a != $b ]]'


def test_regex_operand_quoting_preserved():
    assert _fmt('[[ $x =~ "^foo bar" ]]') == '[[ $x =~ "^foo bar" ]]'


def test_composite_quoted_left_operand():
    assert _fmt('[[ "$HOME/bin" == /* ]]') == '[[ "$HOME/bin" == /* ]]'


def test_roundtrip_does_not_change_semantics():
    # Format then re-parse: the re-parsed AST must format identically (stable).
    for src in ('[[ $x == "*.txt" ]]', '[[ $x == "a b" ]]',
                '[[ -n "$y" ]]', '[[ $a == $b ]]'):
        once = _fmt(src)
        twice = _fmt(once)
        assert once == twice, f"{src}: {once!r} != {twice!r}"
