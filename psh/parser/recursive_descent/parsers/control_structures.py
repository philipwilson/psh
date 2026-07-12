"""
Control structure parsing for PSH shell.

This module handles parsing of control structures like if, while, for, case, and select.
"""
from typing import List, Tuple, Union

from ....ast_nodes import (
    CaseConditional,
    CaseItem,
    CasePattern,
    CStyleForLoop,
    ExpansionPart,
    ForLoop,
    IfConditional,
    LiteralPart,
    Redirect,
    SelectLoop,
    StatementList,
    UntilLoop,
    VariableExpansion,
    WhileLoop,
    Word,
    WordPart,
)
from ....lexer.token_types import TokenType
from ..helpers import TokenGroups, unexpected_token_message
from .base import ParserSubcomponent


def _positional_params_word() -> Word:
    """The implicit ``"$@"`` Word used when for/select has no ``in`` list."""
    return Word(
        parts=[ExpansionPart(expansion=VariableExpansion('@'),
                             quoted=True, quote_char='"')])


class ControlStructureParser(ParserSubcomponent):
    """Parser for control structure constructs.

    Every control structure parsed here is a ``CompoundCommand`` (the unified
    control structures, ``[[ ]]`` and ``(( ))`` all inherit it), so each result
    can appear both at statement level and as a pipeline component. There is no
    per-keyword dispatch method: the single compound-command chokepoint
    ``CommandParser._parse_compound_component`` (called by both pipeline
    components and function bodies) dispatches directly to the individual
    ``parse_*_statement`` methods below under the ``MAX_NESTING_DEPTH`` guard.
    """

    # === If Statement Parsing ===

    def parse_if_statement(self) -> IfConditional:
        """Parse if/then/else/fi conditional statement."""
        self.parser.expect(TokenType.IF)
        self.parser.ctx.push_construct('if')
        self.parser.skip_newlines()

        # Parse main condition and body
        condition, then_part = self._parse_condition_then_block()

        # Parse elif clauses
        elif_parts = []
        while self.parser.match(TokenType.ELIF):
            self.parser.advance()
            self.parser.ctx.retitle_construct('elif')
            elif_condition, elif_then = self._parse_condition_then_block()
            elif_parts.append((elif_condition, elif_then))

        # Parse optional else
        else_part = None
        if self.parser.match(TokenType.ELSE):
            self.parser.advance()
            self.parser.ctx.retitle_construct('else')
            self.parser.skip_newlines()
            else_part = self.parser.statements.parse_required_command_list_until(TokenType.FI)

        self.parser.expect(TokenType.FI)
        self.parser.ctx.pop_construct()
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
        condition = self.parser.statements.parse_required_command_list_until(TokenType.THEN)
        self.parser.expect(TokenType.THEN)
        self.parser.ctx.retitle_construct('then')
        self.parser.skip_newlines()
        body = self.parser.statements.parse_required_command_list_until(TokenType.ELIF, TokenType.ELSE, TokenType.FI)
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
        self.parser.ctx.push_construct(start.name.lower())
        self.parser.skip_newlines()

        condition = self.parser.statements.parse_required_command_list_until(body_start)

        self.parser.expect(body_start)
        self.parser.skip_newlines()

        body = self.parser.statements.parse_required_command_list_until(body_end)

        self.parser.expect(body_end)
        self.parser.ctx.pop_construct()
        redirects = self.parser.redirections.parse_redirects()

        return condition, body, redirects

    # === For Statement Parsing ===

    def parse_for_statement(self) -> Union[ForLoop, CStyleForLoop]:
        """Parse for loop without setting execution context."""
        self.parser.expect(TokenType.FOR)
        self.parser.ctx.push_construct('for')
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

        if self.parser.match(TokenType.IN):
            # Explicit item list provided
            self.parser.advance()
            self.parser.skip_newlines()
            items, item_words = self._parse_for_iterable()
        else:
            # No explicit list - default to positional parameters ("$@")
            items = ['$@']
            item_words = [_positional_params_word()]

        self.parser.skip_separators()
        self.parser.expect(TokenType.DO)
        self.parser.skip_newlines()

        body = self.parser.statements.parse_required_command_list_until(TokenType.DONE)
        self.parser.expect(TokenType.DONE)
        self.parser.ctx.pop_construct()
        redirects = self.parser.redirections.parse_redirects()

        return ForLoop(
            variable=variable,
            items=items,
            item_words=item_words,
            body=body,
            redirects=redirects,
            background=False
        )

    def _parse_for_iterable(self) -> tuple[List[str], List[Word]]:
        """Parse the iterable part of a for/select loop.

        Returns parallel lists: display strings and the Word AST nodes the
        executor expands.
        """
        items = []
        item_words = []

        # Parse items until we hit DO, newline, or semicolon
        while (not self.parser.match(TokenType.DO) and
               not self.parser.match_any(TokenGroups.STATEMENT_SEPARATORS) and
               not self.parser.at_end()):

            if self.parser.match_any(TokenGroups.WORD_LIKE):
                word = self.parser.commands.parse_argument_as_word()
                items.append(word.display_text())
                item_words.append(word)
            else:
                break

        return items, item_words

    def _parse_c_style_for(self) -> CStyleForLoop:
        """Parse C-style for loop without setting execution context."""
        # Parse initialization (an empty section reads as '' -> None).
        init = self.parser.arithmetic.parse_arithmetic_section() or None

        # Handle semicolon(s) after init
        if self.parser.match(TokenType.SEMICOLON):
            self.parser.advance()  # consume ;
            # Parse condition normally (empty section -> None).
            condition = self.parser.arithmetic.parse_arithmetic_section() or None
            # The second ';' is mandatory: a C-style for header has exactly two
            # semicolons (three sections, any may be empty). Without this guard a
            # one-semicolon header like ``for ((i=0; i<3))`` would parse with an
            # empty update and loop forever; bash rejects it. (The collector now
            # stops the condition at ``))``, so a missing ';' surfaces here.)
            if self.parser.match(TokenType.SEMICOLON):
                self.parser.advance()  # consume ;
            else:
                raise self.parser.error("Expected ';' after for loop condition")
        elif self.parser.match(TokenType.DOUBLE_SEMICOLON):
            # Handle ;; case - both init and condition are effectively empty
            self.parser.advance()  # consume ;;
            condition = None
        else:
            # No semicolon, something's wrong
            raise self.parser.error("Expected ';' after for loop initialization")

        # Parse increment
        increment = self.parser.arithmetic.parse_arithmetic_section_until_double_rparen()

        # The body is EITHER `do LIST done` OR a brace group `{ LIST }` — bash
        # accepts both for the C-style for (the brace group is a documented
        # synonym for do..done), and REQUIRES one of them: a bare command with
        # no `do`/`{` is a syntax error (bash rc 2). Separators before the body
        # keyword are optional. Trailing redirections attach to the whole loop
        # in either form. (Prior to this fix `do` was wrongly treated as
        # optional, so `for ((...)); echo x; done` was accepted.)
        self.parser.skip_separators()
        if self.parser.match(TokenType.LBRACE):
            body = self._parse_c_style_for_brace_body()
        else:
            self.parser.expect(TokenType.DO)
            self.parser.skip_newlines()
            body = self.parser.statements.parse_required_command_list_until(
                TokenType.DONE)
            self.parser.expect(TokenType.DONE)
        self.parser.ctx.pop_construct()
        redirects = self.parser.redirections.parse_redirects()

        return CStyleForLoop(
            init_expr=init,
            condition_expr=condition,
            update_expr=increment if increment else None,
            body=body,
            redirects=redirects,
            background=False
        )

    def _parse_c_style_for_brace_body(self) -> StatementList:
        """Parse the `{ LIST }` body form of a C-style for loop.

        Bash accepts `for ((...)) { list; }` as a synonym for
        `for ((...)) do list; done`. This mirrors ``parse_brace_group``'s
        inner rules (space after ``{``, a ``;``/newline before ``}``, at least
        one command) but returns the body as a StatementList — the brace group
        here is the loop body itself, so trailing redirections are parsed by
        the caller and attach to the whole loop.
        """
        self.parser.expect(TokenType.LBRACE)
        self.parser.skip_newlines()
        body = self.parser.statements.parse_command_list_until(TokenType.RBRACE)
        self.parser.skip_newlines()
        if not body.statements:
            raise self.parser.error(
                unexpected_token_message(self.parser.peek()))
        self.parser.expect(TokenType.RBRACE)
        return body


    # === Case Statement Parsing ===

    def parse_case_statement(self) -> CaseConditional:
        """Parse case statement without setting execution context."""
        self.parser.expect(TokenType.CASE)
        self.parser.ctx.push_construct('case')

        subject_word = self._parse_case_expression()
        expr = subject_word.display_text()

        # bash allows newlines between the subject and `in`
        # (`case a <newline> in ...`), but nothing else.
        self.parser.skip_newlines()
        if not self.parser.match(TokenType.IN):
            raise self._case_syntax_error()
        self.parser.advance()
        self.parser.skip_newlines()

        items = []
        while not self.parser.match(TokenType.ESAC) and not self.parser.at_end():
            if self.parser.match_any(TokenGroups.WORD_LIKE_OR_CASE_PATTERNS) or \
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
        self.parser.ctx.pop_construct()
        redirects = self.parser.redirections.parse_redirects()

        return CaseConditional(
            expr=expr,
            items=items,
            redirects=redirects,
            background=False,
            subject_word=subject_word,
        )

    def _parse_case_expression(self) -> Word:
        """Parse the case subject: exactly one word, as a :class:`Word`.

        bash takes exactly one word (possibly a composite like ``a"b"c``)
        between ``case`` and ``in``; ``case a b in ...`` is a syntax error
        near ``b``, raised by the caller when the next token isn't ``in``.
        The subject may be spelled ``in`` or ``esac`` (the lexer leaves the
        word right after ``case`` as a plain WORD). The Word carries per-part
        quote context so the executor expands it without re-expanding
        quoted text.
        """
        if not self.parser.match_any(TokenGroups.WORD_LIKE):
            raise self._case_syntax_error()
        return self.parser.commands.parse_argument_as_word()

    def _case_syntax_error(self):
        """Build a bash-shaped syntax error for a malformed case header."""
        token = self.parser.peek()
        return self.parser.error(unexpected_token_message(token), token)

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

        text_parts = []
        word_parts: List[WordPart] = []

        while (not self.parser.match(TokenType.PIPE, TokenType.RPAREN) and
               not self.parser.at_end()):

            token = self.parser.peek()
            if self.parser.match_any(TokenGroups.WORD_LIKE_OR_CASE_PATTERNS):
                if token.type in TokenGroups.CASE_PATTERN_KEYWORDS:
                    # Keywords can be valid patterns
                    text_parts.append(token.value)
                    word_parts.append(LiteralPart(token.value, quoted=False,
                                                  quote_char=None))
                    self.parser.advance()
                else:
                    word = self.parser.commands.parse_argument_as_word()
                    text_parts.append(word.display_text())
                    word_parts.extend(word.parts)
            else:
                break

        # An alternative must contribute at least one word part. bash rejects
        # empty alternatives — `x|)`, `(|x)`, `()`, `(x|)` — as a syntax error.
        # A QUOTED-empty pattern (`''`) is legal and DOES produce a (quoted)
        # part, so it is not caught here (finding 5e).
        if not word_parts:
            token = self.parser.peek()
            raise self.parser.error(unexpected_token_message(token), token)

        return CasePattern(pattern=''.join(text_parts),
                           word=Word(parts=word_parts))

    # === Select Statement Parsing ===

    def parse_select_statement(self) -> SelectLoop:
        """Parse select statement without setting execution context."""
        self.parser.expect(TokenType.SELECT)
        self.parser.ctx.push_construct('select')
        self.parser.skip_newlines()

        variable = self.parser.expect(TokenType.WORD).value
        self.parser.skip_newlines()

        if self.parser.match(TokenType.IN):
            self.parser.advance()
            self.parser.skip_newlines()
            items, item_words = self._parse_for_iterable()
        else:
            # No explicit list - default to positional parameters ("$@")
            items = ['$@']
            item_words = [_positional_params_word()]

        self.parser.skip_separators()
        self.parser.expect(TokenType.DO)
        self.parser.skip_newlines()

        body = self.parser.statements.parse_required_command_list_until(TokenType.DONE)
        self.parser.expect(TokenType.DONE)
        self.parser.ctx.pop_construct()
        redirects = self.parser.redirections.parse_redirects()

        return SelectLoop(
            variable=variable,
            items=items,
            item_words=item_words,
            body=body,
            redirects=redirects,
            background=False
        )

