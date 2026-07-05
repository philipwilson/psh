"""Loop parsers for the shell parser combinator.

This module provides mixin parsers for while, until, for (traditional and
C-style), and select loops. (break/continue are not statements: they are
ordinary simple commands backed by builtins, as in bash.)
"""

from typing import TYPE_CHECKING, List, Optional, Tuple, Union, cast

from ....ast_nodes import (
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
from ....lexer.token_stream import TokenStream
from ....lexer.token_types import Token
from ..core import ParseFailure, Parser, ParseResult, ParseSuccess, many
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


# Token types that can appear as a for/select ``in``-list item.
_LOOP_ITEM_TOKEN_TYPES = frozenset({
    'WORD', 'STRING', 'VARIABLE', 'COMPOSITE', 'COMMAND_SUB',
    'COMMAND_SUB_BACKTICK', 'ARITH_EXPANSION', 'PARAM_EXPANSION',
})


def _parse_loop_item(tokens: List[Token], pos: int) -> ParseResult[Token]:
    """Parse one for/select list item: a word-like token that isn't ``do``.

    ``do`` is a WORD-typed keyword, so without this guard it would be swallowed
    as a list item; rejecting it lets ``many`` end the list exactly at ``do``.
    A separator (``;``/newline) or any other non-word token ends the list too,
    simply by not matching here.
    """
    if (pos < len(tokens)
            and tokens[pos].type.name in _LOOP_ITEM_TOKEN_TYPES
            and not matches_keyword(tokens[pos], 'do')):
        return ParseSuccess(tokens[pos], pos + 1)
    return ParseFailure(pos, "Expected a for/select list item")


#: One for/select ``in``-list item; ``many`` of these is the whole list.
_loop_item = Parser(_parse_loop_item)


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

    def _collect_loop_items(
        self, tokens: List[Token], pos: int,
    ) -> Tuple[List[str], List[Word], int]:
        """Collect a for/select ``in``-list and build its item Words.

        The list is ``many`` word-like item tokens (:data:`_loop_item`); it ends
        at ``do``, a separator, or any other non-word token. Returns
        ``(items, item_words, new_pos)``.
        """
        result = many(_loop_item).parse(tokens, pos)
        items, item_words = self._build_loop_items(list(result.value or []))
        return items, item_words, result.position

    def _build_while_loop(self) -> Parser[WhileLoop]:
        """Build parser for while/do/done loops."""
        def parse_while_loop(tokens: List[Token], pos: int) -> ParseResult[WhileLoop]:
            """Parse while loop."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'while'):
                return ParseResult(success=False, error="Expected 'while'", position=pos)

            pos += 1  # Skip 'while'

            # Parse the condition by recursion: a statement list up to (but not
            # consuming) the command-position 'do'. Parsing on the real token
            # stream — rather than slicing to the first 'do' — means a 'do' that
            # is merely an argument ('while echo do; ...') is consumed as a word,
            # matching bash and the recursive-descent parser.
            condition_result = self.commands.build_statement_list(
                frozenset({'do'})).parse(tokens, pos)
            if not condition_result.success:
                return ParseResult(success=False,
                                 error=f"Failed to parse while condition: {condition_result.error}",
                                 position=condition_result.position)
            assert condition_result.value is not None
            pos = condition_result.position

            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'do'):
                raise_committed_error(tokens, pos, "Expected 'do' in while loop")
            pos += 1  # Skip 'do'

            # Skip optional separator after 'do'
            empty_body_error_pos = pos
            if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                empty_body_error_pos = pos
                pos += 1

            # Parse the body by recursion: statements up to (but not consuming)
            # the matching 'done'. Nested loops consume their own 'done', so the
            # terminator seen here is this loop's own. No token-slicing required.
            body_result = self.commands.build_statement_list(frozenset({'done'})).parse(tokens, pos)
            if not body_result.success:
                # Past 'do' we are committed to a while loop, so a body failure
                # is a hard syntax error: raise it (at the offending token) so
                # or_else cannot swallow it and retry as a simple command.
                raise_committed_error(tokens, body_result.position,
                                      body_result.error or "Failed to parse while body")
            assert body_result.value is not None  # success implies a body
            done_pos = body_result.position

            if done_pos >= len(tokens) or not matches_keyword(tokens[done_pos], 'done'):
                raise_committed_error(tokens, done_pos, "Expected 'done' to close while loop",
                                      terminator='done')
            if not body_result.value.statements:
                raise_committed_error(tokens, empty_body_error_pos, "Expected command in while body")

            pos = done_pos + 1  # Skip 'done'

            # Parse trailing redirections ('&' is handled at and-or level)
            redirects, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=WhileLoop(
                    condition=condition_result.value,
                    body=body_result.value,
                    redirects=redirects,
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

            # Parse the condition by recursion up to (not consuming) the
            # command-position 'do' (see _build_while_loop for the rationale).
            condition_result = self.commands.build_statement_list(
                frozenset({'do'})).parse(tokens, pos)
            if not condition_result.success:
                return ParseResult(success=False,
                                   error=f"Failed to parse until condition: {condition_result.error}",
                                   position=condition_result.position)
            assert condition_result.value is not None
            pos = condition_result.position

            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'do'):
                raise_committed_error(tokens, pos, "Expected 'do' in until loop")
            pos += 1

            empty_body_error_pos = pos
            if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                empty_body_error_pos = pos
                pos += 1

            # Parse the body by recursion up to (not consuming) the matching 'done'.
            body_result = self.commands.build_statement_list(frozenset({'done'})).parse(tokens, pos)
            if not body_result.success:
                # Committed to an until loop past 'do' — raise hard (see while).
                raise_committed_error(tokens, body_result.position,
                                      body_result.error or "Failed to parse until body")
            assert body_result.value is not None  # success implies a body
            done_pos = body_result.position

            if done_pos >= len(tokens) or not matches_keyword(tokens[done_pos], 'done'):
                raise_committed_error(tokens, done_pos, "Expected 'done' to close until loop",
                                      terminator='done')
            if not body_result.value.statements:
                raise_committed_error(tokens, empty_body_error_pos, "Expected command in until body")

            pos = done_pos + 1

            # Parse trailing redirections ('&' is handled at and-or level)
            redirects, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=UntilLoop(
                    condition=condition_result.value,
                    body=body_result.value,
                    redirects=redirects,
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
                # The item list is `many` word-like tokens (stops at 'do', a
                # separator, or any other token).
                items, item_words, pos = self._collect_loop_items(tokens, pos)
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

            # Parse the body by recursion up to (not consuming) the matching 'done'.
            body_result = self.commands.build_statement_list(frozenset({'done'})).parse(tokens, pos)
            if not body_result.success:
                # Committed to a for loop past 'do' — raise hard (see while).
                raise_committed_error(tokens, body_result.position,
                                      body_result.error or "Failed to parse for body")
            assert body_result.value is not None  # success implies a body
            done_pos = body_result.position

            if done_pos >= len(tokens) or not matches_keyword(tokens[done_pos], 'done'):
                raise_committed_error(tokens, done_pos, "Expected 'done' to close for loop",
                                      terminator='done')
            if not body_result.value.statements:
                raise_committed_error(tokens, empty_body_error_pos, "Expected command in for body")

            pos = done_pos + 1  # Skip 'done'

            # Parse trailing redirections ('&' is handled at and-or level)
            redirects, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=ForLoop(
                    variable=var_name,
                    items=items,
                    body=body_result.value,
                    item_words=item_words,
                    redirects=redirects,
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

            # Parse the three arithmetic sections through the shared depth-tracked
            # collector (``psh/lexer/token_stream.py``), mirroring the recursive
            # descent parser (``recursive_descent/.../_parse_c_style_for``) so the
            # two stay locked together: same paren discipline (``(`` / ``((`` open,
            # ``)`` / ``))`` close, straddling ``))`` split), same normalized
            # expression strings.
            stream = TokenStream(tokens, pos)
            _t, init_str = stream.collect_arithmetic_expression(stop_at_semicolon=True)
            pos = stream.pos
            init_expr = init_str or None

            cond_expr: Optional[str] = None
            if pos < len(tokens) and tokens[pos].type.name == 'SEMICOLON':
                pos += 1  # Skip ';'
                stream = TokenStream(tokens, pos)
                _t, cond_str = stream.collect_arithmetic_expression(stop_at_semicolon=True)
                pos = stream.pos
                cond_expr = cond_str or None
                # The second ';' is mandatory: a C-style for header has exactly
                # two semicolons. Without this a one-semicolon header like
                # ``for ((i=0; i<3))`` would parse with an empty update and loop
                # forever; bash rejects it. Mirrors the recursive descent parser.
                if pos < len(tokens) and tokens[pos].type.name == 'SEMICOLON':
                    pos += 1  # Skip ';'
                else:
                    raise_committed_error(tokens, pos, "Expected ';' after condition expression")
            elif pos < len(tokens) and tokens[pos].type.name == 'DOUBLE_SEMICOLON':
                pos += 1  # Skip ';;' — condition (and, if init empty, init) omitted
            else:
                raise_committed_error(tokens, pos, "Expected ';' after init expression")

            # Parse update expression, then consume the enclosing '))' (a single
            # DOUBLE_RPAREN, or two RPARENs left by a straddle split).
            stream = TokenStream(tokens, pos)
            _t, update_str = stream.collect_arithmetic_expression(stop_at_semicolon=False)
            pos = stream.pos
            update_expr = update_str or None
            if pos < len(tokens) and tokens[pos].type.name == 'DOUBLE_RPAREN':
                pos += 1  # Skip '))'
            elif (pos + 1 < len(tokens) and tokens[pos].type.name == 'RPAREN'
                  and tokens[pos + 1].type.name == 'RPAREN'):
                pos += 2  # Skip ') )'
            else:
                raise_committed_error(tokens, pos, "Expected '))' to close C-style for")

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

            # Parse the body by recursion up to (not consuming) the matching 'done'.
            body_result = self.commands.build_statement_list(frozenset({'done'})).parse(tokens, pos)
            if not body_result.success:
                # Committed to a for loop past 'do' — raise hard (see while).
                raise_committed_error(tokens, body_result.position,
                                      body_result.error or "Failed to parse for body")
            assert body_result.value is not None  # success implies a body
            done_pos = body_result.position

            if done_pos >= len(tokens) or not matches_keyword(tokens[done_pos], 'done'):
                raise_committed_error(tokens, done_pos, "Expected 'done' to close C-style for loop",
                                      terminator='done')
            if not body_result.value.statements:
                raise_committed_error(tokens, empty_body_error_pos, "Expected command in for body")

            pos = done_pos + 1  # Skip 'done'

            # Parse trailing redirections ('&' is handled at and-or level)
            redirects, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=CStyleForLoop(
                    init_expr=init_expr,
                    condition_expr=cond_expr,
                    update_expr=update_expr,
                    body=body_result.value,
                    redirects=redirects,
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

            # The item list is `many` word-like tokens (stops at 'do', a
            # separator, or any other token).
            items, item_words, pos = self._collect_loop_items(tokens, pos)

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

            # Parse the body by recursion up to (not consuming) the matching 'done'.
            body_result = self.commands.build_statement_list(frozenset({'done'})).parse(tokens, pos)
            if not body_result.success:
                return ParseResult(success=False,
                                 error=f"Failed to parse select body: {body_result.error}",
                                 position=pos)
            assert body_result.value is not None  # success implies a body
            done_pos = body_result.position

            if done_pos >= len(tokens) or not matches_keyword(tokens[done_pos], 'done'):
                return ParseResult(success=False, error="Expected 'done' to close select loop", position=pos)
            if not body_result.value.statements:
                raise_committed_error(tokens, empty_body_error_pos, "Expected command in select body")

            pos = done_pos + 1  # Skip 'done'

            # Parse trailing redirections ('&' is handled at and-or level)
            redirects, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=SelectLoop(
                    variable=var_name,
                    items=items,
                    item_words=item_words,
                    body=body_result.value,
                    redirects=redirects,
                ),
                position=pos
            )

        return Parser(parse_select_loop)

