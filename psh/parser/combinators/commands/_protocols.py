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

from typing import TYPE_CHECKING, Any, List, Mapping, Optional, Protocol, Union

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
    from ....lexer.heredoc_lexer import LexedHeredoc
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
    # Per-call collected-heredoc map (id-keyed LexedHeredoc entries),
    # assigned by ParserCombinatorShellParser.parse before parsing.
    heredocs: "Optional[Mapping[int, LexedHeredoc]]"
    # ``statement`` stays ``Parser[Any]``: its closure forwards
    # ``statement.parse()`` as a wider ``ParseResult[StatementList]``, so the
    # element type genuinely varies at the use site.
    #
    # ``redirection`` was ``Any`` for the same inherited reason until
    # remediation 5B.2 typed it. In the pre-split single-module version mypy
    # inferred it as collapsed-``Any`` (bound-method generic inference for
    # ``Parser(self._parse_redirection)`` did not pin ``T``), and declaring it
    # loosely reproduced that — which kept the split type-check-neutral, but
    # also meant nothing checked what the redirection parser produced. Pinning
    # it surfaced exactly one site tree-wide: ``simple.py`` appending a
    # possibly-``None`` ``.value`` to a ``List[Redirect]``, already
    # ``success``-guarded but missing the None-narrowing its own sibling
    # branch performs nine lines earlier.
    redirection: "Parser[Redirect]"
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
