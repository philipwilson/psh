"""Core parser combinator framework.

This module provides the fundamental building blocks for parser combinators,
including the Parser class and the live grammar algebra: ``token``, ``keyword``,
``many``, ``many1``, ``optional``, ``fail_with``, and the ``Parser.or_else`` /
``.map`` / ``.then`` methods.

## The result type: a discriminated success/failure union

A parse produces a :class:`ParseResult`, which is one of two shapes:

* :class:`ParseSuccess` — carries the produced ``value`` and the ``position``
  reached.
* :class:`ParseFailure` — carries the ``position`` at which the failure was
  observed plus an FP-style error channel:

  * ``committed`` — a *cut*. The parser consumed input and is certain this is
    the right production, so :meth:`Parser.or_else` must NOT backtrack to an
    alternative; the committed failure propagates instead.

    RESERVED / currently dormant: nothing in the grammar constructs a committed
    ``ParseFailure`` yet (a repo-wide ``committed=True`` search is empty), so
    this defaults to ``False`` and ``or_else``/``many``/``separated_by`` behave
    as a plain ordered choice. Commitment is presently expressed the imperative
    way — by RAISING a ``ParseError`` via
    :func:`diagnostics.raise_committed_error` once a construct is past its point
    of no return (after ``do``/``then``/``|``/``&&`` …), which propagates past
    every ``or_else``. The ``committed`` field is the in-algebra channel kept
    ready for the eventual migration of those raise sites to returned failures
    (the deferred "move committed errors out of exceptions" item); the cut logic
    in the combinators is already in place so that migration needs no core
    changes. It is wired-but-inert by design, not dead code.
  * ``expected`` — labels describing what would have allowed progress, kept so
    same-position alternatives can be merged into a richer diagnostic.

``ParseSuccess`` / ``ParseFailure`` are the *discriminated constructors*; both
are ``ParseResult`` instances and expose the legacy attribute surface
(``success``/``value``/``position``/``error``) so existing call sites keep
working while the grammar migrates to constructing the two shapes explicitly
and branching on ``result.success``.
"""

from dataclasses import dataclass
from typing import Callable, Generic, List, Optional, Tuple, TypeVar, cast

from ...lexer.keyword_defs import matches_keyword
from ...lexer.token_types import Token, TokenType

# Type variables for parser combinators
T = TypeVar('T')
U = TypeVar('U')


@dataclass
class ParseResult(Generic[T]):
    """Result of a parse operation — a success/failure discriminated union.

    Prefer the :class:`ParseSuccess` / :class:`ParseFailure` constructors in
    new code; branch on ``success``. The raw field constructor is retained for
    back-compatibility with existing call sites.

    Attributes:
        success: Whether the parse succeeded (the discriminant).
        value: The parsed value if successful.
        position: Position reached (success) or where the failure was observed.
        error: Error message if the parse failed.
        committed: Cut flag — a committed failure is not retried by ``or_else``.
        expected: Labels of what would have allowed progress (for diagnostics).
    """
    success: bool
    value: Optional[T] = None
    position: int = 0
    error: Optional[str] = None
    committed: bool = False
    expected: Tuple[str, ...] = ()


class ParseSuccess(ParseResult[T]):
    """A successful parse carrying a value (discriminated constructor)."""

    def __init__(self, value: T, position: int) -> None:
        super().__init__(success=True, value=value, position=position)


class ParseFailure(ParseResult[T]):
    """A failed parse (discriminated constructor) with the FP error channel.

    Args:
        position: Where the failure was observed.
        error: Human-readable message (the one intentionally-unaligned axis vs
            the recursive-descent parser).
        expected: Labels of what would have allowed progress.
        committed: When True, this is a cut — ``or_else`` will not backtrack.
    """

    def __init__(self, position: int, error: Optional[str] = None, *,
                 expected: Tuple[str, ...] = (), committed: bool = False) -> None:
        super().__init__(success=False, value=None, position=position,
                         error=error, expected=expected, committed=committed)


def _farther_failure(a: ParseResult, b: ParseResult) -> ParseResult:
    """Pick the more informative of two recoverable failures.

    The *farthest-error* rule: a failure that consumed more input (higher
    ``position``) is the better diagnostic — it reflects the alternative that
    matched the most before giving up. On a positional tie the two
    ``expected`` label sets are merged (order-preserving, de-duplicated) so the
    message can list every token that could have continued the parse. Both
    arguments must be failures; commitment is not involved (committed failures
    are handled by ``or_else`` before reaching here).
    """
    if a.position > b.position:
        return a
    if b.position > a.position:
        return b
    merged = tuple(dict.fromkeys(a.expected + b.expected))
    return ParseFailure(a.position, b.error, expected=merged)


class Parser(Generic[T]):
    """A parser combinator that produces values of type T.

    This is the core abstraction for parser combinators. A parser is essentially
    a function that takes tokens and a position, and returns a parse result.
    """

    def __init__(self, parse_fn: Callable[[List[Token], int], ParseResult[T]]):
        """Initialize with a parsing function.

        Args:
            parse_fn: Function that performs the actual parsing
        """
        self.parse_fn = parse_fn

    def parse(self, tokens: List[Token], position: int = 0) -> ParseResult[T]:
        """Execute the parser.

        Args:
            tokens: List of tokens to parse
            position: Starting position in token stream

        Returns:
            ParseResult containing success status and parsed value
        """
        return self.parse_fn(tokens, position)

    def map(self, fn: Callable[[T], U]) -> 'Parser[U]':
        """Transform the result of this parser.

        Args:
            fn: Function to transform the parsed value

        Returns:
            New parser that applies the transformation
        """
        def mapped_parse(tokens: List[Token], pos: int) -> ParseResult[U]:
            result = self.parse(tokens, pos)
            if result.success:
                return ParseSuccess(fn(cast(T, result.value)), result.position)
            return ParseFailure(pos, result.error, expected=result.expected,
                                committed=result.committed)

        return Parser(mapped_parse)

    def then(self, next_parser: 'Parser[U]') -> 'Parser[Tuple[T, U]]':
        """Sequence this parser with another.

        Args:
            next_parser: Parser to run after this one

        Returns:
            Parser that returns tuple of both results
        """
        def sequence_parse(tokens: List[Token], pos: int) -> ParseResult[Tuple[T, U]]:
            first_result = self.parse(tokens, pos)
            if not first_result.success:
                return ParseFailure(pos, first_result.error,
                                    expected=first_result.expected,
                                    committed=first_result.committed)

            second_result = next_parser.parse(tokens, first_result.position)
            if not second_result.success:
                # Atomic: a failed sequence resets to the start position, the
                # same backtracking discipline as sequence(). A committed
                # failure keeps its cut so or_else upstream won't backtrack.
                return ParseFailure(pos, second_result.error,
                                    expected=second_result.expected,
                                    committed=second_result.committed)

            return ParseSuccess(
                (cast(T, first_result.value), cast(U, second_result.value)),
                second_result.position,
            )

        return Parser(sequence_parse)

    def or_else(self, alternative: 'Parser') -> 'Parser':
        """Try this parser, or alternative if it fails.

        Ordered choice with a cut: if this parser fails *committed* (it consumed
        input and is sure of the production), the failure propagates and the
        alternative is NOT tried. Otherwise the alternative is attempted.

        The alternative may produce a *different* value type than this parser —
        the shell grammar composes ordered choice over heterogeneous productions
        (e.g. ``arithmetic_command.or_else(enhanced_test_statement)`` yields an
        ``ArithmeticEvaluation`` OR an ``EnhancedTestStatement``). The result
        type is therefore the loose ``Parser`` (a value of either branch) rather
        than a single ``Parser[T]``.

        Args:
            alternative: Parser to try if this one fails

        Returns:
            Parser that tries both options
        """
        def choice_parse(tokens: List[Token], pos: int) -> ParseResult:
            result = self.parse(tokens, pos)
            if result.success or result.committed:
                return result
            alt = alternative.parse(tokens, pos)
            if alt.success or alt.committed:
                return alt
            # Both alternatives failed (recoverably): report the more
            # informative failure by the farthest-error rule.
            return _farther_failure(result, alt)

        return Parser(choice_parse)


# Basic combinators
def token(token_type: str) -> Parser[Token]:
    """Parse a specific token type.

    Args:
        token_type: Name of the token type to match. Must be a real
            :class:`TokenType` member — an unknown name raises immediately at
            construction, so a ghost token parser (a typo or a stale POSIX name
            the lexer never emits) fails at import time instead of silently
            never matching.

    Returns:
        Parser that matches the specified token type

    Raises:
        ValueError: If ``token_type`` is not a ``TokenType`` member.
    """
    if token_type not in TokenType.__members__:
        raise ValueError(
            f"token(): {token_type!r} is not a TokenType member "
            "(ghost token name — the lexer can never emit it)"
        )

    def parse_token(tokens: List[Token], pos: int) -> ParseResult[Token]:
        if pos < len(tokens) and tokens[pos].type.name == token_type:
            return ParseSuccess(tokens[pos], pos + 1)
        error = f"Expected {token_type}"
        if pos < len(tokens):
            error += f", got {tokens[pos].type.name}"
        else:
            error += ", but reached end of input"
        return ParseFailure(pos, error, expected=(token_type,))

    return Parser(parse_token)


def many(parser: Parser[T]) -> Parser[List[T]]:
    """Parse zero or more occurrences.

    Stops on the first non-committed failure (returning what was collected). A
    *committed* failure propagates — it is a real syntax error mid-repetition,
    not the natural end of the repetition.

    Args:
        parser: Parser to repeat

    Returns:
        Parser that returns list of parsed values
    """
    def parse_many(tokens: List[Token], pos: int) -> ParseResult[List[T]]:
        results: List[T] = []
        current_pos = pos

        while True:
            result = parser.parse(tokens, current_pos)
            if not result.success:
                if result.committed:
                    return cast(ParseResult[List[T]], result)
                break
            results.append(cast(T, result.value))
            current_pos = result.position

        return ParseSuccess(results, current_pos)

    return Parser(parse_many)


def many1(parser: Parser[T]) -> Parser[List[T]]:
    """Parse one or more occurrences.

    Args:
        parser: Parser to repeat

    Returns:
        Parser that returns non-empty list of parsed values
    """
    return parser.then(many(parser)).map(lambda pair: [pair[0]] + pair[1])


def optional(parser: Parser[T]) -> Parser[Optional[T]]:
    """Parse optionally.

    Args:
        parser: Parser to try

    Returns:
        Parser that returns value or None
    """
    def parse_optional(tokens: List[Token], pos: int) -> ParseResult[Optional[T]]:
        result = parser.parse(tokens, pos)
        if result.success:
            return cast(ParseResult[Optional[T]], result)
        return ParseSuccess(None, pos)

    return Parser(parse_optional)


def fail_with(msg: str) -> Parser[None]:
    """Parser that always fails with custom message.

    Args:
        msg: Error message

    Returns:
        Parser that always fails
    """
    def parse_fail(tokens: List[Token], pos: int) -> ParseResult[None]:
        return ParseFailure(pos, msg)

    return Parser(parse_fail)


def keyword(kw: str) -> Parser[Token]:
    """Parse specific keyword ensuring word boundaries.

    Args:
        kw: Keyword to match

    Returns:
        Parser that matches the keyword
    """
    def parse_keyword(tokens: List[Token], pos: int) -> ParseResult[Token]:
        if pos >= len(tokens):
            return ParseFailure(pos, f"Expected keyword '{kw}' but reached end of input",
                                expected=(kw,))

        token = tokens[pos]
        if matches_keyword(token, kw):
            return ParseSuccess(token, pos + 1)

        return ParseFailure(pos, f"Expected keyword '{kw}', got {token.value}",
                            expected=(kw,))

    return Parser(parse_keyword)
