"""Type-only Protocol for the CommandParsers mixins.

``CommandParsers`` (``__init__.py``) is composed from four mixins —
``RedirectionMixin`` (redirections.py), ``SimpleCommandMixin`` (simple.py),
``PipelineMixin`` (pipelines.py), and ``StatementMixin`` (statements.py).
Each mixin references attributes set in ``CommandParsers.__init__`` /
``_initialize_parsers`` (``self.config``, ``self.tokens``, ``self.arrays``,
``self.redirection``, ``self.pipeline``, ...) and helper methods defined on a
*sibling* mixin (e.g. ``RedirectionMixin._parse_word_as_word`` is called by
``SimpleCommandMixin``). mypy cannot see those when checking a mixin in
isolation.

``CommandParsersProtocol`` declares exactly that shared surface so the mixins
type-check. It is purely a typing artifact: each mixin declares it as a base
**only** under ``TYPE_CHECKING`` (so there is no runtime MRO or behavior
change), and ``CommandParsers`` structurally satisfies it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Protocol, Union

if TYPE_CHECKING:
    from ....ast_nodes import (
        AndOrList,
        ArrayAssignment,
        ASTNode,
        FunctionDef,
        Pipeline,
        Redirect,
        SimpleCommand,
        StatementList,
    )
    from ....lexer.token_types import Token
    from ...config import ParserConfig
    from ..arrays import ArrayParsers
    from ..core import Parser, ParseResult
    from ..expansions import ExpansionParsers
    from ..tokens import TokenParsers


class CommandParsersProtocol(Protocol):
    """Attributes and shared helpers the command-parser mixins use."""

    # Attributes set in CommandParsers.__init__ / _initialize_parsers
    config: "ParserConfig"
    tokens: "TokenParsers"
    expansions: "ExpansionParsers"
    arrays: "ArrayParsers"
    # ``redirection`` and ``statement`` are typed loosely (``Any`` /
    # ``Parser[Any]``) rather than pinned to their element type. The parse
    # closures append ``redirection.parse().value`` to a ``List[Redirect]``
    # and forward ``statement.parse()`` as a wider ``ParseResult[StatementList]``.
    # In the pre-split single-module version mypy inferred both attributes as
    # collapsed-``Any`` (the bound-method generic inference for
    # ``Parser(self._parse_redirection)`` did not pin ``T``), so those usages
    # type-checked. Declaring them loosely here reproduces that exactly,
    # keeping the move behavior- and type-check-neutral.
    redirection: Any
    simple_command: "Parser[SimpleCommand]"
    pipeline: "Parser[Union[Pipeline, ASTNode]]"
    and_or_list: "Parser[Union[AndOrList, ASTNode]]"
    statement: "Parser[Any]"
    statement_list: "Parser[StatementList]"
    _pipeline_element: "Parser"
    _function_def: "Parser"

    # Cross-mixin helper methods (one mixin calls these on self)
    def _parse_word_as_word(
        self, tokens: List["Token"], pos: int
    ) -> "ParseResult": ...

    def _parse_redirection(
        self, tokens: List["Token"], pos: int
    ) -> "ParseResult[Redirect]": ...

    @staticmethod
    def _parse_fd_dup_word(tok: "Token") -> Optional["Redirect"]: ...

    @staticmethod
    def _group_adjacent_tokens(
        word_tokens: List["Token"],
    ) -> List[List["Token"]]: ...

    def _build_simple_command(
        self,
        word_tokens: List["Token"],
        redirects: List["Redirect"],
        array_assignments: Optional[List["ArrayAssignment"]] = ...,
    ) -> "SimpleCommand": ...

    def _build_simple_command_parser(self) -> "Parser[SimpleCommand]": ...

    def _build_pipeline_parser(self) -> "Parser[Union[Pipeline, ASTNode]]": ...

    def _build_and_or_list_parser(
        self,
    ) -> "Parser[Union[AndOrList, ASTNode]]": ...

    def _build_and_or_list_from_parts(
        self, parse_result: tuple
    ) -> "Union[AndOrList, ASTNode]": ...

    def _build_statement_parser(
        self,
    ) -> "Parser[Union[AndOrList, FunctionDef]]": ...

    def build_statement_list(
        self,
        terminators: frozenset = ...,
        terminator_types: frozenset = ...,
    ) -> "Parser[StatementList]": ...
