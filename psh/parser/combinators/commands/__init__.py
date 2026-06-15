"""Command and pipeline parsers for the shell parser combinator.

This package provides parsers for simple commands, pipelines, and-or lists,
and statement lists - the core command structures in shell syntax.

The CommandParsers class inherits from four mixin classes:
- RedirectionMixin: I/O redirections, heredocs, here strings, fd-dup words
- SimpleCommandMixin: simple commands (words + redirects + array assignments)
- PipelineMixin: pipelines (|/|& chains) and and-or lists (&&/|| chains)
- StatementMixin: statements and the recursion-based statement-list engine
"""

from typing import List, Optional, Union

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
    # Control structures for type checking
    IfConditional,
    Pipeline,
    SelectLoop,
    SimpleCommand,
    WhileLoop,
)
from ....lexer.token_types import Token
from ...config import ParserConfig
from ..arrays import ArrayParsers
from ..core import Parser, ParseResult, fail_with, optional, token
from ..diagnostics import raise_committed_error
from ..expansions import ExpansionParsers
from ..tokens import TokenParsers
from .pipelines import PipelineMixin
from .redirections import RedirectionMixin
from .simple import SimpleCommandMixin
from .statements import StatementMixin

__all__ = [
    'CommandParsers',
    'create_command_parsers',
    'parse_simple_command',
    'parse_pipeline',
    'parse_and_or_list',
]


class CommandParsers(RedirectionMixin, SimpleCommandMixin, PipelineMixin, StatementMixin):
    """Parsers for shell commands and command structures.

    This class provides parsers for building the command hierarchy:
    simple commands -> pipelines -> and-or lists -> statement lists
    """

    def __init__(self, config: Optional[ParserConfig] = None,
                 token_parsers: Optional[TokenParsers] = None,
                 expansion_parsers: Optional[ExpansionParsers] = None):
        """Initialize command parsers.

        Args:
            config: Parser configuration
            token_parsers: Token parsers to use
            expansion_parsers: Expansion parsers to use
        """
        self.config = config or ParserConfig()
        self.tokens = token_parsers or TokenParsers()
        self.expansions = expansion_parsers or ExpansionParsers(self.config)
        self.arrays = ArrayParsers(self.tokens)

        self._initialize_parsers()

    def _initialize_parsers(self):
        """Initialize all command-related parsers.

        The grammar graph is built exactly ONCE here and never rebuilt. Two
        recursive references — which can only be resolved after the control and
        special parsers exist — are held in mutable *slots* that the parsers
        read at parse time:

        * ``self._pipeline_element`` — what may appear as a single element in a
          pipeline. It starts as a bare simple command and is widened to
          "control structure / special command / simple command" by
          :meth:`set_command_parser` during wiring.
        * ``self._function_def`` — the function-definition head tried before an
          ordinary statement. It starts as a never-matching parser and is filled
          by :meth:`set_function_def` during wiring.

        Because the slots are read inside the parse closures, filling them later
        takes effect without reassigning ``pipeline``/``and_or_list``/
        ``statement``/``statement_list`` (the old phase-then-patch wiring).
        """
        # Build redirection parser
        self.redirection = Parser(self._parse_redirection)

        # Build simple command parser
        self.simple_command = self._build_simple_command_parser()

        # Recursion slots (filled once during wiring; read at parse time).
        self._pipeline_element: Parser = self.simple_command
        self._function_def: Parser = fail_with("expected a function definition")

        # Build pipeline parser
        self.pipeline = self._build_pipeline_parser()

        # Build and-or list parser
        self.and_or_list = self._build_and_or_list_parser()

        # Build statement parser
        self.statement = self._build_statement_parser()

        # Build statement list parser — the recursion-based engine (it reads
        # self.statement at parse time, so it tracks the wired slots too).
        self.statement_list = self.build_statement_list()

    def set_command_parser(self, command_parser: Parser):
        """Fill the pipeline-element recursion slot.

        Called once during wiring (after control structures and special commands
        exist) with the parser for a single pipeline element. The pipeline and
        and-or parsers built in ``_initialize_parsers`` read this slot at parse
        time, so nothing is rebuilt — the grammar graph stays a stable value.

        Args:
            command_parser: Parser for one pipeline element (control structure /
                special command / simple command).
        """
        self._pipeline_element = command_parser

    def set_function_def(self, function_def_parser: Parser):
        """Fill the function-definition recursion slot (see set_command_parser).

        Tried ahead of an ordinary statement by the statement parser.
        """
        self._function_def = function_def_parser


# Convenience functions

def create_command_parsers(config: Optional[ParserConfig] = None,
                          token_parsers: Optional[TokenParsers] = None,
                          expansion_parsers: Optional[ExpansionParsers] = None) -> CommandParsers:
    """Create and return a CommandParsers instance.

    Args:
        config: Optional parser configuration
        token_parsers: Optional token parsers
        expansion_parsers: Optional expansion parsers

    Returns:
        Initialized CommandParsers object
    """
    return CommandParsers(config, token_parsers, expansion_parsers)


def parse_simple_command(tokens: TokenParsers,
                         expansions: ExpansionParsers) -> Parser[SimpleCommand]:
    """Create parser for simple commands.

    Args:
        tokens: Token parsers
        expansions: Expansion parsers

    Returns:
        Parser that matches simple commands
    """
    cmd_parsers = CommandParsers(token_parsers=tokens, expansion_parsers=expansions)
    return cmd_parsers.simple_command


def parse_pipeline(command_parser: Parser) -> Parser[Union[Pipeline, ASTNode]]:
    """Create parser for pipelines.

    Args:
        command_parser: Parser for commands

    Returns:
        Parser that matches pipelines
    """
    pipe_sep = token('PIPE').or_else(token('PIPE_AND'))
    exclamation = token('EXCLAMATION')

    def parse_pipeline_with_negation(tokens: List[Token], pos: int) -> ParseResult:
        neg_result = optional(exclamation).parse(tokens, pos)
        negated = neg_result.value is not None
        pos = neg_result.position

        # Parse first command
        first_result = command_parser.parse(tokens, pos)
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

            cmd_result = command_parser.parse(tokens, pos)
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


def parse_and_or_list(pipeline_parser: Parser) -> Parser[AndOrList]:
    """Create parser for and-or lists.

    Args:
        pipeline_parser: Parser for pipelines

    Returns:
        Parser that matches and-or lists
    """
    and_or_operator = token('AND_AND').or_else(token('OR_OR'))

    def build_and_or(parts):
        first = parts[0]
        rest = parts[1]

        if not rest:
            if isinstance(first, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                                CStyleForLoop, ArithmeticEvaluation, EnhancedTestStatement,
                                BreakStatement, ContinueStatement)):
                return first
            return AndOrList(pipelines=[first])

        pipelines = [first]
        operators = []
        for op, pipeline in rest:
            operators.append(op.value)
            pipelines.append(pipeline)

        return AndOrList(pipelines=pipelines, operators=operators)

    def parse_and_or(tokens: List[Token], pos: int) -> ParseResult[AndOrList]:
        first_result = pipeline_parser.parse(tokens, pos)
        if not first_result.success:
            return first_result

        first = first_result.value
        rest = []
        pos = first_result.position

        while pos < len(tokens):
            op_result = and_or_operator.parse(tokens, pos)
            if not op_result.success:
                break
            assert op_result.value is not None
            op_token = op_result.value
            pos = op_result.position

            rhs_result = pipeline_parser.parse(tokens, pos)
            if not rhs_result.success:
                raise_committed_error(
                    tokens,
                    rhs_result.position,
                    rhs_result.error or f"Expected command after {op_token.value}",
                )
            rest.append((op_token, rhs_result.value))
            pos = rhs_result.position

        return ParseResult(success=True, value=build_and_or((first, rest)), position=pos)

    return Parser(parse_and_or)
