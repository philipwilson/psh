"""Command and pipeline parsers for the shell parser combinator.

This package provides parsers for simple commands, pipelines, and-or lists,
and statement lists - the core command structures in shell syntax.

The CommandParsers class inherits from four mixin classes:
- RedirectionMixin: I/O redirections, heredocs, here strings, fd-dup words
- SimpleCommandMixin: simple commands (words + redirects + array assignments)
- PipelineMixin: pipelines (|/|& chains) and and-or lists (&&/|| chains)
- StatementMixin: statements and the recursion-based statement-list engine
"""

from typing import Mapping, Optional

from ....ast_nodes import SimpleCommand
from ....lexer.token_types import Token
from ...config import ParserConfig
from ..arrays import ArrayParsers
from ..core import Parser, fail_with, token
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
        # Per-call collected-heredoc map (the LexedUnit's id-keyed
        # LexedHeredoc entries). ParserCombinatorShellParser.parse assigns it
        # before parsing; the redirection mixin reads it so each heredoc
        # Redirect is built with its spec truth and body AT CONSTRUCTION
        # (the post-parse HeredocProcessor attachment walk is retired).
        self.heredocs: Optional[Mapping[int, object]] = None

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
