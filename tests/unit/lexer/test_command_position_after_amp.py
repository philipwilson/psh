"""`&` and `|&` set command position (reappraisal #15 A2).

STATEMENT_SEPARATORS omitted AMPERSAND (and PIPE_AND), so the lexer pass
and the keyword normalizer treated the token after `&` as non-command
position: `true & if …` lexed `if` as a plain WORD (parse error), `&
[[` as a literal word, and `& !` as a command named `!`. The cmdsub
extent scanner already handled `&` correctly — this locks all three
machines in agreement (docs/architecture/command_position.md).

Every case verified against bash 5.2 (tmp/r15_a2_truth_table.sh).
"""

from psh.lexer import tokenize
from psh.lexer.command_position import STATEMENT_SEPARATORS
from psh.lexer.token_types import TokenType


def types(source):
    return [t.type for t in tokenize(source)]


def type_of(source, value):
    """Token type of the first token with the given value."""
    return next(t.type for t in tokenize(source) if t.value == value)


class TestSeparatorVocabulary:
    def test_ampersand_and_pipe_amp_are_statement_separators(self):
        assert TokenType.AMPERSAND in STATEMENT_SEPARATORS
        assert TokenType.PIPE_AND in STATEMENT_SEPARATORS


class TestKeywordAfterAmpersand:
    def test_if_after_amp_is_keyword(self):
        assert type_of('true & if true; then echo B; fi', 'if') == TokenType.IF

    def test_while_after_amp_is_keyword(self):
        assert type_of('true & while true; do break; done',
                       'while') == TokenType.WHILE

    def test_case_after_amp_is_keyword(self):
        assert type_of('true & case x in x) echo C;; esac',
                       'case') == TokenType.CASE

    def test_for_after_amp_is_keyword(self):
        assert type_of('true & for i in 1; do :; done', 'for') == TokenType.FOR

    def test_keyword_after_amp_without_space(self):
        assert type_of('true &if true; then echo NS; fi', 'if') == TokenType.IF

    def test_keyword_after_pipe_amp(self):
        assert type_of('a |& while true; do break; done',
                       'while') == TokenType.WHILE


class TestOperatorsAfterAmpersand:
    def test_double_bracket_after_amp_is_operator(self):
        assert type_of('true & [[ -n x ]]', '[[') == TokenType.DOUBLE_LBRACKET

    def test_bang_after_amp_is_pipeline_negation(self):
        assert type_of('true & ! false', '!') == TokenType.EXCLAMATION

    def test_closing_keyword_directly_after_amp(self):
        # `{ echo a & }` / `… & fi` — the token after `&` is the closer.
        assert type_of('{ echo a & }', '}') == TokenType.RBRACE
        assert type_of('if true; then echo hi & fi', 'fi') == TokenType.FI


class TestAmpersandTokensUnaffected:
    """`&`-containing tokens that are NOT separators keep their meaning."""

    def test_and_and_still_one_token(self):
        assert TokenType.AND_AND in types('true && echo A')

    def test_case_terminators_still_recognized(self):
        toks = types('case a in a) echo one ;& b) echo two ;;& c) : ;; esac')
        assert TokenType.SEMICOLON_AMP in toks      # ;&
        assert TokenType.AMP_SEMICOLON in toks      # ;;&
        assert TokenType.DOUBLE_SEMICOLON in toks   # ;;

    def test_quoted_amp_is_literal(self):
        assert TokenType.AMPERSAND not in types('echo "a & b"')

    def test_keyword_value_after_amp_as_argument_stays_word(self):
        # `if` here follows `echo`, not `&` — still a plain word.
        assert type_of('true & echo if', 'if') == TokenType.WORD
