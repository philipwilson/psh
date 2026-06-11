"""
Main Parser class for PSH shell.

This module contains the main Parser class that orchestrates parsing by delegating
to specialized parser modules for different language constructs.
"""

from typing import List, Optional, Union

from ...ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    BreakStatement,
    CommandList,
    ContinueStatement,
    EnhancedTestStatement,
    Pipeline,
    Statement,
    TopLevel,
)
from ...lexer.token_types import Token, TokenType
from ..config import ParserConfig
from .base_context import ContextBaseParser
from .context import ParserContext
from .helpers import TokenGroups
from .parsers.arithmetic import ArithmeticParser
from .parsers.arrays import ArrayParser
from .parsers.commands import CommandParser
from .parsers.control_structures import ControlStructureParser
from .parsers.functions import FunctionParser
from .parsers.redirections import RedirectionParser
from .parsers.statements import StatementParser
from .parsers.tests import TestParser
from .support.context_factory import create_context
from .support.utils import ParserUtils


class Parser(ContextBaseParser):
    """Main parser class that orchestrates parsing by delegating to specialized parsers."""

    def __init__(self, tokens: List[Token],
                 source_text: Optional[str] = None,
                 config: Optional[ParserConfig] = None, ctx: Optional[ParserContext] = None):
        # Create or use provided context
        if ctx is not None:
            # Use provided context directly
            super().__init__(ctx)
        else:
            # Configuration (create default if not provided)
            config = config or ParserConfig()

            # Create context
            ctx = create_context(
                tokens=tokens,
                config=config,
                source_text=source_text
            )
            super().__init__(ctx)

        self.config = self.ctx.config

        # Initialize specialized parsers
        self.statements = StatementParser(self)
        self.commands = CommandParser(self)
        self.control_structures = ControlStructureParser(self)
        self.tests = TestParser(self)
        self.arithmetic = ArithmeticParser(self)
        self.redirections = RedirectionParser(self)
        self.arrays = ArrayParser(self)
        self.functions = FunctionParser(self)
        self.utils = ParserUtils(self)

    def create_configured_parser(self, tokens: List[Token], **overrides) -> 'Parser':
        """Create a new parser with the same configuration.

        Uses config.clone() so the child parser gets an independent copy
        of the configuration, avoiding mutation of the parent's config.
        """
        # Separate config-level overrides from context-level overrides
        config_overrides = {k: v for k, v in overrides.items()
                           if k in ParserConfig.__dataclass_fields__}
        ctx_overrides = {k: v for k, v in overrides.items()
                        if k not in config_overrides}

        # Clone config with overrides applied atomically
        ctx = create_context(
            tokens=tokens,
            config=self.ctx.config.clone(**config_overrides),
            source_text=self.ctx.source_text
        )

        # Apply context-level overrides
        for key, value in ctx_overrides.items():
            if hasattr(ctx, key):
                setattr(ctx, key, value)

        return Parser(tokens=[], ctx=ctx)

    @classmethod
    def from_context(cls, ctx: ParserContext) -> 'Parser':
        """Create parser from existing context."""
        return cls(tokens=[], ctx=ctx)

    @classmethod
    def create_with_config(cls, tokens: List[Token], config: ParserConfig,
                          source_text: Optional[str] = None) -> 'Parser':
        """Create parser with specific configuration."""
        ctx = create_context(tokens, config, source_text)
        return cls.from_context(ctx)

    @property
    def tokens(self) -> List[Token]:
        """Access to token list (stored in context)."""
        return self.ctx.tokens

    @property
    def current(self) -> int:
        """Current token position (stored in context)."""
        return self.ctx.current

    @current.setter
    def current(self, value: int):
        self.ctx.current = value

    # === Top-Level Parsing ===

    def parse(self) -> Union[CommandList, TopLevel]:
        """Parse input, returning TopLevel if needed, CommandList for simple cases."""
        top_level = TopLevel()
        self.skip_newlines()

        while not self.at_end():
            item = self._parse_top_level_item()
            if item:
                top_level.items.append(item)
            self.skip_separators()

        return self._simplify_result(top_level)

    def _parse_top_level_item(self) -> Optional[Statement]:
        """Parse a single top-level item."""
        if self.functions.is_function_def():
            return self.functions.parse_function_def()
        elif self.match_any(TokenGroups.CONTROL_KEYWORDS):
            # Check if control structure is part of a pipeline
            control_struct = self.control_structures.parse_control_structure()

            # Check if followed by pipe or logical operators
            if self.match(TokenType.PIPE, TokenType.PIPE_AND):
                # Parse as pipeline with control structure as first component
                return self.commands.parse_pipeline_with_initial_component(control_struct)
            elif self.match(TokenType.AMPERSAND):
                # control structure backgrounded: while ...; done &
                self.advance()
                if self.match(TokenType.AND_AND, TokenType.OR_OR):
                    raise self.error(
                        f"syntax error near unexpected token '{self.peek().value}'")
                pipeline = Pipeline()
                pipeline.commands.append(control_struct)
                and_or_list = AndOrList()
                and_or_list.pipelines.append(pipeline)
                and_or_list.background = True
                return and_or_list
            elif self.match(TokenType.AND_AND, TokenType.OR_OR):
                # Create pipeline with control structure and wrap in and_or_list
                pipeline = Pipeline()
                pipeline.commands.append(control_struct)

                and_or_list = AndOrList()
                and_or_list.pipelines.append(pipeline)

                # Parse the rest of the and_or_list
                return self.statements.parse_and_or_tail(and_or_list)
            else:
                return control_struct
        else:
            # Parse commands until we hit a function or control structure
            cmd_list = self.statements.parse_command_list()
            return cmd_list if cmd_list.statements else None

    def _simplify_result(self, top_level: TopLevel) -> Union[CommandList, TopLevel]:
        """Simplify single-item TopLevel to CommandList when possible."""
        if not top_level.items:
            return CommandList()
        elif len(top_level.items) == 1:
            item = top_level.items[0]
            if isinstance(item, CommandList):
                return item
            elif isinstance(item, (BreakStatement, ContinueStatement)):
                # Convert to CommandList for compatibility
                cmd_list = CommandList()
                cmd_list.statements.append(item)
                return cmd_list
            else:
                # Other single items return TopLevel
                return top_level
        else:
            return top_level

    # === Delegation Methods ===
    # These methods delegate to specialized parsers, adding feature checks where needed.

    def parse_enhanced_test_statement(self) -> EnhancedTestStatement:
        """Parse an enhanced test statement ([[ ... ]])."""
        if not self.should_allow('bash_conditionals'):
            self.check_posix_compliance('[[ ]] enhanced test syntax', '[ ] test command')
        return self.tests.parse_enhanced_test_statement()

    def parse_arithmetic_command(self) -> ArithmeticEvaluation:
        """Parse an arithmetic command ((...)). """
        self.require_feature('arithmetic', 'Arithmetic evaluation is disabled')
        if not self.should_allow('bash_arithmetic'):
            self.check_posix_compliance('(( )) arithmetic syntax', 'expr command')
        return self.arithmetic.parse_arithmetic_command()


