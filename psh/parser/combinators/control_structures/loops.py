"""Loop parsers for the shell parser combinator.

This module provides mixin parsers for while, until, for (traditional and
C-style), select loops, and break/continue statements.
"""

from typing import TYPE_CHECKING, List, Tuple, Union, cast

from ....ast_nodes import (
    BreakStatement,
    ContinueStatement,
    CStyleForLoop,
    ExpansionPart,
    ForLoop,
    SelectLoop,
    UntilLoop,
    VariableExpansion,
    WhileLoop,
    Word,
)
from ....lexer.keyword_defs import matches_keyword
from ....lexer.token_types import Token
from ...recursive_descent.helpers import ParseError
from ..core import Parser, ParseResult
from ..diagnostics import raise_committed_error

if TYPE_CHECKING:
    from ._protocols import ControlStructureProtocol
    _Base = ControlStructureProtocol
else:
    _Base = object


def _positional_params_word() -> Word:
    """The implicit ``"$@"`` Word used when for/select has no ``in`` list."""
    return Word(
        parts=[ExpansionPart(expansion=VariableExpansion('@'),
                             quoted=True, quote_char='"')])


def _is_missing_nested_terminator(error: ParseError) -> bool:
    message = error.message.lower()
    return (
        "expected 'fi' to close" in message
        or "expected 'done' to close" in message
        or "expected 'esac' to close" in message
    )


class LoopParserMixin(_Base):
    """Mixin providing loop parsers for ControlStructureParsers."""

    def _build_loop_items(
        self, item_tokens: List[Token],
    ) -> Tuple[List[str], List[Word]]:
        """Build for/select item lists from collected item tokens.

        Adjacent tokens are merged into composite words (``pre$x`` is ONE
        item) and each item gets a Word AST node, expanded by the executor
        through the canonical Word engine.
        """
        from ...recursive_descent.support.word_builder import WordBuilder

        items: List[str] = []
        item_words: List[Word] = []
        for group in self.commands._group_adjacent_tokens(item_tokens):
            items.append(''.join(
                self.commands.expansions.format_token_value(t) for t in group))
            if len(group) == 1:
                word = self.commands.expansions.build_word_from_token(group[0])
            else:
                word = WordBuilder.build_composite_word(group)
            item_words.append(word)
        return items, item_words

    def _build_while_loop(self) -> Parser[WhileLoop]:
        """Build parser for while/do/done loops."""
        def parse_while_loop(tokens: List[Token], pos: int) -> ParseResult[WhileLoop]:
            """Parse while loop."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'while'):
                return ParseResult(success=False, error="Expected 'while'", position=pos)

            pos += 1  # Skip 'while'

            # Parse condition (until 'do')
            condition_tokens = []
            while pos < len(tokens):
                token = tokens[pos]
                if matches_keyword(token, 'do'):
                    break
                if token.type.name in ['SEMICOLON', 'NEWLINE']:
                    if pos + 1 < len(tokens):
                        next_token = tokens[pos + 1]
                        if matches_keyword(next_token, 'do'):
                            break
                condition_tokens.append(token)
                pos += 1

            if pos >= len(tokens):
                raise_committed_error(tokens, pos, "Expected 'do' in while loop")

            condition_result = self.commands.statement_list.parse(condition_tokens, 0)
            if not condition_result.success:
                return ParseResult(success=False,
                                 error=f"Failed to parse while condition: {condition_result.error}",
                                 position=pos)

            # Skip separator and 'do'
            if tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                pos += 1
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'do'):
                raise_committed_error(tokens, pos, "Expected 'do' after while condition")
            pos += 1  # Skip 'do'

            # Skip optional separator after 'do'
            empty_body_error_pos = pos
            if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                empty_body_error_pos = pos
                pos += 1

            # Parse the body (until 'done', handling nested loops)
            body_tokens, done_pos = self._collect_tokens_until_keyword(tokens, pos, 'done', 'do')

            if done_pos >= len(tokens):
                raise_committed_error(tokens, done_pos, "Expected 'done' to close while loop")

            try:
                body_result = self.commands.statement_list.parse(body_tokens, 0)
            except ParseError as error:
                if done_pos < len(tokens) and _is_missing_nested_terminator(error):
                    raise_committed_error(tokens, done_pos, error.message)
                raise
            if not body_result.success:
                return ParseResult(success=False,
                                 error=f"Failed to parse while body: {body_result.error}",
                                 position=pos)
            if not body_result.value.statements:
                raise_committed_error(tokens, empty_body_error_pos, "Expected command in while body")

            pos = done_pos + 1  # Skip 'done'

            # Parse trailing redirections and background
            redirects, background, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=WhileLoop(
                    condition=condition_result.value,
                    body=body_result.value,
                    redirects=redirects,
                    background=background,
                ),
                position=pos
            )

        return Parser(parse_while_loop)

    def _build_until_loop(self) -> Parser[UntilLoop]:
        """Build parser for until/do/done loops."""
        def parse_until_loop(tokens: List[Token], pos: int) -> ParseResult[UntilLoop]:
            """Parse until loop."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'until'):
                return ParseResult(success=False, error="Expected 'until'", position=pos)

            pos += 1  # Skip 'until'

            # Parse condition until 'do'
            condition_tokens = []
            while pos < len(tokens):
                token = tokens[pos]
                if matches_keyword(token, 'do'):
                    break
                if token.type.name in ['SEMICOLON', 'NEWLINE']:
                    if pos + 1 < len(tokens):
                        next_token = tokens[pos + 1]
                        if matches_keyword(next_token, 'do'):
                            break
                condition_tokens.append(token)
                pos += 1

            if pos >= len(tokens):
                raise_committed_error(tokens, pos, "Expected 'do' in until loop")

            condition_result = self.commands.statement_list.parse(condition_tokens, 0)
            if not condition_result.success:
                return ParseResult(success=False,
                                   error=f"Failed to parse until condition: {condition_result.error}",
                                   position=pos)

            if tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                pos += 1
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'do'):
                raise_committed_error(tokens, pos, "Expected 'do' after until condition")
            pos += 1

            empty_body_error_pos = pos
            if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                empty_body_error_pos = pos
                pos += 1

            body_tokens, done_pos = self._collect_tokens_until_keyword(tokens, pos, 'done', 'do')

            if done_pos >= len(tokens):
                raise_committed_error(tokens, done_pos, "Expected 'done' to close until loop")

            try:
                body_result = self.commands.statement_list.parse(body_tokens, 0)
            except ParseError as error:
                if done_pos < len(tokens) and _is_missing_nested_terminator(error):
                    raise_committed_error(tokens, done_pos, error.message)
                raise
            if not body_result.success:
                return ParseResult(success=False,
                                   error=f"Failed to parse until body: {body_result.error}",
                                   position=pos)
            if not body_result.value.statements:
                raise_committed_error(tokens, empty_body_error_pos, "Expected command in until body")

            pos = done_pos + 1

            # Parse trailing redirections and background
            redirects, background, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=UntilLoop(
                    condition=condition_result.value,
                    body=body_result.value,
                    redirects=redirects,
                    background=background,
                ),
                position=pos
            )

        return Parser(parse_until_loop)

    def _build_for_loops(self) -> Parser[Union[ForLoop, CStyleForLoop]]:
        """Build parser for both traditional and C-style for loops."""
        # Try C-style first, then traditional.  ``Parser`` is invariant, so the
        # per-loop parsers are cast to the common union type before composition.
        c_style = cast("Parser[Union[ForLoop, CStyleForLoop]]", self._build_c_style_for_loop())
        traditional = cast("Parser[Union[ForLoop, CStyleForLoop]]", self._build_traditional_for_loop())
        return c_style.or_else(traditional)

    def _build_traditional_for_loop(self) -> Parser[ForLoop]:
        """Build parser for traditional for/in loops."""
        def parse_for_loop(tokens: List[Token], pos: int) -> ParseResult[ForLoop]:
            """Parse traditional for loop."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'for'):
                return ParseResult(success=False, error="Expected 'for'", position=pos)

            pos += 1  # Skip 'for'

            # Parse variable name
            if pos >= len(tokens) or tokens[pos].type.name != 'WORD':
                raise_committed_error(tokens, pos, "Expected variable name after 'for'")

            var_name = tokens[pos].value
            pos += 1

            # Skip optional newlines before checking for 'in'
            while pos < len(tokens) and tokens[pos].type.name == 'NEWLINE':
                pos += 1

            has_in_clause = False
            if pos < len(tokens) and matches_keyword(tokens[pos], 'in'):
                has_in_clause = True
                pos += 1  # Skip 'in'
                while pos < len(tokens) and tokens[pos].type.name == 'NEWLINE':
                    pos += 1

            items: List[str]
            item_words: List[Word]
            if has_in_clause:
                # Collect item tokens (words until 'do' or separator+do)
                item_tokens: List[Token] = []
                while pos < len(tokens):
                    token = tokens[pos]
                    if matches_keyword(token, 'do'):
                        break
                    if token.type.name in ['SEMICOLON', 'NEWLINE']:
                        if (pos + 1 < len(tokens) and
                            matches_keyword(tokens[pos + 1], 'do')):
                            break
                    if token.type.name in ['WORD', 'STRING', 'VARIABLE', 'COMPOSITE',
                                            'COMMAND_SUB', 'COMMAND_SUB_BACKTICK',
                                            'ARITH_EXPANSION', 'PARAM_EXPANSION']:
                        item_tokens.append(token)
                        pos += 1
                    else:
                        break
                items, item_words = self._build_loop_items(item_tokens)
            else:
                # No explicit list - default to positional parameters ("$@")
                items = ['$@']
                item_words = [_positional_params_word()]

            # Skip optional separator before 'do'
            if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                pos += 1

            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'do'):
                raise_committed_error(tokens, pos, "Expected 'do' in for loop")
            pos += 1  # Skip 'do'

            # Skip optional separator after 'do'
            empty_body_error_pos = pos
            if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                empty_body_error_pos = pos
                pos += 1

            # Parse the body (until 'done', handling nested loops)
            body_tokens, done_pos = self._collect_tokens_until_keyword(tokens, pos, 'done', 'do')

            if done_pos >= len(tokens):
                raise_committed_error(tokens, done_pos, "Expected 'done' to close for loop")

            try:
                body_result = self.commands.statement_list.parse(body_tokens, 0)
            except ParseError as error:
                if done_pos < len(tokens) and _is_missing_nested_terminator(error):
                    raise_committed_error(tokens, done_pos, error.message)
                raise
            if not body_result.success:
                return ParseResult(success=False,
                                 error=f"Failed to parse for body: {body_result.error}",
                                 position=pos)
            if not body_result.value.statements:
                raise_committed_error(tokens, empty_body_error_pos, "Expected command in for body")

            pos = done_pos + 1  # Skip 'done'

            # Parse trailing redirections and background
            redirects, background, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=ForLoop(
                    variable=var_name,
                    items=items,
                    body=body_result.value,
                    item_words=item_words,
                    redirects=redirects,
                    background=background,
                ),
                position=pos
            )

        return Parser(parse_for_loop)

    def _build_c_style_for_loop(self) -> Parser[CStyleForLoop]:
        """Build parser for C-style for loops."""
        def parse_c_style_for(tokens: List[Token], pos: int) -> ParseResult[CStyleForLoop]:
            """Parse C-style for loop."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'for'):
                return ParseResult(success=False, error="Expected 'for'", position=pos)

            # Check for '((' after 'for'
            if pos + 1 >= len(tokens) or (tokens[pos + 1].type.name != 'DOUBLE_LPAREN' and tokens[pos + 1].value != '(('):
                return ParseResult(success=False, error="Not a C-style for loop", position=pos)

            pos += 2  # Skip 'for' and '(('

            # Handle ';;' (DOUBLE_SEMICOLON) — both init and condition are empty
            init_tokens: List[Token]
            cond_tokens: List[Token]
            if pos < len(tokens) and tokens[pos].type.name == 'DOUBLE_SEMICOLON':
                init_tokens = []
                cond_tokens = []
                pos += 1  # Skip ';;'
            else:
                # Parse init expression (until ';')
                init_tokens = []
                while pos < len(tokens) and tokens[pos].value != ';':
                    init_tokens.append(tokens[pos])
                    pos += 1

                if pos >= len(tokens):
                    raise_committed_error(tokens, pos, "Expected ';' after init expression")
                pos += 1  # Skip ';'

                # Parse condition expression (until ';')
                cond_tokens = []
                while pos < len(tokens) and tokens[pos].value != ';':
                    cond_tokens.append(tokens[pos])
                    pos += 1

                if pos >= len(tokens):
                    raise_committed_error(tokens, pos, "Expected ';' after condition expression")
                pos += 1  # Skip ';'

            # Parse update expression (until '))')
            update_tokens = []
            while pos < len(tokens) and tokens[pos].type.name != 'DOUBLE_RPAREN' and tokens[pos].value != '))':
                update_tokens.append(tokens[pos])
                pos += 1

            if pos >= len(tokens):
                raise_committed_error(tokens, pos, "Expected '))' to close C-style for")
            pos += 1  # Skip '))'

            # Skip optional separator and optional 'do' keyword.
            # PSH (like some shells) allows omitting 'do' for C-style for loops:
            #   for ((i=0; i<3; i++)) echo $i; done
            if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                pos += 1
            if pos < len(tokens) and matches_keyword(tokens[pos], 'do'):
                pos += 1  # Skip 'do'
                # Skip optional separator after 'do'
                empty_body_error_pos = pos
                if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                    empty_body_error_pos = pos
                    pos += 1
            else:
                empty_body_error_pos = pos

            # Parse the body (until 'done', handling nested loops)
            body_tokens, done_pos = self._collect_tokens_until_keyword(tokens, pos, 'done', 'do')

            if done_pos >= len(tokens):
                raise_committed_error(tokens, done_pos, "Expected 'done' to close C-style for loop")

            try:
                body_result = self.commands.statement_list.parse(body_tokens, 0)
            except ParseError as error:
                if done_pos < len(tokens) and _is_missing_nested_terminator(error):
                    raise_committed_error(tokens, done_pos, error.message)
                raise
            if not body_result.success:
                return ParseResult(success=False,
                                 error=f"Failed to parse for body: {body_result.error}",
                                 position=pos)
            if not body_result.value.statements:
                raise_committed_error(tokens, empty_body_error_pos, "Expected command in for body")

            pos = done_pos + 1  # Skip 'done'

            # Parse trailing redirections and background
            redirects, background, pos = self._parse_trailing_redirects(tokens, pos)

            # Convert token lists to strings
            init_expr = ' '.join(t.value for t in init_tokens) if init_tokens else None
            cond_expr = ' '.join(t.value for t in cond_tokens) if cond_tokens else None
            update_expr = ' '.join(t.value for t in update_tokens) if update_tokens else None

            return ParseResult(
                success=True,
                value=CStyleForLoop(
                    init_expr=init_expr,
                    condition_expr=cond_expr,
                    update_expr=update_expr,
                    body=body_result.value,
                    redirects=redirects,
                    background=background,
                ),
                position=pos
            )

        return Parser(parse_c_style_for)

    def _build_select_loop(self) -> Parser[SelectLoop]:
        """Build parser for select/do/done loops."""
        def parse_select_loop(tokens: List[Token], pos: int) -> ParseResult[SelectLoop]:
            """Parse select loop."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'select'):
                return ParseResult(success=False, error="Expected 'select'", position=pos)

            pos += 1  # Skip 'select'

            # Parse variable name
            if pos >= len(tokens) or tokens[pos].type.name != 'WORD':
                return ParseResult(success=False, error="Expected variable name after 'select'", position=pos)

            var_name = tokens[pos].value
            pos += 1

            # Expect 'in'
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'in'):
                return ParseResult(success=False, error="Expected 'in' after variable name", position=pos)

            pos += 1  # Skip 'in'

            # Collect item tokens (words until 'do' or separator+do)
            item_tokens: List[Token] = []
            while pos < len(tokens):
                token = tokens[pos]
                if matches_keyword(token, 'do'):
                    break
                if token.type.name in ['SEMICOLON', 'NEWLINE']:
                    if (pos + 1 < len(tokens) and
                        matches_keyword(tokens[pos + 1], 'do')):
                        break
                if token.type.name in ['WORD', 'STRING', 'VARIABLE', 'COMPOSITE',
                                      'COMMAND_SUB', 'COMMAND_SUB_BACKTICK',
                                      'ARITH_EXPANSION', 'PARAM_EXPANSION']:
                    item_tokens.append(token)
                    pos += 1
                else:
                    break
            items, item_words = self._build_loop_items(item_tokens)

            # Skip separator and 'do'
            if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                pos += 1
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'do'):
                return ParseResult(success=False, error="Expected 'do' in select loop", position=pos)
            pos += 1  # Skip 'do'

            # Skip optional separator after 'do'
            empty_body_error_pos = pos
            if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                empty_body_error_pos = pos
                pos += 1

            # Parse the body (until 'done', handling nested loops)
            body_tokens, done_pos = self._collect_tokens_until_keyword(tokens, pos, 'done', 'do')

            if done_pos >= len(tokens):
                return ParseResult(success=False, error="Expected 'done' to close select loop", position=pos)

            try:
                body_result = self.commands.statement_list.parse(body_tokens, 0)
            except ParseError as error:
                if done_pos < len(tokens) and _is_missing_nested_terminator(error):
                    raise_committed_error(tokens, done_pos, error.message)
                raise
            if not body_result.success:
                return ParseResult(success=False,
                                 error=f"Failed to parse select body: {body_result.error}",
                                 position=pos)
            if not body_result.value.statements:
                raise_committed_error(tokens, empty_body_error_pos, "Expected command in select body")

            pos = done_pos + 1  # Skip 'done'

            # Parse trailing redirections and background
            redirects, background, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=SelectLoop(
                    variable=var_name,
                    items=items,
                    item_words=item_words,
                    body=body_result.value,
                    redirects=redirects,
                    background=background,
                ),
                position=pos
            )

        return Parser(parse_select_loop)

    def _build_break_statement(self) -> Parser[BreakStatement]:
        """Build parser for break statement."""
        def parse_break(tokens: List[Token], pos: int) -> ParseResult[BreakStatement]:
            """Parse break statement."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'break'):
                return ParseResult(success=False, error="Expected 'break'", position=pos)

            pos += 1  # Skip 'break'

            # Parse optional level (number)
            level = 1  # Default
            if pos < len(tokens) and tokens[pos].type.name == 'WORD':
                try:
                    level = int(tokens[pos].value)
                    pos += 1
                except ValueError:
                    pass  # Not a number, leave level as 1

            return ParseResult(
                success=True,
                value=BreakStatement(level=level),
                position=pos
            )

        return Parser(parse_break)

    def _build_continue_statement(self) -> Parser[ContinueStatement]:
        """Build parser for continue statement."""
        def parse_continue(tokens: List[Token], pos: int) -> ParseResult[ContinueStatement]:
            """Parse continue statement."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'continue'):
                return ParseResult(success=False, error="Expected 'continue'", position=pos)

            pos += 1  # Skip 'continue'

            # Parse optional level (number)
            level = 1  # Default
            if pos < len(tokens) and tokens[pos].type.name == 'WORD':
                try:
                    level = int(tokens[pos].value)
                    pos += 1
                except ValueError:
                    pass  # Not a number, leave level as 1

            return ParseResult(
                success=True,
                value=ContinueStatement(level=level),
                position=pos
            )

        return Parser(parse_continue)
