"""Expansion and word-building parsers for the shell parser combinator.

This module provides parsers for shell expansions (variable, command substitution,
arithmetic, process substitution) and Word AST node construction.
"""

from typing import List, Optional

from ...ast_nodes import (
    ArithmeticExpansion,
    ExpansionPart,
    LiteralPart,
    Word,
)
from ...lexer.token_types import Token
from ..config import ParserConfig
from ..recursive_descent.support.word_builder import (
    WordBuilder,
    strip_arithmetic,
)
from .core import Parser, ParseResult, token


class ExpansionParsers:
    """Parsers for shell expansions and word building.

    This class handles all expansion types and Word AST node construction
    for the parser combinator implementation.
    """

    def __init__(self, config: Optional[ParserConfig] = None):
        """Initialize expansion parsers.

        Args:
            config: Parser configuration for controlling features
        """
        self.config = config or ParserConfig()
        # WordBuilder uses static methods, no need to instantiate
        self._initialize_parsers()

    def _initialize_parsers(self):
        """Initialize all expansion parsers."""
        # Token parsers for different expansion types
        self.variable = token('VARIABLE')
        self.param_expansion = token('PARAM_EXPANSION')
        self.command_sub = token('COMMAND_SUB')
        self.command_sub_backtick = token('COMMAND_SUB_BACKTICK')
        self.arith_expansion = token('ARITH_EXPANSION')
        self.process_sub_in = token('PROCESS_SUB_IN')
        self.process_sub_out = token('PROCESS_SUB_OUT')

        # Combined expansion parser
        self.expansion = (
            self.variable
            .or_else(self.param_expansion)
            .or_else(self.command_sub)
            .or_else(self.command_sub_backtick)
            .or_else(self.arith_expansion)
            .or_else(self.process_sub_in)
            .or_else(self.process_sub_out)
        )

    def format_token_value(self, token: Token) -> str:
        """Format token value appropriately based on token type.

        Args:
            token: Token to format

        Returns:
            Formatted string value
        """
        if token.type.name == 'VARIABLE':
            # Variables need the $ prefix
            return f"${token.value}"
        elif token.type.name in ['COMMAND_SUB', 'COMMAND_SUB_BACKTICK',
                                 'ARITH_EXPANSION', 'PARAM_EXPANSION']:
            # These already include their delimiters
            return token.value
        else:
            # Everything else uses raw value
            return token.value

    def build_word_from_token(self, token: Token) -> Word:
        """Build a Word AST node from a token.

        Args:
            token: Token to convert to Word

        Returns:
            Word AST node with appropriate parts
        """
        qt = getattr(token, 'quote_type', None)
        is_quoted = qt is not None and qt != 'mixed'

        # Check for decomposable parts from the lexer (RichToken with expansions)
        if WordBuilder.has_decomposable_parts(token):
            # Parts carry per-part quote context; Word.quote_type is derived.
            word_parts = [WordBuilder.token_part_to_word_part(tp)
                          for tp in (token.parts or [])]
            return Word(parts=word_parts)

        # Use TokenType enum values
        if token.type.name == 'STRING':
            # String token - the part carries the quote context.
            return Word(parts=[LiteralPart(token.value, quoted=is_quoted, quote_char=qt)])

        elif token.type.name == 'VARIABLE':
            # Variable expansion — delegate to WordBuilder for brace-stripping
            expansion = WordBuilder.parse_expansion_token(token)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)])

        elif token.type.name in ('COMMAND_SUB', 'COMMAND_SUB_BACKTICK'):
            # Command substitution $(...) / `...`. Delegate to WordBuilder so
            # the recursive-descent and combinator parsers build the SAME node:
            # $(...) carries a nested Program (parsed now, rejecting invalid
            # syntax at the outer parse); backticks keep program=None.
            expansion = WordBuilder.parse_expansion_token(token)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)])

        elif token.type.name == 'ARITH_EXPANSION':
            # Arithmetic expansion $((...))
            expansion = ArithmeticExpansion(strip_arithmetic(token.value))
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)])

        elif token.type.name == 'PARAM_EXPANSION':
            # Parameter expansion - use WordBuilder to parse
            expansion = WordBuilder.parse_expansion_token(token)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)])

        elif token.type.name in ('PROCESS_SUB_IN', 'PROCESS_SUB_OUT'):
            # Process substitution <(...) / >(...) — same ExpansionPart
            # representation as the recursive descent parser (WordBuilder),
            # so the expansion manager performs the substitution and
            # splices the /dev/fd/N path into the word.
            expansion = WordBuilder.parse_expansion_token(token)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)])

        else:
            # Regular word token
            return Word(parts=[LiteralPart(text=token.value, quoted=is_quoted, quote_char=qt)])

    def create_expansion_parser(self) -> Parser[Word]:
        """Create combined expansion parser that returns Word nodes.

        Returns:
            Parser that converts expansion tokens to Word AST nodes
        """
        def parse_expansion_to_word(tokens: List[Token], pos: int) -> ParseResult[Word]:
            """Parse an expansion token and convert to Word."""
            result = self.expansion.parse(tokens, pos)
            if result.success:
                assert result.value is not None
                word = self.build_word_from_token(result.value)
                return ParseResult(
                    success=True,
                    value=word,
                    position=result.position
                )
            return ParseResult(success=False, error=result.error, position=pos)

        return Parser(parse_expansion_to_word)

    def create_word_parser(self) -> Parser[Word]:
        """Create parser for complete words including literals and expansions.

        Returns:
            Parser that handles all word types
        """
        def parse_word(token_list: List[Token], pos: int) -> ParseResult[Word]:
            """Parse any word-like token into a Word AST node."""
            if pos >= len(token_list):
                return ParseResult(success=False, error="Expected word", position=pos)

            token = token_list[pos]

            # Check if it's a word-like token
            if token.type.name in ['WORD', 'STRING'] or self.is_expansion_token(token):
                word = self.build_word_from_token(token)
                return ParseResult(
                    success=True,
                    value=word,
                    position=pos + 1
                )

            return ParseResult(
                success=False,
                error=f"Expected word, got {token.type.name}",
                position=pos
            )

        return Parser(parse_word)

    def is_expansion_token(self, token: Token) -> bool:
        """Check if a token is an expansion type.

        Args:
            token: Token to check

        Returns:
            True if token is an expansion
        """
        expansion_types = {
            'VARIABLE', 'PARAM_EXPANSION', 'COMMAND_SUB',
            'COMMAND_SUB_BACKTICK', 'ARITH_EXPANSION',
            'PROCESS_SUB_IN', 'PROCESS_SUB_OUT'
        }
        return token.type.name in expansion_types


# Convenience functions

def create_expansion_parsers(config: Optional[ParserConfig] = None) -> ExpansionParsers:
    """Create and return an ExpansionParsers instance.

    Args:
        config: Optional parser configuration

    Returns:
        Initialized ExpansionParsers object
    """
    return ExpansionParsers(config)


def parse_variable_expansion() -> Parser[Token]:
    """Create parser for variable expansion tokens.

    Returns:
        Parser that matches $VAR tokens
    """
    return token('VARIABLE')


def parse_command_substitution() -> Parser[Token]:
    """Create parser for command substitution tokens.

    Returns:
        Parser that matches $(cmd) or `cmd` tokens
    """
    return token('COMMAND_SUB').or_else(token('COMMAND_SUB_BACKTICK'))


def parse_arithmetic_expansion() -> Parser[Token]:
    """Create parser for arithmetic expansion tokens.

    Returns:
        Parser that matches $((expr)) tokens
    """
    return token('ARITH_EXPANSION')


def parse_parameter_expansion() -> Parser[Token]:
    """Create parser for parameter expansion tokens.

    Returns:
        Parser that matches ${param} tokens
    """
    return token('PARAM_EXPANSION')


def parse_process_substitution() -> Parser[Token]:
    """Create parser for process substitution tokens.

    Returns:
        Parser that matches <(cmd) or >(cmd) tokens
    """
    return token('PROCESS_SUB_IN').or_else(token('PROCESS_SUB_OUT'))
