"""Pipeline and and-or-list parsers for the shell parser combinator.

This module provides the mixin building pipelines (``|``/``|&`` chains, with
optional ``!`` negation) and and-or lists (``&&``/``||`` chains).
"""

from typing import TYPE_CHECKING, List, Union

from ....ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    ASTNode,
    BreakStatement,
    CaseConditional,
    ContinueStatement,
    CStyleForLoop,
    EnhancedTestStatement,
    ForLoop,
    IfConditional,
    Pipeline,
    SelectLoop,
    WhileLoop,
)
from ....lexer.token_types import Token
from ..core import Parser, ParseResult, many, optional
from ..diagnostics import raise_committed_error

if TYPE_CHECKING:
    from ._protocols import CommandParsersProtocol
    _Base = CommandParsersProtocol
else:
    _Base = object


class PipelineMixin(_Base):
    """Mixin providing pipeline and and-or-list parsers for CommandParsers."""

    def _build_pipeline_parser(self) -> Parser[Union[Pipeline, ASTNode]]:
        """Build parser for pipelines.

        Each pipeline element is ``self._pipeline_element`` (read at parse time
        — a bare simple command until wiring widens it to include control
        structures and special commands).

        Returns:
            Parser that produces Pipeline or unwrapped command nodes
        """
        pipe_sep = self.tokens.pipe.or_else(self.tokens.pipe_and)

        def parse_pipeline_with_negation(tokens: List[Token], pos: int) -> ParseResult:
            """Parse optional `!` followed by a pipeline."""
            neg_result = optional(self.tokens.exclamation).parse(tokens, pos)
            negated = neg_result.value is not None
            pos = neg_result.position

            # Parse first command
            first_result = self._pipeline_element.parse(tokens, pos)
            if not first_result.success:
                return first_result

            commands: List = [first_result.value]
            pipe_stderr_list = []
            pos = first_result.position

            # Parse remaining | or |& separated commands
            while pos < len(tokens):
                sep_result = pipe_sep.parse(tokens, pos)
                if not sep_result.success:
                    break
                assert sep_result.value is not None
                is_pipe_stderr = sep_result.value.type.name == 'PIPE_AND'
                pipe_stderr_list.append(is_pipe_stderr)
                pos = sep_result.position
                # bash allows a newline (line continuation) after a pipe
                # operator before the next stage; skip any.
                pos = many(self.tokens.newline).parse(tokens, pos).position

                cmd_result = self._pipeline_element.parse(tokens, pos)
                if not cmd_result.success:
                    raise_committed_error(
                        tokens,
                        cmd_result.position,
                        cmd_result.error or "Expected command after pipe",
                    )
                commands.append(cmd_result.value)
                pos = cmd_result.position

            if len(commands) == 1 and not negated:
                cmd = commands[0]
                if isinstance(cmd, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                                  CStyleForLoop, ArithmeticEvaluation, EnhancedTestStatement,
                                  BreakStatement, ContinueStatement)):
                    return ParseResult(success=True, value=cmd, position=pos)
            pipeline = Pipeline(commands=commands, negated=negated, pipe_stderr=pipe_stderr_list) if commands else None
            return ParseResult(success=True, value=pipeline, position=pos)

        return Parser(parse_pipeline_with_negation)

    def _build_and_or_list_parser(self) -> Parser[Union[AndOrList, ASTNode]]:
        """Build parser for and-or lists.

        Returns:
            Parser that produces AndOrList nodes
        """
        # And-or operator
        and_or_operator = self.tokens.and_if.or_else(self.tokens.or_if)

        def parse_element(tokens: List[Token], pos: int) -> ParseResult:
            # An and-or element is a pipeline; fall back to a lone element
            # (e.g. a bare compound command). Reads self._pipeline_element at
            # parse time so the wired slot is honoured.
            result = self.pipeline.parse(tokens, pos)
            if result.success or result.committed:
                return result
            return self._pipeline_element.parse(tokens, pos)

        def parse_and_or_list(tokens: List[Token], pos: int) -> ParseResult[Union[AndOrList, ASTNode]]:
            first_result = parse_element(tokens, pos)
            if not first_result.success:
                return first_result

            first = first_result.value
            rest = []
            pos = first_result.position

            while pos < len(tokens):
                op_result = and_or_operator.parse(tokens, pos)
                if not op_result.success:
                    break
                op_token = op_result.value
                assert op_token is not None
                pos = op_result.position
                # bash allows a newline (line continuation) after && / ||
                # before the right-hand command; skip any.
                pos = many(self.tokens.newline).parse(tokens, pos).position

                rhs_result = parse_element(tokens, pos)
                if not rhs_result.success:
                    raise_committed_error(
                        tokens,
                        rhs_result.position,
                        rhs_result.error or f"Expected command after {op_token.value}",
                    )
                rest.append((op_token, rhs_result.value))
                pos = rhs_result.position

            return ParseResult(
                success=True,
                value=self._build_and_or_list_from_parts((first, rest)),
                position=pos,
            )

        return Parser(parse_and_or_list)

    def _build_and_or_list_from_parts(self, parse_result: tuple) -> Union[AndOrList, ASTNode]:
        """Build an AndOrList from parsed components.

        Args:
            parse_result: Tuple of (first_element, rest_pairs)

        Returns:
            AndOrList AST node
        """
        first_element = parse_result[0]
        rest = parse_result[1]  # List of (operator, element) pairs

        # Normalize first element to Pipeline if needed
        if isinstance(first_element, Pipeline):
            first_pipeline = first_element
        else:
            # Single command - add directly as pipeline element
            first_pipeline = first_element

        if not rest:
            # Single element with no operators - return it directly instead of wrapping
            # This prevents unnecessary AndOrList wrapping for standalone control structures
            if isinstance(first_pipeline, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                                         CStyleForLoop, ArithmeticEvaluation, EnhancedTestStatement,
                                         BreakStatement, ContinueStatement)):
                return first_pipeline
            return AndOrList(pipelines=[first_pipeline])

        pipelines = [first_pipeline]
        operators = []

        for op_token, element in rest:
            operators.append(op_token.value)
            # Normalize element to Pipeline if needed
            if isinstance(element, Pipeline):
                pipelines.append(element)
            else:
                # Single command - add directly as pipeline element
                pipelines.append(element)

        return AndOrList(pipelines=pipelines, operators=operators)
