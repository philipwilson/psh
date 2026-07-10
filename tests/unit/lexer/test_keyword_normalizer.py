import dataclasses

from psh.lexer.keyword_normalizer import KeywordNormalizer
from psh.lexer.token_types import Token, TokenType


def make_word(value: str, token_type: TokenType = TokenType.WORD) -> Token:
    return Token(
        type=token_type,
        value=value,
        position=0,
        end_position=len(value)
    )


def test_normalize_does_not_mutate_input_tokens():
    """normalize() is non-mutating: it returns a NEW list of (re)classified
    tokens and leaves the caller's tokens untouched. A regression that mutates
    in place (e.g. via object.__setattr__ to bypass frozen) would change the
    input objects, which the parsers — two of three callers pass their own
    list — must never observe. (Verifier mutation arm (b), 2026-07-10: an
    in-place variant killed 0 of 7,934 unit tests.)"""
    tokens = [
        make_word("if"),
        make_word("x"),
        make_word(";", TokenType.SEMICOLON),
        make_word("then"),
        make_word("echo"),
        make_word("fi"),
    ]
    before = [dataclasses.astuple(t) for t in tokens]

    result = KeywordNormalizer().normalize(tokens)

    # The input tokens' full field-state is unchanged.
    after = [dataclasses.astuple(t) for t in tokens]
    assert after == before, "normalize() must not mutate its input tokens"
    # And the classification genuinely happened — in the RETURNED list.
    assert result is not tokens
    assert result[0].type == TokenType.IF
    assert result[3].type == TokenType.THEN
    assert tokens[0].type == TokenType.WORD  # original still a WORD


def test_normalizer_converts_loop_keywords():
    tokens = [
        make_word("for"),
        make_word("i"),
        make_word("in"),
        make_word("a"),
        make_word("b"),
        make_word(";", TokenType.SEMICOLON),
    ]

    # normalize() does not mutate its input; it returns a new list.
    result = KeywordNormalizer().normalize(tokens)

    assert result[0].type == TokenType.FOR
    assert result[1].type == TokenType.WORD
    assert result[2].type == TokenType.IN


def test_normalizer_handles_case_terminators():
    tokens = [
        make_word("case"),
        make_word("x"),
        make_word("in"),
        make_word("a"),
        make_word(")", TokenType.RPAREN),
        make_word("echo"),
        make_word(";;", TokenType.DOUBLE_SEMICOLON),
        make_word("esac"),
    ]

    result = KeywordNormalizer().normalize(tokens)

    assert result[0].type == TokenType.CASE
    assert result[2].type == TokenType.IN
    assert result[6].type == TokenType.DOUBLE_SEMICOLON
    assert result[7].type == TokenType.ESAC


def test_break_continue_return_are_not_keywords():
    """break/continue/return are ordinary builtins in bash, not reserved
    words — the normalizer must leave them as plain WORDs so they parse as
    simple commands (definable as functions, redirectable, pipeable)."""
    for name in ("break", "continue", "return"):
        tokens = [make_word(name), make_word("1")]

        result = KeywordNormalizer().normalize(tokens)

        assert result[0].type == TokenType.WORD
        assert not result[0].is_keyword


class TestKeywordCaseSensitivity:
    """Keyword recognition is case-sensitive, matching bash.

    `IF`, `If`, `iF` etc. are ordinary words, not reserved words.
    """

    def _normalize(self, *values):
        tokens = [make_word(v) for v in values]
        return KeywordNormalizer().normalize(tokens)

    def test_uppercase_if_stays_word(self):
        tokens = self._normalize("IF", "true")
        assert tokens[0].type == TokenType.WORD
        assert tokens[0].is_keyword is False

    def test_mixed_case_keywords_stay_words(self):
        for value in ("If", "iF", "FOR", "While", "UNTIL", "Case",
                      "THEN", "Do", "DONE", "Fi", "ESAC", "Function",
                      "ELSE", "Elif", "SELECT", "IN", "Return"):
            tokens = self._normalize(value)
            assert tokens[0].type == TokenType.WORD, value
            assert tokens[0].is_keyword is False, value

    def test_uppercase_in_not_converted_after_for(self):
        tokens = self._normalize("for", "i", "IN", "a")
        assert tokens[0].type == TokenType.FOR
        assert tokens[2].type == TokenType.WORD

    def test_lowercase_keywords_still_converted(self):
        tokens = self._normalize("if", "true")
        assert tokens[0].type == TokenType.IF
        assert tokens[0].is_keyword is True


class TestKeywordDefsCaseSensitivity:
    """matches_keyword / KeywordGuard are case-sensitive on token text."""

    def test_matches_keyword_rejects_uppercase_token(self):
        from psh.lexer.keyword_defs import matches_keyword
        token = make_word("IF")
        assert matches_keyword(token, "if") is False
        assert token.is_keyword is False

    def test_matches_keyword_accepts_exact_lowercase(self):
        from psh.lexer.keyword_defs import matches_keyword
        token = make_word("if")
        assert matches_keyword(token, "if") is True
        # matches_keyword is a PURE predicate: it does not stamp is_keyword
        # (the RD path gets is_keyword from the normalizer at lex time).
        assert token.is_keyword is False

    def test_keyword_guard_rejects_uppercase_token(self):
        from psh.lexer.keyword_defs import KeywordGuard
        assert KeywordGuard(make_word("DONE")).matches("done") is False
        assert KeywordGuard(make_word("done")).matches("done") is True


class TestTokenizeKeywordCase:
    """End-to-end tokenize(): uppercase keywords are plain WORDs."""

    def test_tokenize_uppercase_if(self):
        from psh.lexer import tokenize
        tokens = tokenize("IF true; then echo y; fi")
        types = [t.type for t in tokens]
        assert TokenType.IF not in types
        assert tokens[0].type == TokenType.WORD
        assert tokens[0].value == "IF"

    def test_tokenize_lowercase_if_still_keyword(self):
        from psh.lexer import tokenize
        tokens = tokenize("if true; then echo y; fi")
        assert tokens[0].type == TokenType.IF

    def test_tokenize_uppercase_assignment(self):
        from psh.lexer import tokenize
        tokens = tokenize("IF=3")
        assert tokens[0].type == TokenType.WORD
        assert tokens[0].value == "IF=3"


class TestKeywordTablesInSync:
    """R13.C meta-test: the two keyword tables must stay aligned.

    KEYWORDS (lexer/constants.py) is the set the docs and normalizer treat as
    reserved words; KEYWORD_TYPE_MAP (lexer/keyword_defs.py) maps each to its
    TokenType. Adding a keyword to one without the other silently breaks
    normalization or context checking, so pin that they describe the SAME set.
    """

    def test_keywords_set_matches_type_map(self):
        from psh.lexer.constants import KEYWORDS
        from psh.lexer.keyword_defs import KEYWORD_TYPE_MAP
        assert set(KEYWORDS) == set(KEYWORD_TYPE_MAP), (
            "KEYWORDS and KEYWORD_TYPE_MAP disagree: "
            f"only in KEYWORDS={set(KEYWORDS) - set(KEYWORD_TYPE_MAP)}, "
            f"only in KEYWORD_TYPE_MAP={set(KEYWORD_TYPE_MAP) - set(KEYWORDS)}")

    def test_reverse_map_is_bijective(self):
        """Each keyword maps to a distinct TokenType (KEYWORD_BY_TYPE round-trips)."""
        from psh.lexer.keyword_defs import KEYWORD_BY_TYPE, KEYWORD_TYPE_MAP
        assert len(KEYWORD_BY_TYPE) == len(KEYWORD_TYPE_MAP)
