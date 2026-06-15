"""Core parser combinator framework.

This module provides the fundamental building blocks for parser combinators,
including the Parser class and basic combinators like many, optional, sequence, etc.
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
    """Result of a parse operation.

    Attributes:
        success: Whether the parse succeeded
        value: The parsed value if successful
        position: Current position in token stream (where parsing stopped)
        error: Error message if parse failed
    """
    success: bool
    value: Optional[T] = None
    position: int = 0
    error: Optional[str] = None


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
                return ParseResult(
                    success=True,
                    value=fn(cast(T, result.value)),
                    position=result.position
                )
            return ParseResult(success=False, error=result.error, position=pos)

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
                return ParseResult(success=False, error=first_result.error, position=pos)

            second_result = next_parser.parse(tokens, first_result.position)
            if not second_result.success:
                # Atomic: a failed sequence resets to the start position, the
                # same backtracking discipline as sequence().
                return ParseResult(success=False, error=second_result.error,
                                 position=pos)

            return ParseResult(
                success=True,
                value=(cast(T, first_result.value), cast(U, second_result.value)),
                position=second_result.position
            )

        return Parser(sequence_parse)

    def or_else(self, alternative: 'Parser[T]') -> 'Parser[T]':
        """Try this parser, or alternative if it fails.

        Args:
            alternative: Parser to try if this one fails

        Returns:
            Parser that tries both options
        """
        def choice_parse(tokens: List[Token], pos: int) -> ParseResult[T]:
            result = self.parse(tokens, pos)
            if result.success:
                return result
            return alternative.parse(tokens, pos)

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
            return ParseResult(
                success=True,
                value=tokens[pos],
                position=pos + 1
            )
        error = f"Expected {token_type}"
        if pos < len(tokens):
            error += f", got {tokens[pos].type.name}"
        else:
            error += ", but reached end of input"
        return ParseResult(success=False, error=error, position=pos)

    return Parser(parse_token)


def many(parser: Parser[T]) -> Parser[List[T]]:
    """Parse zero or more occurrences.

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
                break
            results.append(cast(T, result.value))
            current_pos = result.position

        return ParseResult(
            success=True,
            value=results,
            position=current_pos
        )

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
        return ParseResult(success=True, value=None, position=pos)

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
                return ParseResult(success=False, error=result.error, position=pos)
            results.append(result.value)
            current_pos = result.position

        return ParseResult(
            success=True,
            value=tuple(results),
            position=current_pos
        )

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
            return ParseResult(success=False, error=first.error, position=pos)

        items: List[T] = [cast(T, first.value)]
        current_pos = first.position

        # Parse remaining items
        while True:
            sep_result = separator.parse(tokens, current_pos)
            if not sep_result.success:
                break

            item_result = parser.parse(tokens, sep_result.position)
            if not item_result.success:
                break

            items.append(cast(T, item_result.value))
            current_pos = item_result.position

        return ParseResult(
            success=True,
            value=items,
            position=current_pos
        )

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
            return ParseResult(success=False, error=f"Expected opening delimiter: {open_result.error}", position=pos)

        # Parse content
        content_result = content_p.parse(tokens, open_result.position)
        if not content_result.success:
            return ParseResult(success=False, error=f"Expected content: {content_result.error}", position=open_result.position)

        # Parse closing delimiter
        close_result = close_p.parse(tokens, content_result.position)
        if not close_result.success:
            return ParseResult(success=False, error=f"Expected closing delimiter: {close_result.error}", position=content_result.position)

        return ParseResult(
            success=True,
            value=content_result.value,
            position=close_result.position
        )

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
            return ParseResult(success=True, value=None, position=result.position)
        return ParseResult(success=False, error=result.error, position=pos)

    return Parser(parse_skip)


def fail_with(msg: str) -> Parser[None]:
    """Parser that always fails with custom message.

    Args:
        msg: Error message

    Returns:
        Parser that always fails
    """
    def parse_fail(tokens: List[Token], pos: int) -> ParseResult[None]:
        return ParseResult(success=False, error=msg, position=pos)

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
            return ParseResult(success=True, value=result.value, position=result.position)
        # Return success with None, keeping original position
        return ParseResult(success=True, value=None, position=pos)

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
            return ParseResult(success=False, error=f"Expected keyword '{kw}' but reached end of input", position=pos)

        token = tokens[pos]
        if matches_keyword(token, kw):
            return ParseResult(success=True, value=token, position=pos + 1)

        return ParseResult(success=False, error=f"Expected keyword '{kw}', got {token.value}", position=pos)

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
            return ParseResult(success=False, error=f"Expected '{lit}' but reached end of input", position=pos)

        token = tokens[pos]
        if token.value == lit:
            return ParseResult(success=True, value=token, position=pos + 1)

        return ParseResult(success=False, error=f"Expected '{lit}', got {token.value}", position=pos)

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
