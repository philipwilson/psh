from psh.lexer.keyword_normalizer import KeywordNormalizer
from psh.lexer.token_types import Token, TokenType


def make_word(value: str, token_type: TokenType = TokenType.WORD) -> Token:
    return Token(
        type=token_type,
        value=value,
        position=0,
        end_position=len(value)
    )


def test_normalizer_converts_loop_keywords():
    tokens = [
        make_word("for"),
        make_word("i"),
        make_word("in"),
        make_word("a"),
        make_word("b"),
        make_word(";")
    ]

    tokens[5].type = TokenType.SEMICOLON

    normalizer = KeywordNormalizer()
    normalizer.normalize(tokens)

    assert tokens[0].type == TokenType.FOR
    assert tokens[1].type == TokenType.WORD
    assert tokens[2].type == TokenType.IN


def test_normalizer_handles_case_terminators():
    tokens = [
        make_word("case"),
        make_word("x"),
        make_word("in"),
        make_word("a"),
        make_word(")"),
        make_word("echo"),
        make_word(";;"),
        make_word("esac")
    ]

    # Adjust token types for punctuation
    tokens[4].type = TokenType.RPAREN
    tokens[6].type = TokenType.DOUBLE_SEMICOLON

    normalizer = KeywordNormalizer()
    normalizer.normalize(tokens)

    assert tokens[0].type == TokenType.CASE
    assert tokens[2].type == TokenType.IN
    assert tokens[6].type == TokenType.DOUBLE_SEMICOLON
    assert tokens[7].type == TokenType.ESAC


def test_normalizer_converts_return_keyword():
    tokens = [
        make_word("return"),
        make_word("1")
    ]

    normalizer = KeywordNormalizer()
    normalizer.normalize(tokens)

    assert tokens[0].type == TokenType.RETURN
    assert tokens[0].is_keyword is True


class TestKeywordCaseSensitivity:
    """Keyword recognition is case-sensitive, matching bash.

    `IF`, `If`, `iF` etc. are ordinary words, not reserved words.
    """

    def _normalize(self, *values):
        tokens = [make_word(v) for v in values]
        KeywordNormalizer().normalize(tokens)
        return tokens

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
        assert token.is_keyword is True

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
