"""
Main Parser class for PSH shell.

This module contains the main Parser class that orchestrates parsing by delegating
to specialized parser modules for different language constructs.
"""

from typing import List, Optional

from ...ast_nodes import (
    ArithmeticEvaluation,
    EnhancedTestStatement,
    Program,
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
                 config: Optional[ParserConfig] = None, ctx: Optional[ParserContext] = None,
                 line_offset: int = 0):
        # Create or use provided context
        if ctx is not None:
            # Use provided context directly
            super().__init__(ctx)
        else:
            # Configuration (create default if not provided)
            config = config or ParserConfig()

            # Create context. line_offset carries the number of source lines
            # before this fragment, so error messages report absolute lines.
            ctx = create_context(
                tokens=tokens,
                config=config,
                source_text=source_text,
                line_offset=line_offset
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

    def parse(self) -> Program:
        """Parse input into the canonical :class:`Program` root.

        Top-level parsing uses the SAME grammar as a nested command list —
        ``parse_command_list`` → ``parse_statement`` → ``parse_pipeline_component``
        already handles function definitions and every control structure,
        including a control structure followed by ``|``/``&&``/``||``/``&``. So
        there is no separate top-level grammar (a control structure at command
        position is just a pipeline component like any other) and no post-parse
        root reshaping: a bare compound keeps its normal ``AndOrList ->
        Pipeline`` ancestry, exactly like every other statement. Every parse —
        including empty input — yields a ``Program``.

        Recursive-descent parsing of nested compounds consumes Python stack.
        Under ``Shell`` the ``MAX_NESTING_DEPTH`` guard pre-empts stack
        exhaustion (``Shell`` raises the interpreter recursion limit at
        construction), but the parser is a public API usable WITHOUT ``Shell``,
        under the interpreter's default limit — where deeply nested input trips
        a raw ``RecursionError`` first. Convert it to a clean ``ParseError`` at
        this boundary so parser safety does not depend on shell initialization
        (appraisal finding 6). This does not lower ``MAX_NESTING_DEPTH`` or
        touch the process recursion limit, so shell-context behavior (1000-deep
        nesting works under ``Shell``'s raised limit) is unchanged.
        """
        try:
            return self._parse_program()
        except RecursionError:
            raise self.error(
                "input too deeply nested to parse") from None

    def _parse_program(self) -> Program:
        """Parse the token stream into a ``Program`` (see :meth:`parse`)."""
        program = Program()
        self.skip_newlines()

        while not self.at_end():
            # Capture the first token's (buffer-relative) line before parsing
            # so any statement parse_statement did not itself stamp still gets
            # a $LINENO stamp; parse_statement already stamps every statement
            # it produces, so this is a belt-and-suspenders fallback that keeps
            # every Program statement stamped. See ASTNode.line.
            item_line = self.peek().line
            command_list = self.statements.parse_command_list()
            for stmt in command_list.statements:
                if stmt.line is None:
                    stmt.line = item_line
                program.statements.append(stmt)
            self.skip_separators()

        return program

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


