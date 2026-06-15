"""Core parser combinator framework.

This module provides the fundamental building blocks for parser combinators,
including the Parser class and basic combinators like many, optional, sequence, etc.

## The result type: a discriminated success/failure union

A parse produces a :class:`ParseResult`, which is one of two shapes:

* :class:`ParseSuccess` — carries the produced ``value`` and the ``position``
  reached.
* :class:`ParseFailure` — carries the ``position`` at which the failure was
  observed plus an FP-style error channel:

  * ``committed`` — a *cut*. The parser consumed input and is certain this is
    the right production, so :meth:`Parser.or_else` must NOT backtrack to an
    alternative; the committed failure propagates instead. (Until callers start
    constructing committed failures, this defaults to ``False`` and ``or_else``
    behaves exactly as a plain ordered choice.)
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
from ...lexer.token_types import Token

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

    def or_else(self, alternative: 'Parser[T]') -> 'Parser[T]':
        """Try this parser, or alternative if it fails.

        Ordered choice with a cut: if this parser fails *committed* (it consumed
        input and is sure of the production), the failure propagates and the
        alternative is NOT tried. Otherwise the alternative is attempted.

        Args:
            alternative: Parser to try if this one fails

        Returns:
            Parser that tries both options
        """
        def choice_parse(tokens: List[Token], pos: int) -> ParseResult[T]:
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
        token_type: Name of the token type to match

    Returns:
        Parser that matches the specified token type
    """
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


def sequence(*parsers: Parser) -> Parser[tuple]:
    """Parse a sequence of parsers.

    Args:
        *parsers: Parsers to run in sequence

    Returns:
        Parser that returns tuple of all results
    """
    def parse_sequence(tokens: List[Token], pos: int) -> ParseResult[tuple]:
        results = []
        current_pos = pos

        for parser in parsers:
            result = parser.parse(tokens, current_pos)
            if not result.success:
                return ParseFailure(pos, result.error,
                                    expected=result.expected,
                                    committed=result.committed)
            results.append(result.value)
            current_pos = result.position

        return ParseSuccess(tuple(results), current_pos)

    return Parser(parse_sequence)


def separated_by(parser: Parser[T], separator: Parser) -> Parser[List[T]]:
    """Parse items separated by a separator.

    Args:
        parser: Parser for items
        separator: Parser for separators

    Returns:
        Parser that returns list of items
    """
    def parse_separated(tokens: List[Token], pos: int) -> ParseResult[List[T]]:
        # Parse first item
        first = parser.parse(tokens, pos)
        if not first.success:
            # If we can't parse even one item, fail instead of returning empty list
            return ParseFailure(pos, first.error, expected=first.expected,
                                committed=first.committed)

        items: List[T] = [cast(T, first.value)]
        current_pos = first.position

        # Parse remaining items
        while True:
            sep_result = separator.parse(tokens, current_pos)
            if not sep_result.success:
                if sep_result.committed:
                    return cast(ParseResult[List[T]], sep_result)
                break

            item_result = parser.parse(tokens, sep_result.position)
            if not item_result.success:
                if item_result.committed:
                    return cast(ParseResult[List[T]], item_result)
                break

            items.append(cast(T, item_result.value))
            current_pos = item_result.position

        return ParseSuccess(items, current_pos)

    return Parser(parse_separated)


# Enhanced combinators for control structures
def lazy(parser_factory: Callable[[], Parser[T]]) -> Parser[T]:
    """Lazy evaluation for recursive grammars.

    Args:
        parser_factory: Function that creates the parser when needed

    Returns:
        Parser that delays creation until first use
    """
    cache: List[Optional[Parser[T]]] = [None]  # Use list for mutability

    def parse_lazy(tokens: List[Token], pos: int) -> ParseResult[T]:
        parser = cache[0]
        if parser is None:
            parser = parser_factory()
            cache[0] = parser
        return parser.parse(tokens, pos)

    return Parser(parse_lazy)


def between(open_p: Parser, close_p: Parser, content_p: Parser[T]) -> Parser[T]:
    """Parse content between delimiters.

    Args:
        open_p: Parser for opening delimiter
        close_p: Parser for closing delimiter
        content_p: Parser for content

    Returns:
        Parser that returns the content value
    """
    def parse_between(tokens: List[Token], pos: int) -> ParseResult[T]:
        # Parse opening delimiter
        open_result = open_p.parse(tokens, pos)
        if not open_result.success:
            return ParseFailure(pos, f"Expected opening delimiter: {open_result.error}",
                                expected=open_result.expected,
                                committed=open_result.committed)

        # Parse content
        content_result = content_p.parse(tokens, open_result.position)
        if not content_result.success:
            return ParseFailure(open_result.position,
                                f"Expected content: {content_result.error}",
                                expected=content_result.expected,
                                committed=content_result.committed)

        # Parse closing delimiter
        close_result = close_p.parse(tokens, content_result.position)
        if not close_result.success:
            return ParseFailure(content_result.position,
                                f"Expected closing delimiter: {close_result.error}",
                                expected=close_result.expected,
                                committed=close_result.committed)

        return ParseSuccess(cast(T, content_result.value), close_result.position)

    return Parser(parse_between)


def skip(parser: Parser) -> Parser[None]:
    """Parse but discard result.

    Args:
        parser: Parser to run

    Returns:
        Parser that returns None
    """
    def parse_skip(tokens: List[Token], pos: int) -> ParseResult[None]:
        result = parser.parse(tokens, pos)
        if result.success:
            return ParseSuccess(None, result.position)
        return ParseFailure(pos, result.error, expected=result.expected,
                            committed=result.committed)

    return Parser(parse_skip)


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


def try_parse(parser: Parser[T]) -> Parser[Optional[T]]:
    """Backtracking support - try parser without consuming on failure.

    Args:
        parser: Parser to try

    Returns:
        Parser that returns value or None without consuming tokens on failure
    """
    def parse_try(tokens: List[Token], pos: int) -> ParseResult[Optional[T]]:
        result = parser.parse(tokens, pos)
        if result.success:
            return ParseSuccess(result.value, result.position)
        # Return success with None, keeping original position
        return ParseSuccess(None, pos)

    return Parser(parse_try)


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


def literal(lit: str) -> Parser[Token]:
    """Parse specific literal value.

    Args:
        lit: Literal value to match

    Returns:
        Parser that matches the literal
    """
    def parse_literal(tokens: List[Token], pos: int) -> ParseResult[Token]:
        if pos >= len(tokens):
            return ParseFailure(pos, f"Expected '{lit}' but reached end of input",
                                expected=(lit,))

        token = tokens[pos]
        if token.value == lit:
            return ParseSuccess(token, pos + 1)

        return ParseFailure(pos, f"Expected '{lit}', got {token.value}",
                            expected=(lit,))

    return Parser(parse_literal)


# Forward declaration support
class ForwardParser(Parser[T], Generic[T]):
    """Parser that can be defined later for handling circular references.

    This is useful for recursive grammars where a parser needs to reference
    itself or create mutual recursion between parsers.
    """

    def __init__(self):
        """Initialize without a parser implementation."""
        self._parser: Optional[Parser[T]] = None
        super().__init__(self._parse_forward)

    def _parse_forward(self, tokens: List[Token], pos: int) -> ParseResult[T]:
        """Parse using the defined parser."""
        if self._parser is None:
            raise RuntimeError("ForwardParser used before being defined")
        return self._parser.parse(tokens, pos)

    def define(self, parser: Parser[T]) -> None:
        """Define the actual parser implementation.

        Args:
            parser: The parser to use for this forward reference
        """
        self._parser = parser


def with_error_context(parser: Parser[T], context: str) -> Parser[T]:
    """Add context to parser errors for better debugging.

    Args:
        parser: Parser to wrap
        context: Context string to prepend to errors

    Returns:
        Parser with contextualized error messages
    """
    def contextualized_parse(tokens: List[Token], pos: int) -> ParseResult[T]:
        result = parser.parse(tokens, pos)
        if not result.success and result.error:
            result.error = f"{context}: {result.error}"
        return result

    return Parser(contextualized_parse)
