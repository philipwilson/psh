"""Tests for core parser combinator framework."""


import pytest

from psh.lexer.token_types import Token, TokenType
from psh.parser.combinators.core import (
    ParseFailure,
    Parser,
    ParseResult,
    ParseSuccess,
    fail_with,
    keyword,
    many,
    many1,
    optional,
    token,
)


def make_token(token_type: TokenType, value: str, position: int = 0) -> Token:
    """Helper to create a token with minimal required fields."""
    return Token(type=token_type, value=value, position=position)


class TestParseResult:
    """Test the ParseResult dataclass."""

    def test_success_result(self):
        """Test creating a successful parse result."""
        result = ParseResult(success=True, value="test", position=5)
        assert result.success is True
        assert result.value == "test"
        assert result.position == 5
        assert result.error is None

    def test_failure_result(self):
        """Test creating a failed parse result."""
        result = ParseResult(success=False, error="Expected token", position=2)
        assert result.success is False
        assert result.value is None
        assert result.position == 2
        assert result.error == "Expected token"

    def test_new_result_defaults(self):
        """The error channel fields default to non-committed / no labels."""
        result = ParseResult(success=False, error="x", position=0)
        assert result.committed is False
        assert result.expected == ()


class TestDiscriminatedConstructors:
    """The ParseSuccess / ParseFailure discriminated-union constructors."""

    def test_parse_success(self):
        """ParseSuccess is a successful ParseResult carrying a value."""
        r = ParseSuccess("v", 3)
        assert isinstance(r, ParseResult)
        assert r.success is True
        assert r.value == "v"
        assert r.position == 3
        assert r.error is None
        assert r.committed is False

    def test_parse_failure(self):
        """ParseFailure is a failed ParseResult with the FP error channel."""
        r = ParseFailure(2, "nope", expected=("WORD", "STRING"), committed=True)
        assert isinstance(r, ParseResult)
        assert r.success is False
        assert r.value is None
        assert r.position == 2
        assert r.error == "nope"
        assert r.expected == ("WORD", "STRING")
        assert r.committed is True

    def test_parse_failure_defaults(self):
        """ParseFailure defaults to recoverable (not committed), no labels."""
        r = ParseFailure(1, "soft")
        assert r.committed is False
        assert r.expected == ()


class TestCommitment:
    """or_else / many honour the cut (committed) flag."""

    def test_or_else_retries_recoverable_failure(self):
        """A plain (recoverable) failure lets or_else try the alternative."""
        left = Parser(lambda t, p: ParseFailure(p, "left"))
        right = Parser(lambda t, p: ParseSuccess("R", p + 1))
        result = left.or_else(right).parse([], 0)
        assert result.success is True
        assert result.value == "R"

    def test_or_else_does_not_retry_committed_failure(self):
        """A committed failure is a cut: or_else must NOT try the alternative."""
        left = Parser(lambda t, p: ParseFailure(p, "committed!", committed=True))
        right = Parser(lambda t, p: ParseSuccess("R", p + 1))
        result = left.or_else(right).parse([], 0)
        assert result.success is False
        assert result.committed is True
        assert result.error == "committed!"

    def test_many_propagates_committed_failure(self):
        """many stops-and-succeeds on a recoverable failure but propagates a cut."""
        committed = Parser(lambda t, p: ParseFailure(p, "boom", committed=True))
        result = many(committed).parse([], 0)
        assert result.success is False
        assert result.committed is True

    def test_many_swallows_recoverable_failure(self):
        """many returns the collected list on a recoverable failure."""
        recoverable = Parser(lambda t, p: ParseFailure(p, "done"))
        result = many(recoverable).parse([], 0)
        assert result.success is True
        assert result.value == []


class TestFarthestError:
    """or_else reports the more informative failure (farthest-error rule)."""

    def test_or_else_keeps_failure_that_consumed_more(self):
        """When both branches fail, keep the one that reached further."""
        near = Parser(lambda t, p: ParseFailure(p, "near", expected=("A",)))
        far = Parser(lambda t, p: ParseFailure(p + 2, "far", expected=("B",)))
        # near is tried first but far reached a higher position -> far wins
        result = near.or_else(far).parse([], 0)
        assert result.success is False
        assert result.error == "far"
        assert result.position == 2

    def test_or_else_keeps_first_when_it_reached_further(self):
        """Order-independent: the farther failure wins even if tried first."""
        far = Parser(lambda t, p: ParseFailure(p + 3, "far", expected=("B",)))
        near = Parser(lambda t, p: ParseFailure(p, "near", expected=("A",)))
        result = far.or_else(near).parse([], 0)
        assert result.success is False
        assert result.error == "far"
        assert result.position == 3

    def test_or_else_merges_expected_on_tie(self):
        """At an equal position the expected-label sets are merged."""
        a = Parser(lambda t, p: ParseFailure(p, "a", expected=("A", "C")))
        b = Parser(lambda t, p: ParseFailure(p, "b", expected=("B", "C")))
        result = a.or_else(b).parse([], 0)
        assert result.success is False
        assert result.position == 0
        # order-preserving, de-duplicated union
        assert result.expected == ("A", "C", "B")


class TestParser:
    """Test the Parser class methods."""

    def test_parse_function(self):
        """Test basic parser execution."""
        def parse_test(tokens, pos):
            return ParseResult(success=True, value="test", position=pos + 1)

        parser = Parser(parse_test)
        result = parser.parse([], 0)
        assert result.success is True
        assert result.value == "test"
        assert result.position == 1

    def test_map(self):
        """Test transforming parser results."""
        def parse_number(tokens, pos):
            return ParseResult(success=True, value=42, position=pos + 1)

        parser = Parser(parse_number).map(lambda x: x * 2)
        result = parser.parse([], 0)
        assert result.value == 84

    def test_map_failure(self):
        """Test that map preserves failures."""
        def parse_fail(tokens, pos):
            return ParseResult(success=False, error="Failed", position=pos)

        parser = Parser(parse_fail).map(lambda x: x * 2)
        result = parser.parse([], 0)
        assert result.success is False
        assert result.error == "Failed"

    def test_then(self):
        """Test sequencing parsers."""
        def parse_a(tokens, pos):
            return ParseResult(success=True, value="a", position=pos + 1)

        def parse_b(tokens, pos):
            return ParseResult(success=True, value="b", position=pos + 1)

        parser = Parser(parse_a).then(Parser(parse_b))
        result = parser.parse([], 0)
        assert result.success is True
        assert result.value == ("a", "b")
        assert result.position == 2

    def test_then_first_fails(self):
        """Test sequencing when first parser fails."""
        def parse_fail(tokens, pos):
            return ParseResult(success=False, error="Failed", position=pos)

        def parse_ok(tokens, pos):
            return ParseResult(success=True, value="ok", position=pos + 1)

        parser = Parser(parse_fail).then(Parser(parse_ok))
        result = parser.parse([], 0)
        assert result.success is False
        assert result.error == "Failed"

    def test_then_second_fails_preserves_failure_position(self):
        """Law (campaign S4 §8): then preserves the FAILURE POSITION.

        When the second member fails, the composite failure reports how far the
        sequence got (the second parser's failure reach), not the sequence's
        start. Backtracking is not driven by this position — or_else always
        retries its alternative from its own start pos — so preserving the reach
        only sharpens the farthest-error diagnostic. (Previously this reset to
        the start, which violated the law.)
        """
        def parse_ok(tokens, pos):
            return ParseResult(success=True, value="ok", position=pos + 1)

        def parse_fail(tokens, pos):
            # Fails at pos+1 (one past where it started, i.e. it "reached" that far).
            return ParseResult(success=False, error="boom", position=pos + 1)

        result = Parser(parse_ok).then(Parser(parse_fail)).parse([], 3)
        assert result.success is False
        # parse_ok: 3->4; parse_fail runs at 4, fails reaching 5. The law
        # propagates the inner failure position (5), not the start (3).
        assert result.position == 5

    def test_or_else(self):
        """Test alternative parsing."""
        def parse_fail(tokens, pos):
            return ParseResult(success=False, error="Failed", position=pos)

        def parse_ok(tokens, pos):
            return ParseResult(success=True, value="ok", position=pos + 1)

        parser = Parser(parse_fail).or_else(Parser(parse_ok))
        result = parser.parse([], 0)
        assert result.success is True
        assert result.value == "ok"

    def test_or_else_first_succeeds(self):
        """Test that or_else doesn't try alternative if first succeeds."""
        def parse_first(tokens, pos):
            return ParseResult(success=True, value="first", position=pos + 1)

        def parse_second(tokens, pos):
            return ParseResult(success=True, value="second", position=pos + 1)

        parser = Parser(parse_first).or_else(Parser(parse_second))
        result = parser.parse([], 0)
        assert result.value == "first"


class TestBasicCombinators:
    """Test basic combinator functions."""

    def test_token(self):
        """Test token parser."""
        tokens = [make_token(TokenType.WORD, "hello")]
        parser = token("WORD")
        result = parser.parse(tokens, 0)
        assert result.success is True
        assert result.value.value == "hello"
        assert result.position == 1

    def test_token_wrong_type(self):
        """Test token parser with wrong type."""
        tokens = [make_token(TokenType.SEMICOLON, ";")]
        parser = token("WORD")
        result = parser.parse(tokens, 0)
        assert result.success is False
        assert "Expected WORD, got SEMICOLON" in result.error

    def test_token_at_end(self):
        """Test token parser at end of input."""
        parser = token("WORD")
        result = parser.parse([], 0)
        assert result.success is False
        assert "reached end of input" in result.error

    def test_token_rejects_ghost_name(self):
        """A token() name that is not a TokenType member raises at construction.

        This converts a future ghost token parser (a typo, or a POSIX name the
        lexer never emits like AND_IF) into an import-time failure instead of a
        parser that silently never matches.
        """
        with pytest.raises(ValueError, match="not a TokenType member"):
            token("AND_IF")
        with pytest.raises(ValueError, match="not a TokenType member"):
            token("NOT_A_REAL_TOKEN")

    def test_token_accepts_every_real_tokentype(self):
        """token() accepts every real TokenType member (no false rejections)."""
        for name in TokenType.__members__:
            token(name)  # must not raise

    def test_many_empty(self):
        """Test many with no matches."""
        tokens = [make_token(TokenType.SEMICOLON, ";")]
        parser = many(token("WORD"))
        result = parser.parse(tokens, 0)
        assert result.success is True
        assert result.value == []
        assert result.position == 0

    def test_many_multiple(self):
        """Test many with multiple matches."""
        tokens = [
            make_token(TokenType.WORD, "a"),
            make_token(TokenType.WORD, "b"),
            make_token(TokenType.SEMICOLON, ";")
        ]
        parser = many(token("WORD"))
        result = parser.parse(tokens, 0)
        assert result.success is True
        assert len(result.value) == 2
        assert result.value[0].value == "a"
        assert result.value[1].value == "b"
        assert result.position == 2

    def test_many1_success(self):
        """Test many1 with at least one match."""
        tokens = [make_token(TokenType.WORD, "test")]
        parser = many1(token("WORD"))
        result = parser.parse(tokens, 0)
        assert result.success is True
        assert len(result.value) == 1
        assert result.value[0].value == "test"

    def test_many1_failure(self):
        """Test many1 with no matches."""
        tokens = [make_token(TokenType.SEMICOLON, ";")]
        parser = many1(token("WORD"))
        result = parser.parse(tokens, 0)
        assert result.success is False

    def test_optional_present(self):
        """Test optional when value is present."""
        tokens = [make_token(TokenType.WORD, "test")]
        parser = optional(token("WORD"))
        result = parser.parse(tokens, 0)
        assert result.success is True
        assert result.value.value == "test"
        assert result.position == 1

    def test_optional_absent(self):
        """Test optional when value is absent."""
        tokens = [make_token(TokenType.SEMICOLON, ";")]
        parser = optional(token("WORD"))
        result = parser.parse(tokens, 0)
        assert result.success is True
        assert result.value is None
        assert result.position == 0


class TestEnhancedCombinators:
    """Test enhanced combinator functions."""

    def test_fail_with(self):
        """Test fail_with combinator."""
        parser = fail_with("Custom error message")
        result = parser.parse([], 0)
        assert result.success is False
        assert result.error == "Custom error message"

    def test_keyword(self):
        """Test keyword parser."""
        tokens = [make_token(TokenType.WORD, "if")]
        parser = keyword("if")
        result = parser.parse(tokens, 0)
        assert result.success is True
        assert result.value.value == "if"

    def test_keyword_uppercase_token(self):
        """Test keyword with uppercase token type."""
        tokens = [make_token(TokenType.IF, "if")]
        parser = keyword("if")
        result = parser.parse(tokens, 0)
        assert result.success is True
        assert result.value.value == "if"

    def test_keyword_wrong(self):
        """Test keyword with wrong value."""
        tokens = [make_token(TokenType.WORD, "else")]
        parser = keyword("if")
        result = parser.parse(tokens, 0)
        assert result.success is False
        assert "Expected keyword 'if'" in result.error
