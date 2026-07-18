"""Statement and statement-list parsers for the shell parser combinator.

This module provides the mixin building statements (a function definition
else an and-or list) and the recursion-based statement-list engine used for
every compound body and the top-level list.
"""

from typing import TYPE_CHECKING, List, Union

from ....ast_nodes import AndOrList, FunctionDef, StatementList
from ....lexer.keyword_defs import matches_keyword
from ....lexer.token_types import Token
from ..core import Parser, ParseResult, many1, optional

if TYPE_CHECKING:
    from ._protocols import CommandParsersProtocol
    _Base = CommandParsersProtocol
else:
    _Base = object


class StatementMixin(_Base):
    """Mixin providing statement and statement-list parsers for CommandParsers."""

    # A function definition followed by one of these is a PipelineComponent, so
    # it is wrapped through the and-or machinery rather than returned bare
    # (#20 H9; campaign S5). Mirrors the recursive descent StatementParser.
    _FUNCTION_DEF_CONTINUATIONS = frozenset({
        'PIPE', 'PIPE_AND', 'AND_AND', 'OR_OR', 'AMPERSAND',
    })

    def _build_statement_parser(self) -> Parser[Union[AndOrList, FunctionDef]]:
        """Build parser for statements: a function definition, else an and-or list.

        The function-definition head is read from ``self._function_def`` at
        parse time (a never-matching parser until wiring fills the slot). A
        STANDALONE definition is returned bare (the historical top-level shape);
        a definition followed by a pipeline/and-or/background continuation is a
        PipelineComponent, so it is reparsed through ``self.and_or_list`` (whose
        pipeline element now accepts a function definition) so it wraps into
        AndOrList -> Pipeline (#20 H9; campaign S5).

        Returns:
            Parser that produces statement nodes
        """
        def parse_statement(tokens: List[Token], pos: int) -> ParseResult:
            fn_result = self._function_def.parse(tokens, pos)
            if fn_result.success:
                npos = fn_result.position
                if (npos < len(tokens)
                        and tokens[npos].type.name in self._FUNCTION_DEF_CONTINUATIONS):
                    return self.and_or_list.parse(tokens, pos)
                return fn_result
            if fn_result.committed:
                return fn_result
            return self.and_or_list.parse(tokens, pos)

        return Parser(parse_statement)

    # Token-type names that always terminate a statement list, independent of
    # the construct: end-of-input and the closers of an enclosing group.
    _STATEMENT_LIST_STOP_TYPES = frozenset({'EOF', 'RPAREN', 'RBRACE'})

    def build_statement_list(self, terminators: frozenset = frozenset(),
                             terminator_types: frozenset = frozenset(),
                             ) -> Parser[StatementList]:
        """Build a statement list that stops at (without consuming) a terminator.

        This is the recursion-based replacement for slicing a compound body out
        of the token stream and re-parsing it. Each statement is parsed by the
        fully-wired ``self.statement`` parser, which recurses into nested
        compounds and consumes their *own* ``done``/``fi``/``esac``. As a result
        a terminator keyword is only ever seen at *this* nesting level, so no
        manual ``nesting_level`` bookkeeping is needed — the recursion is the
        nesting tracker.

        ``terminators`` is a set of keyword strings (e.g. ``{'done'}``) and
        ``terminator_types`` a set of token-type names (e.g. ``{'DOUBLE_SEMICOLON'}``
        for case ``;;``); either ends the list, in addition to EOF and an
        enclosing ``)``/``}``. Because the terminator is only ever checked at
        statement-start position, an argument that merely spells like a keyword
        (``echo done``) is consumed as a word by ``self.statement`` and never
        mistaken for the terminator — fixing a long-standing slicer bug that
        mis-detected such arguments.

        A committed loop (not ``many``) is used deliberately: ``many`` swallows
        failures, which at a real command token would discard the body's own
        diagnostic and surface a generic top-level error instead.
        """
        separators = many1(self.tokens.semicolon.or_else(self.tokens.newline))
        stop_types = self._STATEMENT_LIST_STOP_TYPES | terminator_types

        def at_terminator(tokens: List[Token], pos: int) -> bool:
            if pos >= len(tokens):
                return True
            tok = tokens[pos]
            if tok.type.name in stop_types:
                return True
            return any(matches_keyword(tok, kw) for kw in terminators)

        def parse_statement_list(tokens: List[Token], pos: int) -> ParseResult[StatementList]:
            statements: List = []
            current_pos = optional(separators).parse(tokens, pos).position

            while not at_terminator(tokens, current_pos):
                statement_result = self.statement.parse(tokens, current_pos)
                if not statement_result.success:
                    return statement_result

                statements.append(statement_result.value)
                if statement_result.position == current_pos:
                    break  # No progress — avoid an infinite loop.
                current_pos = statement_result.position
                current_pos = optional(separators).parse(tokens, current_pos).position

            return ParseResult(
                success=True,
                value=StatementList(statements=statements),
                position=current_pos,
            )

        return Parser(parse_statement_list)
