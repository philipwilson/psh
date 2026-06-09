"""
Function parsing for PSH shell.

This module handles parsing of function definitions.
"""

from ....ast_nodes import CommandList, FunctionDef
from ....token_types import TokenType


class FunctionParser:
    """Parser for function constructs."""

    def __init__(self, main_parser):
        """Initialize with reference to main parser."""
        self.parser = main_parser

    def is_function_def(self) -> bool:
        """Check if current position starts a function definition."""
        if self.parser.match(TokenType.FUNCTION):
            return True

        # Check for name() pattern
        if self.parser.match(TokenType.WORD):
            word_token = self.parser.peek()
            # Don't consider it a function if the word ends with '=' (array assignment)
            if word_token.value.endswith('='):
                return False

            saved_pos = self.parser.current
            self.parser.advance()

            if self.parser.match(TokenType.LPAREN):
                self.parser.advance()
                result = self.parser.match(TokenType.RPAREN)
                self.parser.current = saved_pos
                return result

            self.parser.current = saved_pos

        return False

    def parse_function_def(self) -> FunctionDef:
        """Parse function definition."""
        name = None

        if self.parser.match(TokenType.FUNCTION):
            self.parser.advance()
            name = self.parser.expect(TokenType.WORD).value

            # Optional parentheses
            if self.parser.match(TokenType.LPAREN):
                self.parser.advance()
                self.parser.expect(TokenType.RPAREN)
        else:
            # POSIX style: name()
            name = self.parser.expect(TokenType.WORD).value
            self.parser.expect(TokenType.LPAREN)
            self.parser.expect(TokenType.RPAREN)

        self.parser.skip_newlines()
        body = self.parse_compound_command()

        return FunctionDef(name, body)

    def parse_compound_command(self) -> CommandList:
        """Parse a compound command { ... }"""
        if self.parser.match(TokenType.LBRACE):
            # Brace group
            self.parser.advance()
            self.parser.skip_newlines()

            statements = self.parser.statements.parse_command_list_until(TokenType.RBRACE)

            self.parser.expect(TokenType.RBRACE)
            return statements
        elif self.parser.match(TokenType.LPAREN):
            # Subshell group
            subshell = self.parser.commands.parse_subshell_group()
            # Convert subshell to command list for function body
            return subshell.statements
        elif self.parser.match(TokenType.IF, TokenType.WHILE, TokenType.UNTIL, TokenType.FOR, TokenType.CASE,
                              TokenType.SELECT, TokenType.DOUBLE_LPAREN, TokenType.DOUBLE_LBRACKET):
            # Control structure
            stmt = self.parser.control_structures.parse_control_structure()
            # Wrap in command list
            cmd_list = CommandList()
            cmd_list.statements.append(stmt)
            return cmd_list
        else:
            # Missing function body
            raise self.parser.error("Expected '{' for function body")
