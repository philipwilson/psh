"""Unit tests for the ``$((`` arithmetic-vs-command-substitution
disambiguation (POSIX; bash parse.y read_token_word).

``$((`` is arithmetic only if the paren group opened by its second ``(``
closes with another ``)`` immediately following. Otherwise the construct
is re-read as a ``$(`` command substitution whose body starts with a
subshell: ``echo $((echo a); echo b)`` prints ``a b``. The scan lives in
``pure_helpers.scan_double_paren_arithmetic``; these tests pin it both
directly and through the lexer's token classification, including the
sibling extent scanners (cmdsub scanner, ``${...}`` validation, and the
assignment-subscript word scanner). Every behavior here was verified
against bash 5.2 (tmp/truth_a4.py battery, reappraisal #15 finding A4).
"""

import pytest

from psh.lexer import tokenize
from psh.lexer.pure_helpers import (
    ArithParenScan,
    find_balanced_double_parentheses,
    scan_double_paren_arithmetic,
)
from psh.lexer.token_types import TokenType


def scan(text_after_dollar_dparen):
    """Scan text as the content following '$((' and return (pos, status)."""
    return scan_double_paren_arithmetic(text_after_dollar_dparen, 0)


class TestScanDoubleParenArithmetic:
    """The three-way scan outcome, directly."""

    def test_simple_arithmetic_closed(self):
        pos, status = scan('1+2))')
        assert status is ArithParenScan.CLOSED and pos == 5

    def test_inner_parens_still_arithmetic(self):
        pos, status = scan(' (1+2) * 3 ))')
        assert status is ArithParenScan.CLOSED and pos == 13

    def test_nested_arithmetic_expansion(self):
        text = ' $((1+1)) + 1 ))'
        pos, status = scan(text)
        assert status is ArithParenScan.CLOSED and pos == len(text)

    def test_subshell_body_is_not_arithmetic(self):
        _, status = scan('echo a); echo b)')
        assert status is ArithParenScan.NOT_ARITHMETIC

    def test_close_parens_not_adjacent_is_not_arithmetic(self):
        # The group closes on a space, not on ')': `$((echo a) )`.
        _, status = scan('echo a) )')
        assert status is ArithParenScan.NOT_ARITHMETIC

    def test_two_groups_do_not_rebalance(self):
        # Old counting let the depth go negative and matched a later '))'.
        _, status = scan('echo a) + (echo b))')
        assert status is ArithParenScan.NOT_ARITHMETIC

    def test_unclosed_input_exhausted(self):
        pos, status = scan('1 +')
        assert status is ArithParenScan.UNCLOSED and pos == 3

    def test_inner_close_at_end_of_input_is_unclosed(self):
        # `$((echo a` + `)` at EOF: the NEXT character decides (`)` would
        # make it arithmetic), so this is incomplete input, not a verdict.
        _, status = scan('echo a)')
        assert status is ArithParenScan.UNCLOSED

    def test_nested_cmdsub_extent_skipped(self):
        text = 'x + $(case y in y) echo 1;; esac) ))'
        pos, status = scan(text)
        assert status is ArithParenScan.CLOSED and pos == len(text)

    def test_boolean_view_maps_closed_only(self):
        assert find_balanced_double_parentheses('1+2))', 0) == (5, True)
        assert find_balanced_double_parentheses('echo a); echo b)', 0)[1] \
            is False
        assert find_balanced_double_parentheses('1 +', 0)[1] is False


class TestLexerTokenClassification:
    """The lexer emits ARITH_EXPANSION vs COMMAND_SUB per the rule."""

    def one_token(self, source, token_type):
        tokens = [t for t in tokenize(source) if t.type == token_type]
        assert len(tokens) == 1, [(t.type, t.value) for t in tokenize(source)]
        return tokens[0]

    def test_arithmetic_stays_arithmetic(self):
        tok = self.one_token('echo $((1+2))', TokenType.ARITH_EXPANSION)
        assert tok.value == '$((1+2))'

    def test_non_numeric_content_still_arithmetic(self):
        # `$((ls))` and `$((echo a))` have matching '))' — arithmetic
        # (evaluation errors happen later, exactly as in bash).
        tok = self.one_token('echo $((echo a))', TokenType.ARITH_EXPANSION)
        assert tok.value == '$((echo a))'

    def test_subshell_fallback_is_command_sub(self):
        tok = self.one_token('echo $((echo a); echo b)', TokenType.COMMAND_SUB)
        assert tok.value == '$((echo a); echo b)'

    def test_fallback_mid_word(self):
        tok = self.one_token('echo pre$((echo a); echo b)post',
                             TokenType.COMMAND_SUB)
        assert tok.value == '$((echo a); echo b)'

    def test_fallback_inside_double_quotes(self):
        tokens = tokenize('echo "$((echo a); echo b)"')
        strings = [t for t in tokens if t.type == TokenType.STRING]
        assert len(strings) == 1
        assert any(p.expansion_type == 'command'
                   for p in strings[0].parts)

    def test_fallback_inside_nested_cmdsub(self):
        tok = self.one_token('echo $(echo $((echo a); echo b))',
                             TokenType.COMMAND_SUB)
        assert tok.value == '$(echo $((echo a); echo b))'

    def test_fallback_inside_param_expansion_operand(self):
        tok = self.one_token('echo "${v:-$((echo a); echo b)}"',
                             TokenType.STRING)
        assert '$((echo a); echo b)' in tok.value

    def test_fallback_inside_assignment_subscript(self):
        # skip_expansion_region (array-assignment detection) must span the
        # whole cmdsub so the word stays one assignment token.
        tokens = tokenize('a[$((echo 3) )]=v')
        assert tokens[0].value == 'a[$((echo 3) )]=v'


class TestUnclosedIsIncompleteInput:
    """Unclosed `$((` still raises at_eof so line gathering keeps reading."""

    def parse_error(self, source):
        from psh.parser import Parser
        from psh.parser.recursive_descent.helpers import ParseError
        tokens = tokenize(source)
        with pytest.raises(ParseError) as exc:
            Parser(tokens, source_text=source).parse()
        return exc.value

    def test_unclosed_arithmetic_at_eof(self):
        assert self.parse_error('echo $((1 +').at_eof

    def test_inner_close_at_eof(self):
        assert self.parse_error('echo $((echo a)').at_eof

    def test_fallback_cmdsub_unclosed_at_eof(self):
        assert self.parse_error('echo $((echo a); echo b').at_eof
