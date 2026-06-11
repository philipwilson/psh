"""
Main Parser class for PSH shell.

This module contains the main Parser class that orchestrates parsing by delegating
to specialized parser modules for different language constructs.
"""

from typing import List, Optional, Set, Union

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
from ..config import ErrorHandlingMode, ParserConfig
from .base_context import ContextBaseParser
from .context import ParserContext
from .helpers import ParseError, TokenGroups
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

# Recovery token sets for error recovery
_STATEMENT_START = frozenset({
    TokenType.IF, TokenType.WHILE, TokenType.UNTIL, TokenType.FOR,
    TokenType.CASE, TokenType.FUNCTION, TokenType.WORD,
    TokenType.LBRACE, TokenType.DOUBLE_LBRACKET
})

_STATEMENT_END = frozenset({
    TokenType.SEMICOLON, TokenType.NEWLINE,
    TokenType.AMPERSAND, TokenType.PIPE,
    TokenType.AND_AND, TokenType.OR_OR
})


class MultiErrorParseResult:
    """Result of parsing with error collection."""

    def __init__(self, ast=None, errors: List[ParseError] = None):
        self.ast = ast
        self.errors = errors or []
        self.success = ast is not None and not self.errors
        self.partial_success = ast is not None and bool(self.errors)

    def has_errors(self) -> bool:
        """Check if parsing had errors."""
        return bool(self.errors)

    def get_error_count(self) -> int:
        """Get number of parse errors."""
        return len(self.errors)

    def format_errors(self) -> str:
        """Format all errors for display."""
        if not self.errors:
            return "No errors."

        lines = []
        for i, error in enumerate(self.errors, 1):
            lines.append(f"Error {i}: {error.message}")

        return "\n".join(lines)


class Parser(ContextBaseParser):
    """Main parser class that orchestrates parsing by delegating to specialized parsers."""

    def __init__(self, tokens: List[Token],
                 source_text: Optional[str] = None, collect_errors: bool = False,
                 config: Optional[ParserConfig] = None, ctx: Optional[ParserContext] = None):
        # Create or use provided context
        if ctx is not None:
            # Use provided context directly
            super().__init__(ctx)
        else:
            # Configuration (create default if not provided)
            config = config or ParserConfig()

            # Override config with explicit parameters
            if collect_errors:
                config.collect_errors = True
                config.error_handling = ErrorHandlingMode.COLLECT

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

    def parse_with_error_collection(self) -> MultiErrorParseResult:
        """Parse input collecting multiple errors instead of stopping on first error.

        Uses ctx.errors as the sole error list. Returns a MultiErrorParseResult
        containing the AST (possibly partial) and any errors encountered.
        """
        # Ensure error collection is enabled in context
        old_collect_errors = self.ctx.config.collect_errors
        self.ctx.config.collect_errors = True

        try:
            ast = self.parse()
            return MultiErrorParseResult(ast, list(self.ctx.errors))

        except ParseError as e:
            self.ctx.add_error(e)
            # Try to recover and continue parsing
            if self.ctx.can_continue_parsing():
                ast = self._parse_with_recovery()
            else:
                ast = None
            return MultiErrorParseResult(ast, list(self.ctx.errors))
        finally:
            # Restore original error collection setting
            self.ctx.config.collect_errors = old_collect_errors

    def _parse_with_recovery(self) -> Optional[Union[CommandList, TopLevel]]:
        """Continue parsing after error with recovery strategies."""
        top_level = TopLevel()

        while not self.at_end() and self.ctx.can_continue_parsing():
            try:
                # Try to find next statement
                if not _skip_to_sync_token(self, _STATEMENT_START):
                    break

                # Try to parse next item
                item = self._parse_top_level_item_with_recovery()
                if item:
                    top_level.items.append(item)

            except ParseError as e:
                self.ctx.add_error(e)
                # Skip to next recovery point
                _skip_to_sync_token(self, _STATEMENT_END)

            self.skip_separators()

        return self._simplify_result(top_level) if top_level.items else None

    def _parse_top_level_item_with_recovery(self):
        """Parse top level item with error recovery."""
        try:
            return self._parse_top_level_item()
        except ParseError as e:
            # Add error but try to recover
            self.ctx.add_error(e)

            # Try different recovery strategies
            if self._try_statement_recovery():
                return self._parse_top_level_item()
            else:
                # Skip this item and continue
                _skip_to_sync_token(self, _STATEMENT_END)
                return None

    def _try_statement_recovery(self) -> bool:
        """Try to recover at statement level.

        Returns:
            True if recovery successful, False otherwise
        """
        # Look for common missing tokens and try to insert them
        current = self.peek()

        # Try to recover from missing semicolon
        if current.type in {TokenType.THEN, TokenType.DO}:
            # Assume missing semicolon, continue parsing
            return True

        # Try to recover from missing closing tokens
        if current.type in {TokenType.FI, TokenType.DONE, TokenType.ESAC}:
            # Assume we're at the end of a block, continue
            return True

        return False

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
            cmd_list = self.statements.parse_command_list_until_top_level()
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


def _skip_to_sync_token(parser, sync_tokens: Set[TokenType]) -> bool:
    """Skip tokens until reaching a synchronization point.

    Returns:
        True if sync token found, False if EOF reached
    """
    while not parser.at_end() and not parser.match_any(sync_tokens):
        parser.advance()

    return not parser.at_end()


