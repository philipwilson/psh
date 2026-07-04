"""
Arithmetic parsing for PSH shell.

This module handles parsing of arithmetic expressions and commands.
"""

from typing import Optional

from ....ast_nodes import ArithmeticEvaluation
from ....lexer.token_stream import TokenStream
from ....lexer.token_types import TokenType
from .base import ParserSubcomponent


class ArithmeticParser(ParserSubcomponent):
    """Parser for arithmetic expressions and commands."""


    def parse_arithmetic_command(self) -> ArithmeticEvaluation:
        """Parse arithmetic command: ((expression))"""
        self.parser.expect(TokenType.DOUBLE_LPAREN)

        expr = self._parse_arithmetic_expression_until_double_rparen()

        # Handle both old (two RPAREN) and new (DOUBLE_RPAREN) tokenization
        if self.parser.match(TokenType.DOUBLE_RPAREN):
            self.parser.advance()
        else:
            self.parser.expect(TokenType.RPAREN)
            self.parser.expect(TokenType.RPAREN)

        redirects = self.parser.redirections.parse_redirects()

        return ArithmeticEvaluation(
            expression=expr,
            redirects=redirects,
            background=False
        )

    def _parse_arithmetic_expression_until_double_rparen(self) -> str:
        """Parse arithmetic expression until the enclosing )) is found.

        Stops before the ``))`` (consumed by :meth:`parse_arithmetic_command`).
        """
        stream = TokenStream(self.parser.tokens, self.parser.current)
        _tokens, expr_string = stream.collect_arithmetic_expression(
            stop_at_semicolon=False,
            transform_redirects=False,
        )
        self.parser.current = stream.pos
        return expr_string

    def parse_arithmetic_section(self, terminator: str) -> Optional[str]:
        """Parse one ``for``-header arithmetic section up to its ``;`` terminator."""
        stream = TokenStream(self.parser.tokens, self.parser.current)
        _tokens, expr_string = stream.collect_arithmetic_expression(
            stop_at_semicolon=(terminator == ';'),
            transform_redirects=True,
        )
        self.parser.current = stream.pos
        return expr_string if expr_string else ""

    def parse_arithmetic_section_until_double_rparen(self) -> Optional[str]:
        """Parse the ``for``-header update section, ending at the enclosing )).

        Unlike the ``;``-terminated sections, this one consumes the closing
        ``))`` (a single DOUBLE_RPAREN, or two RPARENs after a straddle split).
        """
        stream = TokenStream(self.parser.tokens, self.parser.current)
        _tokens, expr_string = stream.collect_arithmetic_expression(
            stop_at_semicolon=False,
            transform_redirects=True,
        )

        # Consume the )) that ended the section.
        current_token = stream.peek()
        next_token = stream.peek(1)
        if current_token and current_token.type == TokenType.DOUBLE_RPAREN:
            stream.advance(1)
        elif (current_token and current_token.type == TokenType.RPAREN and
              next_token and next_token.type == TokenType.RPAREN):
            stream.advance(2)

        self.parser.current = stream.pos
        return expr_string if expr_string else None
