"""
Arithmetic parsing for PSH shell.

This module handles parsing of arithmetic expressions and commands.
"""

from typing import Optional

from ....ast_nodes import ArithmeticEvaluation
from ....token_stream import TokenStream
from ....token_types import TokenType


class ArithmeticParser:
    """Parser for arithmetic expressions and commands."""

    def __init__(self, main_parser):
        """Initialize with reference to main parser."""
        self.parser = main_parser

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
        """Parse arithmetic expression until )) is found."""
        # Create TokenStream from current position
        stream = TokenStream(self.parser.tokens, self.parser.current)

        # Define stop condition for double RPAREN
        def stop_at_double_rparen(token, paren_depth):
            # Check for DOUBLE_RPAREN token (new tokenization)
            if paren_depth == 0 and token.type == TokenType.DOUBLE_RPAREN:
                return True
            # Check for two consecutive RPAREN tokens (old tokenization)
            if paren_depth == 0 and token.type == TokenType.RPAREN:
                # Peek ahead to see if next is also RPAREN
                next_token = stream.peek(1)
                if next_token and next_token.type == TokenType.RPAREN:
                    # Found ))
                    return True
            return False

        # Collect arithmetic expression (no redirect transformation needed here)
        tokens, expr_string = stream.collect_arithmetic_expression(
            stop_condition=stop_at_double_rparen,
            transform_redirects=False
        )

        # Update parser position
        self.parser.current = stream.pos

        return expr_string

    def parse_arithmetic_section(self, terminator: str) -> Optional[str]:
        """Parse arithmetic expression section until terminator character."""
        # Create TokenStream from current position
        stream = TokenStream(self.parser.tokens, self.parser.current)

        # Define stop condition for semicolon terminator
        def stop_at_semicolon(token, paren_depth):
            if paren_depth == 0 and terminator == ';':
                if token.type == TokenType.SEMICOLON:
                    return True
                elif token.type == TokenType.DOUBLE_SEMICOLON:
                    # Found ;;, treat first ; as terminator
                    return True
            # Also stop at RPAREN when depth would go negative
            if token.type == TokenType.RPAREN and paren_depth == 0:
                return True
            return False

        # Collect arithmetic expression
        tokens, expr_string = stream.collect_arithmetic_expression(
            stop_condition=stop_at_semicolon,
            transform_redirects=True
        )

        # Update parser position
        self.parser.current = stream.pos

        return expr_string if expr_string else ""

    def parse_arithmetic_section_until_double_rparen(self) -> Optional[str]:
        """Parse arithmetic expression until we find )) at depth 0."""
        # Create TokenStream from current position
        stream = TokenStream(self.parser.tokens, self.parser.current)

        # Define stop condition for double RPAREN
        def stop_at_double_rparen(token, paren_depth):
            # Check for DOUBLE_RPAREN token (new tokenization)
            if paren_depth == 0 and token.type == TokenType.DOUBLE_RPAREN:
                return True
            # Check for two consecutive RPAREN tokens (old tokenization)
            if paren_depth == 0 and token.type == TokenType.RPAREN:
                # Peek ahead to see if next is also RPAREN
                next_token = stream.peek(1)
                if next_token and next_token.type == TokenType.RPAREN:
                    # Found ))
                    return True
            return False

        # Collect arithmetic expression
        tokens, expr_string = stream.collect_arithmetic_expression(
            stop_condition=stop_at_double_rparen,
            transform_redirects=True
        )

        # Consume the )) tokens if we stopped because of them
        if stream.pos < len(stream.tokens):
            current_token = stream.tokens[stream.pos]
            if current_token.type == TokenType.DOUBLE_RPAREN:
                stream.advance(1)  # Consume DOUBLE_RPAREN token
            elif (current_token.type == TokenType.RPAREN and
                  stream.pos + 1 < len(stream.tokens) and
                  stream.tokens[stream.pos + 1].type == TokenType.RPAREN):
                stream.advance(2)  # Consume both ) tokens

        # Update parser position
        self.parser.current = stream.pos

        return expr_string if expr_string else None
