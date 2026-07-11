"""Control structure parsers for the shell parser combinator.

This package provides parsers for all control flow structures including
if/elif/else, loops, case statements, and function definitions.

The ControlStructureParsers class inherits from three mixin classes:
- LoopParserMixin: while, until, for, c-style for, select, break, continue
- ConditionalParserMixin: if/elif/else, case/esac
- StructureParserMixin: function definitions, subshell groups, brace groups
"""

from typing import List, Optional, Tuple, cast

from ....ast_nodes import Redirect
from ....lexer.token_types import Token
from ...config import ParserConfig
from ..commands import CommandParsers
from ..core import Parser, fail_with, many
from ..tokens import TokenParsers
from .conditionals import ConditionalParserMixin
from .loops import LoopParserMixin
from .structures import StructureParserMixin


class ControlStructureParsers(LoopParserMixin, ConditionalParserMixin, StructureParserMixin):
    """Parsers for shell control structures.

    This class provides parsers for all control flow structures:
    - If/elif/else conditionals
    - While loops
    - For loops (traditional and C-style)
    - Case statements
    - Select loops
    - Function definitions
    - Subshell and brace groups
    - Break and continue statements
    """

    def __init__(self, config: Optional[ParserConfig] = None,
                 token_parsers: Optional[TokenParsers] = None,
                 command_parsers: Optional[CommandParsers] = None):
        """Initialize control structure parsers.

        Args:
            config: Parser configuration
            token_parsers: Token parsers to use
            command_parsers: Command parsers for parsing bodies
        """
        self.config = config or ParserConfig()
        self.tokens = token_parsers or TokenParsers()
        # The mixins (typed via ControlStructureProtocol) require a non-None
        # CommandParsers; at construction it may legitimately be None and is
        # wired later by set_command_parsers(). The dependent-parser builders
        # that dereference it only run after wiring (guarded in
        # _initialize_dependent_parsers), so the cast documents that invariant.
        self.commands = cast("CommandParsers", command_parsers)  # May be None initially

        self._initialize_parsers()

    def set_command_parsers(self, command_parsers: CommandParsers):
        """Set command parsers after initialization.

        This breaks the circular dependency between command and control parsers.

        Args:
            command_parsers: Command parsers to use
        """
        self.commands = command_parsers
        # Re-initialize parsers that depend on commands
        self._initialize_dependent_parsers()

    def set_special_command_parser(self, special_command: Parser):
        """Fill the compound-function-body recursion slot.

        A function body may be any compound command (bash). The control
        structures live here, but the `(( ))` arithmetic command lives in the
        sibling special-commands module, so the composed parser is injected
        during wiring (after both modules exist).
        """
        self._compound_body = self.control_structure.or_else(special_command)

    def _initialize_parsers(self):
        """Initialize parsers that don't depend on command parsers."""
        # Recursion slot for non-brace function bodies (any compound command,
        # including the sibling module's `(( ))`); filled once during wiring
        # by set_special_command_parser, read at parse time.
        self._compound_body = fail_with("expected a compound command")

    def _initialize_dependent_parsers(self):
        """Initialize parsers that depend on command parsers."""
        if not self.commands:
            return

        # Control structure parsers (from mixins)
        self.if_statement = self._build_if_statement()
        self.while_loop = self._build_while_loop()
        self.until_loop = self._build_until_loop()
        self.for_loop = self._build_for_loops()
        self.case_statement = self._build_case_statement()
        self.select_loop = self._build_select_loop()

        # Function definitions
        self.function_def = self._build_function_def()

        # Compound commands
        self.subshell_group = self._build_subshell_group()
        self.brace_group = self._build_brace_group()

        # Combined control structure parser
        self.control_structure = (
            self.if_statement
            .or_else(self.while_loop)
            .or_else(self.until_loop)
            .or_else(self.for_loop)
            .or_else(self.case_statement)
            .or_else(self.select_loop)
            .or_else(self.subshell_group)
            .or_else(self.brace_group)
        )

    # === Shared helper methods ===

    def _parse_trailing_redirects(self, tokens: List[Token], pos: int
                                  ) -> Tuple[List[Redirect], int]:
        """Parse trailing redirections after a compound command.

        Called after the closing keyword (done, fi, esac, }, )) to collect any
        redirections like ``done > file``. A trailing ``&`` is NOT consumed
        here: backgrounding applies to the whole and-or list and is handled
        at that level (POSIX).

        Returns:
            Tuple of (redirects, new_pos)
        """
        # A trailing redirection list is exactly *zero or more* redirections,
        # which is precisely ``many``: it applies ``redirection`` until it stops
        # matching, gathering the results (and never fails — an empty list is a
        # valid, successful parse).
        result = many(self.commands.redirection).parse(tokens, pos)
        redirects: List[Redirect] = list(result.value or [])
        return redirects, result.position


# Convenience function

def create_control_structure_parsers(config: Optional[ParserConfig] = None,
                                    token_parsers: Optional[TokenParsers] = None,
                                    command_parsers: Optional[CommandParsers] = None) -> ControlStructureParsers:
    """Create and return a ControlStructureParsers instance.

    Args:
        config: Optional parser configuration
        token_parsers: Optional token parsers
        command_parsers: Optional command parsers

    Returns:
        Initialized ControlStructureParsers object
    """
    return ControlStructureParsers(config, token_parsers, command_parsers)
