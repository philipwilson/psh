"""
Control structure parsing for PSH shell.

This module handles parsing of control structures like if, while, for, case, and select.
"""

from typing import List, Optional, Tuple, Union

from ....ast_nodes import (
    BreakStatement,
    CaseConditional,
    CaseItem,
    CasePattern,
    ContinueStatement,
    CStyleForLoop,
    ExpansionPart,
    ForLoop,
    IfConditional,
    Redirect,
    SelectLoop,
    Statement,
    StatementList,
    UntilLoop,
    VariableExpansion,
    WhileLoop,
    Word,
)
from ....lexer.token_types import TokenType
from ..helpers import TokenGroups


def _positional_params_word() -> Word:
    """The implicit ``"$@"`` Word used when for/select has no ``in`` list."""
    return Word(
        parts=[ExpansionPart(expansion=VariableExpansion('@'),
                             quoted=True, quote_char='"')],
        quote_type='"')


class ControlStructureParser:
    """Parser for control structure constructs."""

    def __init__(self, main_parser):
        """Initialize with reference to main parser."""
        self.parser = main_parser

    def parse_control_structure(self) -> Statement:
        """Parse any control structure based on current token."""
        token_type = self.parser.peek().type

        if token_type == TokenType.IF:
            return self.parse_if_statement()
        elif token_type == TokenType.WHILE:
            return self.parse_while_statement()
        elif token_type == TokenType.UNTIL:
            return self.parse_until_statement()
        elif token_type == TokenType.FOR:
            return self.parse_for_statement()
        elif token_type == TokenType.CASE:
            return self.parse_case_statement()
        elif token_type == TokenType.SELECT:
            return self.parse_select_statement()
        elif token_type == TokenType.BREAK:
            return self.parse_break_statement()
        elif token_type == TokenType.CONTINUE:
            return self.parse_continue_statement()
        elif token_type == TokenType.DOUBLE_LBRACKET:
            return self.parser.tests.parse_enhanced_test_statement()
        elif token_type == TokenType.DOUBLE_LPAREN:
            return self.parser.arithmetic.parse_arithmetic_command()
        else:
            raise self.parser.error(f"Unexpected control structure token: {token_type.name}")

    # === If Statement Parsing ===

    def parse_if_statement(self) -> IfConditional:
        """Parse if/then/else/fi conditional statement."""
        self.parser.expect(TokenType.IF)
        self.parser.skip_newlines()

        # Parse main condition and body
        condition, then_part = self._parse_condition_then_block()

        # Parse elif clauses
        elif_parts = []
        while self.parser.match(TokenType.ELIF):
            self.parser.advance()
            elif_condition, elif_then = self._parse_condition_then_block()
            elif_parts.append((elif_condition, elif_then))

        # Parse optional else
        else_part = None
        if self.parser.match(TokenType.ELSE):
            self.parser.advance()
            self.parser.skip_newlines()
            else_part = self.parser.statements.parse_command_list_until(TokenType.FI)

        self.parser.expect(TokenType.FI)
        redirects = self.parser.redirections.parse_redirects()

        return IfConditional(
            condition=condition,
            then_part=then_part,
            elif_parts=elif_parts,
            else_part=else_part,
            redirects=redirects,
            background=False
        )

    def _parse_condition_then_block(self) -> Tuple[StatementList, StatementList]:
        """Parse a condition followed by THEN and a command list."""
        self.parser.skip_newlines()
        condition = self.parser.statements.parse_command_list_until(TokenType.THEN)
        self.parser.expect(TokenType.THEN)
        self.parser.skip_newlines()
        body = self.parser.statements.parse_command_list_until(TokenType.ELIF, TokenType.ELSE, TokenType.FI)
        return condition, body

    # === While Statement Parsing ===

    def parse_while_statement(self) -> WhileLoop:
        """Parse while loop without setting execution context."""
        condition, body, redirects = self._parse_loop_structure(
            TokenType.WHILE, TokenType.DO, TokenType.DONE
        )
        return WhileLoop(
            condition=condition,
            body=body,
            redirects=redirects,
            background=False
        )

    def parse_until_statement(self) -> UntilLoop:
        """Parse until loop without setting execution context."""
        condition, body, redirects = self._parse_loop_structure(
            TokenType.UNTIL, TokenType.DO, TokenType.DONE
        )
        return UntilLoop(
            condition=condition,
            body=body,
            redirects=redirects,
            background=False
        )

    def _parse_loop_structure(self, start: TokenType, body_start: TokenType,
                            body_end: TokenType) -> Tuple[StatementList, StatementList, List[Redirect]]:
        """Common pattern for while/until loops."""
        self.parser.expect(start)
        self.parser.skip_newlines()

        condition = self.parser.statements.parse_command_list_until(body_start)

        self.parser.expect(body_start)
        self.parser.skip_newlines()

        body = self.parser.statements.parse_command_list_until(body_end)

        self.parser.expect(body_end)
        redirects = self.parser.redirections.parse_redirects()

        return condition, body, redirects

    # === For Statement Parsing ===

    def parse_for_statement(self) -> Union[ForLoop, CStyleForLoop]:
        """Parse for loop without setting execution context."""
        self.parser.expect(TokenType.FOR)
        self.parser.skip_newlines()

        # Check if it's a C-style for loop
        if self.parser.peek().type == TokenType.DOUBLE_LPAREN:
            self.parser.advance()  # consume ((
            return self._parse_c_style_for()
        elif self.parser.peek().type == TokenType.LPAREN:
            saved_pos = self.parser.current
            self.parser.advance()  # consume first (

            if self.parser.peek().type == TokenType.LPAREN:
                self.parser.advance()  # consume second (
                return self._parse_c_style_for()
            else:
                self.parser.current = saved_pos

        # Traditional for loop
        variable = self.parser.expect(TokenType.WORD).value
        self.parser.skip_newlines()

        items: List[str]
        quote_types: List[Optional[str]]

        if self.parser.match(TokenType.IN):
            # Explicit item list provided
            self.parser.advance()
            self.parser.skip_newlines()
            items, quote_types, item_words = self._parse_for_iterable()
        else:
            # No explicit list - default to positional parameters ("$@")
            items = ['$@']
            quote_types = ['"']
            item_words = [_positional_params_word()]

        self.parser.skip_separators()
        self.parser.expect(TokenType.DO)
        self.parser.skip_newlines()

        body = self.parser.statements.parse_command_list_until(TokenType.DONE)
        self.parser.expect(TokenType.DONE)
        redirects = self.parser.redirections.parse_redirects()

        return ForLoop(
            variable=variable,
            items=items,
            item_quote_types=quote_types,
            item_words=item_words,
            body=body,
            redirects=redirects,
            background=False
        )

    def _parse_for_iterable(self) -> tuple[List[str], List[Optional[str]], List[Word]]:
        """Parse the iterable part of a for/select loop.

        Returns parallel lists: display strings, legacy quote types, and
        the Word AST nodes the executor expands.
        """
        items = []
        quote_types = []
        item_words = []

        # Parse items until we hit DO, newline, or semicolon
        while (not self.parser.match(TokenType.DO) and
               not self.parser.match_any(TokenGroups.STATEMENT_SEPARATORS) and
               not self.parser.at_end()):

            if self.parser.match_any(TokenGroups.WORD_LIKE):
                word = self.parser.commands.parse_argument_as_word()
                items.append(''.join(str(p) for p in word.parts))
                quote_types.append(word.effective_quote_char)
                item_words.append(word)
            else:
                break

        return items, quote_types, item_words

    def _parse_c_style_for(self) -> CStyleForLoop:
        """Parse C-style for loop without setting execution context."""
        # Parse initialization
        init = self.parser.arithmetic.parse_arithmetic_section(";")
        if init == "":
            init = None

        # Handle semicolon(s) after init
        if self.parser.match(TokenType.SEMICOLON):
            self.parser.advance()  # consume ;
            # Parse condition normally
            condition = self.parser.arithmetic.parse_arithmetic_section(";")
            if condition == "":
                condition = None
            if self.parser.match(TokenType.SEMICOLON):
                self.parser.advance()  # consume ;
        elif self.parser.match(TokenType.DOUBLE_SEMICOLON):
            # Handle ;; case - both init and condition are effectively empty
            self.parser.advance()  # consume ;;
            condition = None
        else:
            # No semicolon, something's wrong
            raise self.parser.error("Expected ';' after for loop initialization")

        # Parse increment
        increment = self.parser.arithmetic.parse_arithmetic_section_until_double_rparen()

        # Skip optional semicolon and newlines before DO (or body)
        self.parser.skip_separators()

        # DO keyword is optional in C-style for loops
        if self.parser.match(TokenType.DO):
            self.parser.advance()
            self.parser.skip_newlines()

        body = self.parser.statements.parse_command_list_until(TokenType.DONE)
        self.parser.expect(TokenType.DONE)
        redirects = self.parser.redirections.parse_redirects()

        return CStyleForLoop(
            init_expr=init,
            condition_expr=condition,
            update_expr=increment if increment else None,
            body=body,
            redirects=redirects,
            background=False
        )


    # === Case Statement Parsing ===

    def parse_case_statement(self) -> CaseConditional:
        """Parse case statement without setting execution context."""
        self.parser.expect(TokenType.CASE)

        expr = self._parse_case_expression()

        # bash allows newlines between the subject and `in`
        # (`case a <newline> in ...`), but nothing else.
        self.parser.skip_newlines()
        if not self.parser.match(TokenType.IN):
            raise self._case_syntax_error()
        self.parser.advance()
        self.parser.skip_newlines()

        items = []
        while not self.parser.match(TokenType.ESAC) and not self.parser.at_end():
            if self.parser.match_any(TokenGroups.WORD_LIKE | TokenGroups.CASE_PATTERN_KEYWORDS) or \
               self.parser.match(TokenType.LPAREN):
                item = self.parse_case_item()
                items.append(item)
            else:
                saved_pos = self.parser.current
                self.parser.skip_newlines()
                if self.parser.current == saved_pos:
                    raise self.parser.error(
                        f"Unexpected token in case statement: '{self.parser.peek().value}'"
                    )

        self.parser.expect(TokenType.ESAC)
        redirects = self.parser.redirections.parse_redirects()

        return CaseConditional(
            expr=expr,
            items=items,
            redirects=redirects,
            background=False
        )

    def _parse_case_expression(self) -> str:
        """Parse the case subject: exactly one word.

        bash takes exactly one word (possibly a composite like ``a"b"c``)
        between ``case`` and ``in``; ``case a b in ...`` is a syntax error
        near ``b``, raised by the caller when the next token isn't ``in``.
        The subject may be spelled ``in`` or ``esac`` (the lexer leaves the
        word right after ``case`` as a plain WORD).
        """
        if not self.parser.match_any(TokenGroups.WORD_LIKE):
            raise self._case_syntax_error()
        word = self.parser.commands.parse_argument_as_word()
        return ''.join(str(p) for p in word.parts)

    def _case_syntax_error(self):
        """Build a bash-shaped syntax error for a malformed case header."""
        token = self.parser.peek()
        if token.type == TokenType.EOF:
            return self.parser.error("syntax error: unexpected end of file", token)
        display = 'newline' if token.type == TokenType.NEWLINE else token.value
        return self.parser.error(
            f"syntax error near unexpected token '{display}'", token)

    def parse_case_item(self) -> CaseItem:
        """Parse a single case item."""
        patterns = []

        # Consume optional leading LPAREN (bash allows (pattern) syntax)
        self.parser.consume_if(TokenType.LPAREN)

        # Parse first pattern
        patterns.append(self._parse_case_pattern())

        # Parse additional patterns separated by |
        while self.parser.match(TokenType.PIPE):
            self.parser.advance()
            patterns.append(self._parse_case_pattern())

        self.parser.expect(TokenType.RPAREN)
        self.parser.skip_newlines()

        # Parse commands until case terminator
        commands = self.parser.statements.parse_command_list_until(
            *TokenGroups.CASE_TERMINATORS, TokenType.ESAC
        )

        # Consume the terminator and capture its value
        terminator = ';;'
        if self.parser.match_any(TokenGroups.CASE_TERMINATORS):
            terminator = self.parser.peek().value
            self.parser.advance()

        self.parser.skip_newlines()

        return CaseItem(patterns=patterns, commands=commands, terminator=terminator)

    def _parse_case_pattern(self) -> CasePattern:
        """Parse a case pattern, keeping per-part quote context.

        The Word parts let the executor distinguish quoted (literal) from
        unquoted (glob-active) pattern text; the flattened string is kept
        for display.
        """
        from ....ast_nodes import LiteralPart, Word

        text_parts = []
        word_parts = []

        while (not self.parser.match(TokenType.PIPE, TokenType.RPAREN) and
               not self.parser.at_end()):

            token = self.parser.peek()
            if self.parser.match_any(TokenGroups.WORD_LIKE | TokenGroups.CASE_PATTERN_KEYWORDS):
                if token.type in TokenGroups.CASE_PATTERN_KEYWORDS:
                    # Keywords can be valid patterns
                    text_parts.append(token.value)
                    word_parts.append(LiteralPart(token.value, quoted=False,
                                                  quote_char=None))
                    self.parser.advance()
                else:
                    word = self.parser.commands.parse_argument_as_word()
                    text_parts.append(''.join(str(p) for p in word.parts))
                    word_parts.extend(word.parts)
            else:
                break

        return CasePattern(pattern=''.join(text_parts),
                           word=Word(parts=word_parts))

    # === Select Statement Parsing ===

    def parse_select_statement(self) -> SelectLoop:
        """Parse select statement without setting execution context."""
        self.parser.expect(TokenType.SELECT)
        self.parser.skip_newlines()

        variable = self.parser.expect(TokenType.WORD).value
        self.parser.skip_newlines()

        if self.parser.match(TokenType.IN):
            self.parser.advance()
            self.parser.skip_newlines()
            items, quote_types, item_words = self._parse_for_iterable()
        else:
            # No explicit list - default to positional parameters ("$@")
            items = ['$@']
            quote_types = ['"']
            item_words = [_positional_params_word()]

        self.parser.skip_separators()
        self.parser.expect(TokenType.DO)
        self.parser.skip_newlines()

        body = self.parser.statements.parse_command_list_until(TokenType.DONE)
        self.parser.expect(TokenType.DONE)
        redirects = self.parser.redirections.parse_redirects()

        return SelectLoop(
            variable=variable,
            items=items,
            item_quote_types=quote_types,
            item_words=item_words,
            body=body,
            redirects=redirects,
            background=False
        )

    # === Break/Continue Statement Parsing ===

    def parse_break_statement(self) -> BreakStatement:
        """Parse break statement with optional level."""
        self.parser.expect(TokenType.BREAK)
        level = self._parse_loop_control_level()
        return BreakStatement(level=level)

    def parse_continue_statement(self) -> ContinueStatement:
        """Parse continue statement with optional level."""
        self.parser.expect(TokenType.CONTINUE)
        level = self._parse_loop_control_level()
        return ContinueStatement(level=level)

    def _parse_loop_control_level(self) -> int:
        """Parse optional loop control level (default 1)."""
        if self.parser.match(TokenType.WORD) and self.parser.peek().value.isdigit():
            level_token = self.parser.advance()
            return int(level_token.value)
        return 1
