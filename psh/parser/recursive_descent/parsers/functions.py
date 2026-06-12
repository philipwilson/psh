"""
Function parsing for PSH shell.

This module handles parsing of function definitions.
"""

from ....ast_nodes import CommandList, FunctionDef
from ....lexer.token_types import TokenType


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
        keyword_form = False

        if self.parser.match(TokenType.FUNCTION):
            self.parser.advance()
            self.parser.ctx.push_construct('function')
            keyword_form = True
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
        if keyword_form:
            self.parser.ctx.pop_construct()

        # Redirections on the definition (f() { ...; } > file) belong to
        # the function and are applied at each call (bash).
        redirects = self.parser.redirections.parse_redirects()

        return FunctionDef(name, body, redirects=redirects)

    def parse_compound_command(self) -> CommandList:
        """Parse a compound command { ... }"""
        if self.parser.match(TokenType.LBRACE):
            # Brace group
            self.parser.advance()
            self.parser.ctx.push_construct('brace')
            self.parser.skip_newlines()

            statements = self.parser.statements.parse_command_list_until(TokenType.RBRACE)

            self.parser.expect(TokenType.RBRACE)
            self.parser.ctx.pop_construct()
            return statements
        elif self.parser.match(TokenType.LPAREN):
            # Subshell body: keep the SubshellGroup node so each call forks
            # (f() (cd /; ...) must not change the caller's state — bash).
            subshell = self.parser.commands.parse_subshell_group()
            cmd_list = CommandList()
            cmd_list.statements.append(subshell)
            return cmd_list
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
