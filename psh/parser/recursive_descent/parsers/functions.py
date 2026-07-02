"""
Function parsing for PSH shell.

This module handles parsing of function definitions.
"""

from typing import cast

from ....ast_nodes import CommandList, FunctionDef, Statement
from ....lexer.token_types import TokenType
from .base import ParserSubcomponent


class FunctionParser(ParserSubcomponent):
    """Parser for function constructs."""


    # Token types that can serve as a function name in the POSIX `name()`
    # form. bash is permissive: any word that is not a reserved word works
    # (`my-func`, `.dot`, `f.g`, even `[` and `]`).
    NAME_TOKENS = (TokenType.WORD, TokenType.LBRACKET, TokenType.RBRACKET)

    def is_function_def(self) -> bool:
        """Check if current position starts a function definition."""
        if self.parser.match(TokenType.FUNCTION):
            return True

        # Check for name() pattern
        if self.parser.match(*self.NAME_TOKENS):
            word_token = self.parser.peek()
            # Don't consider it a function if the word ends with '=' (array assignment)
            if word_token.value.endswith('='):
                return False
            # A reserved word is never a `name()` function name (bash:
            # syntax error). `in` is the one keyword that lexes as a plain
            # WORD at command position; the rest already carry keyword
            # token types and fail the match above.
            from ....lexer.constants import KEYWORDS
            if word_token.value in KEYWORDS:
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
            if not self.parser.match(*self.NAME_TOKENS):
                raise self.parser.error("Expected function name")
            name = self.parser.advance().value
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

            # bash rejects an empty function body `f() { }` (syntax error),
            # exactly as for a standalone brace group `{ }`.
            statements = self.parser.statements.parse_required_command_list_until(TokenType.RBRACE)

            self.parser.expect(TokenType.RBRACE)
            self.parser.ctx.pop_construct()
            return statements
        elif self.parser.match(TokenType.LPAREN):
            # Subshell body: keep the SubshellGroup node so each call forks
            # (f() (cd /; ...) must not change the caller's state — bash).
            subshell = self.parser.commands.parse_subshell_group()
            cmd_list = CommandList()
            # A subshell group is a CompoundCommand AND a Statement at runtime;
            # mypy can't see the intersection from the parse method's type.
            cmd_list.statements.append(cast(Statement, subshell))
            return cmd_list
        elif self.parser.match(TokenType.IF, TokenType.WHILE, TokenType.UNTIL, TokenType.FOR, TokenType.CASE,
                              TokenType.SELECT, TokenType.DOUBLE_LPAREN, TokenType.DOUBLE_LBRACKET):
            # Control structure
            stmt = self.parser.control_structures.parse_control_structure()
            # Wrap in command list (a control structure is both a
            # CompoundCommand and a Statement; mypy can't see the intersection).
            cmd_list = CommandList()
            cmd_list.statements.append(cast(Statement, stmt))
            return cmd_list
        else:
            # Missing function body
            raise self.parser.error("Expected '{' for function body")
