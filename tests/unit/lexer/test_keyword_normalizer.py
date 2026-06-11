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
