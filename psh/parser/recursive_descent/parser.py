"""
Main Parser class for PSH shell.

This module contains the main Parser class that orchestrates parsing by delegating
to specialized parser modules for different language constructs.
"""

from typing import List, Optional, Union

from ...ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    CaseConditional,
    CommandList,
    CStyleForLoop,
    EnhancedTestStatement,
    ForLoop,
    FunctionDef,
    IfConditional,
    SelectLoop,
    Statement,
    StatementList,
    TopLevel,
    UntilLoop,
    WhileLoop,
)
from ...lexer.token_types import Token
from ..config import ParserConfig
from .base_context import ContextBaseParser
from .context import ParserContext
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
            # Capture the first token's (buffer-relative) line before parsing
            # so a top-level control structure / function def — which bypass
            # parse_statement — also gets a $LINENO stamp. parse_command_list
            # items stamp their own inner statements; stamping the wrapper too
            # is harmless (re-stamped per inner statement at execution). See
            # ASTNode.line.
            item_line = self.peek().line
            item = self._parse_top_level_item()
            if item:
                if item.line is None:
                    item.line = item_line
                top_level.items.append(item)
            self.skip_separators()

        return self._simplify_result(top_level)

    def _parse_top_level_item(self) -> Optional[Union[Statement, StatementList]]:
        """Parse the top-level program via the ordinary statement path.

        Top-level parsing uses the SAME grammar as a nested command list —
        ``parse_command_list`` → ``parse_statement`` → ``parse_pipeline_component``
        already handles function definitions and every control structure,
        including a control structure followed by ``|``/``&&``/``||``/``&``. So
        there is no separate top-level grammar: a control structure at command
        position is just a pipeline component like any other. ``_simplify_result``
        restores the historical ``TopLevel``-rooted shape for a program that is a
        single bare compound / function definition.
        """
        cmd_list = self.statements.parse_command_list()
        return cmd_list if cmd_list.statements else None

    def _simplify_result(self, top_level: TopLevel) -> Union[CommandList, TopLevel]:
        """Simplify single-item TopLevel to CommandList when possible."""
        if not top_level.items:
            return CommandList()
        elif len(top_level.items) == 1:
            item = top_level.items[0]
            if isinstance(item, CommandList):
                # A program that is exactly one bare compound / function
                # definition keeps its historical TopLevel root (see
                # _bare_top_level_compound). Multi-statement programs stay a
                # CommandList — so `while ...; done; echo a` groups the same
                # way as `echo a; while ...; done`, which the old top-level
                # special case did not.
                bare = self._bare_top_level_compound(item)
                if bare is not None:
                    return TopLevel(items=[bare])
                return item
            else:
                # Other single items return TopLevel
                return top_level
        else:
            return top_level

    # Compound-command nodes that the old top-level parser returned bare (as a
    # direct TopLevel item) rather than wrapped in a CommandList: the
    # CONTROL_KEYWORDS-headed structures plus `[[ ]]`/`(( ))`. Subshell/brace
    # groups and simple commands were always CommandList-wrapped and stay so.
    _BARE_TOP_LEVEL_TYPES = (
        WhileLoop, UntilLoop, ForLoop, CStyleForLoop, IfConditional,
        CaseConditional, SelectLoop, EnhancedTestStatement, ArithmeticEvaluation,
    )

    def _bare_top_level_compound(
            self, cmd_list: CommandList) -> Optional[Statement]:
        """The lone compound/function-def of a single-statement program.

        Returns the unwrapped node when *cmd_list* is exactly one bare compound
        command (one and-or list, one pipeline, no ``&&``/``||``, not
        backgrounded, not negated, one command) or one function definition —
        the shapes the previous top-level parser returned directly under
        ``TopLevel``. Returns ``None`` otherwise, so the program stays a
        ``CommandList``.
        """
        if len(cmd_list.statements) != 1:
            return None
        stmt = cmd_list.statements[0]
        if isinstance(stmt, FunctionDef):
            return stmt
        if not isinstance(stmt, AndOrList):
            return None
        if stmt.operators or stmt.background or len(stmt.pipelines) != 1:
            return None
        pipeline = stmt.pipelines[0]
        if pipeline.negated or len(pipeline.commands) != 1:
            return None
        command = pipeline.commands[0]
        return command if isinstance(command, self._BARE_TOP_LEVEL_TYPES) else None

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


