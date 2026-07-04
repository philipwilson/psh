"""Pipeline and and-or-list parsers for the shell parser combinator.

This module provides the mixin building pipelines (``|``/``|&`` chains, with
optional ``!`` negation) and and-or lists (``&&``/``||`` chains).
"""

from typing import TYPE_CHECKING, List, Union, cast

from ....ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    ASTNode,
    CaseConditional,
    CStyleForLoop,
    EnhancedTestStatement,
    ForLoop,
    IfConditional,
    Pipeline,
    SelectLoop,
    UntilLoop,
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

    # Token types that terminate a pipeline: a bare `time`/`time -p` with one
    # of these next is a complete (empty) timed pipeline — bash times nothing.
    # Mirrors the recursive descent parser's _PIPELINE_END_TOKENS.
    _PIPELINE_END_TYPES = frozenset({
        'SEMICOLON', 'NEWLINE', 'AMPERSAND', 'AND_AND', 'OR_OR',
        'PIPE', 'PIPE_AND', 'RPAREN', 'RBRACE',
        'DOUBLE_SEMICOLON', 'SEMICOLON_AMP', 'AMP_SEMICOLON',
        'THEN', 'DO', 'DONE', 'FI', 'ELSE', 'ELIF', 'ESAC', 'EOF',
    })

    def _build_pipeline_parser(self) -> Parser[Union[Pipeline, ASTNode]]:
        """Build parser for pipelines.

        Each pipeline element is ``self._pipeline_element`` (read at parse time
        — a bare simple command until wiring widens it to include control
        structures and special commands).

        Returns:
            Parser that produces Pipeline or unwrapped command nodes
        """
        pipe_sep = self.tokens.pipe.or_else(self.tokens.pipe_and)

        def at_pipeline_end(tokens: List[Token], pos: int) -> bool:
            return (pos >= len(tokens)
                    or tokens[pos].type.name in self._PIPELINE_END_TYPES)

        def parse_pipeline_with_negation(tokens: List[Token], pos: int) -> ParseResult:
            """Parse optional `time [-p]` and `!` prefixes, then a pipeline."""
            # `time [-p]` prefix: times the whole following pipeline (bash).
            # It precedes the optional `!` negation, mirroring the RD grammar.
            timed = False
            time_posix = False
            time_result = optional(self.tokens.time_kw).parse(tokens, pos)
            if time_result.value is not None:
                timed = True
                pos = time_result.position
                # `-p` (POSIX output format), only as the immediate next word.
                if (pos < len(tokens) and tokens[pos].type.name == 'WORD'
                        and tokens[pos].value == '-p'):
                    time_posix = True
                    pos += 1
                # `time` with no following command is valid: it times an
                # empty pipeline (bash times nothing).
                if at_pipeline_end(tokens, pos):
                    return ParseResult(
                        success=True,
                        value=Pipeline(commands=[], timed=True,
                                       time_posix=time_posix),
                        position=pos,
                    )

            # Leading `!` negation. bash allows the reserved word to repeat
            # (`! ! cmd`), each occurrence toggling the sense of the exit
            # status: `! ! true` -> 0, `! ! ! true` -> 1. Mirrors the
            # recursive descent parser's consume loop (commands.py).
            neg_result = many(self.tokens.exclamation).parse(tokens, pos)
            assert neg_result.value is not None
            negated = len(neg_result.value) % 2 == 1
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

            if len(commands) == 1 and not negated and not timed:
                cmd = commands[0]
                if isinstance(cmd, (IfConditional, WhileLoop, UntilLoop, ForLoop, CaseConditional,
                                  SelectLoop, CStyleForLoop, ArithmeticEvaluation,
                                  EnhancedTestStatement)):
                    return ParseResult(success=True, value=cmd, position=pos)
            pipeline = Pipeline(commands=commands, negated=negated, pipe_stderr=pipe_stderr_list,
                                timed=timed, time_posix=time_posix) if commands else None
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

            value = self._build_and_or_list_from_parts((first, rest))

            # POSIX: a trailing '&' backgrounds the whole and-or list. '&' is
            # itself a separator, so another operator right after it ('&& b',
            # '| cat', '; c') is a syntax error in bash — while ';;' (case)
            # and closing keywords ('& fi', '& }') remain legal. Mirrors the
            # recursive descent parser's parse_and_or_list/_apply_background.
            amp_result = optional(self.tokens.ampersand).parse(tokens, pos)
            if amp_result.value is not None:
                pos = amp_result.position
                if (pos < len(tokens) and tokens[pos].type.name in
                        ('AND_AND', 'OR_OR', 'PIPE', 'PIPE_AND', 'SEMICOLON')):
                    raise_committed_error(
                        tokens, pos,
                        f"syntax error near unexpected token '{tokens[pos].value}'",
                    )
                if not isinstance(value, AndOrList):
                    # Unwrapped single compound (if/while/...): rewrap so the
                    # background flag has an and-or list to live on. An
                    # AndOrList holds compounds directly as pipeline elements
                    # at runtime (established shape); the cast records that.
                    value = AndOrList(pipelines=[cast(Pipeline, value)])
                self._apply_background(value)

            return ParseResult(success=True, value=value, position=pos)

        return Parser(parse_and_or_list)

    @staticmethod
    def _apply_background(and_or_list: AndOrList) -> None:
        """Mark a parsed and-or list as background.

        Single simple-command and single-pipeline cases keep the legacy
        per-command flag (the executor's direct job-control paths);
        everything else backgrounds the whole list via a subshell. Mirrors
        the recursive descent parser's StatementParser._apply_background.
        """
        from ....ast_nodes import BraceGroup, SimpleCommand, SubshellGroup
        if len(and_or_list.pipelines) == 1 and isinstance(and_or_list.pipelines[0], Pipeline):
            commands = and_or_list.pipelines[0].commands
            if commands and isinstance(commands[-1], SimpleCommand):
                commands[-1].background = True
                return
            if len(commands) == 1 and isinstance(commands[0], (SubshellGroup, BraceGroup)):
                commands[0].background = True
                return
        and_or_list.background = True

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
            if isinstance(first_pipeline, (IfConditional, WhileLoop, UntilLoop, ForLoop,
                                         CaseConditional, SelectLoop,
                                         CStyleForLoop, ArithmeticEvaluation, EnhancedTestStatement)):
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
